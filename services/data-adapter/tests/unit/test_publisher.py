"""Unit tests for CandlePublisher."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from scp_shared.messaging.schemas import CandleMessage

from data_adapter.publisher import CandlePublisher


class TestCandlePublisher:
    """Test CandlePublisher."""
    
    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client."""
        return AsyncMock()
    
    @pytest.fixture
    def sample_candle_gc(self) -> CandleMessage:
        """Create sample Gold candle."""
        return CandleMessage(
            timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2050.0,
            high=2052.0,
            low=2049.0,
            close=2051.0,
            volume=1500.0,
        )
    
    @pytest.fixture
    def sample_candle_dxy(self) -> CandleMessage:
        """Create sample DXY candle."""
        return CandleMessage(
            timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.5,
            volume=0.0,  # DXY often has zero volume
        )
    
    # Core tests
    
    @pytest.mark.asyncio
    async def test_publish_uses_correct_stream_naming(
        self,
        mock_redis_client: AsyncMock,
        sample_candle_gc: CandleMessage,
    ) -> None:
        """'candles.1m.gc' format."""
        publisher = CandlePublisher(mock_redis_client)
        
        with patch.object(publisher.publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = "1234567890-0"
            
            message_id = await publisher.publish(sample_candle_gc)
            
            # Verify correct stream name
            mock_publish.assert_called_once_with("candles.1m.gc", sample_candle_gc)
            assert message_id == "1234567890-0"
    
    @pytest.mark.asyncio
    async def test_publish_returns_message_id(
        self,
        mock_redis_client: AsyncMock,
        sample_candle_gc: CandleMessage,
    ) -> None:
        """Returns Redis message ID."""
        publisher = CandlePublisher(mock_redis_client)
        
        with patch.object(publisher.publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = "1234567890-0"
            
            message_id = await publisher.publish(sample_candle_gc)
            
            assert isinstance(message_id, str)
            assert message_id == "1234567890-0"
    
    @pytest.mark.asyncio
    async def test_publish_different_symbols(
        self,
        mock_redis_client: AsyncMock,
        sample_candle_gc: CandleMessage,
        sample_candle_dxy: CandleMessage,
    ) -> None:
        """GC and DXY routing."""
        publisher = CandlePublisher(mock_redis_client)
        
        with patch.object(publisher.publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = "1234567890-0"
            
            # Publish GC candle
            await publisher.publish(sample_candle_gc)
            assert mock_publish.call_args[0][0] == "candles.1m.gc"
            
            # Publish DXY candle
            await publisher.publish(sample_candle_dxy)
            assert mock_publish.call_args[0][0] == "candles.1m.dxy"
    
    # Edge cases
    
    @pytest.mark.asyncio
    async def test_publish_handles_redis_connection_error(
        self,
        mock_redis_client: AsyncMock,
        sample_candle_gc: CandleMessage,
    ) -> None:
        """Graceful Redis failure handling."""
        publisher = CandlePublisher(mock_redis_client)
        
        with patch.object(publisher.publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.side_effect = RedisConnectionError("Connection failed")
            
            # Should propagate exception (caller handles retry logic)
            with pytest.raises(RedisConnectionError, match="Connection failed"):
                await publisher.publish(sample_candle_gc)
    
    @pytest.mark.asyncio
    async def test_publish_different_timeframes(
        self,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Support for 1m, 15m, 1h streams."""
        publisher = CandlePublisher(mock_redis_client)
        
        with patch.object(publisher.publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = "1234567890-0"
            
            # Test 1m candle
            candle_1m = CandleMessage(
                timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2050.0,
                high=2052.0,
                low=2049.0,
                close=2051.0,
                volume=1500.0,
            )
            await publisher.publish(candle_1m)
            assert mock_publish.call_args[0][0] == "candles.1m.gc"
            
            # Test 15m candle
            candle_15m = CandleMessage(
                timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="15m",
                open=2050.0,
                high=2055.0,
                low=2048.0,
                close=2054.0,
                volume=5000.0,
            )
            await publisher.publish(candle_15m)
            assert mock_publish.call_args[0][0] == "candles.15m.gc"
            
            # Test 1h candle
            candle_1h = CandleMessage(
                timestamp=datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1h",
                open=2050.0,
                high=2060.0,
                low=2045.0,
                close=2058.0,
                volume=20000.0,
            )
            await publisher.publish(candle_1h)
            assert mock_publish.call_args[0][0] == "candles.1h.gc"
