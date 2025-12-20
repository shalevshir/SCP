"""Tests for DXY continuation invalidation logic."""

import pytest
from datetime import datetime, timezone

from backtester.entry_model import EntryExecution
from backtester.invalidations import InvalidationChecker
from backtester.trade import Trade
from common.types import Candle
from rule_engine.signal import Signal


class TestDXYContinuationFeatureKeyBugFix:
    """Test that check_dxy_flip uses correct feature keys from feature engine.

    Bug: The check_dxy_flip function expects specific feature keys:
    - dxy_corr_1m (1-minute correlation)
    - dxy_corr_5m (5-minute correlation)
    - dxy_structure (DXY structure label)

    This caused the entire DXY_CONTINUATION invalidation code path to be dead code
    since all .get() calls returned None.
    """

    @pytest.fixture
    def checker(self) -> InvalidationChecker:
        return InvalidationChecker()

    @pytest.fixture
    def long_continuation_trade(self) -> Trade:
        """Create a long DXY_CONTINUATION trade for testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-bugfix-1",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="long",
            setup_type="DXY_CONTINUATION",
            stop_loss=2648.0,
            take_profit=2656.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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
    def sample_candle(self) -> Candle:
        return Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2651.0,
            high=2652.0,
            low=2650.0,
            close=2651.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

    def test_invalidation_triggers_with_real_feature_keys(
        self, checker, long_continuation_trade, sample_candle
    ):
        """Test that invalidation triggers when using REAL feature keys.

        The feature engine produces:
        - dxy_corr_micro (5-period micro correlation)
        - dxy_corr (50-period correlation)
        - dxy_structure_label (DXY structure label)

        This test verifies the bug fix by using these real keys.
        """
        # Features using the REAL keys from feature_engine/streaming.py
        features = {
            "dxy_corr_1m": 0.1,  # 5-period micro correlation (weak positive)
            "dxy_corr_5m": 0.1,  # 5-minute correlation
            "dxy_corr": 0.05,  # 50-period correlation (weak positive)
            "dxy_structure": "HH",  # DXY turned bullish
        }

        is_invalid, reason = checker.check_dxy_flip(
            long_continuation_trade, sample_candle, features
        )

        # This MUST trigger invalidation - if not, the bug still exists
        assert is_invalid is True, (
            "DXY_CONTINUATION invalidation should trigger with real feature keys. "
            "If this fails, check_dxy_flip is still using wrong keys."
        )
        assert "continuation invalidated" in reason
        assert "structure + correlation flip" in reason

    def test_no_invalidation_with_strong_correlation_real_keys(
        self, checker, long_continuation_trade, sample_candle
    ):
        """Test that strong correlation prevents invalidation (using real keys)."""
        features = {
            "dxy_corr_1m": -0.5,  # Strong negative (good for long)
            "dxy_corr_5m": -0.5,  # 5-minute correlation
            "dxy_corr": -0.6,  # Strong negative
            "dxy_structure": "HH",  # Structure flipped but correlation strong
        }

        is_invalid, reason = checker.check_dxy_flip(
            long_continuation_trade, sample_candle, features
        )

        # Should NOT invalidate - correlation is still strong
        assert is_invalid is False

    def test_no_invalidation_with_bearish_structure_real_keys(
        self, checker, long_continuation_trade, sample_candle
    ):
        """Test that bearish DXY structure prevents invalidation (using real keys)."""
        features = {
            "dxy_corr_1m": 0.1,  # Weak correlation
            "dxy_corr_5m": 0.1,  # 5-minute correlation
            "dxy_corr": 0.05,
            "dxy_structure": "LL",  # DXY still bearish - good for long
        }

        is_invalid, reason = checker.check_dxy_flip(
            long_continuation_trade, sample_candle, features
        )

        # Should NOT invalidate - DXY structure still supports long
        assert is_invalid is False


class TestDXYContinuationInvalidation:
    """Test stricter DXY invalidation logic for continuation setups."""

    def test_long_continuation_invalidated_by_structure_and_correlation_flip(self):
        """Test long continuation invalidated when both correlation and structure flip."""
        checker = InvalidationChecker()

        # Create long continuation trade
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        trade = Trade(
            trade_id="test-1",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="long",
            setup_type="DXY_CONTINUATION",
            stop_loss=2648.0,
            take_profit=2656.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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

        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2651.0,
            high=2652.0,
            low=2650.0,
            close=2651.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Features showing correlation flip + structure flip
        # Uses correct keys: dxy_corr_micro (5-period), dxy_corr (50-period), dxy_structure_label
        features = {
            "dxy_corr_1m": 0.1,  # 5-period micro correlation - weak positive (was negative)
            "dxy_corr_5m": 0.1,  # 5-minute correlation
            "dxy_corr": 0.05,  # 50-period correlation - weak positive (was negative)
            "dxy_structure": "HH",  # DXY turned bullish
        }

        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)

        assert is_invalid is True
        assert "continuation invalidated" in reason
        assert "structure + correlation flip" in reason

    def test_long_continuation_not_invalidated_by_correlation_alone(self):
        """Test long continuation NOT invalidated by correlation flip alone."""
        checker = InvalidationChecker()

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        trade = Trade(
            trade_id="test-2",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="long",
            setup_type="DXY_CONTINUATION",
            stop_loss=2648.0,
            take_profit=2656.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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

        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2651.0,
            high=2652.0,
            low=2650.0,
            close=2651.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Correlation flipped but structure still bearish
        features = {
            "dxy_corr_1m": 0.1,
            "dxy_corr_5m": 0.1,  # 5-minute correlation
            "dxy_corr": 0.05,
            "dxy_structure": "LL",  # Still bearish
        }

        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)

        assert is_invalid is False

    def test_long_continuation_not_invalidated_by_structure_alone(self):
        """Test long continuation NOT invalidated by structure flip alone."""
        checker = InvalidationChecker()

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        trade = Trade(
            trade_id="test-3",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="long",
            setup_type="DXY_CONTINUATION",
            stop_loss=2648.0,
            take_profit=2656.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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

        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2651.0,
            high=2652.0,
            low=2650.0,
            close=2651.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Structure flipped but correlation still strong
        features = {
            "dxy_corr_1m": -0.5,  # Still strong inverse
            "dxy_corr_5m": -0.5,  # 5-minute correlation
            "dxy_corr": -0.6,
            "dxy_structure": "HH",  # Turned bullish
        }

        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)

        assert is_invalid is False

    def test_short_continuation_invalidated_correctly(self):
        """Test short continuation invalidated when correlation weakens and structure flips.

        Short continuation entered with strong inverse correlation (-0.4)
        should be invalidated when correlation weakens toward zero (-0.05)
        AND DXY structure turns bearish (LH/LL).
        """
        checker = InvalidationChecker()

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="DXY_CONTINUATION",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        trade = Trade(
            trade_id="test-4",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="short",
            setup_type="DXY_CONTINUATION",
            stop_loss=2652.0,
            take_profit=2644.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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

        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2649.0,
            high=2650.0,
            low=2648.0,
            close=2648.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Correlation weakened (moved toward zero) + structure turned bearish
        features = {
            "dxy_corr_1m": -0.05,  # Weak correlation (was -0.4 at entry)
            "dxy_corr_5m": -0.05,  # 5-minute correlation
            "dxy_corr": 0.0,  # Near zero
            "dxy_structure": "LL",  # Turned bearish
        }

        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)

        assert is_invalid is True
        assert "continuation invalidated" in reason

    def test_short_continuation_not_invalidated_by_strong_correlation(self):
        """Test short continuation NOT invalidated when correlation remains strong.

        This verifies the bug fix: shorts should NOT be invalidated when
        correlation becomes MORE negative (e.g., -0.4 -> -0.8), only when
        it weakens toward zero.
        """
        checker = InvalidationChecker()

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="DXY_CONTINUATION",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        trade = Trade(
            trade_id="test-4b",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="short",
            setup_type="DXY_CONTINUATION",
            stop_loss=2652.0,
            take_profit=2644.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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

        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2649.0,
            high=2650.0,
            low=2648.0,
            close=2648.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Correlation became MORE strongly negative + structure turned bearish
        # This should NOT invalidate (correlation is still strong, not weakening)
        features = {
            "dxy_corr_1m": -0.7,  # Strong negative (was -0.4, now MORE negative)
            "dxy_corr_5m": -0.7,  # 5-minute correlation
            "dxy_corr": -0.8,
            "dxy_structure": "LL",  # Turned bearish
        }

        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)

        assert is_invalid is False
        assert reason is None

    def test_vwap_reclaim_uses_3_bar_persistence(self):
        """Test that VWAP_RECLAIM requires 3 consecutive bars for DXY flip.

        VWAP_RECLAIM uses stricter invalidation than other setups - it requires
        3 consecutive bars where DXY correlation flips to >= 0.0 (for long).
        """
        checker = InvalidationChecker()

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        trade = Trade(
            trade_id="test-5",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",  # Not continuation
            stop_loss=2648.0,
            take_profit=2656.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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

        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2651.0,
            high=2652.0,
            low=2650.0,
            close=2651.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # DXY correlation flipped to >= 0.0 (triggering condition for long)
        features = {
            "dxy_corr": 0.0,  # Flip condition met
        }

        # Bar 1: condition met, but not invalidated yet (need 3 bars)
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)
        assert is_invalid is False  # Not yet, need 3 consecutive bars

        # Bar 2: condition still met
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)
        assert is_invalid is False  # Still not yet

        # Bar 3: condition still met - NOW should trigger
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)
        assert is_invalid is True  # 3-bar persistence met
        assert "3-bar confirmed" in reason

    def test_vwap_reclaim_none_dxy_corr_resets_counter(self):
        """Test that None dxy_corr resets the consecutive counter.

        Bug fix: When dxy_corr is None (missing data), the counter should reset
        because the "3 consecutive bars" requirement means no gaps allowed.

        Scenario:
        - Bar 1: dxy_corr=0.0 (condition met) → counter=1
        - Bar 2: dxy_corr=None (missing) → should reset counter to 0
        - Bar 3: dxy_corr=0.0 (condition met) → counter should be 1 (not 2!)
        - Bar 4: dxy_corr=0.0 (condition met) → counter=2
        - Bar 5: dxy_corr=0.0 (condition met) → counter=3, NOW invalidate
        """
        checker = InvalidationChecker()

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        trade = Trade(
            trade_id="test-none-dxy-reset",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2648.0,
            take_profit=2656.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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

        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2651.0,
            high=2652.0,
            low=2650.0,
            close=2651.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Bar 1: condition met (dxy_corr >= 0.0 for long)
        is_invalid, _ = checker.check_dxy_flip(trade, candle, {"dxy_corr": 0.0})
        assert is_invalid is False  # counter=1

        # Bar 2: dxy_corr is None (missing data) - should reset counter
        is_invalid, _ = checker.check_dxy_flip(trade, candle, {"dxy_corr": None})
        assert is_invalid is False

        # Bar 3: condition met again - counter should be 1 (reset by None)
        is_invalid, _ = checker.check_dxy_flip(trade, candle, {"dxy_corr": 0.0})
        assert is_invalid is False  # counter=1 (not 2!)

        # Bar 4: condition met - counter=2
        is_invalid, _ = checker.check_dxy_flip(trade, candle, {"dxy_corr": 0.0})
        assert is_invalid is False  # counter=2

        # Bar 5: condition met - counter=3, should trigger now
        is_invalid, reason = checker.check_dxy_flip(trade, candle, {"dxy_corr": 0.0})
        assert is_invalid is True  # 3 consecutive bars after the None
        assert "3-bar confirmed" in reason

    def test_vwap_reclaim_short_sign_flip_detection(self):
        """Test that short VWAP_RECLAIM uses sign flip detection (<= 0.0).

        Short VWAP_RECLAIM expects positive correlation (DXY ↑, GC ↓).
        Invalidation should occur when correlation flips to non-positive (<= 0.0),
        not when it becomes extremely negative (which would be bullish for GC).

        This test verifies:
        1. dxy_corr = 0.3 (positive) → NO invalidation
        2. dxy_corr = 0.0 for 3 bars → invalidation (sign flip)
        3. dxy_corr = -0.5 for 3 bars → invalidation (sign flip to negative)
        """
        checker = InvalidationChecker()

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_RECLAIM",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        trade = Trade(
            trade_id="test-short-signflip",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=2650.0,
            direction="short",
            setup_type="VWAP_RECLAIM",
            stop_loss=2652.0,
            take_profit=2644.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=2.0,
            reward_amount=6.0,
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

        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            open=2649.0,
            high=2650.0,
            low=2648.0,
            close=2649.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Case 1: Positive correlation (0.3) - should NOT trigger
        features_positive = {"dxy_corr": 0.3}
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features_positive)
        assert is_invalid is False
        assert reason is None

        # Case 2: Correlation at 0.0 (sign flip boundary) - requires 3 bars
        features_zero = {"dxy_corr": 0.0}

        # Bar 1
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features_zero)
        assert is_invalid is False  # Need 3 consecutive bars

        # Bar 2
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features_zero)
        assert is_invalid is False  # Still need 1 more

        # Bar 3 - should trigger
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features_zero)
        assert is_invalid is True
        assert "3-bar confirmed" in reason
        assert "0.000" in reason  # Correlation value in reason

        # Reset for next test
        checker.reset_trade(trade.trade_id)

        # Case 3: Negative correlation (-0.5) - also should trigger after 3 bars
        features_negative = {"dxy_corr": -0.5}

        # Bar 1
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features_negative)
        assert is_invalid is False

        # Bar 2
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features_negative)
        assert is_invalid is False

        # Bar 3 - should trigger
        is_invalid, reason = checker.check_dxy_flip(trade, candle, features_negative)
        assert is_invalid is True
        assert "3-bar confirmed" in reason
        assert "-0.500" in reason  # Correlation value in reason



