"""Unit tests for bias publisher module."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from htf_bias_svc.publisher import BiasPublisher
from scp_shared.messaging.schemas import HTFBiasMessage


def create_bias_message() -> HTFBiasMessage:
    """Create a test bias message."""
    return HTFBiasMessage(
        timestamp=datetime.now(timezone.utc),
        bias="bullish",
        score=7.5,
        confidence="A+",
        structure_15m="HL",
        structure_1h="HL",
        dxy_aligned=True,
        chop_detected=False,
    )


class TestBiasPublisher:
    """Tests for BiasPublisher class."""

    @pytest.mark.asyncio
    async def test_publish_returns_message_id(self) -> None:
        """Publishes bias and returns message ID."""
        mock_redis = AsyncMock()
        publisher = BiasPublisher(mock_redis)

        bias = create_bias_message()

        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="123-456")

            result = await publisher.publish(bias)

            assert result == "123-456"
            mock_publisher.publish.assert_called_once_with("htf.bias", bias)

    @pytest.mark.asyncio
    async def test_publish_bearish_bias(self) -> None:
        """Publishes bearish bias."""
        mock_redis = AsyncMock()
        publisher = BiasPublisher(mock_redis)

        bias = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bearish",
            score=8.0,
            confidence="A+",
            structure_15m="LH",
            structure_1h="LL",
            dxy_aligned=True,
            chop_detected=False,
        )

        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="789-012")

            result = await publisher.publish(bias)

            assert result == "789-012"

    @pytest.mark.asyncio
    async def test_publish_neutral_bias(self) -> None:
        """Publishes neutral bias when chop detected."""
        mock_redis = AsyncMock()
        publisher = BiasPublisher(mock_redis)

        bias = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="neutral",
            score=3.0,
            confidence="C",
            structure_15m=None,
            structure_1h=None,
            dxy_aligned=False,
            chop_detected=True,
        )

        with patch.object(publisher, "publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="abc-def")

            result = await publisher.publish(bias)

            assert result == "abc-def"
