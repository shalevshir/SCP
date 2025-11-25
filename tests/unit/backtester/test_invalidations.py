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


class TestVWAPInvalidation:
    """Tests for VWAP invalidation detection."""

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

    def test_vwap_invalidation_long_below_vwap(self, long_continuation_trade):
        """Test VWAP invalidation for long when close < VWAP."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2647.0,
            close=2648.0,  # Below VWAP
        )
        
        features = {"vwap": 2650.0}
        
        is_invalid, reason = checker.check_vwap_invalidation(
            long_continuation_trade, candle, features
        )
        
        assert is_invalid is True
        assert "vwap" in reason.lower()
        assert "invalidation" in reason.lower()

    def test_vwap_invalidation_not_triggered_above_vwap(self, long_continuation_trade):
        """Test VWAP invalidation not triggered when close > VWAP."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2652.0,
            high=2653.0,
            low=2651.0,
            close=2652.0,  # Above VWAP
        )
        
        features = {"vwap": 2650.0}
        
        is_invalid, reason = checker.check_vwap_invalidation(
            long_continuation_trade, candle, features
        )
        
        assert is_invalid is False
        assert reason is None

    def test_vwap_invalidation_not_applicable_to_dxy_continuation(self):
        """Test VWAP invalidation doesn't apply to DXY_CONTINUATION setups."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
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
        trade = Trade(
            trade_id="test-dxy",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="DXY_CONTINUATION",
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
        
        checker = InvalidationChecker()
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2647.0,
            close=2648.0,
        )
        features = {"vwap": 2650.0}
        
        is_invalid, reason = checker.check_vwap_invalidation(trade, candle, features)
        
        assert is_invalid is False
        assert reason is None


class TestSessionEnd:
    """Tests for session end detection."""

    @pytest.fixture
    def long_trade(self):
        """Create a long trade for testing."""
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
            trade_id="test-session",
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

    def test_session_end_at_13_00_ilt(self, long_trade):
        """Test session end detection at 13:00 ILT."""
        from zoneinfo import ZoneInfo
        
        checker = InvalidationChecker()
        
        # 13:00 ILT = 13:00 UTC (during winter) or 12:00 UTC (during summer)
        # Use 13:00 UTC for simplicity (winter time)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 13, 0, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        is_invalid, reason = checker.check_session_end(long_trade, candle)
        
        assert is_invalid is True
        assert "session" in reason.lower()

    def test_session_end_not_triggered_during_session(self, long_trade):
        """Test session end not triggered during active session."""
        checker = InvalidationChecker()
        
        # 11:00 UTC = 11:00 ILT (during winter) - within session
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        is_invalid, reason = checker.check_session_end(long_trade, candle)
        
        assert is_invalid is False
        assert reason is None


class TestInvalidationCheckerWithFeatures:
    """Tests for InvalidationChecker with feature-based checks.
    
    These tests cover the integrated invalidation checks.
    """

    def test_check_all_with_vwap_invalidation(self):
        """Test check_all detects VWAP invalidation."""
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
        trade = Trade(
            trade_id="test-all",
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
        
        checker = InvalidationChecker()
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2647.0,
            close=2648.0,  # Below VWAP
        )
        features = {"vwap": 2650.0}
        
        is_invalid, reason = checker.check_all(trade, candle, bars_elapsed=5, features=features)
        
        assert is_invalid is True
        assert "vwap" in reason.lower()


class TestHTFStructureInvalidation:
    """Tests for HTF structure invalidation detection."""

    @pytest.fixture
    def long_trade_bullish_bias(self):
        """Create a long trade with bullish HTF bias."""
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
            trade_id="test-htf-1",
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
    def long_trade_bearish_bias(self):
        """Create a long trade with bearish HTF bias (misaligned trade)."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bearish",  # Misaligned: long trade with bearish bias
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
            trade_id="test-htf-2",
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
    def short_trade_bearish_bias(self):
        """Create a short trade with bearish HTF bias."""
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
            trade_id="test-htf-3",
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

    @pytest.fixture
    def short_trade_bullish_bias(self):
        """Create a short trade with bullish HTF bias (misaligned trade)."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bullish",  # Misaligned: short trade with bullish bias
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
            trade_id="test-htf-4",
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

    def test_long_trade_invalidated_by_lh_structure_bullish_bias(
        self, long_trade_bullish_bias
    ):
        """Test long trade with bullish bias invalidated by LH structure break."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "LH"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            long_trade_bullish_bias, candle, features
        )
        
        assert is_invalid is True
        assert "htf structure" in reason.lower()
        assert "lh" in reason.lower()

    def test_long_trade_invalidated_by_ll_structure_bullish_bias(
        self, long_trade_bullish_bias
    ):
        """Test long trade with bullish bias invalidated by LL structure break."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "LL"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            long_trade_bullish_bias, candle, features
        )
        
        assert is_invalid is True
        assert "htf structure" in reason.lower()
        assert "ll" in reason.lower()

    def test_long_trade_invalidated_by_lh_structure_bearish_bias(
        self, long_trade_bearish_bias
    ):
        """Test long trade with bearish bias invalidated by LH structure break.
        
        This test verifies the bug fix: long trades should be invalidated by
        bearish structure breaks (LH, LL) regardless of entry bias.
        """
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "LH"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            long_trade_bearish_bias, candle, features
        )
        
        assert is_invalid is True, (
            "Long trade should be invalidated by LH structure break "
            "regardless of entry bias"
        )
        assert "htf structure" in reason.lower()
        assert "lh" in reason.lower()

    def test_long_trade_invalidated_by_ll_structure_bearish_bias(
        self, long_trade_bearish_bias
    ):
        """Test long trade with bearish bias invalidated by LL structure break.
        
        This test verifies the bug fix: long trades should be invalidated by
        bearish structure breaks (LH, LL) regardless of entry bias.
        """
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "LL"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            long_trade_bearish_bias, candle, features
        )
        
        assert is_invalid is True, (
            "Long trade should be invalidated by LL structure break "
            "regardless of entry bias"
        )
        assert "htf structure" in reason.lower()
        assert "ll" in reason.lower()

    def test_short_trade_invalidated_by_hh_structure_bearish_bias(
        self, short_trade_bearish_bias
    ):
        """Test short trade with bearish bias invalidated by HH structure break."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "HH"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            short_trade_bearish_bias, candle, features
        )
        
        assert is_invalid is True
        assert "htf structure" in reason.lower()
        assert "hh" in reason.lower()

    def test_short_trade_invalidated_by_hl_structure_bearish_bias(
        self, short_trade_bearish_bias
    ):
        """Test short trade with bearish bias invalidated by HL structure break."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "HL"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            short_trade_bearish_bias, candle, features
        )
        
        assert is_invalid is True
        assert "htf structure" in reason.lower()
        assert "hl" in reason.lower()

    def test_short_trade_invalidated_by_hh_structure_bullish_bias(
        self, short_trade_bullish_bias
    ):
        """Test short trade with bullish bias invalidated by HH structure break.
        
        This test verifies the bug fix: short trades should be invalidated by
        bullish structure breaks (HH, HL) regardless of entry bias.
        """
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "HH"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            short_trade_bullish_bias, candle, features
        )
        
        assert is_invalid is True, (
            "Short trade should be invalidated by HH structure break "
            "regardless of entry bias"
        )
        assert "htf structure" in reason.lower()
        assert "hh" in reason.lower()

    def test_short_trade_invalidated_by_hl_structure_bullish_bias(
        self, short_trade_bullish_bias
    ):
        """Test short trade with bullish bias invalidated by HL structure break.
        
        This test verifies the bug fix: short trades should be invalidated by
        bullish structure breaks (HH, HL) regardless of entry bias.
        """
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "HL"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            short_trade_bullish_bias, candle, features
        )
        
        assert is_invalid is True, (
            "Short trade should be invalidated by HL structure break "
            "regardless of entry bias"
        )
        assert "htf structure" in reason.lower()
        assert "hl" in reason.lower()

    def test_long_trade_not_invalidated_by_hh_structure(self, long_trade_bullish_bias):
        """Test long trade not invalidated by bullish structure (HH)."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "HH"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            long_trade_bullish_bias, candle, features
        )
        
        assert is_invalid is False
        assert reason is None

    def test_short_trade_not_invalidated_by_ll_structure(self, short_trade_bearish_bias):
        """Test short trade not invalidated by bearish structure (LL)."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"structure_label": "LL"}
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            short_trade_bearish_bias, candle, features
        )
        
        assert is_invalid is False
        assert reason is None

    def test_htf_invalidation_requires_features(self, long_trade_bullish_bias):
        """Test HTF invalidation returns False when features are None."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            long_trade_bullish_bias, candle, features=None
        )
        
        assert is_invalid is False
        assert reason is None

    def test_htf_invalidation_requires_structure_label(self, long_trade_bullish_bias):
        """Test HTF invalidation returns False when structure_label is missing."""
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )
        
        features = {"vwap": 2650.0}  # No structure_label
        
        is_invalid, reason = checker.check_htf_structure_invalidation(
            long_trade_bullish_bias, candle, features
        )
        
        assert is_invalid is False
        assert reason is None

