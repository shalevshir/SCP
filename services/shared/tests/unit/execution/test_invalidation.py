"""Unit tests for InvalidationChecker - missing methods.

Tests for methods that need to be ported from legacy backtester:
- check_micro_structure_invalidation()
- check_dxy_flip()
- check_setup_window_expired()
- check_daily_risk_breach()

Following strict TDD - these tests are written FIRST and should FAIL until
the methods are implemented.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest
from scp_shared.common.types import Candle
from scp_shared.execution import InvalidationChecker
from scp_shared.execution.types import TradeRecord


# Helper to create timezone-aware timestamps
def utc_datetime(*args, **kwargs):
    """Create UTC timezone-aware datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


@pytest.fixture
def checker():
    """Create invalidation checker instance."""
    return InvalidationChecker()


@pytest.fixture
def base_trade():
    """Create base trade record for testing."""
    return TradeRecord(
        trade_id="test-123",
        signal_id="signal-123",
        symbol="GC",
        direction="long",
        setup_type="VWAP_RECLAIM",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2670.0,
        risk_amount=10.0,
        reward_amount=20.0,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        entry_bar_idx=100,
    )


@pytest.fixture
def base_candle():
    """Create base candle for testing."""
    return Candle(
        timestamp=utc_datetime(2024, 10, 15, 10, 5),
        open=2651.0,
        high=2653.0,
        low=2649.0,
        close=2652.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )


# ============================================================================
# Phase 1.1: check_micro_structure_invalidation() Tests
# ============================================================================


class TestMicroStructureInvalidation:
    """Tests for check_micro_structure_invalidation() method."""

    def test_micro_structure_long_LL_invalidates(self, checker, base_trade, base_candle):
        """Long trade should exit on LL structure break (non-VWAP_RECLAIM)."""
        # Use VWAP_FADE setup which doesn't require confirmation
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {"structure_label": "LL", "timeframe": "1m"}
        
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )
        
        assert is_invalid is True
        assert "Micro structure break" in reason
        assert "LL" in reason

    def test_micro_structure_short_HH_invalidates(self, checker, base_trade, base_candle):
        """Short trade should exit on HH structure break (non-VWAP_RECLAIM)."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "direction": "short", "setup_type": "VWAP_FADE"}
        )
        features = {"structure_label": "HH", "timeframe": "1m"}
        
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )
        
        assert is_invalid is True
        assert "Micro structure break" in reason
        assert "HH" in reason

    def test_micro_structure_VWAP_RECLAIM_requires_confirmation(
        self, checker, base_trade, base_candle
    ):
        """VWAP_RECLAIM needs VWAP/HTF confirmation, not just micro break."""
        trade = base_trade  # VWAP_RECLAIM setup
        # Micro break detected BUT no VWAP loss or HTF break
        features = {
            "structure_label": "LL",
            "vwap": 2655.0,  # Still above VWAP (no loss)
            "htf_structure_label": "HH",  # HTF still bullish
            "timeframe": "1m",
        }
        # Create candle with close above VWAP (2656.0)
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2651.0,
            high=2657.0,
            low=2649.0,
            close=2656.0,  # Above VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )
        
        # Should NOT invalidate without confirmation
        assert is_invalid is False
        assert reason is None

    def test_micro_structure_VWAP_RECLAIM_with_vwap_confirmation(
        self, checker, base_trade, base_candle
    ):
        """VWAP_RECLAIM invalidates when micro break + VWAP loss."""
        trade = base_trade
        features = {
            "structure_label": "LL",
            "vwap": 2655.0,
            "timeframe": "1m",
        }
        # Create candle with close below VWAP (2654.0)
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2651.0,
            high=2655.0,
            low=2649.0,
            close=2654.0,  # Below VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )
        
        assert is_invalid is True
        assert "Micro break" in reason
        assert "VWAP loss" in reason

    def test_micro_structure_VWAP_RECLAIM_with_htf_confirmation(
        self, checker, base_trade, base_candle
    ):
        """VWAP_RECLAIM invalidates when micro break + HTF break."""
        trade = base_trade
        features = {
            "structure_label": "LL",
            "htf_structure_label": "LL",  # HTF also breaks
            "vwap": 2655.0,
            "timeframe": "1m",
        }
        # Create candle with close above VWAP (2656.0)
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2651.0,
            high=2657.0,
            low=2649.0,
            close=2656.0,  # Above VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )
        
        assert is_invalid is True
        assert "Micro break" in reason
        assert "HTF break" in reason

    def test_micro_structure_no_break_holds(self, checker, base_trade, base_candle):
        """No structure break = no exit."""
        trade = base_trade
        features = {"structure_label": "HH", "timeframe": "1m"}  # Bullish for long
        
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )
        
        assert is_invalid is False
        assert reason is None

    def test_micro_structure_no_features_no_exit(self, checker, base_trade, base_candle):
        """Missing features should not trigger invalidation."""
        is_invalid, reason = checker.check_micro_structure_invalidation(
            base_trade, base_candle, features=None
        )
        
        assert is_invalid is False
        assert reason is None


# ============================================================================
# Phase 1.1: check_dxy_flip() Tests
# ============================================================================


class TestDXYFlip:
    """Tests for check_dxy_flip() method."""

    def test_dxy_flip_3bar_persistence_VWAP_RECLAIM(
        self, checker, base_trade, base_candle
    ):
        """VWAP_RECLAIM requires 3 consecutive bars of DXY flip."""
        trade = base_trade
        features = {"dxy_corr": 0.1}  # Flipped (>= 0.0)
        
        # Bar 1: flip detected
        is_invalid, _ = checker.check_dxy_flip(trade, base_candle, features)
        assert is_invalid is False  # Not yet 3 bars
        
        # Bar 2: still flipped
        checker.update_state(trade, base_candle, features)
        is_invalid, _ = checker.check_dxy_flip(trade, base_candle, features)
        assert is_invalid is False  # Only 2 bars
        
        # Bar 3: still flipped
        checker.update_state(trade, base_candle, features)
        is_invalid, reason = checker.check_dxy_flip(trade, base_candle, features)
        assert is_invalid is True  # Now 3 bars
        assert "DXY flip" in reason
        assert "3-bar confirmed" in reason

    def test_dxy_flip_reset_on_break(self, checker, base_trade, base_candle):
        """Counter should reset when DXY flip condition breaks."""
        trade = base_trade
        
        # Bar 1: flip detected
        features = {"dxy_corr": 0.1}
        checker.check_dxy_flip(trade, base_candle, features)
        checker.update_state(trade, base_candle, features)
        
        # Bar 2: flip breaks (back to negative correlation)
        features = {"dxy_corr": -0.5}
        is_invalid, _ = checker.check_dxy_flip(trade, base_candle, features)
        assert is_invalid is False
        
        # Bar 3: flip again (counter should have reset to 1)
        features = {"dxy_corr": 0.1}
        is_invalid, _ = checker.check_dxy_flip(trade, base_candle, features)
        assert is_invalid is False  # Only 1 bar since reset

    def test_dxy_flip_DXY_CONTINUATION_immediate(
        self, checker, base_trade, base_candle
    ):
        """DXY_CONTINUATION setups should exit immediately on DXY flip."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "DXY_CONTINUATION", "direction": "long"}
        )
        # For long DXY_CONTINUATION: both correlations > -0.1 AND DXY structure turns bullish (HH/HL)
        features = {
            "dxy_corr_1m": 0.1,  # Weakened (> -0.1)
            "dxy_corr_5m": 0.1,  # Weakened (> -0.1)
            "dxy_structure": "HH",  # Structure flipped bullish
        }
        
        is_invalid, reason = checker.check_dxy_flip(trade, base_candle, features)
        
        assert is_invalid is True
        assert "DXY continuation invalidated" in reason

    def test_dxy_flip_VWAP_FADE_threshold(self, checker, base_trade, base_candle):
        """VWAP_FADE should exit when DXY correlation crosses threshold."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {"dxy_corr": -0.2}  # Above -0.3 threshold for long
        
        is_invalid, reason = checker.check_dxy_flip(trade, base_candle, features)
        
        assert is_invalid is True
        assert "DXY flip" in reason

    def test_dxy_flip_no_features_no_exit(self, checker, base_trade, base_candle):
        """Missing DXY features should not trigger exit."""
        is_invalid, reason = checker.check_dxy_flip(
            base_trade, base_candle, features=None
        )
        
        assert is_invalid is False
        assert reason is None


# ============================================================================
# Phase 1.1: check_setup_window_expired() Tests
# ============================================================================


class TestSetupWindowExpired:
    """Tests for check_setup_window_expired() method."""

    def test_setup_window_FADE_vwap_reclaimed(
        self, checker, base_trade, base_candle
    ):
        """VWAP_FADE should exit when VWAP is reclaimed."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        
        # First update state to mark VWAP as reclaimed
        features = {"vwap": 2640.0}
        # Create candle with close above VWAP (2641.0)
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2640.0,
            high=2643.0,
            low=2639.0,
            close=2641.0,  # Above VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        checker.update_state(trade, candle, features)
        
        # Now check if window expired
        is_invalid, reason = checker.check_setup_window_expired(
            trade, candle, features
        )
        
        assert is_invalid is True
        assert "Setup window expired" in reason
        assert "VWAP_FADE" in reason

    def test_setup_window_FADE_no_reclaim_stays_active(
        self, checker, base_trade, base_candle
    ):
        """VWAP_FADE window stays active if VWAP not reclaimed."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {"vwap": 2655.0}
        # Create candle with close below VWAP (2654.0)
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2651.0,
            high=2655.0,
            low=2649.0,
            close=2654.0,  # Below VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        is_invalid, reason = checker.check_setup_window_expired(
            trade, candle, features
        )
        
        assert is_invalid is False
        assert reason is None

    def test_setup_window_RECLAIM_stays_active(
        self, checker, base_trade, base_candle
    ):
        """VWAP_RECLAIM window should remain active."""
        trade = base_trade  # VWAP_RECLAIM
        
        is_invalid, reason = checker.check_setup_window_expired(
            trade, base_candle, features={}
        )
        
        assert is_invalid is False
        assert reason is None

    def test_setup_window_DXY_CONTINUATION_stays_active(
        self, checker, base_trade, base_candle
    ):
        """DXY_CONTINUATION window should remain active."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "DXY_CONTINUATION"}
        )
        
        is_invalid, reason = checker.check_setup_window_expired(
            trade, base_candle, features={}
        )
        
        assert is_invalid is False
        assert reason is None


# ============================================================================
# Phase 1.1: check_daily_risk_breach() Tests
# ============================================================================


class TestDailyRiskBreach:
    """Tests for check_daily_risk_breach() method."""

    def test_daily_risk_breach_loss_streak(self, checker, base_trade, base_candle):
        """Trade should exit when loss streak limit is hit."""
        daily_state = {
            "consecutive_losses": 2,
            "daily_pnl": -150.0,
        }
        
        is_invalid, reason = checker.check_daily_risk_breach(
            base_trade, base_candle, daily_state
        )
        
        assert is_invalid is True
        assert "Daily risk stop" in reason
        assert "consecutive losses" in reason

    def test_daily_risk_breach_pdll_hit(self, checker, base_trade, base_candle):
        """Trade should exit when PDLL is breached."""
        daily_state = {
            "consecutive_losses": 0,
            "daily_pnl": -650.0,  # Below -600 PDLL
            "pdll": 600.0,
        }
        
        is_invalid, reason = checker.check_daily_risk_breach(
            base_trade, base_candle, daily_state
        )
        
        assert is_invalid is True
        assert "Daily risk stop" in reason
        assert "PDLL breached" in reason

    def test_daily_risk_breach_september_1_loss_max(self, checker, base_trade, base_candle):
        """September should only allow 1 loss max."""
        # September candle
        candle = Candle(
            timestamp=utc_datetime(2024, 9, 15, 10, 0),
            open=2651.0,
            high=2653.0,
            low=2649.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        daily_state = {
            "consecutive_losses": 1,  # Only 1 loss
            "daily_pnl": -50.0,
        }
        
        is_invalid, reason = checker.check_daily_risk_breach(
            base_trade, candle, daily_state
        )
        
        assert is_invalid is True
        assert "Daily risk stop" in reason
        assert "max allowed: 1" in reason

    def test_daily_risk_breach_normal_month_2_losses_ok(
        self, checker, base_trade, base_candle
    ):
        """Normal months allow up to 2 losses."""
        daily_state = {
            "consecutive_losses": 1,  # Only 1 loss in October
            "daily_pnl": -50.0,
        }
        
        is_invalid, reason = checker.check_daily_risk_breach(
            base_trade, base_candle, daily_state
        )
        
        assert is_invalid is False  # 1 loss is under 2 limit
        assert reason is None

    def test_daily_risk_breach_no_state_no_exit(self, checker, base_trade, base_candle):
        """No daily state should not trigger exit."""
        is_invalid, reason = checker.check_daily_risk_breach(
            base_trade, base_candle, daily_pnl_state=None
        )
        
        # Should use internal state (which is empty by default)
        assert is_invalid is False
        assert reason is None

    def test_daily_risk_breach_pdll_with_internal_state(self, base_trade, base_candle):
        """PDLL breach detection should work with internal state when pdll_limit is set."""
        # Create checker with PDLL limit
        checker = InvalidationChecker(pdll_limit=600.0)
        
        # Update internal state with accumulated losses
        checker._daily_state["daily_pnl"] = -650.0  # Below -600 PDLL
        checker._daily_state["consecutive_losses"] = 0
        checker._daily_state["last_session_date"] = base_candle.timestamp.date()
        
        # check_all uses internal state (doesn't pass daily_pnl_state)
        is_invalid, reason = checker.check_all(
            base_trade, base_candle, bars_elapsed=10, features={}
        )
        
        assert is_invalid is True
        assert "Daily risk stop" in reason
        assert "PDLL breached" in reason
        assert "-650.00" in reason or "-650.0" in reason
        assert "600.00" in reason or "600.0" in reason

    def test_daily_risk_breach_pdll_not_breached(self, base_trade, base_candle):
        """PDLL should not trigger when daily_pnl is above limit."""
        checker = InvalidationChecker(pdll_limit=600.0)
        
        # Update internal state with losses but not enough to breach
        checker._daily_state["daily_pnl"] = -500.0  # Above -600 PDLL
        checker._daily_state["consecutive_losses"] = 0
        checker._daily_state["last_session_date"] = base_candle.timestamp.date()
        
        is_invalid, reason = checker.check_daily_risk_breach(
            base_trade, base_candle, daily_pnl_state=None
        )
        
        assert is_invalid is False
        assert reason is None


# ============================================================================
# Integration Test: check_all() should call all methods in priority order
# ============================================================================


class TestCheckAllIntegration:
    """Test that check_all() calls all invalidation methods in correct order."""

    def test_check_all_calls_micro_structure(self, checker, base_trade, base_candle):
        """check_all() should check micro structure."""
        # Use VWAP_FADE to test direct micro invalidation (no confirmation needed)
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {"structure_label": "LL"}
        
        # Use bars_elapsed < time limit so micro structure is checked before timeout
        is_invalid, reason = checker.check_all(
            trade, base_candle, bars_elapsed=5, features=features
        )
        
        # Should detect micro structure break for long trade
        assert is_invalid is True
        assert "Micro structure break" in reason

    def test_check_all_calls_dxy_flip(self, checker, base_trade, base_candle):
        """check_all() should check DXY flip."""
        features = {"dxy_corr": 0.1}  # Flipped
        
        # Need 3 bars for VWAP_RECLAIM
        for _ in range(3):
            checker.update_state(base_trade, base_candle, features)
            is_invalid, reason = checker.check_all(
                base_trade, base_candle, bars_elapsed=10, features=features
            )
        
        assert is_invalid is True
        assert "DXY flip" in reason

    def test_check_all_calls_setup_window(self, checker, base_trade, base_candle):
        """check_all() should check setup window expiration."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {"vwap": 2650.0}
        # Create candle with close above VWAP (2652.0) but not hitting SL/TP
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2651.0,
            high=2653.0,
            low=2650.0,  # Above SL of 2640.0
            close=2652.0,  # Reclaim VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Update state to mark VWAP as reclaimed
        checker.update_state(trade, candle, features)
        
        # Use bars_elapsed < time limit so setup window is checked before timeout
        is_invalid, reason = checker.check_all(
            trade, candle, bars_elapsed=5, features=features
        )
        
        assert is_invalid is True
        assert "Setup window expired" in reason

    def test_check_all_calls_daily_risk(self, checker, base_trade, base_candle):
        """check_all() should check daily risk breach."""
        # Provide daily state via checker's internal state
        checker._daily_state = {
            "consecutive_losses": 2,
            "daily_pnl": -150.0,
            "last_session_date": base_candle.timestamp.date(),
        }
        
        is_invalid, reason = checker.check_all(
            base_trade, base_candle, bars_elapsed=10, features={}
        )
        
        assert is_invalid is True
        assert "Daily risk stop" in reason


# ============================================================================
# Phase 1.2: September Time-Stop Protection Tests
# ============================================================================


class TestSeptemberTimeStop:
    """Tests for September time-stop protection in check_no_1r_reached()."""

    def test_timestop_september_deep_red_exits(self, checker, base_trade):
        """September + VWAP_RECLAIM + deep red (< -0.2R) at half limit = exit."""
        trade = base_trade  # VWAP_RECLAIM setup, entry at 2650.0
        
        # September candle at half time limit (30 bars for VWAP_RECLAIM)
        candle = Candle(
            timestamp=utc_datetime(2024, 9, 15, 10, 30),
            open=2645.0,
            high=2646.0,
            low=2644.0,
            close=2645.0,  # Down 5 points from entry (2650 -> 2645)
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # At 30 bars (half of 60), current loss is -5 points / 10 risk = -0.5R (< -0.2R)
        is_invalid, reason = checker.check_no_1r_reached(
            trade, bars_elapsed=30, candle=candle, month=9
        )
        
        assert is_invalid is True
        assert "time_stop_protection" in reason
        assert "-0.5" in reason or "-0.50" in reason

    def test_timestop_september_shallow_red_holds(self, checker, base_trade):
        """September + VWAP_RECLAIM + shallow red (>= -0.2R) at half limit = hold."""
        trade = base_trade  # Entry at 2650.0
        
        # September candle at half time limit, but only down 1 point
        candle = Candle(
            timestamp=utc_datetime(2024, 9, 15, 10, 30),
            open=2649.0,
            high=2650.0,
            low=2648.0,
            close=2649.0,  # Down 1 point from entry (2650 -> 2649)
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # At 30 bars, current loss is -1 point / 10 risk = -0.1R (>= -0.2R)
        is_invalid, reason = checker.check_no_1r_reached(
            trade, bars_elapsed=30, candle=candle, month=9
        )
        
        assert is_invalid is False  # Not deep enough to trigger time-stop
        assert reason is None

    def test_timestop_non_september_no_early_exit(self, checker, base_trade):
        """Non-September months should not apply time-stop protection."""
        trade = base_trade
        
        # October candle at half time limit with deep red
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2645.0,
            high=2646.0,
            low=2644.0,
            close=2645.0,  # Down 5 points = -0.5R
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Should not exit in October
        is_invalid, reason = checker.check_no_1r_reached(
            trade, bars_elapsed=30, candle=candle, month=10
        )
        
        assert is_invalid is False
        assert reason is None

    def test_timestop_non_VWAP_RECLAIM_ignored(self, checker, base_trade):
        """Non-VWAP_RECLAIM setups should not apply time-stop protection."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        
        # September candle with deep red
        candle = Candle(
            timestamp=utc_datetime(2024, 9, 15, 10, 30),
            open=2645.0,
            high=2646.0,
            low=2644.0,
            close=2645.0,  # Down 5 points = -0.5R
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # VWAP_FADE has 10 bar limit, half = 5 bars
        # Should not trigger time-stop (only applies to VWAP_RECLAIM)
        is_invalid, reason = checker.check_no_1r_reached(
            trade, bars_elapsed=5, candle=candle, month=9
        )
        
        # Should check standard time limit instead (10 bars for VWAP_FADE)
        assert is_invalid is False  # Not at limit yet
        assert reason is None


# ============================================================================
# Phase 1.3: VWAP Slope Confirmation for FADE Tests
# ============================================================================


class TestVWAPSlopeConfirmation:
    """Tests for VWAP slope confirmation in FADE invalidation."""

    def test_vwap_fade_requires_slope_confirmation(self, checker, base_trade, base_candle):
        """FADE invalidation should require slope confirmation, not just price."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {
            "vwap": 2650.0,
            "vwap_slope": None,  # No slope data
        }
        # Candle with close above VWAP
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2650.0,
            high=2653.0,
            low=2649.0,
            close=2651.0,  # Above VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # First bar: should not trigger (need 2 bars)
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is False
        
        # Second bar: WITHOUT slope, should still NOT invalidate (requires slope > 0)
        is_invalid, reason = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is False  # Should not trigger without slope confirmation
        assert reason is None

    def test_vwap_fade_wrong_slope_direction_no_invalidation(self, checker, base_trade, base_candle):
        """FADE with wrong slope direction should not invalidate."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {
            "vwap": 2650.0,
            "vwap_slope": -0.5,  # Negative slope (wrong direction for long)
        }
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2650.0,
            high=2653.0,
            low=2649.0,
            close=2651.0,  # Above VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Even after 2 bars, should not invalidate with wrong slope direction
        checker.check_vwap_invalidation(trade, candle, features)
        is_invalid, reason = checker.check_vwap_invalidation(trade, candle, features)
        
        assert is_invalid is False
        assert reason is None

    def test_vwap_fade_positive_slope_long_invalidates(self, checker, base_trade, base_candle):
        """Long FADE: close > VWAP + positive slope = invalidation."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {
            "vwap": 2650.0,
            "vwap_slope": 0.5,  # Positive slope
        }
        # Candle with close above VWAP
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2650.0,
            high=2653.0,
            low=2649.0,
            close=2651.0,  # Above VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # First bar meeting condition
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is False  # Need 2 bars
        
        # Second bar meeting condition
        is_invalid, reason = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is True  # Now invalidates
        assert "VWAP invalidation" in reason
        assert "2-bar confirmed" in reason

    def test_vwap_fade_negative_slope_short_invalidates(self, checker, base_trade, base_candle):
        """Short FADE: close < VWAP + negative slope = invalidation."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "direction": "short", "setup_type": "VWAP_FADE"}
        )
        features = {
            "vwap": 2650.0,
            "vwap_slope": -0.5,  # Negative slope
        }
        # Candle with close below VWAP
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2650.0,
            high=2651.0,
            low=2648.0,
            close=2649.0,  # Below VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # First bar meeting condition
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is False  # Need 2 bars
        
        # Second bar meeting condition
        is_invalid, reason = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is True  # Now invalidates
        assert "VWAP invalidation" in reason
        assert "2-bar confirmed" in reason

    def test_vwap_fade_2bar_confirmation_required(self, checker, base_trade, base_candle):
        """FADE requires 2 consecutive bars to invalidate."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        features = {
            "vwap": 2650.0,
            "vwap_slope": 0.5,
        }
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2650.0,
            high=2653.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # First bar
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is False
        
        # Second bar
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is True  # Should trigger on second bar

    def test_vwap_fade_counter_resets_on_break(self, checker, base_trade, base_candle):
        """Counter should reset when FADE invalidation condition breaks."""
        trade = TradeRecord(
            **{**base_trade.__dict__, "setup_type": "VWAP_FADE"}
        )
        
        # Bar 1: condition met (close > VWAP, positive slope)
        features = {"vwap": 2650.0, "vwap_slope": 0.5}
        candle = Candle(
            timestamp=base_candle.timestamp,
            open=2650.0,
            high=2653.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is False  # First bar
        
        # Bar 2: condition breaks (close < VWAP)
        candle2 = Candle(
            timestamp=base_candle.timestamp,
            open=2650.0,
            high=2651.0,
            low=2648.0,
            close=2649.0,  # Below VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle2, features)
        assert is_invalid is False  # Reset
        
        # Bar 3: condition met again (should start fresh count)
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle, features)
        assert is_invalid is False  # Only 1 bar again

