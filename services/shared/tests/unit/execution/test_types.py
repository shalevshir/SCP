"""Unit tests for execution types module."""

from datetime import datetime, timezone

from scp_shared.execution.types import TradeRecord


class TestTradeRecord:
    """Tests for TradeRecord dataclass."""

    def test_creates_with_required_fields(self) -> None:
        """Creates TradeRecord with required fields."""
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=5.0,
            reward_amount=10.0,
            entry_timestamp=now,
        )

        assert trade.trade_id == "trade-123"
        assert trade.signal_id == "signal-456"
        assert trade.symbol == "GC"
        assert trade.direction == "long"
        assert trade.setup_type == "VWAP_RECLAIM"
        assert trade.entry_price == 2650.0
        assert trade.sl_price == 2645.0
        assert trade.tp_price == 2660.0
        assert trade.risk_amount == 5.0
        assert trade.reward_amount == 10.0

    def test_default_values(self) -> None:
        """Default optional fields are None/False."""
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=5.0,
            reward_amount=10.0,
            entry_timestamp=now,
        )

        assert trade.exit_timestamp is None
        assert trade.exit_price is None
        assert trade.exit_reason is None
        assert trade.pnl is None
        assert trade.entry_bar_idx is None
        assert trade.reached_1r is False

    def test_creates_with_optional_fields(self) -> None:
        """Creates TradeRecord with optional fields."""
        entry_time = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="short",
            setup_type="VWAP_FADE",
            entry_price=2650.0,
            sl_price=2655.0,
            tp_price=2640.0,
            risk_amount=5.0,
            reward_amount=10.0,
            entry_timestamp=entry_time,
            exit_timestamp=exit_time,
            exit_price=2640.0,
            exit_reason="TP_HIT",
            pnl=10.0,
            entry_bar_idx=100,
            reached_1r=True,
        )

        assert trade.exit_timestamp == exit_time
        assert trade.exit_price == 2640.0
        assert trade.exit_reason == "TP_HIT"
        assert trade.pnl == 10.0
        assert trade.entry_bar_idx == 100
        assert trade.reached_1r is True

    def test_supports_dxy_continuation_setup(self) -> None:
        """Supports DXY_CONTINUATION setup type."""
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-789",
            signal_id="signal-012",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=5.0,
            reward_amount=10.0,
            entry_timestamp=now,
        )

        assert trade.setup_type == "DXY_CONTINUATION"
