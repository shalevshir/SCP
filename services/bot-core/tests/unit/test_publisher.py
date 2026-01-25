"""Unit tests for signal publisher module."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from bot_core_svc.publisher import SignalPublisher
from scp_shared.messaging.schemas import SignalMessage


def create_signal_message() -> SignalMessage:
    """Create a test signal message."""
    return SignalMessage(
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=8.5,
        confidence="A+",
        entry_price=2000.0,
        sl_price=1995.0,
        tp_price=2010.0,
        factors={"vwap_hold": True},
    )


class TestSignalPublisher:
    """Tests for SignalPublisher class."""

    @pytest.mark.asyncio
    async def test_publish_returns_message_id(self) -> None:
        """Publishes signal and returns message ID."""
        mock_redis = AsyncMock()
        publisher = SignalPublisher(mock_redis, stream="test.signals")

        signal = create_signal_message()

        with patch.object(publisher, "_publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="123-456")

            result = await publisher.publish(signal)

            assert result == "123-456"
            mock_publisher.publish.assert_called_once_with("test.signals", signal)

    @pytest.mark.asyncio
    async def test_publish_uses_default_stream(self) -> None:
        """Uses default signals.pending stream."""
        mock_redis = AsyncMock()
        publisher = SignalPublisher(mock_redis)

        assert publisher._stream == "signals.pending"

    @pytest.mark.asyncio
    async def test_publish_logs_signal_details(self) -> None:
        """Logs signal details when publishing."""
        mock_redis = AsyncMock()
        publisher = SignalPublisher(mock_redis)

        signal = create_signal_message()

        with patch.object(publisher, "_publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="123-456")

            # This should not raise
            await publisher.publish(signal)

    @pytest.mark.asyncio
    async def test_publish_handles_short_signal(self) -> None:
        """Publishes short direction signals."""
        mock_redis = AsyncMock()
        publisher = SignalPublisher(mock_redis)

        signal = SignalMessage(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            direction="short",
            setup_type="VWAP_FADE",
            score=7.0,
            confidence="A",
            entry_price=2000.0,
            sl_price=2005.0,
            tp_price=1990.0,
            factors={},
        )

        with patch.object(publisher, "_publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="789-012")

            result = await publisher.publish(signal)

            assert result == "789-012"
