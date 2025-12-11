"""Tests for DXY continuation invalidation logic."""

import pytest
from datetime import datetime, timezone

from backtester.entry_model import EntryExecution
from backtester.invalidations import InvalidationChecker
from backtester.trade import Trade
from common.types import Candle
from rule_engine.signal import Signal


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
        features = {
            "dxy_corr_1m": 0.1,  # Weak positive (was negative)
            "dxy_corr_5m": 0.05,  # Weak positive (was negative)
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
            "dxy_corr_5m": 0.05,
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
            "dxy_corr_5m": -0.6,
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
            "dxy_corr_5m": 0.0,  # Near zero
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
            "dxy_corr_5m": -0.8,
            "dxy_structure": "LL",  # Turned bearish
        }

        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)

        assert is_invalid is False
        assert reason is None

    def test_vwap_reclaim_uses_old_logic(self):
        """Test that VWAP_RECLAIM uses the old (looser) invalidation logic."""
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

        # Old logic: just correlation > -0.3 triggers invalidation
        features = {
            "dxy_corr": 0.0,  # Weak correlation
        }

        is_invalid, reason = checker.check_dxy_flip(trade, candle, features)

        assert is_invalid is True  # Old logic triggers on correlation alone

