#!/usr/bin/env python3
"""Replay historical data through microservices pipeline.

This script loads historical GC and DXY candles from CSV files and publishes
them to Redis streams for microservices to process. Used for validation testing
to compare microservices results against backtester results.

Includes a warmup phase that publishes historical candles from before the start
date to warmup streams, allowing downstream services to initialize their
indicators (VWAP, EMA, RSI, etc.) before the main replay begins.

Usage:
    # Fast replay (100x speed)
    poetry run python scripts/replay_historical.py \
        --start 2024-11-01 --end 2024-11-30 --speed 100

    # Real-time replay
    poetry run python scripts/replay_historical.py \
        --start 2024-11-01 --end 2024-11-30 --speed 1

    # Custom data directory
    poetry run python scripts/replay_historical.py \
        --start 2024-11-01 --end 2024-11-30 \
        --data-dir data/gc_dx_ohlcv

    # Skip warmup phase
    poetry run python scripts/replay_historical.py \
        --start 2024-11-01 --end 2024-11-30 --no-warmup
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import redis.asyncio as redis
from scp_shared.messaging.schemas import CandleMessage

from common.logger import get_logger, setup_logging
from common.config import load_config
from data_layer.loader import HistoricalDataLoader

logger = get_logger(__name__)


# Backpressure configuration
MAX_PENDING_MESSAGES = 500  # Max unacknowledged messages before pausing
BACKPRESSURE_CHECK_INTERVAL = 50  # Check backpressure every N publishes
BACKPRESSURE_WAIT_SECONDS = 0.5  # Wait time when backpressure detected

# Stream trimming configuration
# Keep streams capped to prevent memory bloat during replay
# NOTE: Must be larger than total candles to prevent slower consumers from losing messages
# 30 days * 24h * 60min = 43,200 candles, so use 50,000 to be safe
STREAM_MAXLEN = 50000  # Max messages per stream (uses approximate trimming)

# Warmup configuration
DEFAULT_WARMUP_LOOKBACK_HOURS = 24  # Default lookback for warmup data
WARMUP_STREAM_TTL_SECONDS = 600  # TTL for warmup streams (10 minutes)

# Consumer groups to monitor (stream -> group name)
# These are the downstream consumers that might fall behind
MONITORED_CONSUMER_GROUPS = [
    ("candles.1m.gc", "feature-engine"),
    ("candles.1m.dxy", "feature-engine"),
    ("candles.1m.gc", "htf-bias"),  # HTF Bias also consumes candles
    ("candles.1m.dxy", "htf-bias"),
    ("features.1m", "bot-core"),
    ("features.1m", "execution"),  # Execution also consumes features
    ("htf.bias", "bot-core"),
    ("signals.pending", "execution"),
]


async def get_pending_count(redis_client: redis.Redis, stream: str, group: str) -> int:
    """Get count of pending (unacknowledged) messages for a consumer group.

    Uses XPENDING to check how many messages are waiting to be processed.
    """
    try:
        # XPENDING returns [total_pending, min_id, max_id, [[consumer, count], ...]]
        result = await redis_client.xpending(stream, group)
        if result and len(result) > 0:
            return result[0]  # First element is total pending count
        return 0
    except Exception:
        # Group might not exist yet, that's fine
        return 0


async def check_backpressure(redis_client: redis.Redis) -> tuple[bool, str | None, int]:
    """Check if any consumer group has too many pending (unacknowledged) messages.

    Returns:
        Tuple of (has_backpressure, stream_name, pending_count)
    """
    for stream, group in MONITORED_CONSUMER_GROUPS:
        pending = await get_pending_count(redis_client, stream, group)
        if pending > MAX_PENDING_MESSAGES:
            return True, f"{stream}:{group}", pending
    return False, None, 0


async def publish_with_trim(
    redis_client: redis.Redis,
    stream: str,
    message: CandleMessage,
    maxlen: int = STREAM_MAXLEN,
) -> str:
    """Publish message to stream with automatic trimming.

    Uses XADD with MAXLEN ~ to cap stream size, preventing memory bloat.
    The ~ means approximate trimming (more efficient than exact).
    """
    data = {
        "type": message.__class__.__name__,
        "payload": message.model_dump_json(),
        "published_at": datetime.now(UTC).isoformat(),
    }

    # XADD with MAXLEN ~ for automatic trimming
    message_id = await redis_client.xadd(
        stream,
        data,
        maxlen=maxlen,
        approximate=True,  # ~ in Redis - more efficient
    )
    return message_id.decode() if isinstance(message_id, bytes) else message_id


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO-8601 datetime strings, defaulting to UTC when tzinfo missing."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def publish_warmup_data(
    redis_client: redis.Redis,
    data_dir: Path,
    replay_start: datetime,
    lookback_hours: int = DEFAULT_WARMUP_LOOKBACK_HOURS,
    ttl_seconds: int = WARMUP_STREAM_TTL_SECONDS,
) -> bool:
    """Publish warmup data from CSV files to Redis warmup streams.

    Loads historical candles from BEFORE the replay start date and publishes
    them to warmup streams for downstream services to initialize their indicators.

    If the CSV files don't have enough data for the full lookback period,
    uses as much data as available (goes back to the earliest available candle).

    Args:
        redis_client: Redis client for stream publishing
        data_dir: Directory containing CSV files
        replay_start: Start datetime of the main replay (warmup uses data before this)
        lookback_hours: Desired hours of warmup data (default: 24)
        ttl_seconds: TTL for warmup streams (default: 600s / 10 minutes)

    Returns:
        True if warmup data published successfully, False otherwise
    """
    logger.info("=" * 80)
    logger.info("Warmup Phase")
    logger.info("=" * 80)

    # Calculate desired warmup range
    desired_warmup_start = replay_start - timedelta(hours=lookback_hours)
    warmup_end = replay_start - timedelta(minutes=1)  # End 1 minute before replay starts

    logger.info(f"Desired warmup range: {desired_warmup_start} to {warmup_end}")
    logger.info(f"Lookback: {lookback_hours} hours ({lookback_hours * 60} candles)")

    try:
        # Load warmup data with the requested lookback period
        loader = HistoricalDataLoader(data_dir)

        logger.info("Loading warmup candles from CSV files...")

        # First try with the desired lookback
        try:
            warmup_data = loader.load(["GC", "DXY"], "1m", desired_warmup_start, warmup_end)
        except Exception as e:
            logger.warning(f"Failed to load warmup data with desired lookback: {e}")
            # If that fails, try loading from very early to get whatever is available
            max_lookback_start = replay_start - timedelta(days=365)
            warmup_data = loader.load(["GC", "DXY"], "1m", max_lookback_start, warmup_end)

        gc_warmup_df = warmup_data.get("GC")
        dxy_warmup_df = warmup_data.get("DXY")

        if gc_warmup_df is None or gc_warmup_df.empty:
            logger.warning("No GC warmup data available")
            await _set_warmup_error_status(redis_client, "No GC warmup data", ttl_seconds)
            return False

        if dxy_warmup_df is None or dxy_warmup_df.empty:
            logger.warning("No DXY warmup data available")
            await _set_warmup_error_status(redis_client, "No DXY warmup data", ttl_seconds)
            return False

        # Reset index to get timestamp as column
        if "timestamp" not in gc_warmup_df.columns:
            gc_warmup_df = gc_warmup_df.reset_index()
        if "timestamp" not in dxy_warmup_df.columns:
            dxy_warmup_df = dxy_warmup_df.reset_index()

        # Log actual warmup range
        gc_start = gc_warmup_df["timestamp"].min()
        gc_end = gc_warmup_df["timestamp"].max()
        dxy_start = dxy_warmup_df["timestamp"].min()
        dxy_end = dxy_warmup_df["timestamp"].max()

        logger.info(f"GC warmup data: {len(gc_warmup_df)} candles ({gc_start} to {gc_end})")
        logger.info(f"DXY warmup data: {len(dxy_warmup_df)} candles ({dxy_start} to {dxy_end})")

        # Check if we have less than desired lookback
        actual_gc_hours = (gc_end - gc_start).total_seconds() / 3600 if len(gc_warmup_df) > 1 else 0
        actual_dxy_hours = (dxy_end - dxy_start).total_seconds() / 3600 if len(dxy_warmup_df) > 1 else 0

        if actual_gc_hours < lookback_hours:
            logger.warning(
                f"GC warmup data limited: {actual_gc_hours:.1f}h available "
                f"(requested {lookback_hours}h)"
            )
        if actual_dxy_hours < lookback_hours:
            logger.warning(
                f"DXY warmup data limited: {actual_dxy_hours:.1f}h available "
                f"(requested {lookback_hours}h)"
            )

        # Clear any existing warmup streams and status
        logger.info("Clearing existing warmup streams...")
        await redis_client.delete(
            "warmup.candles.1m.gc",
            "warmup.candles.1m.dxy",
            "warmup:status",
        )

        # Publish GC warmup candles
        logger.info(f"Publishing {len(gc_warmup_df)} GC warmup candles...")
        for _, row in gc_warmup_df.iterrows():
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

        # Publish DXY warmup candles
        logger.info(f"Publishing {len(dxy_warmup_df)} DXY warmup candles...")
        for _, row in dxy_warmup_df.iterrows():
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

        # Set completion status
        await redis_client.hset(
            "warmup:status",
            mapping={
                "gc": "complete",
                "dxy": "complete",
                "gc_count": str(len(gc_warmup_df)),
                "dxy_count": str(len(dxy_warmup_df)),
                "gc_start": str(gc_start),
                "gc_end": str(gc_end),
                "dxy_start": str(dxy_start),
                "dxy_end": str(dxy_end),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        # Set TTL on warmup streams
        await redis_client.expire("warmup.candles.1m.gc", ttl_seconds)
        await redis_client.expire("warmup.candles.1m.dxy", ttl_seconds)
        await redis_client.expire("warmup:status", ttl_seconds)

        logger.info(
            f"Warmup phase complete: {len(gc_warmup_df)} GC, "
            f"{len(dxy_warmup_df)} DXY candles published (TTL: {ttl_seconds}s)"
        )
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"Warmup phase failed: {e}", exc_info=True)
        await _set_warmup_error_status(redis_client, str(e), ttl_seconds)
        return False


async def _set_warmup_error_status(
    redis_client: redis.Redis,
    error_message: str,
    ttl_seconds: int,
) -> None:
    """Set error status in Redis for warmup failure."""
    try:
        await redis_client.delete("warmup:status")
        await redis_client.hset(
            "warmup:status",
            mapping={
                "error": error_message,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await redis_client.expire("warmup:status", ttl_seconds)
    except Exception as e:
        logger.error(f"Failed to set warmup error status: {e}")


async def wait_for_services_warmup_consumption(
    redis_client: redis.Redis,
    timeout_seconds: int = 120,
    poll_interval: float = 2.0,
    settle_delay_seconds: float = 10.0,
) -> bool:
    """Wait for downstream services to consume warmup data.

    Monitors warmup stream lengths - when they reach 0 or are deleted,
    services have consumed all warmup candles.

    Args:
        redis_client: Redis client
        timeout_seconds: Maximum time to wait (default: 120s)
        poll_interval: Seconds between checks (default: 2.0s)
        settle_delay_seconds: Additional delay after services signal consumption
            to allow them to finish processing (default: 5.0s)

    Returns:
        True if services consumed warmup data, False on timeout
    """
    logger.info("=" * 80)
    logger.info("Waiting for services to consume warmup data...")
    logger.info("=" * 80)

    start_time = asyncio.get_event_loop().time()
    last_log_time = 0.0

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time

        if elapsed > timeout_seconds:
            logger.warning(
                f"Timeout waiting for services to consume warmup data after {timeout_seconds}s"
            )
            return False

        # Check if warmup streams are empty or deleted
        gc_len = await redis_client.xlen("warmup.candles.1m.gc")
        dxy_len = await redis_client.xlen("warmup.candles.1m.dxy")

        # Log progress every 10 seconds
        if elapsed - last_log_time >= 10:
            logger.info(
                f"Warmup consumption progress: GC stream={gc_len}, DXY stream={dxy_len} "
                f"({elapsed:.0f}s elapsed)"
            )
            last_log_time = elapsed

        # Streams are consumed when empty (length 0) or deleted (also returns 0)
        # We check if both are 0, meaning services have read all messages
        # Note: Services use XREAD which doesn't delete messages, so we check
        # if warmup:status has been processed by looking for a consumed marker

        # Check if warmup status still exists (TTL hasn't expired)
        status_exists = await redis_client.exists("warmup:status")

        if not status_exists:
            # Status expired - warmup window passed
            logger.info("Warmup status expired - proceeding with replay")
            return True

        # Check for consumption complete marker set by services
        status = await redis_client.hgetall("warmup:status")
        if status:
            status_decoded = {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in status.items()
            }

            # Services set these when they finish consuming
            fe_consumed = status_decoded.get("feature_engine_consumed") == "true"
            htf_consumed = status_decoded.get("htf_bias_consumed") == "true"

            if fe_consumed and htf_consumed:
                logger.info(
                    f"All services consumed warmup data after {elapsed:.1f}s"
                )
                # Add settle delay to allow services to finish processing
                if settle_delay_seconds > 0:
                    logger.info(
                        f"Waiting {settle_delay_seconds}s for services to finish processing warmup..."
                    )
                    await asyncio.sleep(settle_delay_seconds)
                return True

        await asyncio.sleep(poll_interval)

    return False


async def replay_historical_data(
    data_dir: Path,
    start: datetime,
    end: datetime,
    redis_url: str,
    speed_multiplier: float = 1.0,
    processing_delay: float = 5.0,
    warmup_enabled: bool = True,
    warmup_lookback_hours: int = DEFAULT_WARMUP_LOOKBACK_HOURS,
) -> dict:
    """Replay historical candles through Redis streams.

    Args:
        data_dir: Directory containing CSV files
        start: Start datetime (UTC)
        end: End datetime (UTC)
        redis_url: Redis connection URL
        speed_multiplier: Speed multiplier (1.0 = real-time, 100.0 = 100x faster)
        processing_delay: Seconds to wait after publishing for pipeline processing
        warmup_enabled: Whether to run warmup phase before replay (default: True)
        warmup_lookback_hours: Hours of warmup data to load (default: 24)

    Returns:
        Dictionary with replay statistics
    """
    logger.info("=" * 80)
    logger.info("Historical Data Replay")
    logger.info("=" * 80)
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Date range: {start} to {end}")
    logger.info(f"Redis URL: {redis_url}")
    if speed_multiplier == 0:
        logger.info("Speed: TURBO MODE (no delays, maximum speed)")
    else:
        logger.info(f"Speed multiplier: {speed_multiplier}x")

    # Load historical data
    logger.info("\nLoading historical data from CSV...")
    loader = HistoricalDataLoader(data_dir)

    try:
        data = loader.load(["GC", "DXY"], "1m", start, end)
    except Exception as e:
        logger.error(f"Failed to load historical data: {e}")
        raise

    gc_df = data.get("GC")
    dxy_df = data.get("DXY")

    if gc_df is None or gc_df.empty:
        raise ValueError("No GC data loaded")
    if dxy_df is None or dxy_df.empty:
        raise ValueError("No DXY data loaded")

    logger.info(f"Loaded {len(gc_df)} GC candles")
    logger.info(f"Loaded {len(dxy_df)} DXY candles")

    # Connect to Redis
    logger.info(f"\nConnecting to Redis at {redis_url}...")
    redis_client = redis.Redis.from_url(redis_url)

    try:
        await redis_client.ping()
        logger.info("Connected to Redis successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        await redis_client.aclose()
        raise

    # Clean up old streams to prevent leftover data from previous runs
    logger.info("\nCleaning up old streams...")
    streams_to_delete = [
        "candles.1m.gc",
        "candles.1m.dxy",
        "features.1m",
        "features.15m",
        "features.1h",
        "htf.bias",
        "signals.pending",
    ]
    for stream in streams_to_delete:
        try:
            await redis_client.delete(stream)
            logger.debug(f"Deleted stream: {stream}")
        except Exception:
            pass  # Stream might not exist
    logger.info(f"Cleaned up {len(streams_to_delete)} streams")

    # Execute warmup phase - publish historical data before replay start
    # for downstream services to initialize indicators
    if warmup_enabled:
        warmup_success = await publish_warmup_data(
            redis_client=redis_client,
            data_dir=data_dir,
            replay_start=start,
            lookback_hours=warmup_lookback_hours,
        )
        if warmup_success:
            # Wait for downstream services to consume warmup data before starting replay
            await wait_for_services_warmup_consumption(
                redis_client=redis_client,
                timeout_seconds=120,  # 2 minute timeout
            )
        else:
            logger.warning(
                "Warmup phase failed - downstream services may have cold indicators"
            )
    else:
        logger.info("\nWarmup disabled - skipping warmup phase")

    # Prepare candles for publishing
    # Align GC and DXY by timestamp
    logger.info("\nAligning GC and DXY candles by timestamp...")

    # Ensure timestamp is in index
    if "timestamp" not in gc_df.columns:
        gc_df = gc_df.reset_index()
    if "timestamp" not in dxy_df.columns:
        dxy_df = dxy_df.reset_index()

    # Merge on timestamp (inner join to only publish paired candles)
    import pandas as pd

    merged = pd.merge(
        gc_df[["timestamp", "open", "high", "low", "close", "volume"]],
        dxy_df[["timestamp", "open", "high", "low", "close", "volume"]],
        on="timestamp",
        suffixes=("_gc", "_dxy"),
    )

    logger.info(f"Aligned {len(merged)} candle pairs")

    if merged.empty:
        logger.error(
            "No aligned candles found. Check that GC and DXY have overlapping timestamps."
        )
        await redis_client.aclose()
        return {
            "candles_published": 0,
            "gc_published": 0,
            "dxy_published": 0,
            "duration_seconds": 0,
            "success": False,
        }

    # Publish candles
    if speed_multiplier == 0:
        logger.info(
            f"\nPublishing {len(merged)} candle pairs in TURBO MODE (no delays)..."
        )
        logger.info(
            f"Backpressure monitoring: pauses if any consumer has >{MAX_PENDING_MESSAGES} unacked messages"
        )
    else:
        logger.info(
            f"\nPublishing {len(merged)} candle pairs at {speed_multiplier}x speed..."
        )
    logger.info("Press Ctrl+C to stop\n")

    published_count = 0
    gc_published = 0
    dxy_published = 0
    prev_timestamp = None
    start_time = asyncio.get_event_loop().time()
    backpressure_waits = 0

    try:
        for idx, row in merged.iterrows():
            timestamp = row["timestamp"]

            # Simulate time delay (scaled by speed multiplier)
            # Speed 0 = turbo mode (no delays at all)
            if speed_multiplier > 0 and prev_timestamp is not None:
                delay_seconds = (timestamp - prev_timestamp).total_seconds()
                scaled_delay = delay_seconds / speed_multiplier
                if scaled_delay > 0:
                    await asyncio.sleep(scaled_delay)

            # Create GC candle message
            gc_candle = CandleMessage(
                timestamp=timestamp,
                symbol="GC",
                timeframe="1m",
                open=float(row["open_gc"]),
                high=float(row["high_gc"]),
                low=float(row["low_gc"]),
                close=float(row["close_gc"]),
                volume=float(row["volume_gc"]),
            )

            # Create DXY candle message
            dxy_candle = CandleMessage(
                timestamp=timestamp,
                symbol="DXY",
                timeframe="1m",
                open=float(row["open_dxy"]),
                high=float(row["high_dxy"]),
                low=float(row["low_dxy"]),
                close=float(row["close_dxy"]),
                volume=float(row["volume_dxy"]),
            )

            # Publish to Redis streams with automatic trimming
            await publish_with_trim(redis_client, "candles.1m.gc", gc_candle)
            gc_published += 1

            await publish_with_trim(redis_client, "candles.1m.dxy", dxy_candle)
            dxy_published += 1

            published_count += 1

            # Progress update every 100 candles
            if published_count % 100 == 0:
                elapsed = asyncio.get_event_loop().time() - start_time
                rate = published_count / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Published {published_count}/{len(merged)} candle pairs "
                    f"({published_count * 100 / len(merged):.1f}%) - "
                    f"{rate:.1f} candles/sec"
                )

            # Backpressure check in turbo mode
            if (
                speed_multiplier == 0
                and published_count % BACKPRESSURE_CHECK_INTERVAL == 0
            ):
                while True:
                    has_backpressure, stream_name, length = await check_backpressure(
                        redis_client
                    )
                    if not has_backpressure:
                        break

                    if backpressure_waits % 20 == 0:  # Log every ~10 seconds
                        logger.info(
                            f"Backpressure: waiting for {stream_name} to drain "
                            f"({length} > {MAX_PENDING_MESSAGES} unacked)"
                        )
                    backpressure_waits += 1
                    await asyncio.sleep(BACKPRESSURE_WAIT_SECONDS)

            prev_timestamp = timestamp

    except KeyboardInterrupt:
        logger.info("\nReplay interrupted by user")

    except Exception as e:
        logger.error(f"\nError during replay: {e}", exc_info=True)
        await redis_client.aclose()
        raise

    end_time = asyncio.get_event_loop().time()
    duration = end_time - start_time

    logger.info("\n" + "=" * 80)
    logger.info("Replay Complete")
    logger.info("=" * 80)
    logger.info(f"Published {published_count} candle pairs")
    logger.info(f"  - GC candles: {gc_published}")
    logger.info(f"  - DXY candles: {dxy_published}")
    if backpressure_waits > 0:
        logger.info(f"  - Backpressure waits: {backpressure_waits}")
    logger.info(f"Duration: {duration:.2f} seconds ({duration / 60:.1f} minutes)")
    if duration > 0:
        logger.info(f"Average rate: {published_count / duration:.1f} candles/sec")

    # Calculate time saved
    if speed_multiplier > 0:
        real_time_duration = published_count * 60  # Each candle represents 1 minute
        time_saved_hours = (real_time_duration - duration) / 3600
        logger.info(f"Time saved: ~{time_saved_hours:.1f} hours vs real-time")
    else:
        real_time_duration = published_count * 60
        logger.info(
            f"Published {published_count} minutes of data in {duration:.2f} seconds"
        )
        logger.info(
            f"Speedup: {real_time_duration / duration:.0f}x faster than real-time"
        )

    # Wait for entire pipeline to process
    max_wait_seconds = 900  # 15 minutes max wait
    check_interval = 2  # Check every 2 seconds

    async def wait_for_consumer(stream: str, group: str, service_name: str) -> bool:
        """Wait for a consumer group to catch up to the stream."""
        logger.info(f"\nWaiting for {service_name} to consume from {stream}...")
        wait_start = asyncio.get_event_loop().time()
        last_log_time = 0

        while True:
            elapsed = asyncio.get_event_loop().time() - wait_start
            if elapsed > max_wait_seconds:
                logger.warning(
                    f"Timeout waiting for {service_name} after {max_wait_seconds}s"
                )
                return False

            try:
                # Get consumer group info using XINFO GROUPS
                groups = await redis_client.xinfo_groups(stream)
                last_delivered_id = None

                # Debug: log the format on first iteration
                if elapsed < 3 and groups:
                    logger.debug(
                        f"xinfo_groups format for {stream}: {type(groups[0])}, keys: {list(groups[0].keys()) if hasattr(groups[0], 'keys') else 'N/A'}"
                    )

                for group_info in groups:
                    # Handle both dict-like and list-of-pairs formats
                    if isinstance(group_info, dict):
                        # Dict format: {'name': 'group', 'last-delivered-id': 'id', ...}
                        name_key = b"name" if b"name" in group_info else "name"
                        lid_key = (
                            b"last-delivered-id"
                            if b"last-delivered-id" in group_info
                            else "last-delivered-id"
                        )
                        name = group_info.get(name_key, b"")
                        if isinstance(name, bytes):
                            name = name.decode()
                        if name == group:
                            lid = group_info.get(lid_key, b"0")
                            last_delivered_id = (
                                lid.decode() if isinstance(lid, bytes) else str(lid)
                            )
                            break

                if last_delivered_id is None:
                    # Consumer group doesn't exist yet or not found
                    if elapsed - last_log_time >= 10:
                        logger.info(
                            f"Waiting for {service_name}: consumer group '{group}' not found ({elapsed:.0f}s elapsed)"
                        )
                        last_log_time = elapsed
                    await asyncio.sleep(check_interval)
                    continue

                # Get last message in stream
                stream_last = await redis_client.xrevrange(stream, count=1)
                if not stream_last:
                    logger.info(
                        f"{service_name}: stream {stream} is empty, considering caught up"
                    )
                    return True

                stream_last_id = stream_last[0][0]
                if isinstance(stream_last_id, bytes):
                    stream_last_id = stream_last_id.decode()

                # Check if caught up (string comparison works for Redis IDs)
                if last_delivered_id >= stream_last_id:
                    logger.info(
                        f"{service_name} caught up on {stream} after {elapsed:.1f}s"
                    )
                    return True

                if elapsed - last_log_time >= 10:  # Log every 10 seconds
                    logger.info(
                        f"Waiting for {service_name}: {last_delivered_id} / {stream_last_id} ({elapsed:.0f}s elapsed)"
                    )
                    last_log_time = elapsed

            except Exception as e:
                if elapsed - last_log_time >= 10:
                    logger.warning(
                        f"Error checking {service_name} progress on {stream}: {e}"
                    )
                    last_log_time = elapsed

            await asyncio.sleep(check_interval)

    # Stage 1: Wait for Feature Engine to consume candles
    await wait_for_consumer("candles.1m.gc", "feature-engine", "Feature Engine")
    await wait_for_consumer("candles.1m.dxy", "feature-engine", "Feature Engine")

    # Stage 2: Wait for Bot Core to consume features
    await wait_for_consumer("features.1m", "bot-core", "Bot Core")

    # Stage 3: Wait for Execution to consume signals (if any)
    try:
        signals_len = await redis_client.xlen("signals.pending")
        if signals_len > 0:
            await wait_for_consumer("signals.pending", "execution", "Execution")
    except Exception:
        pass  # signals.pending might not exist

    # Additional fixed delay for final processing
    if processing_delay > 0:
        logger.info(f"\nWaiting {processing_delay} seconds for final processing...")
        await asyncio.sleep(processing_delay)
        logger.info("Processing delay complete")

    await redis_client.aclose()

    return {
        "candles_published": published_count,
        "gc_published": gc_published,
        "dxy_published": dxy_published,
        "duration_seconds": duration,
        "success": True,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Replay historical data through microservices pipeline"
    )

    # Date range
    parser.add_argument(
        "--start",
        type=parse_iso_datetime,
        required=True,
        help="Start datetime (ISO-8601, e.g., 2024-11-01T00:00:00Z)",
    )
    parser.add_argument(
        "--end",
        type=parse_iso_datetime,
        required=True,
        help="End datetime (ISO-8601, e.g., 2024-11-30T23:59:59Z)",
    )

    # Data source
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/gc_dx_ohlcv"),
        help="Directory containing CSV files (default: data/gc_dx_ohlcv)",
    )

    # Redis connection
    parser.add_argument(
        "--redis-url",
        type=str,
        default="redis://localhost:6379",
        help="Redis connection URL (default: redis://localhost:6379)",
    )

    # Speed control
    parser.add_argument(
        "--speed",
        type=float,
        default=0,  # 0 = turbo mode (no delays)
        help="Speed multiplier (0 = turbo/no delays, 1.0 = real-time, 100.0 = 100x faster, default: 0)",
    )

    # Processing delay
    parser.add_argument(
        "--processing-delay",
        type=float,
        default=5.0,
        help="Seconds to wait after publishing for pipeline processing (default: 5.0)",
    )

    # Warmup options
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip warmup phase (downstream services will have cold indicators)",
    )
    parser.add_argument(
        "--warmup-lookback",
        type=int,
        default=DEFAULT_WARMUP_LOOKBACK_HOURS,
        help=f"Hours of warmup data to load before replay start (default: {DEFAULT_WARMUP_LOOKBACK_HOURS})",
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

    # Validate data directory
    if not args.data_dir.exists():
        logger.error(f"Data directory not found: {args.data_dir}")
        sys.exit(1)

    # Run replay
    try:
        stats = await replay_historical_data(
            data_dir=args.data_dir,
            start=args.start,
            end=args.end,
            redis_url=args.redis_url,
            speed_multiplier=args.speed,
            processing_delay=args.processing_delay,
            warmup_enabled=not args.no_warmup,
            warmup_lookback_hours=args.warmup_lookback,
        )

        if stats["success"]:
            logger.info("\nReplay completed successfully!")
            sys.exit(0)
        else:
            logger.error("\nReplay failed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"\nReplay failed with error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
