"""Redis Streams pub/sub utilities."""

import json
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

import redis.asyncio as redis
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class RedisStreamPublisher:
    """Publish Pydantic models to Redis Streams.
    
    Example:
        >>> publisher = RedisStreamPublisher(redis_client)
        >>> message = CandleMessage(...)
        >>> msg_id = await publisher.publish("candles.1m.gc", message)
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        """Initialize publisher.
        
        Args:
            redis_client: Async Redis client instance
        """
        self.redis = redis_client

    async def publish(self, stream: str, message: BaseModel) -> str:
        """Publish message to stream.

        Args:
            stream: Stream name (e.g., "candles.1m.gc")
            message: Pydantic model to publish

        Returns:
            Message ID from Redis (e.g., "1234567890-0")
        """
        data = {
            "type": message.__class__.__name__,
            "payload": message.model_dump_json(),
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

        message_id = await self.redis.xadd(stream, data)
        return message_id.decode() if isinstance(message_id, bytes) else message_id


class RedisStreamConsumer(Generic[T]):
    """Consume and deserialize messages from Redis Streams.
    
    Uses consumer groups for reliable delivery and horizontal scaling.
    
    Example:
        >>> consumer = RedisStreamConsumer(
        ...     redis_client,
        ...     stream="candles.1m.gc",
        ...     group="feature-engine",
        ...     consumer_name="instance-1",
        ...     message_type=CandleMessage,
        ... )
        >>> messages = await consumer.read(count=10)
        >>> for msg in messages:
        ...     print(msg.close)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        stream: str,
        group: str,
        consumer_name: str,
        message_type: type[T],
    ) -> None:
        """Initialize consumer.
        
        Args:
            redis_client: Async Redis client instance
            stream: Stream name to consume from
            group: Consumer group name
            consumer_name: Unique name for this consumer instance
            message_type: Pydantic model class to deserialize into
        """
        self.redis = redis_client
        self.stream = stream
        self.group = group
        self.consumer_name = consumer_name
        self.message_type = message_type
        self._initialized = False

    async def ensure_group(self) -> None:
        """Create consumer group if it doesn't exist.
        
        This is idempotent - safe to call multiple times.
        """
        if self._initialized:
            return

        try:
            await self.redis.xgroup_create(
                self.stream,
                self.group,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as e:
            # Group already exists
            if "BUSYGROUP" not in str(e):
                raise

        self._initialized = True

    async def read(
        self,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[T]:
        """Read and deserialize messages from stream.

        Args:
            count: Maximum messages to read per call
            block_ms: Block timeout in milliseconds (0 = no blocking)

        Returns:
            List of deserialized Pydantic models
        """
        await self.ensure_group()

        results = await self.redis.xreadgroup(
            groupname=self.group,
            consumername=self.consumer_name,
            streams={self.stream: ">"},
            count=count,
            block=block_ms,
        )

        messages: list[T] = []
        for stream_name, stream_messages in results:
            for message_id, data in stream_messages:
                # Decode bytes to strings
                decoded_data: dict[str, Any] = {
                    k.decode() if isinstance(k, bytes) else k: v.decode()
                    if isinstance(v, bytes)
                    else v
                    for k, v in data.items()
                }

                # Deserialize payload
                payload = json.loads(decoded_data["payload"])
                model = self.message_type.model_validate(payload)
                messages.append(model)

                # Acknowledge message
                await self.redis.xack(self.stream, self.group, message_id)

        return messages

    async def read_pending(self, count: int = 10) -> list[T]:
        """Read pending (unacknowledged) messages for this consumer.
        
        Useful for recovery after crashes.
        
        Args:
            count: Maximum messages to read
            
        Returns:
            List of deserialized Pydantic models
        """
        await self.ensure_group()

        # Get pending messages for this specific consumer
        results = await self.redis.xreadgroup(
            groupname=self.group,
            consumername=self.consumer_name,
            streams={self.stream: "0"},  # "0" means pending messages
            count=count,
        )

        messages: list[T] = []
        for stream_name, stream_messages in results:
            for message_id, data in stream_messages:
                # Decode and deserialize (same as read())
                decoded_data: dict[str, Any] = {
                    k.decode() if isinstance(k, bytes) else k: v.decode()
                    if isinstance(v, bytes)
                    else v
                    for k, v in data.items()
                }

                payload = json.loads(decoded_data["payload"])
                model = self.message_type.model_validate(payload)
                messages.append(model)

                # Re-acknowledge
                await self.redis.xack(self.stream, self.group, message_id)

        return messages

