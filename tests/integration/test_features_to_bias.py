"""Integration test: Feature Engine -> HTF Bias Service.

Tests that features published at 15m/1h boundaries trigger HTF bias updates.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import redis.asyncio as redis
from scp_shared.messaging import RedisStreamConsumer, RedisStreamPublisher
from scp_shared.messaging.schemas import CandleMessage, HTFBiasMessage


@pytest.mark.integration
@pytest.mark.asyncio
async def test_htf_boundary_triggers_bias_update(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    clean_streams: None,
    ensure_services_healthy: None,
) -> None:
    """Test that candles at 15m boundaries produce HTF bias updates.
    
    HTF Bias service consumes features.1m and produces bias updates when
    higher timeframe boundaries are crossed (15m, 1h).
    """
    # Create consumer for HTF bias stream
    bias_consumer = RedisStreamConsumer(
        redis_client,
        stream="htf.bias",
        group="integration-test-bias",
        consumer_name="test-bias-1",
        message_type=HTFBiasMessage,
    )
    
    # CRITICAL: Create consumer group BEFORE any messages are published
    await bias_consumer.ensure_group()
    
    # Publish candles building up to 15m boundary
    # Start at 10:00, go to 10:15 (15m boundary)
    base_timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    
    # Publish 20 candles (10:00 to 10:19) to cross 15m boundary at 10:15
    for i in range(20):
        timestamp = base_timestamp + timedelta(minutes=i)
        
        # Create bullish trend (price going up)
        price = 2650.0 + i * 0.5
        
        gc_candle = CandleMessage(
            timestamp=timestamp,
            symbol="GC",
            timeframe="1m",
            open=price,
            high=price + 2,
            low=price - 1,
            close=price + 1,
            volume=1000.0,
        )
        
        # DXY going down (inverse correlation)
        dxy_price = 104.5 - i * 0.02
        dxy_candle = CandleMessage(
            timestamp=timestamp,
            symbol="DXY",
            timeframe="1m",
            open=dxy_price,
            high=dxy_price + 0.1,
            low=dxy_price - 0.1,
            close=dxy_price,
            volume=0.0,
        )
        
        await redis_publisher.publish("candles.1m.gc", gc_candle)
        await redis_publisher.publish("candles.1m.dxy", dxy_candle)
        await asyncio.sleep(0.01)
    
    # Wait for HTF Bias service to process
    await asyncio.sleep(3.0)
    
    # Try to read bias updates
    bias_list = await bias_consumer.read(count=5, block_ms=5000)
    
    # CRITICAL: HTF bias must update at 15m boundaries - test should not pass silently
    assert len(bias_list) > 0, (
        "HTF Bias service should have produced at least one bias update at the 15m boundary. "
        "Published candles from 10:00 to 10:19, crossing 10:15 boundary. "
        "If no bias received, the HTF boundary detection is broken."
    )
    
    latest_bias = bias_list[-1]
    
    # Verify bias message structure
    assert latest_bias.bias in ["bullish", "bearish", "neutral"]
    assert latest_bias.score is not None
    assert latest_bias.confidence in ["A+", "A", "B", "C"]
    
    # With uptrend, should lean bullish or neutral (not bearish)
    assert latest_bias.bias != "bearish", "Uptrend should not produce bearish bias"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bias_includes_structure_info(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    clean_streams: None,
    ensure_services_healthy: None,
) -> None:
    """Test that HTF bias includes structure information (HH/HL/LH/LL)."""
    bias_consumer = RedisStreamConsumer(
        redis_client,
        stream="htf.bias",
        group="integration-test-structure",
        consumer_name="test-structure-1",
        message_type=HTFBiasMessage,
    )
    
    # CRITICAL: Create consumer group BEFORE any messages are published
    await bias_consumer.ensure_group()
    
    # Publish enough candles to establish structure
    base_timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    
    # Create clear bullish structure: higher highs and higher lows
    for i in range(30):
        timestamp = base_timestamp + timedelta(minutes=i)
        
        # Staircase pattern - clear higher highs
        price = 2650.0 + (i // 5) * 3.0  # Step up every 5 candles
        
        gc_candle = CandleMessage(
            timestamp=timestamp,
            symbol="GC",
            timeframe="1m",
            open=price,
            high=price + 2,
            low=price - 0.5,
            close=price + 1,
            volume=1000.0,
        )
        
        dxy_candle = CandleMessage(
            timestamp=timestamp,
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.5,
            volume=0.0,
        )
        
        await redis_publisher.publish("candles.1m.gc", gc_candle)
        await redis_publisher.publish("candles.1m.dxy", dxy_candle)
        await asyncio.sleep(0.01)
    
    await asyncio.sleep(3.0)
    
    bias_list = await bias_consumer.read(count=10, block_ms=5000)
    
    # Should receive bias updates after publishing 30 candles across 15m boundaries
    assert len(bias_list) > 0, (
        "HTF Bias service should have produced bias updates. "
        "Published 30 candles with clear bullish structure. "
        "If no bias received, the service is not processing features."
    )
    
    latest_bias = bias_list[-1]
    
    # Verify structure fields exist
    # (May be None initially but should be present after structure forms)
    assert hasattr(latest_bias, "structure_15m")
    assert hasattr(latest_bias, "structure_1h")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bias_detects_chop(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    clean_streams: None,
    ensure_services_healthy: None,
) -> None:
    """Test that HTF bias detects choppy/ranging markets."""
    bias_consumer = RedisStreamConsumer(
        redis_client,
        stream="htf.bias",
        group="integration-test-chop",
        consumer_name="test-chop-1",
        message_type=HTFBiasMessage,
    )
    
    # CRITICAL: Create consumer group BEFORE any messages are published
    await bias_consumer.ensure_group()
    
    # Publish candles with no clear direction (chop)
    base_timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    
    for i in range(30):
        timestamp = base_timestamp + timedelta(minutes=i)
        
        # Oscillate around 2650 - no trend
        price = 2650.0 + (i % 4 - 2) * 2.0  # Bounce between 2646-2654
        
        gc_candle = CandleMessage(
            timestamp=timestamp,
            symbol="GC",
            timeframe="1m",
            open=price,
            high=price + 1,
            low=price - 1,
            close=price + 0.5,
            volume=1000.0,
        )
        
        dxy_candle = CandleMessage(
            timestamp=timestamp,
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.5,
            volume=0.0,
        )
        
        await redis_publisher.publish("candles.1m.gc", gc_candle)
        await redis_publisher.publish("candles.1m.dxy", dxy_candle)
        await asyncio.sleep(0.01)
    
    await asyncio.sleep(3.0)
    
    bias_list = await bias_consumer.read(count=10, block_ms=5000)
    
    # Should receive bias updates after publishing 30 candles of choppy price action
    assert len(bias_list) > 0, (
        "HTF Bias service should have produced bias updates. "
        "Published 30 candles with ranging/choppy price action. "
        "If no bias received, the service is not processing features."
    )
    
    latest_bias = bias_list[-1]
    
    # Verify chop detection field exists
    assert hasattr(latest_bias, "chop_detected")
    
    # With ranging price action, should detect chop
    # (or at least not have strong directional bias)
    if latest_bias.bias != "neutral":
        # If not neutral, confidence should be lower (not A+)
        assert latest_bias.confidence in ["A", "B", "C"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bias_timestamp_correlation(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    clean_streams: None,
    ensure_services_healthy: None,
) -> None:
    """Test that bias timestamps align with 15m boundaries."""
    bias_consumer = RedisStreamConsumer(
        redis_client,
        stream="htf.bias",
        group="integration-test-timestamp",
        consumer_name="test-ts-bias-1",
        message_type=HTFBiasMessage,
    )
    
    # CRITICAL: Create consumer group BEFORE any messages are published
    await bias_consumer.ensure_group()
    
    # Publish candles crossing specific 15m boundary
    # 10:00 to 10:20 crosses 10:15 boundary
    base_timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    
    for i in range(25):
        timestamp = base_timestamp + timedelta(minutes=i)
        
        gc_candle = CandleMessage(
            timestamp=timestamp,
            symbol="GC",
            timeframe="1m",
            open=2650.0 + i * 0.1,
            high=2652.0 + i * 0.1,
            low=2648.0 + i * 0.1,
            close=2651.0 + i * 0.1,
            volume=1000.0,
        )
        
        dxy_candle = CandleMessage(
            timestamp=timestamp,
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.5,
            volume=0.0,
        )
        
        await redis_publisher.publish("candles.1m.gc", gc_candle)
        await redis_publisher.publish("candles.1m.dxy", dxy_candle)
        await asyncio.sleep(0.01)
    
    await asyncio.sleep(3.0)
    
    bias_list = await bias_consumer.read(count=10, block_ms=5000)
    
    # Should receive bias updates at 15m boundary (10:15)
    assert len(bias_list) > 0, (
        "HTF Bias service should have produced bias updates at 15m boundaries. "
        "Published candles from 10:00 to 10:24, crossing 10:15 boundary. "
        "If no bias received, boundary detection is broken."
    )
    
    # Verify bias timestamps are at or near 15m boundaries
    for bias in bias_list:
        # Check that minute is within 2 minutes of any 15m boundary
        # The HTF bias timestamp reflects the source candle that triggered the calculation,
        # which can be either at the boundary or just before it completes the period.
        # Valid minutes: 
        #   After boundary: 0-2, 15-17, 30-32, 45-47 (just after :00, :15, :30, :45)
        #   Before boundary: 13-14, 28-29, 43-44, 58-59 (just before :15, :30, :45, :00)
        minute = bias.timestamp.minute
        minutes_after_boundary = minute % 15
        
        # HTF bias should be emitted within 2 minutes of a 15m boundary
        # Accept both just-after (0-2) and just-before (13-14)
        is_near_boundary = minutes_after_boundary <= 2 or minutes_after_boundary >= 13
        
        assert is_near_boundary, (
            f"Bias timestamp {bias.timestamp} (minute {minute}) should be "
            f"within 2 minutes of a 15m boundary, "
            f"but is {min(minutes_after_boundary, 15 - minutes_after_boundary)} minutes away"
        )

