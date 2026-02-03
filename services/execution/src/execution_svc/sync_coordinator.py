"""Backtest synchronization coordinator for Execution.

This module provides the ExecutionSyncCoordinator class that ensures Execution
waits for Bot-Core to complete signal generation before processing candles.
It's part of the Synchronous Backtesting Orchestration Protocol (SBOP).

Usage:
    # In Execution main loop
    coordinator = ExecutionSyncCoordinator(redis_client, config.service_mode)

    for pair in candle_feature_pairs:
        # Wait for bot-core to complete (blocks in backtest mode, noop in live)
        await coordinator.wait_for_bot_core_ready(pair[0].timestamp)

        # Now safe to process - bot-core has generated signals
        await process_candle_with_features(pair, ...)
"""

from collections import defaultdict
from datetime import datetime

import redis.asyncio as redis

from scp_shared.messaging import RedisStreamConsumer, SYNC_ACK_STREAM
from scp_shared.messaging.schemas import SyncAckMessage


class ExecutionSyncCoordinator:
    """Coordinates Execution processing with Bot-Core synchronization.

    In backtest mode, ensures Execution only processes a tick after
    Bot-Core has signaled completion. In live mode, all methods are no-ops.

    Example:
        >>> coordinator = ExecutionSyncCoordinator(redis_client, "backtest")
        >>> await coordinator.wait_for_bot_core_ready(timestamp)  # Blocks

        >>> coordinator = ExecutionSyncCoordinator(redis_client, "live")
        >>> await coordinator.wait_for_bot_core_ready(timestamp)  # No-op
    """

    # Service that must complete before Execution can process
    REQUIRED_SERVICE = "bot-core"

    # Timeout for waiting (in seconds)
    DEFAULT_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        redis_client: redis.Redis,
        mode: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the sync coordinator.

        Args:
            redis_client: Async Redis client instance
            mode: Service mode - "backtest" or "replay" enables sync, others disable
            timeout_seconds: Maximum time to wait for acks (default: 30s)
        """
        self.redis = redis_client
        self.enabled = mode in ("backtest", "replay")
        self.timeout_seconds = timeout_seconds

        # Buffer for acks that arrive before we need them
        # Maps timestamp -> bool (has bot-core acked?)
        self._ack_buffer: dict[datetime, bool] = defaultdict(bool)

        # Consumer for sync acks (only initialized if enabled)
        self._consumer: RedisStreamConsumer[SyncAckMessage] | None = None
        self._initialized = False

    async def _ensure_consumer(self) -> None:
        """Initialize the consumer if not already done."""
        if self._initialized or not self.enabled:
            return

        self._consumer = RedisStreamConsumer(
            self.redis,
            stream=SYNC_ACK_STREAM,
            group="execution-sync",
            consumer_name="coordinator-1",
            message_type=SyncAckMessage,
        )
        await self._consumer.ensure_group()
        self._initialized = True

    async def wait_for_bot_core_ready(self, tick_timestamp: datetime) -> bool:
        """Wait until Bot-Core has acked for this tick.

        In backtest mode, blocks until Bot-Core signals completion.
        In live mode, returns immediately.

        Args:
            tick_timestamp: The candle timestamp to wait for

        Returns:
            True if data is ready (or if sync is disabled)

        Raises:
            TimeoutError: If Bot-Core doesn't ack within timeout (backtest only)
        """
        if not self.enabled:
            return True

        await self._ensure_consumer()

        # Check buffer first - maybe we already have the ack
        if self._check_buffer(tick_timestamp):
            return True

        # Read acks until we have the required one
        import asyncio

        deadline = asyncio.get_event_loop().time() + self.timeout_seconds

        while asyncio.get_event_loop().time() < deadline:
            # Calculate remaining time
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break

            # Read with short timeout to allow checking deadline
            block_ms = min(int(remaining * 1000), 500)

            if self._consumer is not None:
                try:
                    acks = await self._consumer.read(count=50, block_ms=block_ms)
                    for ack in acks:
                        if ack.service_id == self.REQUIRED_SERVICE:
                            self._ack_buffer[ack.tick_timestamp] = True

                    # Check if we now have the required ack
                    if self._check_buffer(tick_timestamp):
                        return True
                except Exception:
                    # On error, continue trying until timeout
                    await asyncio.sleep(0.1)

        # Timeout - this is a fatal error in backtest mode
        raise TimeoutError(
            f"Timeout waiting for sync ack from {self.REQUIRED_SERVICE} at tick {tick_timestamp}"
        )

    def _check_buffer(self, tick_timestamp: datetime) -> bool:
        """Check if bot-core ack is in the buffer.

        Args:
            tick_timestamp: The timestamp to check

        Returns:
            True if bot-core has acked
        """
        if self._ack_buffer.get(tick_timestamp, False):
            # Clear the buffer entry to free memory
            del self._ack_buffer[tick_timestamp]
            # Also clean up old entries (older than 5 minutes of data)
            self._cleanup_old_entries(tick_timestamp)
            return True
        return False

    def _cleanup_old_entries(self, current_timestamp: datetime) -> None:
        """Remove buffer entries that are too old.

        Args:
            current_timestamp: Current tick timestamp
        """
        from datetime import timedelta

        cutoff = current_timestamp - timedelta(minutes=5)
        old_keys = [ts for ts in self._ack_buffer if ts < cutoff]
        for key in old_keys:
            del self._ack_buffer[key]

    def get_buffer_stats(self) -> dict[str, int | bool]:
        """Get buffer statistics for monitoring.

        Returns:
            Dict with buffer size info
        """
        return {
            "buffered_timestamps": len(self._ack_buffer),
            "enabled": self.enabled,
        }
