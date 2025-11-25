"""Unit tests for InvalidationChecker - trade invalidation detection.

Following TDD principles: tests written first to define behavior.
"""

from datetime import UTC, datetime

import pytest
from backtester.entry_model import EntryExecution
from backtester.invalidations import InvalidationChecker
from backtester.trade import Trade
from common.types import Candle
from rule_engine.signal import Signal


def make_candle(
    timestamp: datetime,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100,
    symbol: str = "GC",
    timeframe: str = "1m",
    source: str = "TEST",
) -> Candle:
    """Helper to create test candles with default values."""
    return Candle(
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        symbol=symbol,
        timeframe=timeframe,
        source=source,
    )


class TestInvalidationChecker:
    """Tests for InvalidationChecker class."""

    @pytest.fixture
    def long_continuation_trade(self):
        """Create a long continuation trade for testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
        )

    @pytest.fixture
    def short_fade_trade(self):
        """Create a short fade trade for testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="Mild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-002",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="short",
            setup_type="VWAP_FADE",
            stop_loss=2655.0,
            take_profit=2640.0,
            sl_rationale="Above sweep",
            tp_rationale="2R fade",
            risk_amount=5.0,
            reward_amount=10.0,
            r_multiple=2.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
        )

    def test_no_1r_reached_continuation(self, long_continuation_trade):
        """Test invalidation when +1R not reached within 20 bars for continuation."""
        checker = InvalidationChecker()
        
        # Candle at 19 bars, price hasn't reached +1R (entry + risk = 2655)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 20, tzinfo=UTC),
            open=2652.0,
            high=2653.0,
            low=2651.0,
            close=2652.0,
        )
        
        is_invalid, reason = checker.check_all(long_continuation_trade, candle, 20)
        
        assert is_invalid is True
        assert "1R not reached" in reason

    def test_no_1r_reached_fade(self, short_fade_trade):
        """Test invalidation when +1R not reached within 10 bars for fade."""
        checker = InvalidationChecker()
        
        # Candle at 10 bars, price hasn't reached +1R (entry - risk = 2645)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 11, tzinfo=UTC),
            open=2649.0,
            high=2650.0,
            low=2648.0,
            close=2649.0,
        )
        
        is_invalid, reason = checker.check_all(short_fade_trade, candle, 10)
        
        assert is_invalid is True
        assert "1R not reached" in reason

    def test_1r_reached_no_invalidation(self, long_continuation_trade):
        """Test no invalidation when +1R is reached within time limit."""
        checker = InvalidationChecker()
        
        # Candle at 15 bars, price has reached +1R (2655+)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 16, tzinfo=UTC),
            open=2656.0,
            high=2657.0,
            low=2655.0,
            close=2656.0,
        )
        
        # Mark that +1R was reached
        checker.update_state(long_continuation_trade, candle)
        
        # Now check at 20 bars
        is_invalid, reason = checker.check_all(long_continuation_trade, candle, 20)
        
        assert is_invalid is False
        assert reason is None

    def test_no_invalidation_before_time_limit(self, long_continuation_trade):
        """Test no invalidation before time limit is reached."""
        checker = InvalidationChecker()
        
        # Candle at 15 bars (before 20 bar limit)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 16, tzinfo=UTC),
            open=2652.0,
            high=2653.0,
            low=2651.0,
            close=2652.0,
        )
        
        is_invalid, reason = checker.check_all(long_continuation_trade, candle, 15)
        
        assert is_invalid is False
        assert reason is None

    def test_update_state_tracks_1r_reached(self, long_continuation_trade):
        """Test that update_state tracks when +1R is reached."""
        checker = InvalidationChecker()
        
        # First candle - no +1R yet
        candle1 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2652.0,
            high=2653.0,
            low=2651.0,
            close=2652.0,
        )
        checker.update_state(long_continuation_trade, candle1)
        
        # Check that +1R not reached yet
        state = checker._get_trade_state(long_continuation_trade.trade_id)
        assert state["reached_1r"] is False
        
        # Second candle - reaches +1R (2655+)
        candle2 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
            open=2655.0,
            high=2656.0,
            low=2654.0,
            close=2655.5,
        )
        checker.update_state(long_continuation_trade, candle2)
        
        # Check that +1R is now reached
        state = checker._get_trade_state(long_continuation_trade.trade_id)
        assert state["reached_1r"] is True

    def test_multiple_trades_tracked_independently(
        self, long_continuation_trade, short_fade_trade
    ):
        """Test that multiple trades are tracked independently."""
        checker = InvalidationChecker()
        
        # Update state for both trades
        candle1 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2655.0,
            high=2656.0,
            low=2654.0,
            close=2655.5,
        )
        checker.update_state(long_continuation_trade, candle1)  # Reaches +1R
        
        candle2 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2649.0,
            high=2650.0,
            low=2648.0,
            close=2649.0,
        )
        checker.update_state(short_fade_trade, candle2)  # Doesn't reach +1R
        
        # Check states
        state1 = checker._get_trade_state(long_continuation_trade.trade_id)
        state2 = checker._get_trade_state(short_fade_trade.trade_id)
        
        assert state1["reached_1r"] is True
        assert state2["reached_1r"] is False

    def test_check_all_with_no_features(self, long_continuation_trade):
        """Test check_all works without optional features (minimal mode)."""
        checker = InvalidationChecker()
        
        # Candle at 15 bars (before time limit)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 16, tzinfo=UTC),
            open=2652.0,
            high=2653.0,
            low=2651.0,
            close=2652.0,
        )
        
        # Should not invalidate without features
        is_invalid, reason = checker.check_all(
            long_continuation_trade, candle, 15, features=None
        )
        
        assert is_invalid is False
        assert reason is None


class TestInvalidationCheckerWithFeatures:
    """Tests for InvalidationChecker with feature-based checks.
    
    These tests will be implemented once we add DXY, VWAP, HTF invalidation checks.
    For now, we'll keep the checker minimal and focus on the +1R time limit.
    """

    def test_placeholder(self):
        """Placeholder for future feature-based invalidation tests."""
        # TODO: Add tests for:
        # - DXY flip invalidation
        # - VWAP invalidation (continuation trades)
        # - Structure break invalidation
        # - HTF bias flip invalidation
        # - Session end invalidation
        pass

