"""Redis Streams pub/sub utilities."""

import json
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

import redis.asyncio as redis
from pydantic import BaseModel

from scp_shared.messaging.retry import RetryConfig, with_retry

T = TypeVar("T", bound=BaseModel)


class RedisStreamPublisher:
    """Publish Pydantic models to Redis Streams.
    
    Example:
        >>> publisher = RedisStreamPublisher(redis_client)
        >>> message = CandleMessage(...)
        >>> msg_id = await publisher.publish("candles.1m.gc", message)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        retry_config: RetryConfig | None = None,
    ) -> None:
        """Initialize publisher.
        
        Args:
            redis_client: Async Redis client instance
            retry_config: Retry configuration (uses defaults if None)
        """
        self.redis = redis_client
        self.retry_config = retry_config or RetryConfig()

    async def publish(self, stream: str, message: BaseModel) -> str:
        """Publish message to stream with automatic retry.

        Args:
            stream: Stream name (e.g., "candles.1m.gc")
            message: Pydantic model to publish

        Returns:
            Message ID from Redis (e.g., "1234567890-0")
        """
        @with_retry(self.retry_config)
        async def _publish() -> str:
            data = {
                "type": message.__class__.__name__,
                "payload": message.model_dump_json(),
                "published_at": datetime.now(UTC).isoformat(),
            }

            message_id = await self.redis.xadd(stream, data)
            return message_id.decode() if isinstance(message_id, bytes) else message_id

        return await _publish()


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
        retry_config: RetryConfig | None = None,
    ) -> None:
        """Initialize consumer.
        
        Args:
            redis_client: Async Redis client instance
            stream: Stream name to consume from
            group: Consumer group name
            consumer_name: Unique name for this consumer instance
            message_type: Pydantic model class to deserialize into
            retry_config: Retry configuration for Redis operations
                (uses defaults if None)
        
        Note:
            Messages are NOT automatically moved to DLQ. Application code must
            call move_to_dlq() explicitly when a message fails processing.
        """
        self.redis = redis_client
        self.stream = stream
        self.group = group
        self.consumer_name = consumer_name
        self.message_type = message_type
        self.retry_config = retry_config or RetryConfig()
        self._initialized = False
        self._dlq_stream = f"{stream}.dlq"

    async def ensure_group(self) -> None:
        """Create consumer group if it doesn't exist.
        
        This is idempotent - safe to call multiple times.
        """
        if self._initialized:
            return

        @with_retry(self.retry_config)
        async def _ensure_group() -> None:
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

        await _ensure_group()
        self._initialized = True

    async def read(
        self,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[T]:
        """Read and deserialize messages from stream with automatic retry.

        Args:
            count: Maximum messages to read per call
            block_ms: Block timeout in milliseconds (0 = no blocking)

        Returns:
            List of deserialized Pydantic models
        
        Note:
            Only the xreadgroup operation is retried. Acknowledgments are NOT retried
            to prevent data loss. If acknowledgment fails, the message remains in the
            pending list and can be recovered via read_pending().
        """
        await self.ensure_group()

        # Only retry the read operation, not the entire read+ack loop
        @with_retry(self.retry_config)
        async def _read() -> list[tuple[Any, dict[bytes, bytes]]]:
            try:
                results = await self.redis.xreadgroup(
                    groupname=self.group,
                    consumername=self.consumer_name,
                    streams={self.stream: ">"},
                    count=count,
                    block=block_ms,
                )
                # Flatten results to list of (message_id, data) tuples
                flat_messages = []
                for _stream_name, stream_messages in results:
                    flat_messages.extend(stream_messages)
                return flat_messages
            except redis.ResponseError as e:
                # If consumer group was deleted (e.g., by test cleanup), recreate it
                if "NOGROUP" in str(e):
                    self._initialized = False  # Force recreation
                    await self.ensure_group()
                    # Retry the read after recreating group
                    results = await self.redis.xreadgroup(
                        groupname=self.group,
                        consumername=self.consumer_name,
                        streams={self.stream: ">"},
                        count=count,
                        block=block_ms,
                    )
                    flat_messages = []
                    for _stream_name, stream_messages in results:
                        flat_messages.extend(stream_messages)
                    return flat_messages
                raise

        # Retry only the read operation
        raw_messages = await _read()

        # Process and acknowledge messages WITHOUT retry wrapper
        # If acknowledgment fails, message stays in pending list for recovery
        messages: list[T] = []
        for message_id, data in raw_messages:
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

            # Acknowledge message (no retry - if this fails, message stays pending)
            await self.redis.xack(self.stream, self.group, message_id)

        return messages

    async def read_pending(self, count: int = 10) -> list[T]:
        """Read pending (unacknowledged) messages with automatic retry.
        
        Useful for recovery after crashes.
        
        Args:
            count: Maximum messages to read
            
        Returns:
            List of deserialized Pydantic models
        
        Note:
            Only the xreadgroup operation is retried. Acknowledgments are NOT retried
            to prevent data loss. If acknowledgment fails, the message remains in the
            pending list and will be returned on the next read_pending() call.
        """
        await self.ensure_group()

        # Only retry the read operation, not the entire read+ack loop
        @with_retry(self.retry_config)
        async def _read() -> list[tuple[Any, dict[bytes, bytes]]]:
            # Get pending messages for this specific consumer
            results = await self.redis.xreadgroup(
                groupname=self.group,
                consumername=self.consumer_name,
                streams={self.stream: "0"},  # "0" means pending messages
                count=count,
            )
            # Flatten results to list of (message_id, data) tuples
            flat_messages = []
            for _stream_name, stream_messages in results:
                flat_messages.extend(stream_messages)
            return flat_messages

        # Retry only the read operation
        raw_messages = await _read()

        # Process and acknowledge messages WITHOUT retry wrapper
        messages: list[T] = []
        for message_id, data in raw_messages:
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

            # Re-acknowledge (no retry - if this fails, message stays pending)
            await self.redis.xack(self.stream, self.group, message_id)

        return messages

    async def move_to_dlq(
        self,
        message: T,
        failure_reason: str,
    ) -> str:
        """Move a failed message to the dead-letter queue with automatic retry.
        
        This is a MANUAL operation - application code must call this method
        when a message fails processing. Messages are NOT automatically moved
        to DLQ; the application is responsible for tracking failure counts
        and deciding when to call this method.
        
        Args:
            message: The Pydantic model that failed processing
            failure_reason: Reason for failure (for debugging)
            
        Returns:
            Message ID in the DLQ stream
        """
        @with_retry(self.retry_config)
        async def _move_to_dlq() -> str:
            dlq_data = {
                "type": message.__class__.__name__,
                "payload": message.model_dump_json(),
                "failure_reason": failure_reason,
                "original_stream": self.stream,
                "consumer_group": self.group,
                "consumer_name": self.consumer_name,
                "moved_at": datetime.now(UTC).isoformat(),
            }

            message_id = await self.redis.xadd(self._dlq_stream, dlq_data)
            return message_id.decode() if isinstance(message_id, bytes) else message_id

        return await _move_to_dlq()

    async def read_from_dlq(self, count: int = 10) -> list[T]:
        """Read messages from the dead-letter queue with automatic retry.
        
        Useful for investigating failures and manual reprocessing.
        
        Args:
            count: Maximum messages to read
            
        Returns:
            List of deserialized Pydantic models
        """
        @with_retry(self.retry_config)
        async def _read_from_dlq() -> list[T]:
            # Read from DLQ stream
            results = await self.redis.xrange(
                self._dlq_stream,
                b"-",
                b"+",
                count=count,
            )

            messages: list[T] = []
            for _message_id, data in results:
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

            return messages

        return await _read_from_dlq()

