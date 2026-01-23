"""Unit tests for trade publisher module."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from execution_svc.trade_publisher import TradePublisher
from scp_shared.messaging.schemas import TradeMessage


def create_trade_message(
    direction: str = "long",
    closed: bool = False,
) -> TradeMessage:
    """Create a test trade message."""
    return TradeMessage(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        direction=direction,
        entry_price=2000.0,
        sl_price=1995.0 if direction == "long" else 2005.0,
        tp_price=2010.0 if direction == "long" else 1990.0,
        quantity=1,
        opened_at=datetime.now(timezone.utc),
        closed_at=datetime.now(timezone.utc) if closed else None,
        exit_price=2010.0 if closed else None,
        exit_reason="TP_HIT" if closed else None,
        pnl_points=10.0 if closed else None,
    )


class TestTradePublisher:
    """Tests for TradePublisher class."""

    @pytest.mark.asyncio
    async def test_publish_opened_returns_message_id(self) -> None:
        """Publishes opened trade and returns message ID."""
        mock_redis = AsyncMock()
        publisher = TradePublisher(mock_redis)

        trade = create_trade_message(direction="long")

        with patch.object(publisher, "_publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="123-456")

            result = await publisher.publish_opened(trade)

            assert result == "123-456"
            mock_publisher.publish.assert_called_once_with("trades.opened", trade)

    @pytest.mark.asyncio
    async def test_publish_closed_returns_message_id(self) -> None:
        """Publishes closed trade and returns message ID."""
        mock_redis = AsyncMock()
        publisher = TradePublisher(mock_redis)

        trade = create_trade_message(direction="long", closed=True)

        with patch.object(publisher, "_publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="789-012")

            result = await publisher.publish_closed(trade)

            assert result == "789-012"
            mock_publisher.publish.assert_called_once_with("trades.closed", trade)

    @pytest.mark.asyncio
    async def test_uses_default_streams(self) -> None:
        """Uses default stream names."""
        mock_redis = AsyncMock()
        publisher = TradePublisher(mock_redis)

        assert publisher._opened_stream == "trades.opened"
        assert publisher._closed_stream == "trades.closed"

    @pytest.mark.asyncio
    async def test_uses_custom_streams(self) -> None:
        """Uses custom stream names when provided."""
        mock_redis = AsyncMock()
        publisher = TradePublisher(
            mock_redis,
            opened_stream="custom.opened",
            closed_stream="custom.closed",
        )

        assert publisher._opened_stream == "custom.opened"
        assert publisher._closed_stream == "custom.closed"

    @pytest.mark.asyncio
    async def test_publish_opened_short_position(self) -> None:
        """Publishes short position opened trade."""
        mock_redis = AsyncMock()
        publisher = TradePublisher(mock_redis)

        trade = create_trade_message(direction="short")

        with patch.object(publisher, "_publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="abc-123")

            result = await publisher.publish_opened(trade)

            assert result == "abc-123"

    @pytest.mark.asyncio
    async def test_publish_closed_handles_none_pnl(self) -> None:
        """Handles trade with None pnl_points."""
        mock_redis = AsyncMock()
        publisher = TradePublisher(mock_redis)

        trade = TradeMessage(
            id=str(uuid4()),
            signal_id=str(uuid4()),
            direction="long",
            entry_price=2000.0,
            sl_price=1995.0,
            tp_price=2010.0,
            quantity=1,
            opened_at=datetime.now(timezone.utc),
            closed_at=datetime.now(timezone.utc),
            exit_price=2005.0,
            exit_reason="MANUAL",
            pnl_points=None,  # No P&L calculated
        )

        with patch.object(publisher, "_publisher") as mock_publisher:
            mock_publisher.publish = AsyncMock(return_value="def-456")

            # Should not raise even with None pnl
            result = await publisher.publish_closed(trade)

            assert result == "def-456"
