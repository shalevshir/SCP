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

    def test_session_reset_clears_consecutive_losses(self, base_trade: TradeRecord) -> None:
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
            entry_timestamp=datetime(2024, 3, 16, 10, 0, tzinfo=timezone.utc),  # Next day
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
            entry_timestamp=datetime(2024, 3, 16, 10, 0, tzinfo=timezone.utc),  # Next day
            entry_bar_idx=200,
            reached_1r=False,
        )
        checker.record_trade_outcome(trade_day2, won=True)
        
        # Daily PnL should be reset
        assert checker._daily_state["daily_pnl"] == 0.0

    def test_last_session_date_updated(self, base_trade: TradeRecord) -> None:
        """Test that last_session_date is updated on trade outcome."""
        checker = InvalidationChecker()
        
        checker.record_trade_outcome(base_trade, won=True)
        
        assert checker._daily_state["last_session_date"] == base_trade.entry_timestamp.date()

