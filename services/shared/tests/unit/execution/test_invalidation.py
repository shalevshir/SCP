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
        quantity=1,
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

    def test_micro_structure_long_LL_invalidates(
        self, checker, base_trade, base_candle
    ):
        """Long trade should exit on LL structure break (non-VWAP_RECLAIM)."""
        # Use VWAP_FADE setup which doesn't require confirmation
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
        features = {"structure_label": "LL", "timeframe": "1m"}

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )

        assert is_invalid is True
        assert "Micro structure break" in reason
        assert "LL" in reason

    def test_micro_structure_short_HH_invalidates(
        self, checker, base_trade, base_candle
    ):
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

    def test_micro_structure_no_features_no_exit(
        self, checker, base_trade, base_candle
    ):
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
            **{
                **base_trade.__dict__,
                "setup_type": "DXY_CONTINUATION",
                "direction": "long",
            }
    )
        # For long DXY_CONTINUATION: both correlations > 0 (true contradiction) AND DXY structure turns bullish
        # NOTE: Changed from > -0.1 to > 0 threshold, and requires 5-bar persistence
        features = {
            "dxy_corr_1m": 0.15,  # Positive (true contradiction)
            "dxy_corr_5m": 0.10,  # Positive (true contradiction)
            "dxy_structure": "HH",  # Structure flipped bullish
        }

        # Need 5 consecutive bars for DXY_CONTINUATION (no longer immediate)
        for _ in range(4):
            is_invalid, _ = checker.check_dxy_flip(trade, base_candle, features)
            assert is_invalid is False

        # 5th bar triggers exit
        is_invalid, reason = checker.check_dxy_flip(trade, base_candle, features)

        assert is_invalid is True
        assert "5-bar" in reason

    def test_dxy_flip_VWAP_FADE_threshold(self, checker, base_trade, base_candle):
        """VWAP_FADE should exit when DXY correlation crosses threshold."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
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

    def test_setup_window_FADE_vwap_reclaimed(self, checker, base_trade, base_candle):
        """VWAP_FADE should exit when VWAP is reclaimed."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})

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
        is_invalid, reason = checker.check_setup_window_expired(trade, candle, features)

        assert is_invalid is True
        assert "Setup window expired" in reason
        assert "VWAP_FADE" in reason

    def test_setup_window_FADE_no_reclaim_stays_active(
        self, checker, base_trade, base_candle
    ):
        """VWAP_FADE window stays active if VWAP not reclaimed."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
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

        is_invalid, reason = checker.check_setup_window_expired(trade, candle, features)

        assert is_invalid is False
        assert reason is None

    def test_setup_window_RECLAIM_stays_active(self, checker, base_trade, base_candle):
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
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "DXY_CONTINUATION"})

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

    def test_daily_risk_breach_september_1_loss_max(
        self, checker, base_trade, base_candle
    ):
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
        is_invalid, reason, action = checker.check_all(
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
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
        features = {"structure_label": "LL"}

        # Use bars_elapsed < time limit so micro structure is checked before timeout
        is_invalid, reason, action = checker.check_all(
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
            is_invalid, reason, action = checker.check_all(
                base_trade, base_candle, bars_elapsed=10, features=features
            )

        assert is_invalid is True
        assert "DXY flip" in reason

    def test_check_all_calls_setup_window(self, checker, base_trade, base_candle):
        """check_all() should check setup window expiration."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
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
        is_invalid, reason, action = checker.check_all(
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

        is_invalid, reason, action = checker.check_all(
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
        is_invalid, reason, action = checker.check_no_1r_reached(
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
        is_invalid, reason, action = checker.check_no_1r_reached(
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
        is_invalid, reason, action = checker.check_no_1r_reached(
            trade, bars_elapsed=30, candle=candle, month=10
        )

        assert is_invalid is False
        assert reason is None

    def test_timestop_non_VWAP_RECLAIM_ignored(self, checker, base_trade):
        """Non-VWAP_RECLAIM setups should not apply time-stop protection."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})

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
        is_invalid, reason, action = checker.check_no_1r_reached(
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

    def test_vwap_fade_requires_slope_confirmation(
        self, checker, base_trade, base_candle
    ):
        """FADE invalidation should require slope confirmation, not just price."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
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

    def test_vwap_fade_wrong_slope_direction_no_invalidation(
        self, checker, base_trade, base_candle
    ):
        """FADE with wrong slope direction should not invalidate."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
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

    def test_vwap_fade_positive_slope_long_invalidates(
        self, checker, base_trade, base_candle
    ):
        """Long FADE: close > VWAP + positive slope = invalidation."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
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

    def test_vwap_fade_negative_slope_short_invalidates(
        self, checker, base_trade, base_candle
    ):
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

    def test_vwap_fade_2bar_confirmation_required(
        self, checker, base_trade, base_candle
    ):
        """FADE requires 2 consecutive bars to invalidate."""
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})
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
        trade = TradeRecord(**{**base_trade.__dict__, "setup_type": "VWAP_FADE"})

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


# ============================================================================
# Daily State Reset Tests
# ============================================================================


class TestDailyStateReset:
    """Tests for reset_daily_state() method.

    Verifies that reset_daily_state() correctly resets daily tracking state
    while preserving the PDLL limit configuration.
    """

    def test_reset_daily_state_clears_consecutive_losses(self):
        """reset_daily_state should reset consecutive_losses to 0."""
        checker = InvalidationChecker(pdll_limit=600.0)

        # Simulate some losses
        trade = TradeRecord(
            trade_id="test-1",
            signal_id="signal-1",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2670.0,
            risk_amount=10.0,
            reward_amount=20.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            entry_bar_idx=100,
        )

        # Record two losses
        checker.record_trade_outcome(trade, won=False, pnl_points=-50.0)
        checker.record_trade_outcome(trade, won=False, pnl_points=-30.0)

        # Verify state is set
        assert checker._daily_state["consecutive_losses"] == 2
        assert checker._daily_state["daily_pnl"] == -80.0

        # Reset daily state
        checker.reset_daily_state()

        # Verify reset
        assert checker._daily_state["consecutive_losses"] == 0
        assert checker._daily_state["daily_pnl"] == 0.0
        assert checker._daily_state["last_session_date"] is None

    def test_reset_daily_state_preserves_pdll_limit(self):
        """reset_daily_state should preserve PDLL limit configuration."""
        pdll_limit = 600.0
        checker = InvalidationChecker(pdll_limit=pdll_limit)

        # Verify initial state
        assert checker._daily_state["pdll"] == pdll_limit

        # Modify daily state
        checker._daily_state["consecutive_losses"] = 5
        checker._daily_state["daily_pnl"] = -500.0
        checker._daily_state["last_session_date"] = datetime(2024, 10, 15).date()

        # Reset daily state
        checker.reset_daily_state()

        # Verify PDLL limit is preserved
        assert checker._daily_state["pdll"] == pdll_limit
        assert checker._daily_state["consecutive_losses"] == 0
        assert checker._daily_state["daily_pnl"] == 0.0
        assert checker._daily_state["last_session_date"] is None

    def test_reset_daily_state_with_none_pdll(self):
        """reset_daily_state should handle None PDLL limit correctly."""
        checker = InvalidationChecker(pdll_limit=None)

        # Modify state
        checker._daily_state["consecutive_losses"] = 3
        checker._daily_state["daily_pnl"] = -200.0

        # Reset
        checker.reset_daily_state()

        # Verify reset and None PDLL preserved
        assert checker._daily_state["pdll"] is None
        assert checker._daily_state["consecutive_losses"] == 0
        assert checker._daily_state["daily_pnl"] == 0.0


# ============================================================================
# DXY_CONTINUATION Exit Rules Redesign Tests
# ============================================================================


class TestDXYContinuationNoMicroExit:
    """Tests for DXY_CONTINUATION micro structure bypass (uses HTF instead)."""

    def test_dxy_continuation_ignores_micro_ll_break(self, checker, base_candle):
        """DXY_CONTINUATION should NOT exit on 1m LL break (expects micro breaks during pullback)."""
        trade = TradeRecord(
            trade_id="test-dxy-1",
            signal_id="signal-dxy-1",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # 1m structure break that would exit other setups
        features = {"structure_label": "LL", "timeframe": "1m"}

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )

        # Should NOT invalidate - DXY_CONTINUATION uses HTF invalidation
        assert is_invalid is False
        assert reason is None

    def test_dxy_continuation_ignores_micro_hh_break_short(self, checker, base_candle):
        """Short DXY_CONTINUATION should NOT exit on 1m HH break."""
        trade = TradeRecord(
            trade_id="test-dxy-2",
            signal_id="signal-dxy-2",
            symbol="GC",
            direction="short",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2660.0,
            tp_price=2620.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        features = {"structure_label": "HH", "timeframe": "1m"}

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )

        assert is_invalid is False
        assert reason is None


class TestDXYContinuationHTFInvalidation:
    """Tests for DXY_CONTINUATION HTF-based invalidation."""

    def test_dxy_continuation_exits_on_15m_structure_break_long(
        self, checker, base_candle
    ):
        """Long DXY_CONTINUATION should exit on 15m LL/LH structure break."""
        trade = TradeRecord(
            trade_id="test-dxy-htf-1",
            signal_id="signal-dxy-htf-1",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # HTF structure break against long
        features = {"htf_structure_label": "LL", "structure_label": "HH"}  # 1m is bullish but ignored

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )

        assert is_invalid is True
        assert "HTF" in reason or "15m" in reason
        assert "LL" in reason

    def test_dxy_continuation_exits_on_15m_structure_break_short(
        self, checker, base_candle
    ):
        """Short DXY_CONTINUATION should exit on 15m HH/HL structure break."""
        trade = TradeRecord(
            trade_id="test-dxy-htf-2",
            signal_id="signal-dxy-htf-2",
            symbol="GC",
            direction="short",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2660.0,
            tp_price=2620.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        features = {"htf_structure_label": "HH"}

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )

        assert is_invalid is True
        assert "HTF" in reason or "15m" in reason
        assert "HH" in reason

    def test_dxy_continuation_holds_when_htf_intact_long(self, checker, base_candle):
        """Long DXY_CONTINUATION should hold when HTF structure is HH/HL."""
        trade = TradeRecord(
            trade_id="test-dxy-htf-3",
            signal_id="signal-dxy-htf-3",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # HTF structure supports long
        features = {"htf_structure_label": "HH", "structure_label": "LL"}  # 1m break ignored

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, base_candle, features
        )

        assert is_invalid is False
        assert reason is None

    def test_dxy_continuation_exits_on_vwap_trend_failure(self, checker):
        """DXY_CONTINUATION should exit on VWAP loss + EMA stack flip."""
        trade = TradeRecord(
            trade_id="test-dxy-vwap-1",
            signal_id="signal-dxy-vwap-1",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # Candle closes below VWAP
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2648.0,
            high=2649.0,
            low=2644.0,
            close=2645.0,  # Below VWAP
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        # VWAP violated + EMA stack flipped (EMA9 < EMA20)
        features = {
            "vwap": 2648.0,
            "ema_9": 2646.0,
            "ema_20": 2649.0,  # EMA9 < EMA20 = bearish flip
            "htf_structure_label": "HH",  # HTF still intact
        }

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )

        assert is_invalid is True
        assert "VWAP" in reason
        assert "EMA" in reason


class TestDXYContinuationFlipPersistence:
    """Tests for DXY flip 5-bar persistence requirement."""

    def test_dxy_flip_no_exit_before_5_bars(self, checker, base_candle):
        """DXY_CONTINUATION should NOT exit on DXY flip until 5 bars of persistence."""
        trade = TradeRecord(
            trade_id="test-dxy-flip-1",
            signal_id="signal-dxy-flip-1",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # Both correlations positive (true contradiction) + structure flipped
        features = {
            "dxy_corr_1m": 0.15,
            "dxy_corr_5m": 0.10,
            "dxy_structure": "HH",
        }

        # Bars 1-4: Should NOT exit
        for i in range(4):
            is_invalid, reason = checker.check_dxy_flip(trade, base_candle, features)
            assert is_invalid is False, f"Should not exit at bar {i+1}"

    def test_dxy_flip_exits_at_5_bars(self, checker, base_candle):
        """DXY_CONTINUATION should exit after 5 consecutive bars of DXY flip."""
        trade = TradeRecord(
            trade_id="test-dxy-flip-2",
            signal_id="signal-dxy-flip-2",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        features = {
            "dxy_corr_1m": 0.15,
            "dxy_corr_5m": 0.10,
            "dxy_structure": "HH",
        }

        # 4 bars - no exit
        for _ in range(4):
            is_invalid, _ = checker.check_dxy_flip(trade, base_candle, features)
            assert is_invalid is False

        # 5th bar - should exit
        is_invalid, reason = checker.check_dxy_flip(trade, base_candle, features)
        assert is_invalid is True
        assert "5-bar" in reason

    def test_dxy_flip_counter_resets_when_condition_breaks(self, checker, base_candle):
        """DXY flip counter should reset when condition is no longer met."""
        trade = TradeRecord(
            trade_id="test-dxy-flip-3",
            signal_id="signal-dxy-flip-3",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )

        flip_features = {
            "dxy_corr_1m": 0.15,
            "dxy_corr_5m": 0.10,
            "dxy_structure": "HH",
        }
        no_flip_features = {
            "dxy_corr_1m": -0.3,  # Back to negative
            "dxy_corr_5m": -0.25,
            "dxy_structure": "HH",
        }

        # 3 bars of flip
        for _ in range(3):
            checker.check_dxy_flip(trade, base_candle, flip_features)

        # Condition breaks - counter should reset
        checker.check_dxy_flip(trade, base_candle, no_flip_features)

        # Now need full 5 bars again
        for i in range(4):
            is_invalid, _ = checker.check_dxy_flip(trade, base_candle, flip_features)
            assert is_invalid is False, f"Should need full 5 bars after reset, failed at bar {i+1}"

        # 5th bar after reset - should exit
        is_invalid, _ = checker.check_dxy_flip(trade, base_candle, flip_features)
        assert is_invalid is True

    def test_dxy_flip_requires_both_positive_correlations(self, checker, base_candle):
        """DXY flip should only trigger when BOTH correlations are positive (true contradiction)."""
        trade = TradeRecord(
            trade_id="test-dxy-flip-4",
            signal_id="signal-dxy-flip-4",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # Only 1m positive, 5m still negative - not a true contradiction
        features = {
            "dxy_corr_1m": 0.15,
            "dxy_corr_5m": -0.05,  # Still slightly negative
            "dxy_structure": "HH",
        }

        # Even after 10 bars, should not exit
        for _ in range(10):
            is_invalid, _ = checker.check_dxy_flip(trade, base_candle, features)
            assert is_invalid is False


class TestDXYContinuationTieredTimeStop:
    """Tests for DXY_CONTINUATION tiered time stop (de-risk at 30, exit at 60)."""

    def test_no_action_before_30_bars(self, checker):
        """No de-risk or exit action before 30 bars."""
        trade = TradeRecord(
            trade_id="test-dxy-time-1",
            signal_id="signal-dxy-time-1",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # Candle at 0R (flat)
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 25),
            open=2650.0,
            high=2652.0,
            low=2648.0,
            close=2650.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        is_invalid, reason, action = checker.check_no_1r_reached(
            trade, bars_elapsed=25, candle=candle
        )

        assert is_invalid is False
        assert action is None

    def test_derisk_at_30_bars_below_half_r(self, checker):
        """De-risk action at 30 bars if below +0.5R."""
        trade = TradeRecord(
            trade_id="test-dxy-time-2",
            signal_id="signal-dxy-time-2",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # Candle at +0.2R (below threshold)
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2651.0,
            high=2653.0,
            low=2650.0,
            close=2652.0,  # +2 points = +0.2R
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        is_invalid, reason, action = checker.check_no_1r_reached(
            trade, bars_elapsed=30, candle=candle
        )

        assert is_invalid is False  # Not exiting
        assert action == "de_risk"
        assert "de_risk" in reason

    def test_no_derisk_at_30_bars_if_above_half_r(self, checker):
        """No de-risk at 30 bars if already above +0.5R."""
        trade = TradeRecord(
            trade_id="test-dxy-time-3",
            signal_id="signal-dxy-time-3",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # First candle reaches +0.6R
        candle_1 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 15),
            open=2652.0,
            high=2657.0,  # Touched +0.7R
            low=2651.0,
            close=2656.0,  # +0.6R
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        # Update state to track +0.5R milestone
        checker.check_no_1r_reached(trade, bars_elapsed=15, candle=candle_1)

        # Now at 30 bars, slightly down but already reached milestone
        candle_30 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2653.0,
            high=2654.0,
            low=2651.0,
            close=2652.0,  # +0.2R now
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        is_invalid, reason, action = checker.check_no_1r_reached(
            trade, bars_elapsed=30, candle=candle_30
        )

        # Should not de-risk because +0.5R milestone was already reached
        assert action is None or action != "de_risk"

    def test_exit_at_60_bars_if_structure_deteriorated(self, checker):
        """Exit at 60 bars if +1R not reached AND HTF structure deteriorated."""
        trade = TradeRecord(
            trade_id="test-dxy-time-4",
            signal_id="signal-dxy-time-4",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 11, 0),
            open=2651.0,
            high=2653.0,
            low=2649.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        # HTF structure deteriorated for long
        features = {"htf_structure_label": "LL"}

        is_invalid, reason, action = checker.check_no_1r_reached(
            trade, bars_elapsed=60, candle=candle, features=features
        )

        assert is_invalid is True
        assert action == "exit"
        assert "structure deteriorated" in reason.lower() or "htf" in reason.lower()

    def test_no_exit_at_60_bars_if_structure_intact(self, checker):
        """Do NOT exit at 60 bars if HTF structure still intact."""
        trade = TradeRecord(
            trade_id="test-dxy-time-5",
            signal_id="signal-dxy-time-5",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 11, 0),
            open=2651.0,
            high=2653.0,
            low=2649.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        # HTF structure still bullish for long
        features = {"htf_structure_label": "HH"}

        is_invalid, reason, action = checker.check_no_1r_reached(
            trade, bars_elapsed=60, candle=candle, features=features
        )

        assert is_invalid is False
        # Continue holding


class TestDXYContinuationPartialProfit:
    """Tests for partial profit taking at +1R."""

    def test_partial_profit_action_at_1r(self, checker):
        """DXY_CONTINUATION should trigger partial profit action at +1R with BE buffer."""
        trade = TradeRecord(
            trade_id="test-dxy-partial-1",
            signal_id="signal-dxy-partial-1",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,  # 10 points risk
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        # Candle that reaches +1R
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 15),
            open=2655.0,
            high=2662.0,  # Touches +1.2R
            low=2654.0,
            close=2660.0,  # +1R
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action = checker.update_state(trade, candle)

        assert action is not None
        assert action["action"] == "partial_profit"
        assert action["close_pct"] == 40  # Per DXY_CONTINUATION spec: 40% partial at TP1
        assert action["move_sl_to_breakeven"] is True
        # Phase 2.0: BE with 0.1R buffer, NOT exact entry
        # risk_points = 2650 - 2640 = 10, buffer = 0.1 * 10 = 1.0
        # BE price = 2650 + 1.0 = 2651.0
        assert action["new_sl_price"] == 2651.0  # entry + 0.1R buffer
        assert action["be_price"] == 2651.0
        assert action["be_buffer_r"] == 0.10

    def test_partial_profit_only_triggers_once(self, checker):
        """Partial profit should only trigger once per trade."""
        trade = TradeRecord(
            trade_id="test-dxy-partial-2",
            signal_id="signal-dxy-partial-2",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 15),
            open=2655.0,
            high=2662.0,
            low=2654.0,
            close=2660.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # First call triggers partial
        action1 = checker.update_state(trade, candle)
        assert action1 is not None
        assert action1["action"] == "partial_profit"

        # Second call should NOT trigger again
        action2 = checker.update_state(trade, candle)
        assert action2 is None

    def test_no_partial_profit_for_vwap_reclaim(self, checker):
        """VWAP_RECLAIM should NOT trigger partial profit action."""
        trade = TradeRecord(
            trade_id="test-vwap-partial-1",
            signal_id="signal-vwap-partial-1",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 15),
            open=2655.0,
            high=2662.0,
            low=2654.0,
            close=2660.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action = checker.update_state(trade, candle)

        # VWAP_RECLAIM doesn't get partial profit
        assert action is None


class TestCheckAllWithActions:
    """Tests for check_all returning action alongside exit status."""

    def test_check_all_returns_action_tuple(self, checker, base_trade, base_candle):
        """check_all should return (should_exit, reason, action) tuple."""
        result = checker.check_all(base_trade, base_candle, bars_elapsed=5)

        assert isinstance(result, tuple)
        assert len(result) == 3
        should_exit, reason, action = result

    def test_check_all_derisk_action_not_exit(self, checker):
        """De-risk action should not cause exit."""
        trade = TradeRecord(
            trade_id="test-all-derisk",
            signal_id="signal-all-derisk",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2650.0,
            high=2652.0,
            low=2648.0,
            close=2651.0,  # Only +0.1R
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        should_exit, reason, action = checker.check_all(
            trade, candle, bars_elapsed=30, features={}
        )

        assert should_exit is False
        assert action == "de_risk"

    def test_check_all_partial_profit_action(self, checker):
        """check_all should return partial_profit action when +1R reached."""
        trade = TradeRecord(
            trade_id="test-all-partial",
            signal_id="signal-all-partial",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2680.0,
            risk_amount=10.0,
            reward_amount=30.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 15),
            open=2655.0,
            high=2662.0,
            low=2654.0,
            close=2660.0,  # +1R
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        should_exit, reason, action = checker.check_all(
            trade, candle, bars_elapsed=15, features={}
        )

        assert should_exit is False  # Partial doesn't exit
        assert action == "partial_profit"


class TestRunnerUnlockModeA:
    """Tests for Phase-2 runner unlock (Mode A: Post-TP1 Micro-BOS)."""

    def test_unlock_on_bullish_bos_for_long_trade(self, checker):
        """Runner unlocks when bullish BOS detected for long trade."""
        trade = TradeRecord(
            trade_id="test-runner-long",
            signal_id="signal-runner",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,  # TP1 hit at bar 25
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Simulate partial taken (TP1 hit)
        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        features = {
            "bos_detected": True,
            "bos_direction": "bullish",
        }

        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=30, features=features
        )

        assert action == "unlock_runner"
        assert "bullish BOS" in reason
        assert state["runner_unlocked"] is True
        assert state["runner_unlock_bar_idx"] == 30

    def test_unlock_on_bearish_bos_for_short_trade(self, checker):
        """Runner unlocks when bearish BOS detected for short trade."""
        trade = TradeRecord(
            trade_id="test-runner-short",
            signal_id="signal-runner",
            symbol="GC",
            direction="short",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2655.0,
            tp_price=2640.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2642.0,
            high=2644.0,
            low=2638.0,
            close=2639.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Simulate partial taken
        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        features = {
            "bos_detected": True,
            "bos_direction": "bearish",
        }

        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=30, features=features
        )

        assert action == "unlock_runner"
        assert "bearish BOS" in reason
        assert state["runner_unlocked"] is True

    def test_no_bos_unlock_on_opposite_direction_bos(self, checker):
        """Runner does NOT unlock via BOS when BOS is opposite direction.

        Note: With Phase 2 fallback enabled, the runner may still unlock via
        fallback conditions. This test ensures BOS direction is checked correctly.
        """
        trade = TradeRecord(
            trade_id="test-runner-opposite",
            signal_id="signal-runner",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        # TP1 = 2655 (entry + 1R), hold floor = 2655 - 0.25*5 = 2653.75
        # Use a candle that violates hold to prevent fallback unlock
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2654.0,
            high=2656.0,
            low=2650.0,  # Below hold floor (2653.75) - hold violated
            close=2655.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # BOS in wrong direction (bearish for long trade)
        features = {
            "bos_detected": True,
            "bos_direction": "bearish",  # Wrong direction for long
        }

        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=30, features=features
        )

        # No unlock because: BOS wrong direction AND fallback hold violated
        assert action is None
        assert reason is None
        assert state["runner_unlocked"] is False

    def test_close_at_market_when_window_expires(self, checker):
        """Runner closes at market when unlock window expires without BOS."""
        trade = TradeRecord(
            trade_id="test-runner-expire",
            signal_id="signal-runner",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 45),
            open=2656.0,
            high=2658.0,
            low=2654.0,
            close=2657.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # No BOS detected, window = 15 bars, bar 25+15=40 would expire
        features = {
            "bos_detected": False,
            "bos_direction": None,
        }

        # At bar 40, window expires (15 bars after TP1 at bar 25)
        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=40, features=features
        )

        assert action == "close_at_market"
        assert "window expired" in reason
        assert "15 bars since TP1" in reason

    def test_window_measured_from_tp1_bar_not_entry(self, checker):
        """Unlock window is measured from TP1 bar, not entry bar."""
        trade = TradeRecord(
            trade_id="test-runner-window",
            signal_id="signal-runner",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            entry_bar_idx=0,  # Entry at bar 0
            tp1_hit_bar_idx=100,  # TP1 hit at bar 100
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 12, 0),
            open=2656.0,
            high=2658.0,
            low=2654.0,
            close=2657.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 100

        features = {"bos_detected": False}

        # Bar 110 = only 10 bars after TP1, should still be waiting
        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=110, features=features
        )
        assert action is None  # Still waiting, not expired

        # Bar 115 = exactly 15 bars after TP1, window expires
        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=115, features=features
        )
        assert action == "close_at_market"

    def test_no_action_before_partial_taken(self, checker):
        """No runner action before partial profit is taken."""
        trade = TradeRecord(
            trade_id="test-runner-no-partial",
            signal_id="signal-runner",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # partial_taken is False by default
        features = {
            "bos_detected": True,
            "bos_direction": "bullish",
        }

        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=30, features=features
        )

        assert action is None
        assert reason is None

    def test_no_action_for_non_dxy_continuation(self, checker):
        """No runner action for non-DXY_CONTINUATION trades."""
        trade = TradeRecord(
            trade_id="test-runner-vwap",
            signal_id="signal-runner",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",  # Not DXY_CONTINUATION
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Even with partial taken, VWAP_RECLAIM should not trigger runner logic
        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        features = {
            "bos_detected": True,
            "bos_direction": "bullish",
        }

        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=30, features=features
        )

        assert action is None
        assert reason is None

    def test_no_action_after_already_unlocked(self, checker):
        """No action if runner is already unlocked."""
        trade = TradeRecord(
            trade_id="test-runner-already",
            signal_id="signal-runner",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 35),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25
        state["runner_unlocked"] = True  # Already unlocked!
        state["runner_unlock_bar_idx"] = 30

        features = {
            "bos_detected": True,
            "bos_direction": "bullish",
        }

        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=35, features=features
        )

        assert action is None
        assert reason is None


# ============================================================================
# Phase 2: Runner Hard Invalidation Tests (Section 4 of spec)
# ============================================================================


class TestRunnerHardInvalidation:
    """Tests for Phase-2 hard invalidation (Section 4 of spec).

    Hard invalidation conditions exit the runner IMMEDIATELY when the
    continuation thesis is broken. These are checked BEFORE any unlock attempt.
    """

    def test_chop_detected_exits_immediately(self, checker):
        """Runner should exit immediately when chop_detected=True."""
        trade = TradeRecord(
            trade_id="test-hard-chop",
            signal_id="signal-hard",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        htf_bias = {
            "chop_detected": True,
            "dxy_aligned": True,
            "conflict_detected": False,
        }

        action, reason = checker.check_runner_hard_invalidation(
            trade, candle, 30, {}, htf_bias
        )

        assert action == "exit_runner"
        assert "chop_detected" in reason

    def test_htf_conflict_exits_immediately(self, checker):
        """Runner should exit immediately when conflict_detected=True."""
        trade = TradeRecord(
            trade_id="test-hard-conflict",
            signal_id="signal-hard",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        htf_bias = {
            "chop_detected": False,
            "dxy_aligned": True,
            "conflict_detected": True,
            "conflict_reason": "1H vs 15M structure opposition",
        }

        action, reason = checker.check_runner_hard_invalidation(
            trade, candle, 30, {}, htf_bias
        )

        assert action == "exit_runner"
        assert "htf_conflict_detected" in reason

    def test_dxy_misaligned_5_bars_exits(self, checker):
        """Runner exits after 5 consecutive bars of dxy_aligned=False."""
        trade = TradeRecord(
            trade_id="test-hard-dxy",
            signal_id="signal-hard",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        htf_bias = {
            "chop_detected": False,
            "dxy_aligned": False,  # Misaligned
            "conflict_detected": False,
        }

        # Simulate 4 bars of misalignment - should NOT exit yet
        for bar in range(30, 34):
            action, reason = checker.check_runner_hard_invalidation(
                trade, candle, bar, {}, htf_bias
            )
            assert action is None, f"Should not exit at bar {bar}"

        # 5th bar - should exit
        action, reason = checker.check_runner_hard_invalidation(
            trade, candle, 34, {}, htf_bias
        )
        assert action == "exit_runner"
        assert "dxy_misaligned_5_bars" in reason

    def test_dxy_misaligned_counter_resets_on_realign(self, checker):
        """Counter resets when dxy_aligned becomes True."""
        trade = TradeRecord(
            trade_id="test-hard-reset",
            signal_id="signal-hard",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # 3 bars misaligned
        htf_bias_misaligned = {
            "chop_detected": False,
            "dxy_aligned": False,
            "conflict_detected": False,
        }
        for bar in range(30, 33):
            checker.check_runner_hard_invalidation(
                trade, candle, bar, {}, htf_bias_misaligned
            )

        assert state["dxy_misaligned_bars"] == 3

        # Realign
        htf_bias_aligned = {
            "chop_detected": False,
            "dxy_aligned": True,
            "conflict_detected": False,
        }
        checker.check_runner_hard_invalidation(
            trade, candle, 33, {}, htf_bias_aligned
        )

        # Counter should be reset
        assert state["dxy_misaligned_bars"] == 0

        # Now 4 more misaligned bars - still shouldn't exit (total < 5)
        for bar in range(34, 38):
            action, reason = checker.check_runner_hard_invalidation(
                trade, candle, bar, {}, htf_bias_misaligned
            )
            assert action is None

    def test_hard_invalidation_skipped_without_htf_bias(self, checker):
        """Hard invalidation is skipped when htf_bias is None."""
        trade = TradeRecord(
            trade_id="test-hard-no-htf",
            signal_id="signal-hard",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # No HTF bias available
        action, reason = checker.check_runner_hard_invalidation(
            trade, candle, 30, {}, None
        )

        assert action is None
        assert reason is None

    def test_hard_invalidation_checked_before_bos_in_full_flow(self, checker):
        """Hard invalidation is checked BEFORE BOS unlock in full flow."""
        trade = TradeRecord(
            trade_id="test-hard-before-bos",
            signal_id="signal-hard",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2660.0,
            risk_amount=500.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=5.0,
            tp1_hit_bar_idx=25,
        )
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2658.0,
            high=2662.0,
            low=2657.0,
            close=2661.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # Even though BOS is detected, chop should cause exit first
        features = {
            "bos_detected": True,
            "bos_direction": "bullish",
        }
        htf_bias = {
            "chop_detected": True,  # Hard invalidation
            "dxy_aligned": True,
            "conflict_detected": False,
        }

        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=30, features=features, htf_bias=htf_bias
        )

        # Should exit due to hard invalidation, NOT unlock
        assert action == "exit_runner"
        assert "chop_detected" in reason
        assert state["runner_unlocked"] is False


# ============================================================================
# Phase 2: Fallback A Tests (Hold + Impulse, Section 6 of spec)
# ============================================================================


class TestFallbackAHoldImpulse:
    """Tests for Fallback A: Hold + Impulse Continuation (Section 6 of spec).

    Fallback A unlocks when:
    - Hold condition: price stays within 0.25R of TP1
    - Impulse condition: close > prior_high OR body_ratio >= 0.6
    """

    def test_hold_condition_long_within_buffer(self, checker):
        """Long: hold is met when min_low >= tp1_price - 0.25R."""
        trade = TradeRecord(
            trade_id="test-fallback-hold-long",
            signal_id="signal-fallback",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,  # 10 point risk
            tp_price=2660.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=10.0,  # R = 10 points
            tp1_hit_bar_idx=25,
        )
        # TP1 = entry + 1R = 2660.0
        # Hold floor = 2660.0 - 0.25 * 10 = 2657.5

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # Candle with low above hold floor (hold met)
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2661.0,
            high=2665.0,
            low=2658.0,  # Above 2657.5 hold floor
            close=2664.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action, reason = checker.check_runner_fallback_unlock(
            trade, candle, 30, {}
        )

        # Hold is met but no impulse yet
        assert action is None

    def test_hold_condition_long_violated_rejects(self, checker):
        """Long: hold is violated when price drops > 0.25R below TP1."""
        trade = TradeRecord(
            trade_id="test-fallback-hold-violated",
            signal_id="signal-fallback",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,  # 10 point risk
            tp_price=2660.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=10.0,
            tp1_hit_bar_idx=25,
        )
        # Hold floor = 2660.0 - 0.25 * 10 = 2657.5

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # First candle with impulse
        candle1 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2661.0,
            high=2665.0,
            low=2660.0,
            close=2664.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        checker.check_runner_fallback_unlock(trade, candle1, 30, {})

        # Second candle breaks hold floor
        candle2 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 31),
            open=2660.0,
            high=2666.0,  # Close above prior high = impulse
            low=2655.0,  # Below 2657.5 = hold violated
            close=2666.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action, reason = checker.check_runner_fallback_unlock(
            trade, candle2, 31, {}
        )

        # Even with impulse, hold is violated so no unlock
        assert action is None

    def test_impulse_close_above_prior_high(self, checker):
        """Impulse detected when close > prior_high."""
        trade = TradeRecord(
            trade_id="test-fallback-impulse-close",
            signal_id="signal-fallback",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2660.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=10.0,
            tp1_hit_bar_idx=25,
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # First candle - establishes prior high
        candle1 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2661.0,
            high=2663.0,  # Prior high
            low=2660.0,
            close=2662.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        checker.check_runner_fallback_unlock(trade, candle1, 30, {})

        # Second candle - close > prior_high (2663), hold maintained
        candle2 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 31),
            open=2662.0,
            high=2666.0,
            low=2661.0,  # Above hold floor (2657.5)
            close=2665.0,  # > 2663 = impulse!
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action, reason = checker.check_runner_fallback_unlock(
            trade, candle2, 31, {}
        )

        assert action == "unlock_runner"
        assert "hold_impulse" in reason
        assert "close" in reason and "prior_high" in reason

    def test_impulse_body_ratio_0_6(self, checker):
        """Impulse detected when body_ratio >= 0.6."""
        trade = TradeRecord(
            trade_id="test-fallback-impulse-body",
            signal_id="signal-fallback",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2660.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=10.0,
            tp1_hit_bar_idx=25,
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # Candle with high body ratio (>= 0.6)
        # Range = 5, body = 4, ratio = 0.8
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2660.0,
            high=2665.0,
            low=2660.0,  # Range = 5
            close=2664.0,  # Body = 4, ratio = 0.8
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action, reason = checker.check_runner_fallback_unlock(
            trade, candle, 30, {}
        )

        assert action == "unlock_runner"
        assert "hold_impulse" in reason
        assert "body_ratio" in reason

    def test_unlock_requires_both_hold_and_impulse(self, checker):
        """Fallback unlock requires BOTH hold AND impulse."""
        trade = TradeRecord(
            trade_id="test-fallback-both",
            signal_id="signal-fallback",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2660.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=10.0,
            tp1_hit_bar_idx=25,
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # Candle with impulse (high body ratio) but hold violated
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2656.0,
            high=2661.0,
            low=2655.0,  # Below hold floor (2657.5) - hold violated
            close=2660.0,  # Body ratio = 4/6 = 0.67 - impulse met
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action, reason = checker.check_runner_fallback_unlock(
            trade, candle, 30, {}
        )

        # Impulse met but hold violated - no unlock
        assert action is None

    def test_impulse_persists_once_detected(self, checker):
        """Once impulse detected in window, it persists."""
        trade = TradeRecord(
            trade_id="test-fallback-persist",
            signal_id="signal-fallback",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2660.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=10.0,
            tp1_hit_bar_idx=25,
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # First candle - impulse detected (high body ratio) but hold violated
        # Body = 4, Range = 5, ratio = 0.8
        # Low 2655 < hold floor 2657.5, so hold violated
        candle1 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2660.0,
            high=2664.0,
            low=2655.0,  # Below hold floor = hold violated
            close=2664.0,  # Body = 4, Range = 9, ratio = 4/9 = 0.44, not enough
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Actually we need a stronger impulse - let's use close > prior_high approach
        # First, establish a prior bar
        candle0 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 29),
            open=2659.0,
            high=2660.0,  # This becomes prior_high
            low=2658.0,
            close=2659.5,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        checker.check_runner_fallback_unlock(trade, candle0, 29, {})

        # Second call: candle1 with close (2664) > prior_high (2660) = impulse!
        # But low 2655 < hold floor 2657.5 = hold violated
        checker.check_runner_fallback_unlock(trade, candle1, 30, {})

        # Impulse should be persisted
        assert state["impulse_detected"] is True

        # Reset min_low to simulate hold being met again
        state["min_low_since_tp1"] = 2658.0  # Above hold floor

        # Second candle - no impulse on this bar, but hold is now met
        candle2 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 31),
            open=2664.0,
            high=2665.0,
            low=2662.0,  # Above hold floor
            close=2663.0,  # No new impulse on this bar
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action, reason = checker.check_runner_fallback_unlock(
            trade, candle2, 31, {}
        )

        # Should unlock because impulse was persisted from bar 1
        assert action == "unlock_runner"
        assert "hold_impulse" in reason

    def test_fallback_only_if_no_bos_in_full_flow(self, checker):
        """Fallback is only evaluated if primary BOS hasn't triggered."""
        trade = TradeRecord(
            trade_id="test-fallback-after-bos",
            signal_id="signal-fallback",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2660.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=10.0,
            tp1_hit_bar_idx=25,
        )

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # Candle that would trigger fallback (impulse + hold)
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2660.0,
            high=2665.0,
            low=2660.0,
            close=2664.0,  # Body ratio = 0.8
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # BOS detected in trade direction - should unlock via BOS, not fallback
        features = {
            "bos_detected": True,
            "bos_direction": "bullish",
        }

        action, reason = checker.check_runner_unlock(
            trade, candle, current_bar_idx=30, features=features, htf_bias=None
        )

        # Should unlock via BOS (primary), not fallback
        assert action == "unlock_runner"
        assert "micro_bos" in reason
        assert state["runner_unlock_reason"] == "micro_bos"

    def test_fallback_short_direction(self, checker):
        """Fallback works correctly for short trades."""
        trade = TradeRecord(
            trade_id="test-fallback-short",
            signal_id="signal-fallback",
            symbol="GC",
            direction="short",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2660.0,  # 10 point risk
            tp_price=2640.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            risk_points=10.0,
            tp1_hit_bar_idx=25,
        )
        # TP1 = entry - 1R = 2640.0
        # Hold ceiling = 2640.0 + 0.25 * 10 = 2642.5

        state = checker._get_trade_state(trade.trade_id)
        state["partial_taken"] = True
        state["tp1_hit_bar_idx"] = 25

        # First candle - establishes prior low
        candle1 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 30),
            open=2639.0,
            high=2641.0,  # Below hold ceiling (2642.5)
            low=2637.0,  # Prior low
            close=2638.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        checker.check_runner_fallback_unlock(trade, candle1, 30, {})

        # Second candle - close < prior_low (2637), hold maintained
        candle2 = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 31),
            open=2638.0,
            high=2640.0,  # Below hold ceiling
            low=2634.0,
            close=2635.0,  # < 2637 = impulse!
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        action, reason = checker.check_runner_fallback_unlock(
            trade, candle2, 31, {}
        )

        assert action == "unlock_runner"
        assert "hold_impulse" in reason
        assert "close" in reason and "prior_low" in reason
