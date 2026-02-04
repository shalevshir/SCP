#!/usr/bin/env python3
"""Synchronous Backtesting Orchestrator (SBOP).

This script implements the Tick-Lock orchestration pattern for deterministic
backtesting. Unlike the async replay_historical.py script, this orchestrator
ensures that for every simulation timestamp T:

1. All worker services (Feature Engine, HTF Bias) complete processing
2. Bot-Core completes signal evaluation
3. Execution service completes trade management (entries, exits, invalidations)
4. BEFORE the system advances to T+1

This eliminates race conditions and ensures identical results regardless of
hardware speed, which is critical for strategy validation and debugging.

Architecture:
    Orchestrator (this script)
        |
        v [1. Publish Candle(T)]
        |
        v [2. Block-wait for acks from Feature Engine + HTF Bias]
        |
        v [3. Wait for Bot-Core ack]
        |
        v [4. Wait for Execution ack]
        |
        v [5. Advance to T+1]

Usage:
    # Run synchronous backtest
    poetry run python scripts/backtest_orchestrator.py \\
        --start 2024-11-01 --end 2024-11-30

    # With custom data directory
    poetry run python scripts/backtest_orchestrator.py \\
        --start 2024-11-01 --end 2024-11-30 \\
        --data-dir data/gc_dx_ohlcv

    # Skip warmup (for testing)
    poetry run python scripts/backtest_orchestrator.py \\
        --start 2024-11-01 --end 2024-11-30 --no-warmup
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import redis.asyncio as redis

from common.config import load_config
from common.logger import get_logger, setup_logging
from data_layer.loader import HistoricalDataLoader
from scp_shared.messaging import RedisStreamConsumer, RedisStreamPublisher, SYNC_ACK_STREAM
from scp_shared.messaging.schemas import CandleMessage, SyncAckMessage

logger = get_logger(__name__)


# Synchronization configuration
SYNC_TIMEOUT_SECONDS = 30  # Max time to wait for service acks
WORKER_SERVICES = frozenset(["feature-engine", "htf-bias"])
BOT_CORE_SERVICE = "bot-core"
EXECUTION_SERVICE = "execution"

# Warmup configuration
DEFAULT_WARMUP_LOOKBACK_HOURS = 24
WARMUP_STREAM_TTL_SECONDS = 600


class SynchronizationTimeoutError(Exception):
    """Raised when services fail to acknowledge within timeout."""

    pass


class BacktestOrchestratorError(Exception):
    """Raised when backtest encounters an unrecoverable error."""

    pass


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO-8601 datetime strings, defaulting to UTC when tzinfo missing."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class BacktestOrchestrator:
    """Synchronous backtest orchestrator implementing Tick-Lock pattern."""

    def __init__(
        self,
        redis_client: redis.Redis,
        timeout_seconds: float = SYNC_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            redis_client: Async Redis client
            timeout_seconds: Timeout for waiting on service acks
        """
        self.redis = redis_client
        self.timeout_seconds = timeout_seconds

        # Publishers and consumers
        self._publisher = RedisStreamPublisher(redis_client)
        self._ack_consumer: RedisStreamConsumer[SyncAckMessage] | None = None

        # Ack buffer for out-of-order messages
        self._ack_buffer: dict[datetime, dict[str, SyncAckMessage]] = defaultdict(dict)

        # Statistics
        self.stats = {
            "ticks_processed": 0,
            "worker_acks_received": 0,
            "bot_core_acks_received": 0,
            "execution_acks_received": 0,
            "timeouts": 0,
        }

        # Performance profiling
        self.phase_timings = {
            "publish": 0.0,
            "workers": 0.0,
            "bot_core": 0.0,
            "execution": 0.0,
        }
        self.service_wait_times: dict[str, list[float]] = {
            "feature-engine": [],
            "htf-bias": [],
            "bot-core": [],
            "execution": [],
        }

    async def initialize(self) -> None:
        """Initialize consumers and verify Redis connection."""
        # Verify Redis is accessible
        await self.redis.ping()
        logger.info("Connected to Redis")

        # Create ack consumer
        self._ack_consumer = RedisStreamConsumer(
            self.redis,
            stream=SYNC_ACK_STREAM,
            group="orchestrator",
            consumer_name="main",
            message_type=SyncAckMessage,
        )
        await self._ack_consumer.ensure_group()
        logger.info(f"Listening for acks on {SYNC_ACK_STREAM}")

    async def run_backtest(
        self,
        candle_pairs: list[tuple[CandleMessage, CandleMessage]],
    ) -> dict:
        """Run synchronous backtest over candle pairs.

        Args:
            candle_pairs: List of (gc_candle, dxy_candle) pairs, sorted by timestamp

        Returns:
            Statistics dictionary
        """
        total = len(candle_pairs)
        start_time = asyncio.get_event_loop().time()
        last_log_time = start_time

        # Print header
        print("\n" + "=" * 100)
        print(f"  SYNCHRONOUS BACKTEST - {total:,} ticks")
        print("=" * 100)
        print(f"  {'Progress':<12} {'Rate':<15} {'Elapsed':<12} {'ETA':<12} {'Current Timestamp'}")
        print("-" * 100)

        for i, (gc_candle, dxy_candle) in enumerate(candle_pairs):
            tick_ts = gc_candle.timestamp

            # Progress logging every 100 ticks or every 5 seconds
            current_time = asyncio.get_event_loop().time()
            if (i + 1) % 100 == 0 or (current_time - last_log_time) >= 5:
                elapsed = current_time - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                remaining_ticks = total - (i + 1)
                eta_seconds = remaining_ticks / rate if rate > 0 else 0
                eta_minutes = eta_seconds / 60

                # Format times
                elapsed_str = f"{elapsed / 60:.1f}m" if elapsed >= 60 else f"{elapsed:.0f}s"

                if eta_minutes >= 60:
                    eta_str = f"{eta_minutes / 60:.1f}h"
                elif eta_minutes >= 1:
                    eta_str = f"{eta_minutes:.1f}m"
                else:
                    eta_str = f"{eta_seconds:.0f}s"

                # Progress bar
                pct = (i + 1) * 100 / total
                bar_width = 20
                filled = int(bar_width * (i + 1) / total)
                bar = "█" * filled + "░" * (bar_width - filled)

                print(
                    f"  {bar} {pct:5.1f}%  "
                    f"{rate:5.1f} ticks/s   "
                    f"{elapsed_str:>10}   "
                    f"{eta_str:>10}   "
                    f"{tick_ts}"
                )
                last_log_time = current_time

            await self._process_tick(gc_candle, dxy_candle)
            self.stats["ticks_processed"] += 1

        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time

        # Final progress bar (100%)
        bar = "█" * 20
        print(f"  {bar} 100.0%")
        print("=" * 100)
        print(f"\n  ✓ BACKTEST COMPLETE\n")
        print(f"  Ticks processed:     {self.stats['ticks_processed']:>10,}")
        print(f"  Duration:            {duration / 60:>10.1f} minutes ({duration:.1f}s)")
        if duration > 0:
            print(f"  Average rate:        {self.stats['ticks_processed'] / duration:>10.1f} ticks/sec")
        print(f"  Worker acks:         {self.stats['worker_acks_received']:>10,}")
        print(f"  Bot-Core acks:       {self.stats['bot_core_acks_received']:>10,}")
        print(f"  Execution acks:      {self.stats['execution_acks_received']:>10,}")
        print("=" * 100)

        # Performance breakdown
        print("\n  PERFORMANCE BREAKDOWN\n")
        total_phase_time = sum(self.phase_timings.values())
        print(f"  Phase                Time       % of Total    Avg per Tick")
        print("-" * 100)
        for phase, time_spent in self.phase_timings.items():
            pct = (time_spent / total_phase_time * 100) if total_phase_time > 0 else 0
            avg_per_tick = (time_spent / self.stats['ticks_processed'] * 1000) if self.stats['ticks_processed'] > 0 else 0
            print(f"  {phase.title():<20} {time_spent:>8.2f}s    {pct:>6.1f}%     {avg_per_tick:>8.2f}ms")

        print()

        # Service wait time analysis
        print("  SERVICE WAIT TIMES (time spent waiting for each service to ack)\n")
        print(f"  Service              Avg        P50        P95        P99        Max")
        print("-" * 100)

        import statistics
        for service, times in sorted(self.service_wait_times.items()):
            if times:
                avg = statistics.mean(times) * 1000
                p50 = statistics.median(times) * 1000
                sorted_times = sorted(times)
                p95 = sorted_times[int(len(sorted_times) * 0.95)] * 1000 if len(sorted_times) > 0 else 0
                p99 = sorted_times[int(len(sorted_times) * 0.99)] * 1000 if len(sorted_times) > 0 else 0
                max_time = max(times) * 1000
                print(f"  {service:<20} {avg:>7.2f}ms   {p50:>7.2f}ms   {p95:>7.2f}ms   {p99:>7.2f}ms   {max_time:>7.2f}ms")

        # Bottleneck identification
        print("\n  BOTTLENECK ANALYSIS\n")
        slowest_phase = max(self.phase_timings.items(), key=lambda x: x[1])
        print(f"  Slowest phase: {slowest_phase[0].title()} ({slowest_phase[1]:.2f}s, {slowest_phase[1]/total_phase_time*100:.1f}% of total)")

        # Find slowest service
        avg_wait_times = {
            service: statistics.mean(times) * 1000 if times else 0
            for service, times in self.service_wait_times.items()
        }
        if avg_wait_times:
            slowest_service = max(avg_wait_times.items(), key=lambda x: x[1])
            print(f"  Slowest service: {slowest_service[0]} (avg {slowest_service[1]:.2f}ms wait time)")

        print("\n  RECOMMENDATIONS:")
        if slowest_phase[0] == "workers":
            print("  • Workers (Feature Engine + HTF Bias) are the bottleneck")
            print("  • Consider optimizing indicator calculations or HTF processing")
        elif slowest_phase[0] == "bot_core":
            print("  • Bot-Core signal generation is the bottleneck")
            print("  • Consider optimizing rule engine or signal scoring logic")
        elif slowest_phase[0] == "execution":
            print("  • Execution trade management is the bottleneck")
            print("  • Consider optimizing state machine processing or trade logic")
        elif slowest_phase[0] == "publish":
            print("  • Redis publishing is the bottleneck (unlikely)")
            print("  • Check Redis performance and network latency")

        print("=" * 100 + "\n")

        return {
            **self.stats,
            "duration_seconds": duration,
            "success": True,
        }

    async def _process_tick(
        self,
        gc_candle: CandleMessage,
        dxy_candle: CandleMessage,
    ) -> None:
        """Process a single tick with barrier synchronization.

        Args:
            gc_candle: GC candle for this tick
            dxy_candle: DXY candle for this tick
        """
        import asyncio
        tick_ts = gc_candle.timestamp

        # Phase 1: Publish candles
        t0 = asyncio.get_event_loop().time()
        await self._publish_candles(gc_candle, dxy_candle)
        t1 = asyncio.get_event_loop().time()
        self.phase_timings["publish"] += (t1 - t0)

        # Phase 2: Wait for worker services (Feature Engine + HTF Bias)
        t0 = asyncio.get_event_loop().time()
        await self._wait_for_services(WORKER_SERVICES, tick_ts, "workers")
        t1 = asyncio.get_event_loop().time()
        self.phase_timings["workers"] += (t1 - t0)

        # Phase 3: Wait for Bot-Core
        t0 = asyncio.get_event_loop().time()
        await self._wait_for_services({BOT_CORE_SERVICE}, tick_ts, "bot-core")
        t1 = asyncio.get_event_loop().time()
        self.phase_timings["bot_core"] += (t1 - t0)

        # Phase 4: Wait for Execution (trade management, entries, exits)
        t0 = asyncio.get_event_loop().time()
        await self._wait_for_services({EXECUTION_SERVICE}, tick_ts, "execution")
        t1 = asyncio.get_event_loop().time()
        self.phase_timings["execution"] += (t1 - t0)

    async def _publish_candles(
        self,
        gc_candle: CandleMessage,
        dxy_candle: CandleMessage,
    ) -> None:
        """Publish candle pair to Redis streams.

        Args:
            gc_candle: GC candle
            dxy_candle: DXY candle
        """
        await self._publisher.publish("candles.1m.gc", gc_candle)
        await self._publisher.publish("candles.1m.dxy", dxy_candle)

    async def _wait_for_services(
        self,
        expected_services: set[str],
        tick_ts: datetime,
        phase_name: str,
    ) -> None:
        """Wait for all expected services to ack for this tick.

        Args:
            expected_services: Set of service IDs to wait for
            tick_ts: Timestamp to wait for
            phase_name: Name for logging

        Raises:
            SynchronizationTimeoutError: If services don't ack in time
        """
        phase_start = asyncio.get_event_loop().time()
        pending = set(expected_services)
        deadline = asyncio.get_event_loop().time() + self.timeout_seconds
        service_ack_times: dict[str, float] = {}

        # Check buffer first
        pending = self._check_buffer_for_acks(tick_ts, pending)
        if not pending:
            # All acks were already in buffer - record instant wait time
            for service in expected_services:
                service_ack_times[service] = 0.0
                self.service_wait_times[service].append(0.0)
            return

        # Read acks until all received or timeout
        while pending and asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            block_ms = min(int(remaining * 1000), 500)

            if self._ack_consumer is not None:
                try:
                    acks = await self._ack_consumer.read(count=50, block_ms=block_ms)
                    for ack in acks:
                        logger.debug(
                            f"SBOP: Received ack from {ack.service_id} for {ack.tick_timestamp} "
                            f"(status={ack.status})"
                        )
                        # Store in buffer
                        self._ack_buffer[ack.tick_timestamp][ack.service_id] = ack

                        # Check for errors
                        if ack.status == "ERROR":
                            raise BacktestOrchestratorError(
                                f"Service {ack.service_id} failed at {ack.tick_timestamp}: "
                                f"{ack.error_message}"
                            )

                        # Update stats
                        if ack.service_id in WORKER_SERVICES:
                            self.stats["worker_acks_received"] += 1
                        elif ack.service_id == BOT_CORE_SERVICE:
                            self.stats["bot_core_acks_received"] += 1
                        elif ack.service_id == EXECUTION_SERVICE:
                            self.stats["execution_acks_received"] += 1

                    # Check if we have all acks now
                    new_pending = self._check_buffer_for_acks(tick_ts, pending)

                    # Track when each service acked
                    for service in pending - new_pending:
                        wait_time = asyncio.get_event_loop().time() - phase_start
                        service_ack_times[service] = wait_time
                        self.service_wait_times[service].append(wait_time)

                    pending = new_pending
                    if not pending:
                        return

                except asyncio.CancelledError:
                    raise
                except BacktestOrchestratorError:
                    raise
                except Exception as e:
                    logger.warning(f"Error reading acks: {e}")
                    await asyncio.sleep(0.1)

        # Timeout
        if pending:
            self.stats["timeouts"] += 1
            raise SynchronizationTimeoutError(
                f"Timeout waiting for {phase_name} acks from {pending} at {tick_ts}"
            )

    def _check_buffer_for_acks(
        self,
        tick_ts: datetime,
        pending: set[str],
    ) -> set[str]:
        """Check buffer for acks and return remaining pending services.

        Args:
            tick_ts: Timestamp to check
            pending: Set of services still waiting for

        Returns:
            Updated set of pending services
        """
        if tick_ts not in self._ack_buffer:
            return pending

        buffered = self._ack_buffer[tick_ts]
        received = set(buffered.keys())
        pending = pending - received

        # Clean up if all expected acks received
        if not pending:
            del self._ack_buffer[tick_ts]
            # Also clean old entries
            self._cleanup_old_buffer_entries(tick_ts)

        return pending

    def _cleanup_old_buffer_entries(self, current_ts: datetime) -> None:
        """Remove buffer entries older than 5 minutes.

        Args:
            current_ts: Current timestamp
        """
        cutoff = current_ts - timedelta(minutes=5)
        old_keys = [ts for ts in self._ack_buffer if ts < cutoff]
        for key in old_keys:
            del self._ack_buffer[key]


async def publish_warmup_data(
    redis_client: redis.Redis,
    data_dir: Path,
    replay_start: datetime,
    lookback_hours: int = DEFAULT_WARMUP_LOOKBACK_HOURS,
    ttl_seconds: int = WARMUP_STREAM_TTL_SECONDS,
) -> bool:
    """Publish warmup data to Redis streams.

    Args:
        redis_client: Redis client
        data_dir: Data directory
        replay_start: Start of replay (warmup uses data before this)
        lookback_hours: Hours of warmup data
        ttl_seconds: TTL for warmup streams

    Returns:
        True if successful
    """
    logger.info("=" * 80)
    logger.info("Warmup Phase")
    logger.info("=" * 80)

    warmup_start = replay_start - timedelta(hours=lookback_hours)
    warmup_end = replay_start - timedelta(minutes=1)

    logger.info(f"Warmup range: {warmup_start} to {warmup_end}")

    try:
        loader = HistoricalDataLoader(data_dir)
        warmup_data = loader.load(["GC", "DXY"], "1m", warmup_start, warmup_end)

        gc_df = warmup_data.get("GC")
        dxy_df = warmup_data.get("DXY")

        if gc_df is None or gc_df.empty or dxy_df is None or dxy_df.empty:
            logger.warning("Insufficient warmup data")
            return False

        # Reset index to get timestamp as column
        if "timestamp" not in gc_df.columns:
            gc_df = gc_df.reset_index()
        if "timestamp" not in dxy_df.columns:
            dxy_df = dxy_df.reset_index()

        logger.info(f"GC warmup: {len(gc_df)} candles")
        logger.info(f"DXY warmup: {len(dxy_df)} candles")

        # Clear existing warmup streams
        await redis_client.delete(
            "warmup.candles.1m.gc",
            "warmup.candles.1m.dxy",
            "warmup:status",
        )

        # Publish GC candles
        for _, row in gc_df.iterrows():
            candle = CandleMessage(
                timestamp=row["timestamp"],
                symbol="GC",
                timeframe="1m",
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            await redis_client.xadd(
                "warmup.candles.1m.gc",
                {"data": candle.model_dump_json()},
            )

        # Publish DXY candles
        for _, row in dxy_df.iterrows():
            candle = CandleMessage(
                timestamp=row["timestamp"],
                symbol="DXY",
                timeframe="1m",
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            await redis_client.xadd(
                "warmup.candles.1m.dxy",
                {"data": candle.model_dump_json()},
            )

        # Set status
        await redis_client.hset(
            "warmup:status",
            mapping={
                "gc": "complete",
                "dxy": "complete",
                "gc_count": str(len(gc_df)),
                "dxy_count": str(len(dxy_df)),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        # Set TTL
        await redis_client.expire("warmup.candles.1m.gc", ttl_seconds)
        await redis_client.expire("warmup.candles.1m.dxy", ttl_seconds)
        await redis_client.expire("warmup:status", ttl_seconds)

        logger.info(f"Warmup complete: {len(gc_df)} GC, {len(dxy_df)} DXY candles")
        return True

    except Exception as e:
        logger.error(f"Warmup failed: {e}", exc_info=True)
        return False


async def wait_for_warmup_consumption(
    redis_client: redis.Redis,
    timeout_seconds: int = 120,
) -> bool:
    """Wait for services to consume warmup data.

    Args:
        redis_client: Redis client
        timeout_seconds: Maximum wait time

    Returns:
        True if services consumed warmup
    """
    logger.info("Waiting for services to consume warmup data...")

    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout_seconds:
            logger.warning(f"Warmup consumption timeout after {timeout_seconds}s")
            return False

        status = await redis_client.hgetall("warmup:status")
        if status:
            status_decoded = {
                k.decode() if isinstance(k, bytes) else k: v.decode()
                if isinstance(v, bytes)
                else v
                for k, v in status.items()
            }

            fe_consumed = status_decoded.get("feature_engine_consumed") == "true"
            htf_consumed = status_decoded.get("htf_bias_consumed") == "true"

            if fe_consumed and htf_consumed:
                logger.info(f"Services consumed warmup data after {elapsed:.1f}s")
                # Wait a bit more for processing to complete
                await asyncio.sleep(5.0)
                return True

        await asyncio.sleep(2.0)


async def clear_streams(redis_client: redis.Redis) -> None:
    """Clear all data streams and consumer groups for clean backtest start.

    Args:
        redis_client: Redis client
    """
    streams = [
        "candles.1m.gc",
        "candles.1m.dxy",
        "features.1m",
        "features.15m",
        "features.1h",
        "htf.bias",
        "signals.pending",
        SYNC_ACK_STREAM,
    ]

    # Clear streams (this also removes consumer groups)
    for stream in streams:
        try:
            await redis_client.delete(stream)
        except Exception:
            pass

    logger.info(f"Cleared {len(streams)} streams and their consumer groups")


async def run_synchronous_backtest(
    data_dir: Path,
    start: datetime,
    end: datetime,
    redis_url: str,
    warmup_enabled: bool = True,
    warmup_lookback_hours: int = DEFAULT_WARMUP_LOOKBACK_HOURS,
) -> dict:
    """Run a synchronous backtest.

    Args:
        data_dir: Directory containing CSV files
        start: Start datetime
        end: End datetime
        redis_url: Redis URL
        warmup_enabled: Whether to run warmup phase
        warmup_lookback_hours: Hours of warmup data

    Returns:
        Statistics dictionary
    """
    logger.info("=" * 80)
    logger.info("Synchronous Backtest Orchestrator (SBOP)")
    logger.info("=" * 80)
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Date range: {start} to {end}")
    logger.info(f"Redis URL: {redis_url}")

    # Load data
    logger.info("\nLoading historical data...")
    loader = HistoricalDataLoader(data_dir)
    data = loader.load(["GC", "DXY"], "1m", start, end)

    gc_df = data.get("GC")
    dxy_df = data.get("DXY")

    if gc_df is None or gc_df.empty:
        raise ValueError("No GC data loaded")
    if dxy_df is None or dxy_df.empty:
        raise ValueError("No DXY data loaded")

    logger.info(f"Loaded {len(gc_df)} GC candles")
    logger.info(f"Loaded {len(dxy_df)} DXY candles")

    # Ensure timestamp column
    if "timestamp" not in gc_df.columns:
        gc_df = gc_df.reset_index()
    if "timestamp" not in dxy_df.columns:
        dxy_df = dxy_df.reset_index()

    # Merge and align
    merged = pd.merge(
        gc_df[["timestamp", "open", "high", "low", "close", "volume"]],
        dxy_df[["timestamp", "open", "high", "low", "close", "volume"]],
        on="timestamp",
        suffixes=("_gc", "_dxy"),
    )

    logger.info(f"Aligned {len(merged)} candle pairs")

    if merged.empty:
        raise ValueError("No aligned candles found")

    # Connect to Redis
    redis_client = redis.Redis.from_url(redis_url)

    try:
        await redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        await redis_client.aclose()
        raise

    # Create orchestrator and initialize BEFORE clearing streams
    # so we can reset the consumer after clearing
    orchestrator = BacktestOrchestrator(redis_client)
    await orchestrator.initialize()

    # Clear streams (this deletes the consumer groups too)
    await clear_streams(redis_client)

    # CRITICAL: Reset the ack consumer's initialized state so it recreates the group
    # after streams were cleared. Otherwise it thinks the group exists when it doesn't.
    if orchestrator._ack_consumer is not None:
        orchestrator._ack_consumer._initialized = False
        await orchestrator._ack_consumer.ensure_group()
        logger.info("Reset ack consumer after clearing streams")

    # Warmup phase
    if warmup_enabled:
        warmup_ok = await publish_warmup_data(
            redis_client,
            data_dir,
            start,
            warmup_lookback_hours,
        )
        if warmup_ok:
            await wait_for_warmup_consumption(redis_client)
        else:
            logger.warning("Warmup failed - services may have cold indicators")
    else:
        logger.info("Warmup disabled")

    # Create candle pairs
    candle_pairs = []
    for _, row in merged.iterrows():
        gc_candle = CandleMessage(
            timestamp=row["timestamp"],
            symbol="GC",
            timeframe="1m",
            open=float(row["open_gc"]),
            high=float(row["high_gc"]),
            low=float(row["low_gc"]),
            close=float(row["close_gc"]),
            volume=float(row["volume_gc"]),
        )
        dxy_candle = CandleMessage(
            timestamp=row["timestamp"],
            symbol="DXY",
            timeframe="1m",
            open=float(row["open_dxy"]),
            high=float(row["high_dxy"]),
            low=float(row["low_dxy"]),
            close=float(row["close_dxy"]),
            volume=float(row["volume_dxy"]),
        )
        candle_pairs.append((gc_candle, dxy_candle))

    # Orchestrator was already created and initialized earlier
    # (before clearing streams)

    try:
        stats = await orchestrator.run_backtest(candle_pairs)
    except (SynchronizationTimeoutError, BacktestOrchestratorError) as e:
        logger.error(f"Backtest failed: {e}")
        await redis_client.aclose()
        return {"success": False, "error": str(e)}

    await redis_client.aclose()
    return stats


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Run synchronous backtest with Tick-Lock orchestration (SBOP)"
    )

    parser.add_argument(
        "--start",
        type=parse_iso_datetime,
        required=True,
        help="Start datetime (ISO-8601)",
    )
    parser.add_argument(
        "--end",
        type=parse_iso_datetime,
        required=True,
        help="End datetime (ISO-8601)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/gc_dx_ohlcv"),
        help="Data directory (default: data/gc_dx_ohlcv)",
    )
    parser.add_argument(
        "--redis-url",
        type=str,
        default="redis://localhost:6379",
        help="Redis URL (default: redis://localhost:6379)",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip warmup phase",
    )
    parser.add_argument(
        "--warmup-lookback",
        type=int,
        default=DEFAULT_WARMUP_LOOKBACK_HOURS,
        help=f"Hours of warmup data (default: {DEFAULT_WARMUP_LOOKBACK_HOURS})",
    )

    return parser


async def main() -> None:
    """Main entry point."""
    # Initialize logging
    project_root = Path(__file__).parent.parent
    config = load_config(project_root / "config" / "core.yaml")
    setup_logging(config.system)

    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.data_dir.exists():
        logger.error(f"Data directory not found: {args.data_dir}")
        sys.exit(1)

    try:
        stats = await run_synchronous_backtest(
            data_dir=args.data_dir,
            start=args.start,
            end=args.end,
            redis_url=args.redis_url,
            warmup_enabled=not args.no_warmup,
            warmup_lookback_hours=args.warmup_lookback,
        )

        if stats.get("success"):
            logger.info("\nBacktest completed successfully!")
            sys.exit(0)
        else:
            logger.error(f"\nBacktest failed: {stats.get('error')}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"\nBacktest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
