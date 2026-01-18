"""Test NOGROUP error handling in RedisStreamConsumer."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis
from scp_shared.messaging import RedisStreamConsumer
from scp_shared.messaging.schemas import CandleMessage


@pytest.mark.asyncio
async def test_nogroup_error_retry():
    """Test that NOGROUP errors trigger consumer group recreation and retry."""
    # Create mock Redis client
    mock_redis = AsyncMock(spec=redis.Redis)
    
    # First call to xreadgroup raises NOGROUP (simulating stream deletion)
    # Second call succeeds after group is recreated
    async def xreadgroup_side_effect(*args, **kwargs):
        # First call raises NOGROUP
        if mock_redis.xreadgroup.call_count == 1:
            raise redis.ResponseError("NOGROUP No such key 'candles.1m.dxy' or consumer group 'test-group'")
        # Second call returns empty results
        return []  # Empty results after successful recreation
    
    mock_redis.xreadgroup = AsyncMock(side_effect=xreadgroup_side_effect)
    
    # Mock xgroup_create to succeed (AsyncMock returns awaitable by default)
    async def mock_xgroup_create(*args, **kwargs):
        return True
    mock_redis.xgroup_create = AsyncMock(side_effect=mock_xgroup_create)
    
    # Create consumer
    consumer = RedisStreamConsumer(
        mock_redis,
        stream="candles.1m.dxy",
        group="test-group",
        consumer_name="test-consumer",
        message_type=CandleMessage,
    )
    
    # This should NOT raise - should recreate group and retry
    messages = await consumer.read(count=10, block_ms=1000)
    
    # Verify behavior
    assert messages == []  # No messages in stream
    assert mock_redis.xreadgroup.call_count == 2  # First failed, second succeeded
    assert mock_redis.xgroup_create.call_count == 2  # Initial + recreation


@pytest.mark.asyncio
async def test_nogroup_error_max_retries():
    """Test that NOGROUP errors eventually raise after max retries."""
    # Create mock Redis client
    mock_redis = AsyncMock(spec=redis.Redis)
    
    # All calls to xreadgroup raise NOGROUP (group can't be created)
    mock_redis.xreadgroup.side_effect = redis.ResponseError(
        "NOGROUP No such key 'candles.1m.dxy' or consumer group 'test-group'"
    )
    
    # Mock xgroup_create to succeed (but xreadgroup still fails)
    async def mock_xgroup_create(*args, **kwargs):
        return True
    mock_redis.xgroup_create = AsyncMock(side_effect=mock_xgroup_create)
    
    # Create consumer
    consumer = RedisStreamConsumer(
        mock_redis,
        stream="candles.1m.dxy",
        group="test-group",
        consumer_name="test-consumer",
        message_type=CandleMessage,
    )
    
    # This SHOULD raise after 3 attempts
    with pytest.raises(redis.ResponseError, match="NOGROUP"):
        await consumer.read(count=10, block_ms=1000)
    
    # Verify it tried 4 times total (initial + 3 retries)
    assert mock_redis.xreadgroup.call_count == 3  # max_nogroup_retries = 3


@pytest.mark.asyncio
async def test_nogroup_error_with_backoff():
    """Test that NOGROUP retries use exponential backoff."""
    # Create mock Redis client
    mock_redis = AsyncMock(spec=redis.Redis)
    
    # All calls raise NOGROUP
    mock_redis.xreadgroup.side_effect = redis.ResponseError(
        "NOGROUP No such key 'candles.1m.dxy' or consumer group 'test-group'"
    )
    
    # Mock xgroup_create
    async def mock_xgroup_create(*args, **kwargs):
        return True
    mock_redis.xgroup_create = AsyncMock(side_effect=mock_xgroup_create)
    
    # Create consumer
    consumer = RedisStreamConsumer(
        mock_redis,
        stream="candles.1m.dxy",
        group="test-group",
        consumer_name="test-consumer",
        message_type=CandleMessage,
    )
    
    # Patch asyncio.sleep to track delays
    sleep_delays = []
    
    async def mock_sleep(delay: float) -> None:
        sleep_delays.append(delay)
    
    with patch("asyncio.sleep", side_effect=mock_sleep):
        with pytest.raises(redis.ResponseError, match="NOGROUP"):
            await consumer.read(count=10, block_ms=1000)
    
    # Verify exponential backoff: 0.1s, 0.2s
    # (only 2 sleeps because we fail on the 3rd attempt)
    assert len(sleep_delays) == 2
    assert sleep_delays[0] == pytest.approx(0.1)
    assert sleep_delays[1] == pytest.approx(0.2)
