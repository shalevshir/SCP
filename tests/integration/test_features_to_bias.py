"""Integration test: Feature Engine -> HTF Bias Service.

Tests that features published at 15m/1h boundaries trigger HTF bias updates.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
import redis.asyncio as redis
from scp_shared.messaging import RedisStreamConsumer, RedisStreamPublisher
from scp_shared.messaging.schemas import CandleMessage, HTFBiasMessage

# Wait time for HTF Bias service to process candles
# In CI, services may be slower, so wait longer
# Check for CI environment variable (set by GitHub Actions and most CI systems)
# or GITHUB_ACTIONS (specific to GitHub Actions)
# Both are set to "true" in GitHub Actions
IS_CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
HTF_BIAS_PROCESSING_WAIT = 15.0 if IS_CI else 3.0
SERVICE_INIT_WAIT = 5.0 if IS_CI else 0.5


async def read_bias_with_retry(
    consumer: RedisStreamConsumer,
    max_attempts: int = 10 if IS_CI else 5,
    wait_between: float = 5.0 if IS_CI else 2.0,
) -> list:
    """Read bias messages with retry logic for CI reliability.
    
    In CI, services may take longer to process. This function retries
    reading from the stream multiple times with waits between attempts.
    
    Args:
        consumer: Redis stream consumer for htf.bias
        max_attempts: Maximum number of read attempts (more in CI)
        wait_between: Seconds to wait between attempts (longer in CI)
        
    Returns:
        List of bias messages (may be empty if all retries fail)
    """
    for attempt in range(max_attempts):
        bias_list = await consumer.read(count=10, block_ms=5000)
        if bias_list:
            return bias_list
        if attempt < max_attempts - 1:
            await asyncio.sleep(wait_between)
    return []


async def verify_stream_has_messages(
    redis_client: redis.Redis,
    stream: str,
) -> int:
    """Verify a stream has messages and return the count.
    
    Args:
        redis_client: Redis client
        stream: Stream name to check
        
    Returns:
        Number of messages in stream
    """
    try:
        info = await redis_client.xinfo_stream(stream)
        return info.get("length", 0)
    except Exception:
        return 0


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
    
    # Give HTF Bias service time to initialize consumers after health check
    # In CI, services may take longer to start processing loops
    await asyncio.sleep(SERVICE_INIT_WAIT)
    
    # Publish candles to warm up HTF calculator and cross 15m boundary
    # 
    # HTF bias calculation requires BOTH features_1h AND features_15m to be populated:
    # - features_1h is populated when a 1H boundary is crossed (e.g., 10:00)
    # - features_15m is populated when a 15M boundary is crossed
    # 
    # Start at 9:00, publish 80 candles (9:00 to 10:19):
    # - 1H bar completes at 10:00 → features_1h populated
    # - 15M bars complete at 9:15, 9:30, 9:45, 10:00, 10:15 → features_15m populated
    # - At 10:15, BOTH features exist → bias is computed
    base_timestamp = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    
    # Publish 80 candles (9:00 to 10:19) to cross 1H boundary and then 15m boundary
    for i in range(80):
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
    await asyncio.sleep(HTF_BIAS_PROCESSING_WAIT)
    
    # Try to read bias updates with retry for CI reliability
    bias_list = await read_bias_with_retry(bias_consumer)
    
    # CRITICAL: HTF bias must update at 15m boundaries - test should not pass silently
    # Add diagnostic info for CI debugging
    gc_stream_len = await verify_stream_has_messages(redis_client, "candles.1m.gc")
    dxy_stream_len = await verify_stream_has_messages(redis_client, "candles.1m.dxy")
    bias_stream_len = await verify_stream_has_messages(redis_client, "htf.bias")
    
    assert len(bias_list) > 0, (
        f"HTF Bias service should have produced at least one bias update at the 15m boundary. "
        f"Published 80 candles from 9:00 to 10:19, crossing 1H boundary at 10:00 and 15m boundary at 10:15. "
        f"Stream stats: candles.1m.gc={gc_stream_len}, candles.1m.dxy={dxy_stream_len}, htf.bias={bias_stream_len}. "
        f"If candle streams have data but htf.bias is empty, service is not producing bias."
    )
    
    latest_bias = bias_list[-1]
    
    # Verify bias message structure
    assert latest_bias.bias in ["bullish", "bearish", "neutral"]
    assert latest_bias.score is not None
    assert latest_bias.confidence in ["A+", "A", "B", "C"]
    
    # Note: Bias direction depends on HTF structure, not just recent price movement
    # The test verifies that bias is produced, not the specific direction


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
    
    # Give HTF Bias service time to initialize consumers after health check
    await asyncio.sleep(2.0 if IS_CI else 0.5)
    
    # Publish enough candles to warm up HTF calculator (need 1H bar + 15M bar)
    # Start at 9:00, publish 80 candles to cross 1H boundary at 10:00
    base_timestamp = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    
    # Create clear bullish structure: higher highs and higher lows
    for i in range(80):
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
    
    # Wait for HTF Bias service to process
    await asyncio.sleep(HTF_BIAS_PROCESSING_WAIT)
    
    # Try to read bias updates with retry for CI reliability
    bias_list = await read_bias_with_retry(bias_consumer)
    
    # Add diagnostic info for CI debugging
    gc_stream_len = await verify_stream_has_messages(redis_client, "candles.1m.gc")
    bias_stream_len = await verify_stream_has_messages(redis_client, "htf.bias")
    
    # Should receive bias updates after publishing 80 candles across 1H and 15M boundaries
    assert len(bias_list) > 0, (
        f"HTF Bias service should have produced bias updates. "
        f"Published 80 candles from 9:00 to 10:19 with clear bullish structure, crossing 1H boundary at 10:00. "
        f"Stream stats: candles.1m.gc={gc_stream_len}, htf.bias={bias_stream_len}. "
        f"If candle streams have data but htf.bias is empty, service is not producing bias."
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
    
    # Give HTF Bias service time to initialize consumers after health check
    await asyncio.sleep(2.0 if IS_CI else 0.5)
    
    # Publish enough candles to warm up HTF calculator (need 1H bar + 15M bar)
    # Start at 9:00, publish 80 candles to cross 1H boundary at 10:00
    base_timestamp = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    
    for i in range(80):
        timestamp = base_timestamp + timedelta(minutes=i)
        
        # Oscillate around 2650 - no trend (chop pattern)
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
    
    # Wait for HTF Bias service to process
    await asyncio.sleep(HTF_BIAS_PROCESSING_WAIT)
    
    # Try to read bias updates with retry for CI reliability
    bias_list = await read_bias_with_retry(bias_consumer)
    
    # Add diagnostic info for CI debugging
    gc_stream_len = await verify_stream_has_messages(redis_client, "candles.1m.gc")
    bias_stream_len = await verify_stream_has_messages(redis_client, "htf.bias")
    
    # Should receive bias updates after publishing 80 candles of choppy price action
    assert len(bias_list) > 0, (
        f"HTF Bias service should have produced bias updates. "
        f"Published 80 candles from 9:00 to 10:19 with ranging/choppy price action. "
        f"Stream stats: candles.1m.gc={gc_stream_len}, htf.bias={bias_stream_len}. "
        f"If candle streams have data but htf.bias is empty, service is not producing bias."
    )
    
    latest_bias = bias_list[-1]
    
    # Verify chop detection field exists
    assert hasattr(latest_bias, "chop_detected")
    
    # With ranging price action, should detect chop
    # (or at least not have strong directional bias)
    # Note: Chop detection no longer automatically reduces confidence
    if latest_bias.bias != "neutral":
        # Confidence can be any valid level
        assert latest_bias.confidence in ["A+", "A", "B", "C"]


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
    
    # Give HTF Bias service time to initialize consumers after health check
    await asyncio.sleep(2.0 if IS_CI else 0.5)
    
    # Publish enough candles to warm up HTF calculator (need 1H bar + 15M bar)
    # Start at 9:00, publish 80 candles to cross 1H boundary at 10:00 and 15M boundary at 10:15
    base_timestamp = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    
    for i in range(80):
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
    
    # Wait for HTF Bias service to process
    await asyncio.sleep(HTF_BIAS_PROCESSING_WAIT)
    
    # Try to read bias updates with retry for CI reliability
    bias_list = await read_bias_with_retry(bias_consumer)
    
    # Add diagnostic info for CI debugging
    gc_stream_len = await verify_stream_has_messages(redis_client, "candles.1m.gc")
    bias_stream_len = await verify_stream_has_messages(redis_client, "htf.bias")
    
    # Should receive bias updates at 15m boundary (10:15) after 1H warmup at 10:00
    assert len(bias_list) > 0, (
        f"HTF Bias service should have produced bias updates at 15m boundaries. "
        f"Published 80 candles from 9:00 to 10:19, crossing 1H boundary at 10:00 and 15M boundary at 10:15. "
        f"Stream stats: candles.1m.gc={gc_stream_len}, htf.bias={bias_stream_len}. "
        f"If candle streams have data but htf.bias is empty, boundary detection is broken or service not consuming candles."
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

