"""HTF Bias Publisher - publishes bias to Redis streams."""

import redis.asyncio as redis
from scp_shared.messaging import RedisStreamPublisher
from scp_shared.messaging.schemas import HTFBiasMessage


class BiasPublisher:
    """Publishes HTFBiasMessage to Redis streams.
    
    Wraps RedisStreamPublisher with bias-specific logic.
    """
    
    def __init__(self, redis_client: redis.Redis):
        """Initialize bias publisher.
        
        Args:
            redis_client: Redis client instance
        """
        self.publisher = RedisStreamPublisher(redis_client)
    
    async def publish(self, bias: HTFBiasMessage) -> str:
        """Publish bias to htf.bias stream.
        
        Args:
            bias: Bias message to publish
            
        Returns:
            Message ID from Redis
        """
        return await self.publisher.publish("htf.bias", bias)



