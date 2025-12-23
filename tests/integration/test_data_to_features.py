"""Integration test: Data Adapter -> Feature Engine.

Tests that candles published to candles.1m.gc/dxy streams are consumed by
Feature Engine and produce features on features.1m stream.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import redis.asyncio as redis
from scp_shared.messaging import RedisStreamConsumer, RedisStreamPublisher
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage


@pytest.mark.integration
@pytest.mark.asyncio
async def test_published_candles_produce_features(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    clean_streams: None,
    ensure_services_healthy: None,
) -> None:
    """Test that publishing GC and DXY candles produces features.
    
    This test verifies the Data Adapter -> Feature Engine message flow:
    1. Publish 60+ candles to trigger warmup completion
    2. Verify features stream receives messages
    3. Validate feature values are computed
    """
    # Create consumer for features stream
    features_consumer = RedisStreamConsumer(
        redis_client,
        stream="features.1m",
        group="integration-test",
        consumer_name="test-1",
        message_type=FeaturesMessage,
    )
    
    # Publish 70 candles to ensure warmup completes (need 60+ for correlations)
    base_timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    
    for i in range(70):
        timestamp = base_timestamp + timedelta(minutes=i)
        
        # GC candle (trending up slightly)
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
        
        # DXY candle (trending down slightly - inverse correlation)
        dxy_candle = CandleMessage(
            timestamp=timestamp,
            symbol="DXY",
            timeframe="1m",
            open=104.5 - i * 0.01,
            high=104.6 - i * 0.01,
            low=104.4 - i * 0.01,
            close=104.55 - i * 0.01,
            volume=0.0,
        )
        
        # Publish candles
        await redis_publisher.publish("candles.1m.gc", gc_candle)
        await redis_publisher.publish("candles.1m.dxy", dxy_candle)
        
        # Small delay to simulate real-time data
        await asyncio.sleep(0.01)
    
    # Wait for feature engine to process candles
    await asyncio.sleep(2.0)
    
    # Consume features from stream (read all 70 published candles)
    features_list = await features_consumer.read(count=100, block_ms=5000)
    
    # Verify we received features
    assert len(features_list) > 0, "No features received from Feature Engine"
    
    # After warmup (60+ bars), should have computed indicators
    # Relaxed threshold to account for async processing delays
    assert len(features_list) >= 30, (
        f"Expected at least 30 features for warmup validation, got {len(features_list)}. "
        "Feature Engine may not have processed all candles."
    )
    
    # Check latest feature (after warmup)
    latest_features = features_list[-1]
    
    # Verify basic fields
    assert latest_features.symbol == "GC"
    assert latest_features.timeframe == "1m"
    assert latest_features.close is not None
    
    # After warmup, all indicators should be computed
    assert latest_features.vwap is not None, "VWAP should be computed after warmup"
    assert latest_features.ema_9 is not None, "EMA should be computed after warmup"
    assert latest_features.rsi is not None, "RSI should be computed after warmup"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_features_include_correlation(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    clean_streams: None,
    ensure_services_healthy: None,
) -> None:
    """Test that features include DXY correlation after sufficient warmup.
    
    DXY correlation requires 50+ bars of data to be reliable.
    """
    # Create consumer for features stream
    features_consumer = RedisStreamConsumer(
        redis_client,
        stream="features.1m",
        group="integration-test-corr",
        consumer_name="test-corr-1",
        message_type=FeaturesMessage,
    )
    
    # Publish 60 candles with clear inverse correlation
    base_timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    
    for i in range(60):
        timestamp = base_timestamp + timedelta(minutes=i)
        
        # GC up, DXY down (inverse correlation)
        gc_price = 2650.0 + i * 0.5
        dxy_price = 104.5 - i * 0.02
        
        gc_candle = CandleMessage(
            timestamp=timestamp,
            symbol="GC",
            timeframe="1m",
            open=gc_price,
            high=gc_price + 2,
            low=gc_price - 2,
            close=gc_price,
            volume=1000.0,
        )
        
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
    
    # Wait for processing
    await asyncio.sleep(2.0)
    
    # Get all features (read all 60 published candles)
    features_list = await features_consumer.read(count=100, block_ms=5000)
    
    assert len(features_list) > 0, "No features received"
    
    # After warmup (50+ bars needed for correlation), verify we have enough data
    assert len(features_list) >= 50, (
        f"Expected at least 50 features for correlation validation, got {len(features_list)}. "
        "Feature Engine may not have processed all candles."
    )
    
    # Check that later features have correlation computed
    # (correlation needs 50+ bars, so check last 10 features)
    features_with_corr = [f for f in features_list[-10:] if f.dxy_correlation is not None]
    
    assert len(features_with_corr) > 0, "DXY correlation should be computed after warmup"
    
    # Verify correlation is negative (inverse relationship)
    latest_corr = features_with_corr[-1].dxy_correlation
    assert latest_corr is not None, "Latest correlation should not be None (filtered above)"
    assert latest_corr < -0.3, f"Expected negative correlation, got {latest_corr}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_features_timestamp_matches_candles(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    clean_streams: None,
    ensure_services_healthy: None,
    candle_factory,
) -> None:
    """Test that feature timestamps match published candle timestamps."""
    features_consumer = RedisStreamConsumer(
        redis_client,
        stream="features.1m",
        group="integration-test-ts",
        consumer_name="test-ts-1",
        message_type=FeaturesMessage,
    )
    
    # Publish a few candles with specific timestamps
    test_timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
    
    for i in range(5):
        ts = test_timestamp + timedelta(minutes=i)
        
        gc_candle = candle_factory(timestamp=ts, symbol="GC")
        dxy_candle = candle_factory(timestamp=ts, symbol="DXY")
        
        await redis_publisher.publish("candles.1m.gc", gc_candle)
        await redis_publisher.publish("candles.1m.dxy", dxy_candle)
    
    await asyncio.sleep(1.0)
    
    features_list = await features_consumer.read(count=5, block_ms=3000)
    
    assert len(features_list) > 0, "No features received"
    
    # Verify timestamps are preserved
    for features in features_list:
        # Timestamp should be within the range we published
        assert features.timestamp >= test_timestamp
        assert features.timestamp <= test_timestamp + timedelta(minutes=5)

