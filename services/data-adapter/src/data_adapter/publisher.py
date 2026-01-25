"""Candle Publisher - publishes candles to Redis Streams.

This module wraps the shared RedisStreamPublisher for publishing
CandleMessage objects to Redis Streams.
"""

import redis.asyncio as redis
from scp_shared.messaging import RedisStreamPublisher
from scp_shared.messaging.schemas import CandleMessage


class CandlePublisher:
    """Publishes candles to Redis Streams.

    Wraps RedisStreamPublisher and provides a simple interface for
    publishing CandleMessage objects to the appropriate streams.
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        """Initialize candle publisher.

        Args:
            redis_client: Redis client instance
        """
        self.publisher = RedisStreamPublisher(redis_client)

    async def publish(self, candle: CandleMessage) -> str:
        """Publish candle to appropriate stream.

        Stream naming convention: candles.{timeframe}.{symbol_lower}
        Example: candles.1m.gc, candles.1m.dxy

        Args:
            candle: CandleMessage to publish

        Returns:
            Message ID from Redis
        """
        stream_name = f"candles.{candle.timeframe}.{candle.symbol.lower()}"
        message_id = await self.publisher.publish(stream_name, candle)
        return message_id
