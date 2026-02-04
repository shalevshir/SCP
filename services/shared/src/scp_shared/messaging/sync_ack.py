"""Synchronization acknowledgment utilities for backtest orchestration.

This module provides the SyncAckPublisher class for sending completion signals
during synchronous backtesting. It's part of the Synchronous Backtesting
Orchestration Protocol (SBOP) that ensures deterministic backtest execution.

Usage:
    # In a service (e.g., Feature Engine)
    ack_publisher = SyncAckPublisher(redis_client, "feature-engine", config.service_mode)

    # After processing each tick
    await ack_publisher.ack(candle.timestamp)

    # On error
    await ack_publisher.ack(candle.timestamp, status="ERROR", error="Processing failed")
"""

from datetime import datetime

import redis.asyncio as redis

from scp_shared.messaging.redis_streams import RedisStreamPublisher
from scp_shared.messaging.schemas import SyncAckMessage


# Stream name for synchronization acks
SYNC_ACK_STREAM = "sync.ack"


class SyncAckPublisher:
    """Mode-aware publisher for synchronization acknowledgments.

    Sends completion signals only in backtest mode, no-ops in live mode.
    This allows services to work in both async (live) and sync (backtest) modes
    with minimal code changes.

    Example:
        >>> publisher = SyncAckPublisher(redis_client, "feature-engine", "backtest")
        >>> await publisher.ack(timestamp)  # Sends ack

        >>> publisher = SyncAckPublisher(redis_client, "feature-engine", "live")
        >>> await publisher.ack(timestamp)  # No-op, returns immediately
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        service_id: str,
        mode: str,
    ) -> None:
        """Initialize the sync ack publisher.

        Args:
            redis_client: Async Redis client instance
            service_id: Unique service identifier (e.g., "feature-engine", "htf-bias", "bot-core")
            mode: Service mode - "backtest" enables acks, any other value disables them
        """
        self.redis = redis_client
        self.service_id = service_id
        self.enabled = mode == "backtest"
        self._publisher = RedisStreamPublisher(redis_client) if self.enabled else None

    async def ack(
        self,
        tick_timestamp: datetime,
        status: str = "OK",
        error: str | None = None,
    ) -> str | None:
        """Send a synchronization acknowledgment for a processed tick.

        In backtest mode, publishes a SyncAckMessage to the sync.ack stream.
        In live mode, this is a no-op that returns immediately.

        Args:
            tick_timestamp: The candle/tick timestamp that was processed
            status: Completion status - "OK" for success, "ERROR" for failure
            error: Error message if status is "ERROR"

        Returns:
            Message ID if published, None if acks are disabled (live mode)
        """
        if not self.enabled or self._publisher is None:
            return None

        message = SyncAckMessage(
            service_id=self.service_id,
            tick_timestamp=tick_timestamp,
            status=status,
            error_message=error,
        )

        return await self._publisher.publish(SYNC_ACK_STREAM, message)

    async def ack_error(
        self,
        tick_timestamp: datetime,
        error: str,
    ) -> str | None:
        """Convenience method for sending error acknowledgments.

        Args:
            tick_timestamp: The candle/tick timestamp that failed
            error: Error description

        Returns:
            Message ID if published, None if acks are disabled
        """
        return await self.ack(tick_timestamp, status="ERROR", error=error)
