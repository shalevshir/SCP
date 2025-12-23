"""Unit tests for candle publisher module."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from data_adapter.publisher import CandlePublisher
from scp_shared.messaging.schemas import CandleMessage


def create_candle_message(
    symbol: str = "GC",
    timeframe: str = "1m",
) -> CandleMessage:
    """Create a test candle message."""
    return CandleMessage(
        timestamp=datetime.now(timezone.utc),
        symbol=symbol,
        timeframe=timeframe,
        open=2650.0,
        high=2652.0,
        low=2648.0,
        close=2651.0,
        volume=100.0,
    )


class TestCandlePublisher:
    """Tests for CandlePublisher class."""

    @pytest.mark.asyncio
    async def test_publish_gc_1m(self) -> None:
        """Publishes GC 1m candle to correct stream."""
        mock_redis = AsyncMock()
        publisher = CandlePublisher(mock_redis)
        
        candle = create_candle_message(symbol="GC", timeframe="1m")
        
        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="123-456")
            
            result = await publisher.publish(candle)
            
            assert result == "123-456"
            mock_publisher.publish.assert_called_once_with("candles.1m.gc", candle)

    @pytest.mark.asyncio
    async def test_publish_dxy_1m(self) -> None:
        """Publishes DXY 1m candle to correct stream."""
        mock_redis = AsyncMock()
        publisher = CandlePublisher(mock_redis)
        
        candle = create_candle_message(symbol="DXY", timeframe="1m")
        
        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="789-012")
            
            result = await publisher.publish(candle)
            
            assert result == "789-012"
            mock_publisher.publish.assert_called_once_with("candles.1m.dxy", candle)

    @pytest.mark.asyncio
    async def test_publish_15m_candle(self) -> None:
        """Publishes 15m candle to correct stream."""
        mock_redis = AsyncMock()
        publisher = CandlePublisher(mock_redis)
        
        candle = create_candle_message(symbol="GC", timeframe="15m")
        
        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="abc-def")
            
            result = await publisher.publish(candle)
            
            assert result == "abc-def"
            mock_publisher.publish.assert_called_once_with("candles.15m.gc", candle)

    @pytest.mark.asyncio
    async def test_publish_1h_candle(self) -> None:
        """Publishes 1h candle to correct stream."""
        mock_redis = AsyncMock()
        publisher = CandlePublisher(mock_redis)
        
        candle = create_candle_message(symbol="GC", timeframe="1h")
        
        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="ghi-jkl")
            
            result = await publisher.publish(candle)
            
            assert result == "ghi-jkl"
            mock_publisher.publish.assert_called_once_with("candles.1h.gc", candle)
