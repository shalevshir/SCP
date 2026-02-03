"""Backtest synchronization coordinator for Bot-Core.

This module provides the BacktestSyncCoordinator class that ensures Bot-Core
waits for upstream services (Feature Engine, HTF Bias) to complete processing
before evaluating signals. It's part of the Synchronous Backtesting Orchestration
Protocol (SBOP) that ensures deterministic backtest execution.

Usage:
    # In Bot-Core main loop
    coordinator = BacktestSyncCoordinator(redis_client, config.service_mode)

    for features_msg in features_list:
        # Wait for workers to complete (blocks in backtest mode, noop in live)
        await coordinator.wait_for_data_ready(features_msg.timestamp)

        # Now safe to process - all data for this tick is guaranteed ready
        result = await process_feature_message(features_msg, ...)
"""

from collections import defaultdict
from datetime import datetime

import redis.asyncio as redis

from scp_shared.messaging import RedisStreamConsumer, SYNC_ACK_STREAM
from scp_shared.messaging.schemas import SyncAckMessage


class BacktestSyncCoordinator:
    """Coordinates Bot-Core processing with barrier synchronization.

    In backtest mode, this coordinator ensures that Bot-Core only processes
    a tick after both Feature Engine and HTF Bias have signaled completion.
    In live mode, all methods are no-ops that return immediately.

    Example:
        >>> coordinator = BacktestSyncCoordinator(redis_client, "backtest")
        >>> await coordinator.wait_for_data_ready(timestamp)  # Blocks until ready

        >>> coordinator = BacktestSyncCoordinator(redis_client, "live")
        >>> await coordinator.wait_for_data_ready(timestamp)  # Returns immediately
    """

    # Services that must complete before Bot-Core can process
    REQUIRED_SERVICES = frozenset(["feature-engine", "htf-bias"])

    # Timeout for waiting (in seconds) - should never be reached in normal operation
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
        # Maps timestamp -> set of service_ids that have acked
        self._ack_buffer: dict[datetime, set[str]] = defaultdict(set)

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
            group="bot-core-sync",
            consumer_name="coordinator-1",
            message_type=SyncAckMessage,
        )
        await self._consumer.ensure_group()
        self._initialized = True

    async def wait_for_data_ready(self, tick_timestamp: datetime) -> bool:
        """Wait until all required services have acked for this tick.

        In backtest mode, blocks until Feature Engine and HTF Bias both
        signal completion for the given timestamp. In live mode, returns
        immediately.

        Args:
            tick_timestamp: The candle timestamp to wait for

        Returns:
            True if data is ready (or if sync is disabled)

        Raises:
            TimeoutError: If services don't ack within timeout (backtest only)
        """
        if not self.enabled:
            return True

        await self._ensure_consumer()

        # Check buffer first - maybe we already have the acks
        if self._check_buffer(tick_timestamp):
            return True

        # Read acks until we have all required ones
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
                        if ack.service_id in self.REQUIRED_SERVICES:
                            self._ack_buffer[ack.tick_timestamp].add(ack.service_id)

                    # Check if we now have all required acks
                    if self._check_buffer(tick_timestamp):
                        return True
                except Exception:
                    # On error, continue trying until timeout
                    await asyncio.sleep(0.1)

        # Timeout - this is a fatal error in backtest mode
        missing = self.REQUIRED_SERVICES - self._ack_buffer.get(tick_timestamp, set())
        raise TimeoutError(
            f"Timeout waiting for sync acks from {missing} at tick {tick_timestamp}"
        )

    def _check_buffer(self, tick_timestamp: datetime) -> bool:
        """Check if all required acks are in the buffer.

        Args:
            tick_timestamp: The timestamp to check

        Returns:
            True if all required services have acked
        """
        buffered = self._ack_buffer.get(tick_timestamp, set())
        if self.REQUIRED_SERVICES.issubset(buffered):
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

    def get_buffer_stats(self) -> dict[str, int]:
        """Get buffer statistics for monitoring.

        Returns:
            Dict with buffer size info
        """
        return {
            "buffered_timestamps": len(self._ack_buffer),
            "enabled": self.enabled,
        }
