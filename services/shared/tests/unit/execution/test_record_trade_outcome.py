"""Tests for InvalidationChecker.record_trade_outcome() method."""

from datetime import datetime, timezone
import pytest

from scp_shared.execution import InvalidationChecker
from scp_shared.execution.types import TradeRecord


@pytest.fixture
def base_trade() -> TradeRecord:
    """Create a base trade for testing."""
    return TradeRecord(
        trade_id="test-trade-1",
        signal_id="signal-1",
        symbol="GC",
        direction="long",
        setup_type="VWAP_RECLAIM",
        entry_price=2000.0,
        sl_price=1990.0,
        tp_price=2020.0,
        risk_amount=10.0,
        reward_amount=20.0,
        quantity=1,
        entry_timestamp=datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc),
        entry_bar_idx=100,
        reached_1r=False,
    )


class TestRecordTradeOutcome:
    """Test suite for record_trade_outcome() method."""

    def test_loss_increments_consecutive_losses(self, base_trade: TradeRecord) -> None:
        """Test that a loss increments consecutive_losses counter."""
        checker = InvalidationChecker()

        # Record a loss
        checker.record_trade_outcome(base_trade, won=False)

        # Verify consecutive losses incremented
        assert checker._daily_state["consecutive_losses"] == 1

    def test_multiple_losses_increment_streak(self, base_trade: TradeRecord) -> None:
        """Test that multiple losses increment the streak."""
        checker = InvalidationChecker()

        # Record two losses
        checker.record_trade_outcome(base_trade, won=False)
        assert checker._daily_state["consecutive_losses"] == 1

        checker.record_trade_outcome(base_trade, won=False)
        assert checker._daily_state["consecutive_losses"] == 2

        checker.record_trade_outcome(base_trade, won=False)
        assert checker._daily_state["consecutive_losses"] == 3

    def test_win_resets_consecutive_losses(self, base_trade: TradeRecord) -> None:
        """Test that a win resets consecutive losses to 0."""
        checker = InvalidationChecker()

        # Build up a loss streak
        checker.record_trade_outcome(base_trade, won=False)
        checker.record_trade_outcome(base_trade, won=False)
        assert checker._daily_state["consecutive_losses"] == 2

        # Win should reset
        checker.record_trade_outcome(base_trade, won=True)
        assert checker._daily_state["consecutive_losses"] == 0

    def test_breakeven_does_not_affect_streak(self, base_trade: TradeRecord) -> None:
        """Test that breakeven (won=None) doesn't change the loss streak."""
        checker = InvalidationChecker()

        # Build up a loss streak
        checker.record_trade_outcome(base_trade, won=False)
        checker.record_trade_outcome(base_trade, won=False)
        assert checker._daily_state["consecutive_losses"] == 2

        # Breakeven should NOT change streak
        checker.record_trade_outcome(base_trade, won=None)
        assert checker._daily_state["consecutive_losses"] == 2

    def test_session_reset_clears_consecutive_losses(
        self, base_trade: TradeRecord
    ) -> None:
        """Test that a new session date resets consecutive losses."""
        checker = InvalidationChecker()

        # Record losses on day 1
        trade_day1 = base_trade
        checker.record_trade_outcome(trade_day1, won=False)
        checker.record_trade_outcome(trade_day1, won=False)
        assert checker._daily_state["consecutive_losses"] == 2

        # New day should reset
        trade_day2 = TradeRecord(
            trade_id="test-trade-2",
            signal_id="signal-2",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2000.0,
            sl_price=1990.0,
            tp_price=2020.0,
            risk_amount=10.0,
            reward_amount=20.0,
            quantity=1,
        entry_timestamp=datetime(
                2024, 3, 16, 10, 0, tzinfo=timezone.utc
            ),  # Next day
            entry_bar_idx=200,
            reached_1r=False,
        )
        checker.record_trade_outcome(trade_day2, won=False)
        assert checker._daily_state["consecutive_losses"] == 1  # Reset to 1 (new day)

    def test_session_reset_clears_daily_pnl(self, base_trade: TradeRecord) -> None:
        """Test that a new session date resets daily PnL."""
        checker = InvalidationChecker()

        # Set some daily PnL on day 1
        checker._daily_state["daily_pnl"] = -50.0
        checker._daily_state["last_session_date"] = datetime(2024, 3, 15).date()

        # Record trade on new day
        trade_day2 = TradeRecord(
            trade_id="test-trade-2",
            signal_id="signal-2",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2000.0,
            sl_price=1990.0,
            tp_price=2020.0,
            risk_amount=10.0,
            reward_amount=20.0,
            quantity=1,
        entry_timestamp=datetime(
                2024, 3, 16, 10, 0, tzinfo=timezone.utc
            ),  # Next day
            entry_bar_idx=200,
            reached_1r=False,
        )
        checker.record_trade_outcome(trade_day2, won=True)

        # Daily PnL should be reset
        assert checker._daily_state["daily_pnl"] == 0.0

    def test_last_session_date_updated(self, base_trade: TradeRecord) -> None:
        """Test that last_session_date is updated on trade outcome."""
        checker = InvalidationChecker()

        # Without close_timestamp, falls back to entry_timestamp (backward compatibility)
        checker.record_trade_outcome(base_trade, won=True)

        assert (
            checker._daily_state["last_session_date"]
            == base_trade.entry_timestamp.date()
        )

        # With close_timestamp, uses close date
        close_time = datetime(2024, 3, 16, 10, 0, tzinfo=timezone.utc)
        checker.record_trade_outcome(base_trade, won=True, close_timestamp=close_time)

        assert checker._daily_state["last_session_date"] == close_time.date()

    def test_record_trade_outcome_updates_daily_pnl(
        self, base_trade: TradeRecord
    ) -> None:
        """Test that record_trade_outcome updates daily_pnl when pnl_points is provided."""
        checker = InvalidationChecker()

        # Record a loss with PnL
        checker.record_trade_outcome(base_trade, won=False, pnl_points=-50.0)
        assert checker._daily_state["daily_pnl"] == -50.0

        # Record another loss
        checker.record_trade_outcome(base_trade, won=False, pnl_points=-30.0)
        assert checker._daily_state["daily_pnl"] == -80.0  # Accumulated

        # Record a win
        checker.record_trade_outcome(base_trade, won=True, pnl_points=100.0)
        assert checker._daily_state["daily_pnl"] == 20.0  # -80 + 100

    def test_record_trade_outcome_without_pnl_points(
        self, base_trade: TradeRecord
    ) -> None:
        """Test that record_trade_outcome works without pnl_points (backward compatibility)."""
        checker = InvalidationChecker()

        # Record without pnl_points - should only update loss streak
        checker.record_trade_outcome(base_trade, won=False)
        assert checker._daily_state["daily_pnl"] == 0.0  # Unchanged
        assert checker._daily_state["consecutive_losses"] == 1  # Updated

    def test_trade_spanning_multiple_days_uses_close_date(
        self, base_trade: TradeRecord
    ) -> None:
        """Test that trade opened Day 1, closed Day 2 uses Day 2's date for session tracking.

        This is a bug fix: previously used entry_timestamp.date() which would attribute
        the outcome to Day 1 instead of Day 2 (when it actually closed).
        """
        checker = InvalidationChecker()

        # Trade opened on Day 1
        trade_opened_day1 = TradeRecord(
            trade_id="test-trade-day1",
            signal_id="signal-1",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2000.0,
            sl_price=1990.0,
            tp_price=2020.0,
            risk_amount=10.0,
            reward_amount=20.0,
            quantity=1,
        entry_timestamp=datetime(
                2024, 3, 15, 22, 0, tzinfo=timezone.utc
            ),  # Day 1, late evening
            entry_bar_idx=100,
            reached_1r=False,
            exit_timestamp=datetime(
                2024, 3, 16, 2, 0, tzinfo=timezone.utc
            ),  # Day 2, early morning
        )

        # Record outcome - should use Day 2's date (close date), not Day 1's entry date
        checker.record_trade_outcome(
            trade_opened_day1,
            won=False,
            pnl_points=-50.0,
            close_timestamp=trade_opened_day1.exit_timestamp,
        )

        # Session date should be Day 2 (when it closed), not Day 1 (when it opened)
        assert checker._daily_state["last_session_date"] == datetime(2024, 3, 16).date()
        assert checker._daily_state["consecutive_losses"] == 1
        assert checker._daily_state["daily_pnl"] == -50.0

        # If we record another trade that closes on Day 2, it should NOT reset
        # (because we're still on Day 2)
        trade2_day2 = TradeRecord(
            trade_id="test-trade-day2",
            signal_id="signal-2",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2000.0,
            sl_price=1990.0,
            tp_price=2020.0,
            risk_amount=10.0,
            reward_amount=20.0,
            quantity=1,
        entry_timestamp=datetime(
                2024, 3, 15, 20, 0, tzinfo=timezone.utc
            ),  # Also opened Day 1
            entry_bar_idx=200,
            reached_1r=False,
            exit_timestamp=datetime(
                2024, 3, 16, 10, 0, tzinfo=timezone.utc
            ),  # Closed Day 2
        )

        checker.record_trade_outcome(
            trade2_day2,
            won=False,
            pnl_points=-30.0,
            close_timestamp=trade2_day2.exit_timestamp,
        )

        # Should still be Day 2, streak should continue (not reset)
        assert checker._daily_state["last_session_date"] == datetime(2024, 3, 16).date()
        assert (
            checker._daily_state["consecutive_losses"] == 2
        )  # Continued from previous loss
        assert checker._daily_state["daily_pnl"] == -80.0  # Accumulated: -50 + -30

    def test_interleaved_trades_from_different_entry_dates(self) -> None:
        """Test that trades from different entry dates closing on same day don't flip-flop session.

        Bug scenario: Trade A opened Day 1, Trade B opened Day 2, both close Day 2.
        Using entry_timestamp would cause session date to flip between Day 1 and Day 2.
        Using close_timestamp ensures both are attributed to Day 2.
        """
        checker = InvalidationChecker()

        # Trade A: opened Day 1, closes Day 2
        trade_a = TradeRecord(
            trade_id="trade-a",
            signal_id="signal-a",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2000.0,
            sl_price=1990.0,
            tp_price=2020.0,
            risk_amount=10.0,
            reward_amount=20.0,
            quantity=1,
        entry_timestamp=datetime(2024, 3, 15, 22, 0, tzinfo=timezone.utc),  # Day 1
            entry_bar_idx=100,
            reached_1r=False,
            exit_timestamp=datetime(2024, 3, 16, 10, 0, tzinfo=timezone.utc),  # Day 2
        )

        # Trade B: opened Day 2, closes Day 2
        trade_b = TradeRecord(
            trade_id="trade-b",
            signal_id="signal-b",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2000.0,
            sl_price=1990.0,
            tp_price=2020.0,
            risk_amount=10.0,
            reward_amount=20.0,
            quantity=1,
        entry_timestamp=datetime(2024, 3, 16, 8, 0, tzinfo=timezone.utc),  # Day 2
            entry_bar_idx=200,
            reached_1r=False,
            exit_timestamp=datetime(2024, 3, 16, 12, 0, tzinfo=timezone.utc),  # Day 2
        )

        # Record Trade A first (opened Day 1, closes Day 2)
        checker.record_trade_outcome(
            trade_a, won=False, pnl_points=-50.0, close_timestamp=trade_a.exit_timestamp
        )
        assert checker._daily_state["last_session_date"] == datetime(2024, 3, 16).date()
        assert checker._daily_state["consecutive_losses"] == 1

        # Record Trade B (opened Day 2, closes Day 2)
        # Should NOT reset because we're still on Day 2 (same close date)
        checker.record_trade_outcome(
            trade_b, won=False, pnl_points=-30.0, close_timestamp=trade_b.exit_timestamp
        )

        # Session should still be Day 2, streak should continue
        assert checker._daily_state["last_session_date"] == datetime(2024, 3, 16).date()
        assert checker._daily_state["consecutive_losses"] == 2  # Continued, not reset
        assert checker._daily_state["daily_pnl"] == -80.0  # Accumulated
