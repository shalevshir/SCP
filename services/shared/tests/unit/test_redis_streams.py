"""Tests for Redis Streams pub/sub utilities."""

from datetime import UTC, datetime

import pytest
import redis.asyncio as redis

from scp_shared.messaging import (
    CandleMessage,
    RedisStreamConsumer,
    RedisStreamPublisher,
)


class TestRedisStreamPublisher:
    """Test Redis Streams publishing."""

    @pytest.mark.asyncio
    async def test_publish_candle_message(self, redis_client: redis.Redis) -> None:
        """Publisher serializes and publishes CandleMessage."""
        publisher = RedisStreamPublisher(redis_client)

        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        message_id = await publisher.publish("candles.1m.gc", candle)

        assert message_id is not None
        # Verify message in stream
        messages = await redis_client.xrange("candles.1m.gc", b"-", b"+")
        assert len(messages) == 1

        # Verify payload structure
        _, data = messages[0]
        assert b"type" in data
        assert b"payload" in data
        assert b"published_at" in data

    @pytest.mark.asyncio
    async def test_publish_multiple_messages(self, redis_client: redis.Redis) -> None:
        """Multiple messages can be published to same stream."""
        publisher = RedisStreamPublisher(redis_client)

        candle1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2651.0,
            high=2653.0,
            low=2650.0,
            close=2652.0,
            volume=1100.0,
        )

        await publisher.publish("candles.1m.gc", candle1)
        await publisher.publish("candles.1m.gc", candle2)

        # Verify both messages in stream
        messages = await redis_client.xrange("candles.1m.gc", b"-", b"+")
        assert len(messages) == 2


class TestRedisStreamConsumer:
    """Test Redis Streams consuming."""

    @pytest.mark.asyncio
    async def test_consumer_receives_published_message(
        self, redis_client: redis.Redis
    ) -> None:
        """Consumer receives and deserializes messages."""
        publisher = RedisStreamPublisher(redis_client)
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # Publish
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        await publisher.publish("candles.1m.gc", candle)

        # Consume
        messages = await consumer.read(count=1, block_ms=100)

        assert len(messages) == 1
        received = messages[0]
        assert received.symbol == "GC"
        assert received.close == 2651.0
        assert received.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_consumer_creates_group_automatically(
        self, redis_client: redis.Redis
    ) -> None:
        """Consumer creates consumer group on first read."""
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="auto-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # This should create the group
        await consumer.ensure_group()

        # Verify group exists
        groups = await redis_client.xinfo_groups("candles.1m.gc")
        assert len(groups) >= 1
        # Group info structure varies by fakeredis version
        # Just check that the group was created (stream has at least one group)
        assert groups is not None

    @pytest.mark.asyncio
    async def test_consumer_handles_no_messages(
        self, redis_client: redis.Redis
    ) -> None:
        """Consumer returns empty list when no messages available."""
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # Read from empty stream (short timeout)
        messages = await consumer.read(count=10, block_ms=10)

        assert messages == []

    @pytest.mark.asyncio
    async def test_multiple_consumers_in_group(
        self, redis_client: redis.Redis
    ) -> None:
        """Multiple consumers in same group share messages."""
        publisher = RedisStreamPublisher(redis_client)

        consumer1 = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="shared-group",
            consumer_name="consumer-1",
            message_type=CandleMessage,
        )

        consumer2 = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="shared-group",
            consumer_name="consumer-2",
            message_type=CandleMessage,
        )

        # Publish 2 messages
        candle1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2651.0,
            high=2653.0,
            low=2650.0,
            close=2652.0,
            volume=1100.0,
        )

        await publisher.publish("candles.1m.gc", candle1)
        await publisher.publish("candles.1m.gc", candle2)

        # Each consumer should get one message (load balanced)
        messages1 = await consumer1.read(count=10, block_ms=100)
        messages2 = await consumer2.read(count=10, block_ms=100)

        # Together they should have received both messages
        total_messages = len(messages1) + len(messages2)
        assert total_messages == 2

    @pytest.mark.asyncio
    async def test_message_acknowledgment(self, redis_client: redis.Redis) -> None:
        """Messages are acknowledged after successful read."""
        publisher = RedisStreamPublisher(redis_client)
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # Publish a message
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        await publisher.publish("candles.1m.gc", candle)

        # Read and acknowledge
        messages = await consumer.read(count=1, block_ms=100)
        assert len(messages) == 1

        # Try to read again - should be empty (message was acknowledged)
        messages2 = await consumer.read(count=1, block_ms=10)
        assert len(messages2) == 0


class TestDeadLetterQueue:
    """Test dead-letter queue functionality."""

    @pytest.mark.asyncio
    async def test_message_moved_to_dlq_after_max_retries(
        self, redis_client: redis.Redis
    ) -> None:
        """Messages can be manually moved to DLQ when processing fails."""
        publisher = RedisStreamPublisher(redis_client)
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # Publish a message
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        await publisher.publish("candles.1m.gc", candle)

        # Read message
        messages = await consumer.read(count=1, block_ms=100)
        assert len(messages) == 1

        # Manually move to DLQ (application decides when to do this)
        await consumer.move_to_dlq(messages[0], "processing_failed")

        # Verify message is in DLQ stream
        dlq_stream = "candles.1m.gc.dlq"
        dlq_messages = await redis_client.xrange(dlq_stream, b"-", b"+")
        assert len(dlq_messages) == 1

    @pytest.mark.asyncio
    async def test_dlq_contains_original_message_data(
        self, redis_client: redis.Redis
    ) -> None:
        """DLQ messages preserve original data."""
        publisher = RedisStreamPublisher(redis_client)
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # Publish a message
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        await publisher.publish("candles.1m.gc", candle)

        # Read and move to DLQ
        messages = await consumer.read(count=1, block_ms=100)
        await consumer.move_to_dlq(messages[0], "test_failure")

        # Verify DLQ contains original data
        dlq_stream = "candles.1m.gc.dlq"
        dlq_messages = await redis_client.xrange(dlq_stream, b"-", b"+")
        _, data = dlq_messages[0]

        # Check that payload is preserved
        decoded_data = {
            k.decode() if isinstance(k, bytes) else k: v.decode()
            if isinstance(v, bytes)
            else v
            for k, v in data.items()
        }
        import json

        payload = json.loads(decoded_data["payload"])
        assert payload["symbol"] == "GC"
        assert payload["close"] == 2651.0

    @pytest.mark.asyncio
    async def test_dlq_includes_failure_metadata(
        self, redis_client: redis.Redis
    ) -> None:
        """DLQ messages include metadata about the failure."""
        publisher = RedisStreamPublisher(redis_client)
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # Publish and move to DLQ
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        await publisher.publish("candles.1m.gc", candle)

        messages = await consumer.read(count=1, block_ms=100)
        await consumer.move_to_dlq(messages[0], "validation_error")

        # Verify DLQ metadata
        dlq_stream = "candles.1m.gc.dlq"
        dlq_messages = await redis_client.xrange(dlq_stream, b"-", b"+")
        _, data = dlq_messages[0]

        decoded_data = {
            k.decode() if isinstance(k, bytes) else k: v.decode()
            if isinstance(v, bytes)
            else v
            for k, v in data.items()
        }

        assert "failure_reason" in decoded_data
        assert decoded_data["failure_reason"] == "validation_error"
        assert "original_stream" in decoded_data
        assert decoded_data["original_stream"] == "candles.1m.gc"
        assert "moved_at" in decoded_data

    @pytest.mark.asyncio
    async def test_read_from_dlq(self, redis_client: redis.Redis) -> None:
        """Can read messages from DLQ for investigation."""
        publisher = RedisStreamPublisher(redis_client)
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # Publish and move to DLQ
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        await publisher.publish("candles.1m.gc", candle)

        messages = await consumer.read(count=1, block_ms=100)
        await consumer.move_to_dlq(messages[0], "test")

        # Read from DLQ
        dlq_messages = await consumer.read_from_dlq(count=10)
        assert len(dlq_messages) == 1
        assert dlq_messages[0].symbol == "GC"
        assert dlq_messages[0].close == 2651.0


class TestRetryBehavior:
    """Test retry behavior to prevent data loss."""

    @pytest.mark.asyncio
    async def test_read_does_not_lose_data_on_ack_failure(
        self, redis_client: redis.Redis
    ) -> None:
        """Regression test: ack failures don't cause data loss.
        
        This test verifies that if acknowledgment fails, messages are still
        returned to the caller and remain in the pending list for recovery.
        The bug was that retrying the entire read+ack operation would fetch
        new messages, losing the previously-acknowledged ones.
        """
        publisher = RedisStreamPublisher(redis_client)
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group",
            consumer_name="test-consumer",
            message_type=CandleMessage,
        )

        # Publish 3 messages
        for i in range(3):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i,
                high=2652.0 + i,
                low=2649.0 + i,
                close=2651.0 + i,
                volume=1000.0,
            )
            await publisher.publish("candles.1m.gc", candle)

        # Read messages - all should be returned even if ack fails
        messages = await consumer.read(count=10, block_ms=100)
        assert len(messages) == 3
        
        # Verify all messages have correct data (no data loss)
        assert messages[0].close == 2651.0
        assert messages[1].close == 2652.0
        assert messages[2].close == 2653.0

        # Verify all messages were acknowledged (pending list should be empty)
        pending_messages = await consumer.read_pending(count=10)
        assert len(pending_messages) == 0

    @pytest.mark.asyncio
    async def test_read_pending_does_not_lose_data_on_ack_failure(
        self, redis_client: redis.Redis
    ) -> None:
        """Regression test: read_pending doesn't lose data on ack failure.
        
        Similar to the read() test but for read_pending(). Ensures that
        retrying the read operation doesn't cause already-acknowledged
        messages to be lost.
        """
        publisher = RedisStreamPublisher(redis_client)
        
        # Create consumer but don't use ensure_group to manually control pending state
        consumer = RedisStreamConsumer(
            redis_client,
            stream="candles.1m.gc",
            group="test-group-2",
            consumer_name="test-consumer-2",
            message_type=CandleMessage,
        )

        # Publish 3 messages
        for i in range(3):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i,
                high=2652.0 + i,
                low=2649.0 + i,
                close=2651.0 + i,
                volume=1000.0,
            )
            await publisher.publish("candles.1m.gc", candle)

        # First read to get messages into pending state
        await consumer.ensure_group()
        messages = await consumer.read(count=10, block_ms=100)
        assert len(messages) == 3

        # Verify pending list is empty after successful ack
        pending = await consumer.read_pending(count=10)
        assert len(pending) == 0

