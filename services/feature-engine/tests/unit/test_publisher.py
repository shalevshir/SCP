"""Unit tests for feature publisher module."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from feature_engine_svc.publisher import FeaturePublisher
from scp_shared.messaging.schemas import FeaturesMessage


def create_features_message(timeframe: str = "1m") -> FeaturesMessage:
    """Create a test features message."""
    return FeaturesMessage(
        timestamp=datetime.now(timezone.utc),
        symbol="GC",
        timeframe=timeframe,
        close=2000.0,
        vwap=1999.5,
        rsi=55.0,
        ema_9=1998.0,
        ema_20=1995.0,
        ema_50=1990.0,
        dxy_correlation=-0.65,
        structure_label="HL",
        vwap_deviation=0.025,
    )


class TestFeaturePublisher:
    """Tests for FeaturePublisher class."""

    @pytest.mark.asyncio
    async def test_publish_1m_features(self) -> None:
        """Publishes 1m features to correct stream."""
        mock_redis = AsyncMock()
        publisher = FeaturePublisher(mock_redis)
        
        features = create_features_message(timeframe="1m")
        
        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="123-456")
            
            result = await publisher.publish(features)
            
            assert result == "123-456"
            mock_publisher.publish.assert_called_once_with("features.1m", features)

    @pytest.mark.asyncio
    async def test_publish_15m_features(self) -> None:
        """Publishes 15m features to correct stream."""
        mock_redis = AsyncMock()
        publisher = FeaturePublisher(mock_redis)
        
        features = create_features_message(timeframe="15m")
        
        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="789-012")
            
            result = await publisher.publish(features)
            
            assert result == "789-012"
            mock_publisher.publish.assert_called_once_with("features.15m", features)

    @pytest.mark.asyncio
    async def test_publish_1h_features(self) -> None:
        """Publishes 1h features to correct stream."""
        mock_redis = AsyncMock()
        publisher = FeaturePublisher(mock_redis)
        
        features = create_features_message(timeframe="1h")
        
        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="abc-def")
            
            result = await publisher.publish(features)
            
            assert result == "abc-def"
            mock_publisher.publish.assert_called_once_with("features.1h", features)
