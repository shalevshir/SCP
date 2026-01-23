"""Trade event publisher for Redis streams."""

import redis.asyncio as redis

from scp_shared.common.logger import get_logger
from scp_shared.messaging import RedisStreamPublisher
from scp_shared.messaging.schemas import TradeMessage

logger = get_logger(__name__)


class TradePublisher:
    """Publish trade lifecycle events to Redis streams.

    Publishes TradeMessage objects to trades.opened and trades.closed streams
    for consumption by monitoring and analytics services.

    Example:
        >>> publisher = TradePublisher(redis_client)
        >>> await publisher.publish_opened(trade_message)
        >>> await publisher.publish_closed(trade_message)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        opened_stream: str = "trades.opened",
        closed_stream: str = "trades.closed",
    ) -> None:
        """Initialize trade publisher.

        Args:
            redis_client: Redis client
            opened_stream: Stream name for opened trades
            closed_stream: Stream name for closed trades
        """
        self._publisher = RedisStreamPublisher(redis_client)
        self._opened_stream = opened_stream
        self._closed_stream = closed_stream

    async def publish_opened(self, trade: TradeMessage) -> str:
        """Publish trade opened event.

        Args:
            trade: Trade message to publish

        Returns:
            Message ID from Redis
        """
        message_id = await self._publisher.publish(self._opened_stream, trade)

        logger.info(
            f"Published trade opened: {trade.direction} {trade.quantity} @ {trade.entry_price:.2f} "
            f"(trade_id={trade.id}, signal_id={trade.signal_id})"
        )

        return message_id

    async def publish_closed(self, trade: TradeMessage) -> str:
        """Publish trade closed event.

        Args:
            trade: Trade message to publish

        Returns:
            Message ID from Redis
        """
        message_id = await self._publisher.publish(self._closed_stream, trade)

        pnl_str = (
            f"{trade.pnl_points:.2f} points" if trade.pnl_points is not None else "N/A"
        )

        logger.info(
            f"Published trade closed: {trade.direction} exit @ {trade.exit_price:.2f} "
            f"(pnl={pnl_str}, reason={trade.exit_reason}, trade_id={trade.id})"
        )

        return message_id
