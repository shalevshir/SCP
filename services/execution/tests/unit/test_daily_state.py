"""Unit tests for daily state tracker."""

from datetime import date

import pytest

from execution_svc.daily_state import DailyState, DailyStateTracker


class TestDailyState:
    """Test DailyState dataclass."""
    
    def test_default_values(self) -> None:
        """Test default values are initialized correctly."""
        state = DailyState(date=date(2025, 1, 15))
        
        assert state.date == date(2025, 1, 15)
        assert state.daily_pnl == 0.0
        assert state.trades_count == 0
        assert state.pdll_hit is False


class TestDailyStateTracker:
    """Test DailyStateTracker."""
    
    def test_initialization(self) -> None:
        """Test tracker initializes with correct defaults."""
        tracker = DailyStateTracker(pdll_limit=600.0, max_trades_per_day=2)
        
        assert tracker.pdll_limit == 600.0
        assert tracker.max_trades_per_day == 2
        assert tracker.state.daily_pnl == 0.0
        assert tracker.state.trades_count == 0
        assert tracker.state.pdll_hit is False
    
    def test_can_trade_returns_true_initially(self) -> None:
        """Test can_trade returns True when no limits hit."""
        tracker = DailyStateTracker()
        
        can_trade, reason = tracker.can_trade()
        
        assert can_trade is True
        assert reason is None
    
    def test_can_trade_blocks_after_pdll_hit(self) -> None:
        """Test can_trade blocks trading after PDLL limit reached."""
        tracker = DailyStateTracker(pdll_limit=600.0)
        
        # Simulate losses exceeding PDLL
        tracker.record_trade_closed(-400.0)
        tracker.record_trade_closed(-250.0)  # Total: -650
        
        can_trade, reason = tracker.can_trade()
        
        assert can_trade is False
        assert "PDLL" in reason
        assert tracker.state.pdll_hit is True
    
    def test_can_trade_blocks_exactly_at_pdll_limit(self) -> None:
        """Test can_trade blocks when daily P&L equals negative PDLL limit."""
        tracker = DailyStateTracker(pdll_limit=600.0)
        
        tracker.record_trade_closed(-600.0)  # Exactly at limit
        
        can_trade, reason = tracker.can_trade()
        
        assert can_trade is False
        assert "PDLL" in reason
    
    def test_can_trade_allows_when_below_pdll_limit(self) -> None:
        """Test can_trade allows trading when P&L is above negative PDLL."""
        tracker = DailyStateTracker(pdll_limit=600.0)
        
        tracker.record_trade_closed(-500.0)  # Below limit
        
        can_trade, reason = tracker.can_trade()
        
        assert can_trade is True
        assert reason is None
    
    def test_can_trade_blocks_after_max_trades_per_day(self) -> None:
        """Test can_trade blocks after max trades per day reached."""
        tracker = DailyStateTracker(max_trades_per_day=2)
        
        tracker.record_trade_opened()
        tracker.record_trade_opened()  # Max reached
        
        can_trade, reason = tracker.can_trade()
        
        assert can_trade is False
        assert reason == "MAX_TRADES"
    
    def test_pdll_blocks_before_trade_limit(self) -> None:
        """Test PDLL takes priority over trade count limit."""
        tracker = DailyStateTracker(pdll_limit=600.0, max_trades_per_day=5)
        
        # Hit PDLL but not trade limit
        tracker.record_trade_closed(-700.0)
        tracker.record_trade_opened()  # Only 1 trade, limit is 5
        
        can_trade, reason = tracker.can_trade()
        
        assert can_trade is False
        assert "PDLL" in reason  # PDLL reason, not trade limit
    
    def test_record_trade_closed_accumulates_pnl(self) -> None:
        """Test record_trade_closed accumulates P&L correctly."""
        tracker = DailyStateTracker()
        
        tracker.record_trade_closed(50.0)   # Win
        tracker.record_trade_closed(-30.0)  # Loss
        tracker.record_trade_closed(20.0)   # Win
        
        assert tracker.state.daily_pnl == 40.0
    
    def test_check_session_reset_resets_state_on_date_change(self) -> None:
        """Test check_session_reset resets state at date boundary."""
        tracker = DailyStateTracker()
        
        # Simulate trading activity
        tracker.record_trade_opened()
        tracker.record_trade_closed(-100.0)
        tracker._state.pdll_hit = True
        
        # Change date
        new_date = date(2025, 1, 16)
        tracker.check_session_reset(new_date)
        
        # State should be reset
        assert tracker.state.date == new_date
        assert tracker.state.daily_pnl == 0.0
        assert tracker.state.trades_count == 0
        assert tracker.state.pdll_hit is False
    
    def test_check_session_reset_no_change_on_same_date(self) -> None:
        """Test check_session_reset does nothing when date hasn't changed."""
        tracker = DailyStateTracker()
        current_date = date.today()
        
        tracker.record_trade_opened()
        tracker.record_trade_closed(-50.0)
        
        # Check with same date
        tracker.check_session_reset(current_date)
        
        # State should NOT be reset
        assert tracker.state.trades_count == 1
        assert tracker.state.daily_pnl == -50.0
    
    def test_pdll_hit_flag_persists_until_session_reset(self) -> None:
        """Test PDLL hit flag persists even if P&L improves."""
        tracker = DailyStateTracker(pdll_limit=600.0)
        
        # Hit PDLL
        tracker.record_trade_closed(-700.0)
        tracker.can_trade()  # Triggers pdll_hit flag
        
        assert tracker.state.pdll_hit is True
        
        # Even if P&L improves, flag stays set
        tracker.record_trade_closed(200.0)  # Now at -500
        
        can_trade, reason = tracker.can_trade()
        assert can_trade is False  # Still blocked
        assert reason == "PDLL"





