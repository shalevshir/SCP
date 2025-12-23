"""Unit tests for broker base module dataclasses."""

from datetime import datetime, timezone

from execution_svc.broker.base import OrderResult, Position


class TestOrderResult:
    """Tests for OrderResult dataclass."""

    def test_creates_with_defaults(self) -> None:
        """Creates OrderResult with default values."""
        result = OrderResult(
            order_id="test-123",
            symbol="GC",
            side="long",
            quantity=1,
        )
        
        assert result.order_id == "test-123"
        assert result.symbol == "GC"
        assert result.side == "long"
        assert result.quantity == 1
        assert result.filled_price is None
        assert result.filled_at is None
        assert result.status == "pending"

    def test_creates_with_all_fields(self) -> None:
        """Creates OrderResult with all fields."""
        now = datetime.now(timezone.utc)
        result = OrderResult(
            order_id="test-456",
            symbol="SI",
            side="short",
            quantity=2,
            filled_price=30.5,
            filled_at=now,
            status="filled",
        )
        
        assert result.filled_price == 30.5
        assert result.filled_at == now
        assert result.status == "filled"


class TestPosition:
    """Tests for Position dataclass."""

    def test_creates_with_defaults(self) -> None:
        """Creates Position with default values."""
        position = Position(
            symbol="GC",
            side="long",
            quantity=1,
            entry_price=2650.0,
        )
        
        assert position.symbol == "GC"
        assert position.side == "long"
        assert position.quantity == 1
        assert position.entry_price == 2650.0
        assert position.unrealized_pnl == 0.0

    def test_creates_with_unrealized_pnl(self) -> None:
        """Creates Position with unrealized P&L."""
        position = Position(
            symbol="GC",
            side="long",
            quantity=1,
            entry_price=2650.0,
            unrealized_pnl=15.0,
        )
        
        assert position.unrealized_pnl == 15.0

    def test_short_position(self) -> None:
        """Creates short position."""
        position = Position(
            symbol="GC",
            side="short",
            quantity=2,
            entry_price=2660.0,
        )
        
        assert position.side == "short"
        assert position.quantity == 2
