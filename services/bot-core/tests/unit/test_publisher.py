"""Unit tests for SignalPublisher."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from scp_shared.messaging.schemas import SignalMessage

from bot_core_svc.publisher import SignalPublisher


class TestSignalPublisher:
    """Test SignalPublisher."""
    
    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client."""
        return AsyncMock()
    
    @pytest.fixture
    def sample_signal(self) -> SignalMessage:
        """Create sample signal message."""
        return SignalMessage(
            id="test-signal-123",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.5,
            confidence="A+",
            entry_price=2050.0,
            sl_price=2045.0,
            tp_price=2065.0,
            factors={
                "htf_bias": "bullish",
                "rationale": "VWAP reclaim with HTF alignment",
            },
        )
    
    # Core tests
    
    @pytest.mark.asyncio
    async def test_publish_sends_to_correct_stream(
        self,
        mock_redis_client: AsyncMock,
        sample_signal: SignalMessage,
    ) -> None:
        """Publishes to 'signals.pending' stream."""
        publisher = SignalPublisher(mock_redis_client, stream="signals.pending")
        
        with patch.object(publisher._publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = "1234567890-0"
            
            message_id = await publisher.publish(sample_signal)
            
            # Verify correct stream and message
            mock_publish.assert_called_once_with("signals.pending", sample_signal)
            assert message_id == "1234567890-0"
    
    @pytest.mark.asyncio
    async def test_publish_returns_message_id(
        self,
        mock_redis_client: AsyncMock,
        sample_signal: SignalMessage,
    ) -> None:
        """Returns Redis message ID."""
        publisher = SignalPublisher(mock_redis_client)
        
        with patch.object(publisher._publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = "1234567890-0"
            
            message_id = await publisher.publish(sample_signal)
            
            assert isinstance(message_id, str)
            assert message_id == "1234567890-0"
    
    @pytest.mark.asyncio
    async def test_publish_logs_signal_details(
        self,
        mock_redis_client: AsyncMock,
        sample_signal: SignalMessage,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Logging verification."""
        import logging
        
        # Set log level to INFO to capture log messages
        caplog.set_level(logging.INFO)
        
        publisher = SignalPublisher(mock_redis_client)
        
        with patch.object(publisher._publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = "1234567890-0"
            
            await publisher.publish(sample_signal)
            
            # Check log contains signal details
            assert "Published signal" in caplog.text
            assert "long" in caplog.text
            assert "VWAP_RECLAIM" in caplog.text
            assert "8.5" in caplog.text
            assert "A+" in caplog.text
    
    # Error handling tests
    
    @pytest.mark.asyncio
    async def test_publish_handles_redis_connection_error(
        self,
        mock_redis_client: AsyncMock,
        sample_signal: SignalMessage,
    ) -> None:
        """Graceful handling of Redis failures."""
        publisher = SignalPublisher(mock_redis_client)
        
        with patch.object(publisher._publisher, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.side_effect = RedisConnectionError("Connection failed")
            
            # Should propagate exception (caller handles retry logic)
            with pytest.raises(RedisConnectionError, match="Connection failed"):
                await publisher.publish(sample_signal)
    
    @pytest.mark.asyncio
    async def test_publish_validates_signal_message(
        self,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Rejects invalid SignalMessage."""
        from pydantic import ValidationError
        
        publisher = SignalPublisher(mock_redis_client)
        
        # Create invalid signal (missing required fields)
        # This should fail Pydantic validation
        with pytest.raises((ValidationError, TypeError, AttributeError)):
            # None will cause AttributeError when trying to serialize
            await publisher.publish(None)  # type: ignore
