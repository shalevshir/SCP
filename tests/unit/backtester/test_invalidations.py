"""Unit tests for InvalidationChecker - trade invalidation detection.

Following TDD principles: tests written first to define behavior.
"""

from datetime import UTC, datetime

import numpy as np
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
            ignore_first_retest_bar=False,  # Default: no retest protection
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
            ignore_first_retest_bar=False,  # Default: no retest protection
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
            ignore_first_retest_bar=False,  # Default: no retest protection
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

    def test_vwap_invalidation_ignores_numpy_inf_values(self, long_continuation_trade):
        """Ensure numpy float values like inf/NaN don't trigger false invalidations."""
        checker = InvalidationChecker()

        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2647.0,
            close=2648.0,
        )

        # pandas often provides numpy scalar types; inf should be treated as invalid data
        features = {"vwap": np.float32(float("inf"))}

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
            ignore_first_retest_bar=False,  # Default: no retest protection
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

    @pytest.fixture
    def long_fade_trade(self):
        """Create a long fade trade for testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
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
            entry_price=2645.0,  # Below VWAP (fading from below)
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-fade-long",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2645.0,
            direction="long",
            setup_type="VWAP_FADE",
            stop_loss=2640.0,
            take_profit=2655.0,
            sl_rationale="Below sweep",
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
            ignore_first_retest_bar=False,  # Default: no retest protection
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
            entry_price=2650.0,  # Above VWAP (fading from above)
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-fade-short",
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
            ignore_first_retest_bar=False,  # Default: no retest protection
        )

    def test_vwap_invalidation_long_fade_requires_2_bars(self, long_fade_trade):
        """Test VWAP invalidation for long fade requires 2 consecutive bars (2-bar confirmation)."""
        checker = InvalidationChecker()

        # Bar 1: close below VWAP + negative slope (condition met)
        candle1 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2648.0,
            close=2649.0,  # Below VWAP with negative slope (bar 1)
        )

        features1 = {"vwap": 2650.0, "vwap_slope": -0.0001}

        # First bar: condition met but not yet invalid
        is_invalid, reason = checker.check_vwap_invalidation(
            long_fade_trade, candle1, features1
        )
        assert is_invalid is False
        assert reason is None

        # Bar 2: condition met again → 2-bar confirmed → invalid
        candle2 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 6, tzinfo=UTC),
            open=2649.0,
            high=2650.0,
            low=2647.0,
            close=2648.0,  # Still below VWAP with negative slope (bar 2)
        )

        features2 = {"vwap": 2650.0, "vwap_slope": -0.0002}

        is_invalid, reason = checker.check_vwap_invalidation(
            long_fade_trade, candle2, features2
        )

        assert is_invalid is True
        assert "2-bar" in reason.lower()
        assert "confirmed" in reason.lower()

    def test_vwap_invalidation_long_fade_counter_resets(self, long_fade_trade):
        """Test FADE invalidation counter resets when condition not met."""
        checker = InvalidationChecker()

        # Bar 1: condition met (bar 1/2)
        candle1 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2649.0,
            high=2650.0,
            low=2648.0,
            close=2648.0,  # Below VWAP with negative slope
        )
        features1 = {"vwap": 2650.0, "vwap_slope": -0.0001}

        is_invalid, _ = checker.check_vwap_invalidation(
            long_fade_trade, candle1, features1
        )
        assert is_invalid is False

        # Bar 2: condition NOT met (positive slope) → counter resets
        candle2 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 6, tzinfo=UTC),
            open=2651.0,
            high=2652.0,
            low=2650.0,
            close=2651.0,  # Above VWAP (condition not met)
        )
        features2 = {"vwap": 2650.0, "vwap_slope": 0.0001}

        is_invalid, _ = checker.check_vwap_invalidation(
            long_fade_trade, candle2, features2
        )
        assert is_invalid is False

        # Bar 3: condition met again (but counter was reset, so bar 1/2 again)
        candle3 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 7, tzinfo=UTC),
            open=2649.0,
            high=2650.0,
            low=2648.0,
            close=2648.0,  # Below VWAP with negative slope
        )
        features3 = {"vwap": 2650.0, "vwap_slope": -0.0001}

        is_invalid, _ = checker.check_vwap_invalidation(
            long_fade_trade, candle3, features3
        )
        assert is_invalid is False  # Still bar 1, not yet invalid

    def test_vwap_invalidation_short_fade_requires_2_bars(self, short_fade_trade):
        """Test VWAP invalidation for short fade requires 2 consecutive bars (2-bar confirmation)."""
        checker = InvalidationChecker()

        # Bar 1: condition met (above VWAP + positive slope)
        candle1 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2649.0,
            high=2651.0,
            low=2648.0,
            close=2651.0,  # Above VWAP with positive slope (bar 1)
        )
        features1 = {"vwap": 2650.0, "vwap_slope": 0.0001}

        # First bar: condition met but not yet invalid
        is_invalid, reason = checker.check_vwap_invalidation(
            short_fade_trade, candle1, features1
        )
        assert is_invalid is False
        assert reason is None

        # Bar 2: condition met again → 2-bar confirmed → invalid
        candle2 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 6, tzinfo=UTC),
            open=2651.0,
            high=2652.0,
            low=2650.0,
            close=2652.0,  # Still above VWAP with positive slope (bar 2)
        )
        features2 = {"vwap": 2650.0, "vwap_slope": 0.0002}

        is_invalid, reason = checker.check_vwap_invalidation(
            short_fade_trade, candle2, features2
        )

        assert is_invalid is True
        assert "2-bar" in reason.lower()
        assert "confirmed" in reason.lower()

    def test_vwap_invalidation_short_fade_not_triggered_with_one_bar(
        self, short_fade_trade
    ):
        """Test short fade NOT invalidated with only 1 bar meeting condition."""
        checker = InvalidationChecker()

        # Only 1 bar meeting condition → not invalid
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2649.0,
            high=2651.0,
            low=2648.0,
            close=2651.0,  # Above VWAP with positive slope
        )
        features = {"vwap": 2650.0, "vwap_slope": 0.0001}

        is_invalid, reason = checker.check_vwap_invalidation(
            short_fade_trade, candle, features
        )

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
            ignore_first_retest_bar=False,  # Default: no retest protection
        )

    def test_session_end_at_13_00_ilt(self, long_trade):
        """Test session end detection at 13:00 ILT.
        
        FIX #6: Session end should NOT close trades.
        Trades run to TP/SL regardless of session time.
        """

        checker = InvalidationChecker()

        # 13:00 ILT (winter, IST) = 11:00 UTC
        # 13:00 ILT (summer, IDT) = 10:00 UTC
        # Use 11:00 UTC for January (winter time)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )

        is_invalid, reason = checker.check_session_end(long_trade, candle)

        # FIX #6: Session end does NOT close trades
        assert is_invalid is False
        assert reason is None

    def test_session_end_not_triggered_during_session(self, long_trade):
        """Test session end not triggered during active session."""
        checker = InvalidationChecker()

        # 09:00 UTC = 11:00 ILT (during winter, IST) - within session (before 13:00 ILT)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )

        is_invalid, reason = checker.check_session_end(long_trade, candle)

        assert is_invalid is False
        assert reason is None

    def test_session_end_at_13_00_ilt_summer(self, long_trade):
        """Test session end detection at 13:00 ILT during summer (IDT).
        
        FIX #6: Session end should NOT close trades.
        """
        checker = InvalidationChecker()

        # 13:00 ILT (summer, IDT) = 10:00 UTC
        # Use 10:00 UTC for July (summer time)
        candle = make_candle(
            timestamp=datetime(2025, 7, 1, 10, 0, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )

        is_invalid, reason = checker.check_session_end(long_trade, candle)

        # FIX #6: Session end does NOT close trades
        assert is_invalid is False

    def test_session_end_before_13_00_ilt_summer(self, long_trade):
        """Test session end not triggered before 13:00 ILT during summer."""
        checker = InvalidationChecker()

        # 09:00 UTC = 12:00 ILT (during summer, IDT) - within session (before 13:00 ILT)
        candle = make_candle(
            timestamp=datetime(2025, 7, 1, 9, 0, tzinfo=UTC),
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
            ignore_first_retest_bar=False,  # Default: no retest protection
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

        is_invalid, reason = checker.check_all(
            trade, candle, bars_elapsed=5, features=features
        )

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
            ignore_first_retest_bar=False,  # Default: no retest protection
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
            ignore_first_retest_bar=False,  # Default: no retest protection
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
            ignore_first_retest_bar=False,  # Default: no retest protection
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
            ignore_first_retest_bar=False,  # Default: no retest protection
        )

    def test_long_trade_not_invalidated_by_lh_structure_bullish_bias(
        self, long_trade_bullish_bias
    ):
        """Test long trade with bullish bias NOT invalidated by LH (tightened logic).
        
        Updated: LH no longer triggers invalidation for longs (only LL does).
        This reduces noise from intermediate structure labels.
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
            long_trade_bullish_bias, candle, features
        )

        assert is_invalid is False
        assert reason is None

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
        assert "htf break" in reason.lower()
        assert "ll" in reason.lower()

    def test_long_trade_not_invalidated_by_lh_structure_bearish_bias(
        self, long_trade_bearish_bias
    ):
        """Test long trade with bearish bias NOT invalidated by LH (tightened logic).

        Updated: LH no longer triggers invalidation for longs (only LL does).
        This test verifies the tightened invalidation logic that reduces noise
        from intermediate structure labels.
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

        assert is_invalid is False
        assert reason is None

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
        assert "htf break" in reason.lower()
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
        assert "htf break" in reason.lower()
        assert "hh" in reason.lower()

    def test_short_trade_not_invalidated_by_hl_structure_bearish_bias(
        self, short_trade_bearish_bias
    ):
        """Test short trade with bearish bias NOT invalidated by HL (tightened logic).
        
        Updated: HL no longer triggers invalidation for shorts (only HH does).
        This reduces noise from intermediate structure labels.
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
            short_trade_bearish_bias, candle, features
        )

        assert is_invalid is False
        assert reason is None

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
        assert "htf break" in reason.lower()
        assert "hh" in reason.lower()

    def test_short_trade_not_invalidated_by_hl_structure_bullish_bias(
        self, short_trade_bullish_bias
    ):
        """Test short trade with bullish bias NOT invalidated by HL (tightened logic).

        Updated: HL no longer triggers invalidation for shorts (only HH does).
        This test verifies the tightened invalidation logic that reduces noise
        from intermediate structure labels.
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

        assert is_invalid is False
        assert reason is None

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

    def test_short_trade_not_invalidated_by_ll_structure(
        self, short_trade_bearish_bias
    ):
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

    def test_htf_invalidation_works_without_entry_htf_bias(self):
        """Test HTF invalidation works when entry HTF bias is None.

        This verifies the fix: the function should work regardless of entry HTF bias,
        using only the structure_label from features.
        """
        checker = InvalidationChecker()

        # Create a trade without HTF bias
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias=None,  # No HTF bias
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
            trade_id="test-htf-no-bias",
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
            ignore_first_retest_bar=False,  # Default: no retest protection
        )

        # Test with bearish structure (should invalidate long trade)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.0,
        )

        features = {"structure_label": "LH"}  # Bearish structure

        is_invalid, reason = checker.check_htf_structure_invalidation(
            trade, candle, features
        )

        # With tightened HTF logic, LH no longer triggers invalidation for longs (only LL)
        # This test verifies the loosened logic works even without entry HTF bias
        assert is_invalid is False
        assert reason is None


class TestRecordTradeOutcome:
    """Tests for record_trade_outcome() method."""

    def test_record_trade_outcome_updates_consecutive_losses(self):
        """Test that record_trade_outcome updates consecutive losses counter."""
        from datetime import UTC, datetime

        checker = InvalidationChecker()

        # Create a losing trade
        losing_trade = Trade(
            trade_id="test-loss-1",
            symbol="GC",
            timeframe="1m",
            entry_execution=None,
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
            exit_timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            exit_price=2645.0,
            exit_reason="sl",
            pnl=-5.0,  # Loss
            pnl_percent=-1.0,
            r_realized=-1.0,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="STOPPED_OUT",
            duration_bars=4,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        # Record first loss
        checker.record_trade_outcome(losing_trade, won=False)
        assert checker._daily_state["consecutive_losses"] == 1

        # Record second loss
        losing_trade2 = Trade(
            trade_id="test-loss-2",
            symbol="GC",
            timeframe="1m",
            entry_execution=None,
            entry_timestamp=datetime(2025, 1, 1, 10, 6, tzinfo=UTC),
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
            exit_timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            exit_price=2645.0,
            exit_reason="sl",
            pnl=-5.0,
            pnl_percent=-1.0,
            r_realized=-1.0,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="STOPPED_OUT",
            duration_bars=4,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )
        checker.record_trade_outcome(losing_trade2, won=False)
        assert checker._daily_state["consecutive_losses"] == 2

        # Record a win - should reset counter
        winning_trade = Trade(
            trade_id="test-win-1",
            symbol="GC",
            timeframe="1m",
            entry_execution=None,
            entry_timestamp=datetime(2025, 1, 1, 10, 11, tzinfo=UTC),
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
            exit_timestamp=datetime(2025, 1, 1, 10, 15, tzinfo=UTC),
            exit_price=2665.0,
            exit_reason="tp",
            pnl=15.0,  # Win
            pnl_percent=3.0,
            r_realized=3.0,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="CLOSED_WIN",
            duration_bars=4,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )
        checker.record_trade_outcome(winning_trade, won=True)
        assert checker._daily_state["consecutive_losses"] == 0

    def test_record_trade_outcome_updates_daily_pnl(self):
        """Test that record_trade_outcome updates daily PnL."""
        from datetime import UTC, datetime

        checker = InvalidationChecker()

        # Create trades with PnL
        trade1 = Trade(
            trade_id="test-1",
            symbol="GC",
            timeframe="1m",
            entry_execution=None,
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
            exit_timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            exit_price=2665.0,
            exit_reason="tp",
            pnl=15.0,
            pnl_percent=3.0,
            r_realized=3.0,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="CLOSED_WIN",
            duration_bars=4,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        checker.record_trade_outcome(trade1, won=True)
        assert checker._daily_state["daily_pnl"] == 15.0

        trade2 = Trade(
            trade_id="test-2",
            symbol="GC",
            timeframe="1m",
            entry_execution=None,
            entry_timestamp=datetime(2025, 1, 1, 10, 6, tzinfo=UTC),
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
            exit_timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            exit_price=2645.0,
            exit_reason="sl",
            pnl=-5.0,
            pnl_percent=-1.0,
            r_realized=-1.0,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="STOPPED_OUT",
            duration_bars=4,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        checker.record_trade_outcome(trade2, won=False)
        assert checker._daily_state["daily_pnl"] == 10.0  # 15.0 - 5.0

    def test_record_trade_outcome_resets_on_new_session(self):
        """Test that record_trade_outcome resets state on new session date."""
        from datetime import UTC, datetime

        checker = InvalidationChecker()

        # First trade on day 1
        trade1 = Trade(
            trade_id="test-day1",
            symbol="GC",
            timeframe="1m",
            entry_execution=None,
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
            exit_timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            exit_price=2645.0,
            exit_reason="sl",
            pnl=-5.0,
            pnl_percent=-1.0,
            r_realized=-1.0,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="STOPPED_OUT",
            duration_bars=4,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        checker.record_trade_outcome(trade1, won=False)
        assert checker._daily_state["consecutive_losses"] == 1
        assert checker._daily_state["daily_pnl"] == -5.0

        # Second trade on day 2 (new session)
        trade2 = Trade(
            trade_id="test-day2",
            symbol="GC",
            timeframe="1m",
            entry_execution=None,
            entry_timestamp=datetime(2025, 1, 2, 10, 1, tzinfo=UTC),
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
            exit_timestamp=datetime(2025, 1, 2, 10, 5, tzinfo=UTC),
            exit_price=2645.0,
            exit_reason="sl",
            pnl=-5.0,
            pnl_percent=-1.0,
            r_realized=-1.0,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="STOPPED_OUT",
            duration_bars=4,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        checker.record_trade_outcome(trade2, won=False)
        # Should reset on new day
        assert checker._daily_state["consecutive_losses"] == 1  # Reset to 0, then +1
        assert checker._daily_state["daily_pnl"] == -5.0  # Reset to 0, then -5.0


class TestSanitizeFloat:
    """Test _sanitize_float() helper function - specification-based."""

    def test_sanitizes_none_to_none(self):
        """None input returns None.
        
        Specification: "if value is None: return None"
        """
        from backtester.invalidations import _sanitize_float
        
        result = _sanitize_float(None)
        assert result is None

    def test_sanitizes_valid_float(self):
        """Valid float returns the float value.
        
        Specification: Convert to finite float if possible.
        """
        from backtester.invalidations import _sanitize_float
        
        result = _sanitize_float(3.14)
        assert result == 3.14

    def test_sanitizes_nan_to_none(self):
        """NaN input returns None.
        
        Specification: "if math.isnan(numeric_value) ... return None"
        """
        from backtester.invalidations import _sanitize_float
        
        result = _sanitize_float(float('nan'))
        assert result is None

    def test_sanitizes_inf_to_none(self):
        """Inf input returns None.
        
        Specification: "if math.isinf(numeric_value) ... return None"
        """
        from backtester.invalidations import _sanitize_float
        
        result = _sanitize_float(float('inf'))
        assert result is None

    def test_sanitizes_negative_inf_to_none(self):
        """Negative inf input returns None.
        
        Specification: Inf values (positive or negative) return None.
        """
        from backtester.invalidations import _sanitize_float
        
        result = _sanitize_float(float('-inf'))
        assert result is None

    def test_sanitizes_invalid_type_to_none(self):
        """Invalid type (non-convertible) returns None.
        
        Specification: "except (TypeError, ValueError): return None"
        """
        from backtester.invalidations import _sanitize_float
        
        result = _sanitize_float("not_a_number")
        assert result is None

    def test_sanitizes_string_number_to_float(self):
        """String containing valid number converts to float.
        
        Specification: Should convert string numbers to float if possible.
        """
        from backtester.invalidations import _sanitize_float
        
        result = _sanitize_float("3.14")
        assert result == 3.14


class TestDXYContinuationInvalidation:
    """Test DXY invalidation logic for DXY_CONTINUATION setups - specification-based."""

    @pytest.fixture
    def long_dxy_continuation_trade(self):
        """Create a long DXY_CONTINUATION trade."""
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
        return Trade(
            trade_id="test-dxy-long",
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
            ignore_first_retest_bar=False,
        )

    @pytest.fixture
    def short_dxy_continuation_trade(self):
        """Create a short DXY_CONTINUATION trade."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="DXY_CONTINUATION",
            htf_bias="bearish",
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
            trade_id="test-dxy-short",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="short",
            setup_type="DXY_CONTINUATION",
            stop_loss=2655.0,
            take_profit=2635.0,
            sl_rationale="Above structure",
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
            ignore_first_retest_bar=False,
        )

    def test_long_dxy_continuation_invalidated_by_correlation_and_structure_flip(
        self, long_dxy_continuation_trade
    ):
        """Long DXY_CONTINUATION invalidated when correlation weakens AND DXY turns bullish.
        
        Specification: "corr_1m > -0.1 and corr_5m > -0.1 and dxy_structure in ('HH', 'HL')"
        """
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        # Features showing correlation flip and structure break
        # Uses correct keys: dxy_corr_micro (5-period), dxy_corr (50-period), dxy_structure_label
        features = {
            "dxy_corr_micro": 0.1,  # 5-period micro correlation - weakened (was negative)
            "dxy_corr": 0.05,  # 50-period correlation - weakened
            "dxy_structure_label": "HH",  # DXY bullish (bad for long gold)
        }
        
        is_invalid, reason = checker.check_dxy_flip(
            long_dxy_continuation_trade, candle, features=features
        )
        
        # Should be invalidated
        assert is_invalid is True
        assert "DXY continuation invalidated" in reason
        assert "correlation flip" in reason

    def test_long_dxy_continuation_not_invalidated_by_correlation_alone(
        self, long_dxy_continuation_trade
    ):
        """Long DXY_CONTINUATION NOT invalidated by correlation alone (needs structure too).
        
        Specification: Requires BOTH correlation flip AND structure break.
        """
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        # Correlation weakened but structure still bearish
        features = {
            "dxy_corr_micro": 0.1,
            "dxy_corr": 0.05,
            "dxy_structure_label": "LL",  # DXY still bearish (OK for long gold)
        }
        
        is_invalid, reason = checker.check_dxy_flip(
            long_dxy_continuation_trade, candle, features=features
        )
        
        # Should NOT be invalidated
        assert is_invalid is False

    def test_short_dxy_continuation_invalidated_by_correlation_and_structure_flip(
        self, short_dxy_continuation_trade
    ):
        """Short DXY_CONTINUATION invalidated when correlation weakens AND DXY turns bearish.
        
        Specification: For short: "corr_1m > -0.1 and corr_5m > -0.1 and dxy_structure in ('LH', 'LL')"
        """
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        # Features showing correlation flip and structure break
        features = {
            "dxy_corr_micro": 0.1,
            "dxy_corr": 0.05,
            "dxy_structure_label": "LL",  # DXY bearish (bad for short gold)
        }
        
        is_invalid, reason = checker.check_dxy_flip(
            short_dxy_continuation_trade, candle, features=features
        )
        
        # Should be invalidated
        assert is_invalid is True
        assert "DXY continuation invalidated" in reason

    def test_dxy_continuation_not_invalidated_when_features_missing(
        self, long_dxy_continuation_trade
    ):
        """DXY_CONTINUATION not invalidated when features missing.
        
        Specification: "if corr_1m is None or corr_5m is None: return False"
        """
        checker = InvalidationChecker()
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        # Missing correlation features
        features = {
            "dxy_structure_label": "HH",
        }
        
        is_invalid, reason = checker.check_dxy_flip(
            long_dxy_continuation_trade, candle, features=features
        )
        
        # Should NOT be invalidated (missing data)
        assert is_invalid is False


class TestMultipleInvalidations:
    """Test multiple invalidation conditions triggering - specification-based."""

    @pytest.fixture
    def long_reclaim_trade(self):
        """Create a long VWAP_RECLAIM trade."""
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
            trade_id="test-multi",
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
            ignore_first_retest_bar=False,
        )

    def test_check_all_returns_first_invalidation_found(self, long_reclaim_trade):
        """check_all() returns first invalidation found.
        
        Specification: Invalidations are checked in priority order.
        """
        checker = InvalidationChecker()
        # Update state for the trade
        candle_before = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        checker.update_state(long_reclaim_trade, candle_before)
        
        # Candle at session end time
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 13, 0, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        # Features with multiple invalidation triggers
        features = {
            "vwap": 2655.0,  # Above price = VWAP invalidation for long
            "dxy_corr": 0.5,  # Positive = DXY flip for long
        }
        
        # Should return first invalidation (priority order)
        is_invalid, reason = checker.check_all(
            long_reclaim_trade, candle, bars_elapsed=5, features=features
        )
        
        # Should be invalidated
        assert is_invalid is True
        assert reason is not None

    def test_check_all_with_no_features_handles_gracefully(self, long_reclaim_trade):
        """check_all() with no features handles gracefully without crashing.
        
        Specification: FIX #6 - Session end no longer invalidates trades.
        This tests that check_all doesn't crash with None features.
        """
        checker = InvalidationChecker()
        # Update state for the trade
        candle_before = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        checker.update_state(long_reclaim_trade, candle_before)
        
        # Candle mid-session
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        # No features - should not crash
        is_invalid, reason = checker.check_all(
            long_reclaim_trade, candle, bars_elapsed=5, features=None
        )
        
        # Should return a boolean without crashing
        assert isinstance(is_invalid, bool)


class TestInvalidationEdgeCases:
    """Test edge cases in invalidation logic - specification-based."""

    @pytest.fixture
    def generic_trade(self):
        """Create a generic trade for edge case testing."""
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
            trade_id="test-edge",
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
            ignore_first_retest_bar=False,
        )

    def test_check_all_with_features_as_dict(self, generic_trade):
        """check_all() handles features as dict (not just None).
        
        Specification: features parameter is dict | None.
        """
        checker = InvalidationChecker()
        # Update state for the trade
        candle_before = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        checker.update_state(generic_trade, candle_before)
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        features_dict = {
            "vwap": 2648.0,
            "dxy_corr": -0.7,
            "structure_label": "HH",
        }
        
        # Should not raise
        is_invalid, reason = checker.check_all(
            generic_trade, candle, bars_elapsed=5, features=features_dict
        )
        
        # Should return a boolean
        assert isinstance(is_invalid, bool)

    def test_invalidation_with_numpy_values_in_features(self, generic_trade):
        """Invalidation handles numpy values in features.
        
        Specification: Features may come from pandas/numpy and have numpy types.
        """
        checker = InvalidationChecker()
        # Update state for the trade
        candle_before = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        checker.update_state(generic_trade, candle_before)
        
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        # Features with numpy types
        features = {
            "vwap": np.float64(2648.0),
            "dxy_corr": np.float64(-0.7),
            "structure_label": "HH",
        }
        
        # Should not raise
        is_invalid, reason = checker.check_all(
            generic_trade, candle, bars_elapsed=5, features=features
        )
        
        assert isinstance(is_invalid, bool)


class TestSetupWindowExpiration:
    """Test setup window expiration logic - specification-based."""

    @pytest.fixture
    def long_fade_trade(self):
        """Create a long VWAP_FADE trade."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
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
            trade_id="test-fade",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_FADE",
            stop_loss=2655.0,  # Above entry for fade
            take_profit=2640.0,  # Below entry for fade
            sl_rationale="Above structure",
            tp_rationale="Fade target",
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
            ignore_first_retest_bar=False,
        )

    def test_vwap_fade_window_expires_when_vwap_reclaimed(self, long_fade_trade):
        """VWAP_FADE window expires when VWAP is reclaimed.
        
        Specification: "if state['vwap_reclaimed']: return True, 'Setup window expired'"
        """
        checker = InvalidationChecker()
        
        # Update state to mark VWAP as reclaimed
        candle1 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        features1 = {"vwap": 2649.0}  # Below price = reclaimed
        checker.update_state(long_fade_trade, candle1, features=features1)
        
        # Now check if window expired
        candle2 = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
        )
        
        is_invalid, reason = checker.check_setup_window_expired(
            long_fade_trade, candle2
        )
        
        # Should be invalidated (window expired)
        assert is_invalid is True
        assert "window expired" in reason.lower()
        assert "vwap_fade" in reason.lower()
