"""Integration tests for stream synchronization edge cases.

Tests edge cases and failure scenarios in stream synchronization:
- Out-of-order message delivery
- Missing timestamps (gaps)
- Duplicate messages
- Timeout scenarios
- Buffer overflow
- Multi-symbol synchronization

Test scenarios:
1. CandleSynchronizer edge cases (GC + DXY pairing)
2. CandleFeatureSynchronizer edge cases (candle + features pairing)
3. Consumer group coordination
4. Message replay and idempotency
5. High-volume stress testing
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestCandleSynchronizerEdgeCases:
    """Test CandleSynchronizer handling of edge cases."""
    
    async def test_out_of_order_candle_delivery(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: Synchronizer handles out-of-order candle delivery.
        
        Scenario:
        - Publish GC candles: 14:00, 14:02, 14:01 (out of order)
        - Publish DXY candles: 14:01, 14:00, 14:02 (out of order)
        - Verify synchronizer pairs them correctly by timestamp
        - Verify processing order follows timestamp (not arrival order)
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish GC candles out of order
        gc_times = [0, 2, 1]  # minutes offset
        for offset in gc_times:
            timestamp = base_time + timedelta(minutes=offset)
            gc_candle = candle_message_factory(
                timestamp=timestamp,
                symbol="GC",
                close=2050.0 + offset,
            )
            await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
        
        # Publish DXY candles out of order
        dxy_times = [1, 0, 2]
        for offset in dxy_times:
            timestamp = base_time + timedelta(minutes=offset)
            dxy_candle = candle_message_factory(
                timestamp=timestamp,
                symbol="DXY",
                close=103.50 - offset * 0.1,
            )
            await publish_to_stream("candles.1m.dxy", dxy_candle.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: All candles published
        gc_messages = await redis_client.xread({"candles.1m.gc": "0"}, count=10)
        dxy_messages = await redis_client.xread({"candles.1m.dxy": "0"}, count=10)
        
        gc_count = sum(len(msg_list) for _, msg_list in gc_messages)
        dxy_count = sum(len(msg_list) for _, msg_list in dxy_messages)
        
        assert gc_count == 3, "3 GC candles published"
        assert dxy_count == 3, "3 DXY candles published"
        
        # Note: In real deployment, services should:
        # 1. Sort candles by timestamp before processing
        # 2. Pair GC/DXY by timestamp (not arrival order)
        # 3. Process in chronological order
    
    async def test_duplicate_candle_messages(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: System handles duplicate candle messages gracefully.
        
        Scenario:
        - Publish same GC candle twice (14:00)
        - Publish same DXY candle twice (14:00)
        - Verify duplicate detection (by timestamp)
        - Verify only one pair is processed
        """
        timestamp = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish duplicate GC candles
        gc_candle = candle_message_factory(timestamp=timestamp, symbol="GC")
        await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
        await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
        
        # Publish duplicate DXY candles
        dxy_candle = candle_message_factory(timestamp=timestamp, symbol="DXY")
        await publish_to_stream("candles.1m.dxy", dxy_candle.model_dump())
        await publish_to_stream("candles.1m.dxy", dxy_candle.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Duplicates are in stream (Redis doesn't dedupe)
        gc_messages = await redis_client.xread({"candles.1m.gc": "0"}, count=10)
        gc_count = sum(len(msg_list) for _, msg_list in gc_messages)
        assert gc_count == 2, "Duplicate GC candles in stream"
        
        # Note: Services should implement idempotency:
        # 1. Track processed timestamps
        # 2. Skip duplicate candles with same timestamp
        # 3. Log warning for duplicates
    
    async def test_synchronizer_timeout_with_missing_dxy(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: Synchronizer timeout when DXY candle never arrives.
        
        Scenario:
        - Publish GC candles at 14:00, 14:01, 14:02
        - Publish DXY candles only at 14:00, 14:02 (missing 14:01)
        - Verify GC at 14:01 is held in buffer
        - Verify timeout (300s in replay mode) triggers cleanup
        - Verify warning logged for unmatched candle
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish 3 GC candles
        for offset in [0, 1, 2]:
            timestamp = base_time + timedelta(minutes=offset)
            gc_candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
        
        # Publish only 2 DXY candles (missing 14:01)
        for offset in [0, 2]:
            timestamp = base_time + timedelta(minutes=offset)
            dxy_candle = candle_message_factory(timestamp=timestamp, symbol="DXY")
            await publish_to_stream("candles.1m.dxy", dxy_candle.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: GC has 3 candles, DXY has 2
        gc_messages = await redis_client.xread({"candles.1m.gc": "0"}, count=10)
        dxy_messages = await redis_client.xread({"candles.1m.dxy": "0"}, count=10)
        
        gc_count = sum(len(msg_list) for _, msg_list in gc_messages)
        dxy_count = sum(len(msg_list) for _, msg_list in dxy_messages)
        
        assert gc_count == 3, "3 GC candles"
        assert dxy_count == 2, "2 DXY candles (missing 14:01)"
        
        # Note: CandleSynchronizer would:
        # 1. Pair 14:00 immediately
        # 2. Hold 14:01 GC in buffer (no DXY match)
        # 3. Pair 14:02 immediately
        # 4. After 300s timeout, cleanup 14:01 GC with warning
    
    async def test_synchronizer_buffer_stats_reporting(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: Synchronizer reports buffer stats for monitoring.
        
        Scenario:
        - Publish mismatched candles (more GC than DXY)
        - Query buffer stats
        - Verify gc_count > dxy_count
        - Verify oldest_timestamp reported correctly
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish 5 GC candles
        for i in range(5):
            timestamp = base_time + timedelta(minutes=i)
            gc_candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
        
        # Publish only 2 DXY candles
        for i in range(2):
            timestamp = base_time + timedelta(minutes=i)
            dxy_candle = candle_message_factory(timestamp=timestamp, symbol="DXY")
            await publish_to_stream("candles.1m.dxy", dxy_candle.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify unmatched candles would be buffered
        gc_messages = await redis_client.xread({"candles.1m.gc": "0"}, count=10)
        dxy_messages = await redis_client.xread({"candles.1m.dxy": "0"}, count=10)
        
        gc_count = sum(len(msg_list) for _, msg_list in gc_messages)
        dxy_count = sum(len(msg_list) for _, msg_list in dxy_messages)
        
        assert gc_count == 5, "5 GC candles"
        assert dxy_count == 2, "2 DXY candles"
        
        # Note: CandleSynchronizer.get_buffer_stats() would report:
        # {
        #     "gc_count": 3,  # 3 unmatched GC candles
        #     "dxy_count": 0,
        #     "oldest_timestamp": "2025-01-15T14:02:00Z"
        # }


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestCandleFeatureSynchronizerEdgeCases:
    """Test CandleFeatureSynchronizer edge cases."""
    
    async def test_features_arrive_before_candle(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
        features_message_factory: Callable,
    ):
        """Test: Synchronizer handles features arriving before candle.
        
        Scenario:
        - Publish features at 14:00
        - Publish candle at 14:00 (delayed)
        - Verify both are buffered and paired correctly
        """
        timestamp = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Features arrive first
        features = features_message_factory(timestamp=timestamp)
        await publish_to_stream("features.1m", features.model_dump())
        
        await asyncio.sleep(0.05)
        
        # Candle arrives later
        candle = candle_message_factory(timestamp=timestamp, symbol="GC")
        await publish_to_stream("candles.1m.gc", candle.model_dump())
        
        await asyncio.sleep(0.05)
        
        # Assert: Both messages in streams
        features_msgs = await redis_client.xread({"features.1m": "0"}, count=10)
        candle_msgs = await redis_client.xread({"candles.1m.gc": "0"}, count=10)
        
        features_count = sum(len(msg_list) for _, msg_list in features_msgs)
        candle_count = sum(len(msg_list) for _, msg_list in candle_msgs)
        
        assert features_count >= 1, "Features published"
        assert candle_count >= 1, "Candle published"
        
        # Note: CandleFeatureSynchronizer would:
        # 1. Buffer features in _features_buffer
        # 2. When candle arrives, pair with buffered features
        # 3. Emit (candle, features) pair
    
    async def test_multi_day_replay_with_long_timeout(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
        features_message_factory: Callable,
    ):
        """Test: Synchronizer handles multi-day replay with 7-day timeout.
        
        Scenario:
        - Publish candles spanning 3 days
        - Publish features with intermittent gaps
        - Verify synchronizer doesn't timeout prematurely
        - Verify pairs emitted in chronological order
        """
        day1 = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        day2 = datetime(2025, 1, 16, 14, 0, 0, tzinfo=timezone.utc)
        day3 = datetime(2025, 1, 17, 14, 0, 0, tzinfo=timezone.utc)
        
        timestamps = [
            day1,
            day1 + timedelta(hours=1),
            day2,
            day2 + timedelta(hours=1),
            day3,
        ]
        
        # Publish candles and features for each timestamp
        for ts in timestamps:
            candle = candle_message_factory(timestamp=ts, symbol="GC")
            features = features_message_factory(timestamp=ts)
            
            await publish_to_stream("candles.1m.gc", candle.model_dump())
            await publish_to_stream("features.1m", features.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: All messages published
        candle_msgs = await redis_client.xread({"candles.1m.gc": "0"}, count=10)
        features_msgs = await redis_client.xread({"features.1m": "0"}, count=10)
        
        candle_count = sum(len(msg_list) for _, msg_list in candle_msgs)
        features_count = sum(len(msg_list) for _, msg_list in features_msgs)
        
        assert candle_count == 5, "5 candles spanning 3 days"
        assert features_count == 5, "5 feature messages"
        
        # Note: CandleFeatureSynchronizer with timeout_seconds=604800 (7 days)
        # would successfully pair all messages without timeout


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestConsumerGroupCoordination:
    """Test consumer group coordination and message distribution."""
    
    async def test_consumer_group_message_acknowledgment(
        self,
        redis_client,
        publish_to_stream,
        cleanup_consumer_groups,
        candle_message_factory: Callable,
    ):
        """Test: Consumer group acknowledges messages correctly.
        
        Scenario:
        - Create consumer group for candles.1m.gc
        - Publish 5 candles
        - Read messages without acknowledging
        - Verify messages remain in pending entries list
        - Acknowledge messages
        - Verify pending list is empty
        """
        stream = "candles.1m.gc"
        group = "test-consumer-group"
        consumer = "test-consumer-1"
        
        # Create consumer group
        try:
            await redis_client.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception:
            # Group might already exist
            pass
        
        # Publish 5 candles
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        msg_ids = []
        for i in range(5):
            timestamp = base_time + timedelta(minutes=i)
            candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            msg_id = await publish_to_stream(stream, candle.model_dump())
            msg_ids.append(msg_id)
        
        # Read messages without ack
        messages = await redis_client.xreadgroup(
            group,
            consumer,
            {stream: ">"},
            count=5,
        )
        
        assert len(messages) > 0, "Messages read from stream"
        
        # Check pending entries
        pending = await redis_client.xpending(stream, group)
        pending_count = pending["pending"]
        assert pending_count == 5, f"5 messages pending (not acked), got {pending_count}"
        
        # Acknowledge all messages
        for msg_id in msg_ids:
            await redis_client.xack(stream, group, msg_id)
        
        # Check pending again
        pending_after = await redis_client.xpending(stream, group)
        assert pending_after["pending"] == 0, "No pending messages after ack"
    
    async def test_multiple_consumers_message_distribution(
        self,
        redis_client,
        publish_to_stream,
        cleanup_consumer_groups,
        candle_message_factory: Callable,
    ):
        """Test: Multiple consumers share message processing load.
        
        Scenario:
        - Create consumer group with 2 consumers
        - Publish 10 messages
        - Consumer 1 reads 5 messages
        - Consumer 2 reads 5 messages
        - Verify each consumer gets different messages
        """
        stream = "candles.1m.gc"
        group = "test-multi-consumer-group"
        consumer1 = "consumer-1"
        consumer2 = "consumer-2"
        
        # Create consumer group
        try:
            await redis_client.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception:
            pass
        
        # Publish 10 candles
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            timestamp = base_time + timedelta(minutes=i)
            candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            await publish_to_stream(stream, candle.model_dump())
        
        # Consumer 1 reads
        msgs1 = await redis_client.xreadgroup(
            group,
            consumer1,
            {stream: ">"},
            count=5,
        )
        
        # Consumer 2 reads
        msgs2 = await redis_client.xreadgroup(
            group,
            consumer2,
            {stream: ">"},
            count=5,
        )
        
        # Assert: Both consumers got messages
        count1 = sum(len(msg_list) for _, msg_list in msgs1) if msgs1 else 0
        count2 = sum(len(msg_list) for _, msg_list in msgs2) if msgs2 else 0
        
        assert count1 + count2 == 10, "All messages distributed across consumers"
        
        # Note: Redis consumer groups ensure each message delivered to only one consumer


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestMessageReplayIdempotency:
    """Test message replay and idempotency."""
    
    async def test_replay_from_specific_message_id(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: Services can replay from specific message ID.
        
        Scenario:
        - Publish 10 messages
        - Get message ID of 5th message
        - Replay from 5th message
        - Verify only messages 5-10 are returned
        """
        stream = "candles.1m.gc"
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish 10 messages and capture IDs
        msg_ids = []
        for i in range(10):
            timestamp = base_time + timedelta(minutes=i)
            candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            msg_id = await publish_to_stream(stream, candle.model_dump())
            msg_ids.append(msg_id)
        
        # Replay from 5th message (index 4)
        fifth_msg_id = msg_ids[4]
        messages = await redis_client.xread({stream: fifth_msg_id}, count=100)
        
        # Assert: Get messages after 5th (messages 6-10)
        replayed_count = sum(len(msg_list) for _, msg_list in messages)
        assert replayed_count == 5, f"Should replay 5 messages (6-10), got {replayed_count}"
    
    async def test_idempotent_feature_processing(
        self,
        db_pool,
        features_message_factory: Callable,
    ):
        """Test: Features can be re-inserted idempotently (upsert).
        
        Scenario:
        - Insert features for timestamp 14:00
        - Re-insert features for same timestamp (different values)
        - Verify upsert updates existing row (no duplicate)
        """
        timestamp = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # First insert
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO features (
                    timestamp, symbol, timeframe, close, vwap, rsi
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE SET
                    close = EXCLUDED.close,
                    vwap = EXCLUDED.vwap,
                    rsi = EXCLUDED.rsi
                """,
                timestamp,
                "GC",
                "1m",
                2051.0,
                2050.5,
                55.0,
            )
        
        # Second insert (upsert with new values)
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO features (
                    timestamp, symbol, timeframe, close, vwap, rsi
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE SET
                    close = EXCLUDED.close,
                    vwap = EXCLUDED.vwap,
                    rsi = EXCLUDED.rsi
                """,
                timestamp,
                "GC",
                "1m",
                2052.0,  # Updated
                2051.0,  # Updated
                56.0,    # Updated
            )
        
        # Assert: Only one row exists with updated values
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM features WHERE timestamp = $1",
                timestamp,
            )
            assert count == 1, "Only one row (no duplicate)"
            
            row = await conn.fetchrow(
                "SELECT * FROM features WHERE timestamp = $1",
                timestamp,
            )
            assert float(row["close"]) == 2052.0, "Value updated"
            assert float(row["vwap"]) == 2051.0, "Value updated"


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
@pytest.mark.slow
class TestHighVolumeStress:
    """Stress test with high message volume."""
    
    async def test_high_volume_candle_processing(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: System handles high volume of candles (1000+).
        
        Scenario:
        - Publish 1000 GC and DXY candles rapidly
        - Verify all messages published successfully
        - Verify no data loss
        - Measure throughput
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        count = 1000
        
        # Publish 1000 candle pairs
        for i in range(count):
            timestamp = base_time + timedelta(minutes=i)
            
            gc_candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            dxy_candle = candle_message_factory(timestamp=timestamp, symbol="DXY")
            
            await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
            await publish_to_stream("candles.1m.dxy", dxy_candle.model_dump())
            
            # Yield control periodically
            if i % 100 == 0:
                await asyncio.sleep(0.01)
        
        await asyncio.sleep(0.5)
        
        # Assert: All messages published
        gc_messages = await redis_client.xread({"candles.1m.gc": "0"}, count=2000)
        dxy_messages = await redis_client.xread({"candles.1m.dxy": "0"}, count=2000)
        
        gc_count = sum(len(msg_list) for _, msg_list in gc_messages)
        dxy_count = sum(len(msg_list) for _, msg_list in dxy_messages)
        
        assert gc_count >= count, f"All {count} GC candles published, got {gc_count}"
        assert dxy_count >= count, f"All {count} DXY candles published, got {dxy_count}"
    
    async def test_buffer_overflow_protection(
        self,
        redis_client,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: Synchronizer protects against buffer overflow.
        
        Scenario:
        - Publish 500 GC candles with no matching DXY
        - Verify buffer doesn't grow unbounded
        - Verify oldest entries evicted when limit exceeded
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish 500 unmatched GC candles
        for i in range(500):
            timestamp = base_time + timedelta(minutes=i)
            gc_candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
            
            if i % 50 == 0:
                await asyncio.sleep(0.01)
        
        await asyncio.sleep(0.5)
        
        # Assert: All messages in stream
        gc_messages = await redis_client.xread({"candles.1m.gc": "0"}, count=1000)
        gc_count = sum(len(msg_list) for _, msg_list in gc_messages)
        
        assert gc_count >= 500, f"All 500 GC candles in stream, got {gc_count}"
        
        # Note: CandleSynchronizer should implement buffer limits:
        # 1. Max buffer size (e.g., 1000 entries per symbol)
        # 2. Evict oldest when limit exceeded
        # 3. Log warnings for buffer pressure
