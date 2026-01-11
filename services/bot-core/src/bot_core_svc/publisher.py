"""Signal publisher for Bot Core service."""

import redis.asyncio as redis
from scp_shared.common.logger import get_logger
from scp_shared.messaging import RedisStreamPublisher
from scp_shared.messaging.schemas import SignalMessage

logger = get_logger(__name__)


class SignalPublisher:
    """Publish signals to Redis stream.
    
    Publishes SignalMessage objects to the signals.pending stream for
    consumption by the Execution service.
    
    Args:
        redis_client: Redis client for publishing
        stream: Stream name (default: "signals.pending")
    
    Example:
        >>> publisher = SignalPublisher(redis_client)
        >>> await publisher.publish(signal_message)
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        stream: str = "signals.pending",
    ) -> None:
        """Initialize signal publisher.
        
        Args:
            redis_client: Redis client
            stream: Stream name (default: "signals.pending")
        """
        self._publisher = RedisStreamPublisher(redis_client)
        self._stream = stream
    
    async def publish(self, signal: SignalMessage) -> str:
        """Publish signal to stream.
        
        Args:
            signal: Signal message to publish
            
        Returns:
            Message ID from Redis
        """
        message_id = await self._publisher.publish(self._stream, signal)
        
        logger.info(
            f"Published signal: {signal.direction} {signal.setup_type} "
            f"(score: {signal.score:.1f}, confidence: {signal.confidence}, "
            f"timestamp: {signal.timestamp})"
        )
        
        return message_id
