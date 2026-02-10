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
            quantity=1,
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
            quantity=1,
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
            quantity=1,
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
            quantity=1,
        entry_timestamp=now,
        )

        assert trade.setup_type == "DXY_CONTINUATION"

    def test_risk_points_field_defaults_to_none(self) -> None:
        """risk_points field defaults to None."""
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,  # money
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=now,
        )

        assert trade.risk_points is None

    def test_risk_points_can_be_set(self) -> None:
        """risk_points can be set at entry."""
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,  # 5 points risk
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=now,
            risk_points=5.0,  # CRITICAL: in price units, not money
        )

        assert trade.risk_points == 5.0

    def test_be_tracking_fields_default_values(self) -> None:
        """BE tracking fields have correct defaults."""
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=now,
        )

        # BE tracking defaults
        assert trade.be_set is False
        assert trade.be_price is None
        assert trade.be_set_bar_idx is None
        assert trade.tp1_hit_bar_idx is None

    def test_be_buffer_calculation_uses_risk_points(self) -> None:
        """BE buffer calculated from risk_points, not risk_amount.

        CRITICAL: BE buffer is 0.1R in PRICE units.
        - risk_points = abs(entry - sl) = 5.0 points
        - BE buffer = 0.1 * 5.0 = 0.5 points
        - BE price (long) = entry + buffer = 2650.0 + 0.5 = 2650.5
        """
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,  # money - NOT used for BE calculation
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=now,
            risk_points=5.0,  # price points - USED for BE calculation
        )

        # Calculate BE price correctly
        be_buffer_r = 0.1
        be_buffer_points = be_buffer_r * trade.risk_points  # 0.1 * 5.0 = 0.5
        expected_be_price = trade.entry_price + be_buffer_points  # 2650.0 + 0.5 = 2650.5

        # Simulate setting BE
        trade.be_set = True
        trade.be_price = expected_be_price
        trade.be_set_bar_idx = 50

        assert trade.be_set is True
        assert trade.be_price == 2650.5
        assert trade.be_set_bar_idx == 50

    def test_phase2_runner_fields_default_values(self) -> None:
        """Phase-2 runner unlock fields have correct defaults."""
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=now,
        )

        # Phase-2 runner fields defaults
        assert trade.runner_unlocked is False
        assert trade.runner_unlock_mode is None
        assert trade.runner_unlock_bar_idx is None
        assert trade.runner_exited_at_market is False
        assert trade.tp2_price is None

    def test_phase2_runner_unlock_flow(self) -> None:
        """Phase-2 runner unlock state transitions."""
        now = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2655.0,  # TP1 at 1R
            risk_amount=500.0,
            reward_amount=500.0,
            quantity=1,
        entry_timestamp=now,
            risk_points=5.0,
            tp2_price=2665.0,  # TP2 at 3R (set at signal time)
        )

        # Initial state
        assert trade.partial_taken is False
        assert trade.runner_unlocked is False

        # Simulate TP1 hit (40% partial, BE set)
        trade.partial_taken = True
        trade.tp1_hit_bar_idx = 25
        trade.be_set = True
        trade.be_price = 2650.5  # entry + 0.1R buffer
        trade.be_set_bar_idx = 25

        # Simulate runner unlock (BOS detected at bar 30)
        trade.runner_unlocked = True
        trade.runner_unlock_mode = "micro_bos"
        trade.runner_unlock_bar_idx = 30

        assert trade.partial_taken is True
        assert trade.runner_unlocked is True
        assert trade.runner_unlock_mode == "micro_bos"
        assert trade.runner_unlock_bar_idx == 30
        # TP effectively becomes TP2
        assert trade.tp2_price == 2665.0
