"""Unit tests for warmup publisher."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from scp_shared.messaging.schemas import CandleMessage

from data_adapter.warmup_publisher import WarmupPublisher


def create_candle(symbol: str, timestamp: datetime) -> CandleMessage:
    """Create a test candle message."""
    return CandleMessage(
        timestamp=timestamp,
        symbol=symbol,
        timeframe="1m",
        open=2650.0,
        high=2652.0,
        low=2648.0,
        close=2651.0,
        volume=100.0,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_warmup_data_clears_streams_before_publish() -> None:
    """Clears existing warmup streams before appending new data."""
    mock_redis = AsyncMock()
    mock_fetcher = AsyncMock()

    base_time = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
    gc_candles = [
        create_candle("GC", base_time),
        create_candle("GC", base_time + timedelta(minutes=1)),
    ]
    dxy_candles = [
        create_candle("DXY", base_time),
        create_candle("DXY", base_time + timedelta(minutes=1)),
    ]

    mock_fetcher.fetch_candles = AsyncMock(side_effect=[gc_candles, dxy_candles])

    publisher = WarmupPublisher(
        redis_client=mock_redis,
        ib_fetcher=mock_fetcher,
        lookback_hours=1,
        ttl_seconds=600,
    )

    result = await publisher.publish_warmup_data()

    assert result is True
    mock_redis.delete.assert_awaited_once_with(
        "warmup.candles.1m.gc",
        "warmup.candles.1m.dxy",
        "warmup.status"
    )
    call_order = [call_item[0] for call_item in mock_redis.method_calls]
    assert "xadd" in call_order
    assert call_order.index("delete") < call_order.index("xadd")
    assert mock_redis.xadd.await_count == len(gc_candles) + len(dxy_candles)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_status_clears_stale_success_markers() -> None:
    """Error status deletes entire hash to prevent stale success markers.

    Regression test for bug where _set_error_status would leave gc/dxy
    completion markers from previous successful runs, causing downstream
    consumers to incorrectly see warmup as available.
    """
    mock_redis = AsyncMock()
    mock_fetcher = AsyncMock()

    # Simulate fetch failure (no candles)
    mock_fetcher.fetch_candles = AsyncMock(return_value=[])

    publisher = WarmupPublisher(
        redis_client=mock_redis,
        ib_fetcher=mock_fetcher,
        lookback_hours=1,
        ttl_seconds=600,
    )

    # Execute publish (will fail due to no candles)
    result = await publisher.publish_warmup_data()

    assert result is False

    # Verify error status setting behavior:
    # 1. First delete call clears warmup:status hash (removes stale markers)
    # 2. Then hset adds fresh error status
    delete_calls = [
        call for call in mock_redis.delete.await_args_list if "warmup:status" in str(call)
    ]
    assert len(delete_calls) >= 1, "Should delete warmup:status to clear stale markers"

    # Verify hset was called with error status
    mock_redis.hset.assert_awaited()
    hset_call = mock_redis.hset.await_args_list[-1]
    assert hset_call[0][0] == "warmup:status"
    assert "error" in hset_call[1]["mapping"]
    assert "timestamp" in hset_call[1]["mapping"]
