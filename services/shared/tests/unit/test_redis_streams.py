"""Tests for Redis Streams pub/sub utilities."""

from datetime import datetime, timezone

import pytest
import redis.asyncio as redis

from scp_shared.messaging import CandleMessage, RedisStreamConsumer, RedisStreamPublisher


class TestRedisStreamPublisher:
    """Test Redis Streams publishing."""

    @pytest.mark.asyncio
    async def test_publish_candle_message(self, redis_client: redis.Redis) -> None:
        """Publisher serializes and publishes CandleMessage."""
        publisher = RedisStreamPublisher(redis_client)

        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
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
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
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
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
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
        assert received.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)

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
        assert len(groups) == 1
        # Group name is bytes in fakeredis
        group_names = [g[b"name"] if isinstance(g, dict) else g for g in groups]
        assert any(b"auto-group" in str(name) for name in group_names)

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
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
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
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
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

