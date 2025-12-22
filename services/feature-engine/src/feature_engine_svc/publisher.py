"""Feature Publisher - publishes features to Redis streams."""

import redis.asyncio as redis
from scp_shared.messaging import RedisStreamPublisher
from scp_shared.messaging.schemas import FeaturesMessage


class FeaturePublisher:
    """Publishes FeaturesMessage to Redis streams.
    
    Wraps RedisStreamPublisher with feature-specific logic.
    """
    
    def __init__(self, redis_client: redis.Redis):
        """Initialize feature publisher.
        
        Args:
            redis_client: Redis client instance
        """
        self.publisher = RedisStreamPublisher(redis_client)
    
    async def publish(self, features: FeaturesMessage) -> str:
        """Publish features to appropriate stream.
        
        Args:
            features: Features message to publish
            
        Returns:
            Message ID from Redis
        """
        # Determine stream name based on timeframe
        stream = f"features.{features.timeframe}"
        
        return await self.publisher.publish(stream, features)

