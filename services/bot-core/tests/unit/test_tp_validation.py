"""Unit tests for TP structural target validation (SOP Section 4.3)."""

from datetime import datetime, timezone

import pytest

from bot_core_svc.signal_engine import validate_tp_target
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage


@pytest.fixture
def base_features():
    """Base features message for testing."""
    return FeaturesMessage(
        timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        vwap=2645.0,
    )


@pytest.fixture
def base_htf_bias():
    """Base HTF bias message for testing (with no structural targets set)."""
    return HTFBiasMessage(
        timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        bias="bullish",
        score=8.0,
        confidence="A+",
        structure_15m="HH",
        structure_1h="HH",
        dxy_aligned=True,
        chop_detected=False,
        # TP targets - None by default, set per test
        htf_range_high=None,
        htf_range_low=None,
        untouched_liquidity_high=None,
        untouched_liquidity_low=None,
        nearest_fvg_high=None,
        nearest_fvg_low=None,
    )


class TestSLValidation:
    """Test SL placement validation (SOP critical requirement)."""

    def test_long_rejects_sl_above_entry(self, base_features, base_htf_bias):
        """Long trade rejected when SL is above entry price (invalid stop)."""
        entry_price = 2650.0
        sl_price = 2655.0  # INVALID: SL above entry for long

        base_features.nearest_liquidity_long = 2680.0

        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None
        assert "Invalid SL" in rejection
        assert "below entry" in rejection

    def test_long_rejects_sl_equal_to_entry(self, base_features, base_htf_bias):
        """Long trade rejected when SL equals entry (zero risk)."""
        entry_price = 2650.0
        sl_price = 2650.0  # INVALID: Zero risk distance

        base_features.nearest_liquidity_long = 2680.0

        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None
        assert "Invalid SL" in rejection
        # Zero risk is caught by direction-specific check (sl_price >= entry_price)
        assert "below entry" in rejection

    def test_short_rejects_sl_below_entry(self, base_features, base_htf_bias):
        """Short trade rejected when SL is below entry price (invalid stop)."""
        entry_price = 2650.0
        sl_price = 2645.0  # INVALID: SL below entry for short

        base_features.nearest_liquidity_short = 2620.0

        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None
        assert "Invalid SL" in rejection
        assert "above entry" in rejection

    def test_short_rejects_sl_equal_to_entry(self, base_features, base_htf_bias):
        """Short trade rejected when SL equals entry (zero risk)."""
        entry_price = 2650.0
        sl_price = 2650.0  # INVALID: Zero risk distance

        base_features.nearest_liquidity_short = 2620.0

        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None
        assert "Invalid SL" in rejection
        # Zero risk is caught by direction-specific check (sl_price <= entry_price)
        assert "above entry" in rejection

    def test_long_accepts_valid_sl_below_entry(self, base_features, base_htf_bias):
        """Long trade accepted when SL is correctly below entry."""
        entry_price = 2650.0
        sl_price = 2640.0  # VALID: SL below entry for long

        base_features.nearest_liquidity_long = 2680.0

        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2680.0

    def test_short_accepts_valid_sl_above_entry(self, base_features, base_htf_bias):
        """Short trade accepted when SL is correctly above entry."""
        entry_price = 2640.0
        sl_price = 2650.0  # VALID: SL above entry for short

        base_features.nearest_liquidity_short = 2610.0

        tp_plan, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2610.0


class TestTPStructuralValidation:
    """Test TP structural target validation (SOP Section 4.3)."""

    def test_long_accepts_target_at_exactly_3r(self, base_features, base_htf_bias):
        """Long trade accepted when target exists at exactly 3R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = entry + (3 * 10) = 2680.0

        base_features.nearest_liquidity_long = 2680.0

        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2680.0

    def test_long_accepts_target_above_3r(self, base_features, base_htf_bias):
        """Long trade accepted when target exists above 3R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0

        base_features.nearest_liquidity_long = 2690.0  # Above 3R

        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2690.0

    def test_long_rejects_target_below_3r(self, base_features, base_htf_bias):
        """Long trade rejected when nearest target is below 3R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0

        base_features.nearest_liquidity_long = 2670.0  # Below 3R
        base_features.prior_session_high = None

        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None
        assert "No structural target" in rejection
        assert "≥3.0R" in rejection

    def test_long_rejects_when_no_target_available(self, base_features, base_htf_bias):
        """Long trade rejected when no structural target exists."""
        entry_price = 2650.0
        sl_price = 2640.0

        base_features.nearest_liquidity_long = None
        base_features.prior_session_high = None

        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None
        assert "No structural target" in rejection

    def test_short_accepts_target_at_exactly_3r(self, base_features, base_htf_bias):
        """Short trade accepted when target exists at exactly 3R."""
        entry_price = 2640.0
        sl_price = 2650.0  # Risk = 10 points
        # 3R = entry - (3 * 10) = 2610.0

        base_features.nearest_liquidity_short = 2610.0

        tp_plan, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2610.0

    def test_short_accepts_target_below_3r(self, base_features, base_htf_bias):
        """Short trade accepted when target exists below 3R."""
        entry_price = 2640.0
        sl_price = 2650.0  # Risk = 10 points
        # 3R = 2610.0

        base_features.nearest_liquidity_short = 2600.0  # Below 3R (better)

        tp_plan, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2600.0

    def test_short_rejects_target_above_3r(self, base_features, base_htf_bias):
        """Short trade rejected when nearest target is above 3R."""
        entry_price = 2640.0
        sl_price = 2650.0  # Risk = 10 points
        # 3R = 2610.0

        base_features.nearest_liquidity_short = 2620.0  # Above 3R (not far enough)
        base_features.prior_session_low = None

        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None
        assert "No structural target" in rejection

    def test_short_rejects_when_no_target_available(self, base_features, base_htf_bias):
        """Short trade rejected when no structural target exists."""
        entry_price = 2640.0
        sl_price = 2650.0

        base_features.nearest_liquidity_short = None
        base_features.prior_session_low = None

        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None

    def test_priority_order_nearest_liquidity_first(self, base_features, base_htf_bias):
        """Nearest liquidity target has priority over prior session high."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0

        base_features.nearest_liquidity_long = 2685.0  # Valid at 3.5R
        base_features.prior_session_high = 2695.0  # Also valid at 4.5R

        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2685.0, "Should use nearest_liquidity (first priority)"

    def test_fallback_to_prior_session_high_when_liquidity_invalid(
        self, base_features, base_htf_bias
    ):
        """Falls back to prior session high when nearest liquidity below 3R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0

        base_features.nearest_liquidity_long = 2670.0  # Below 3R (invalid)
        base_features.prior_session_high = 2690.0  # Above 3R (valid)

        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2690.0, "Should fallback to prior_session_high"

    def test_configurable_min_rr_2r(self, base_features, base_htf_bias):
        """Test with configurable minimum R:R (2R instead of 3R)."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 2R = entry + (2 * 10) = 2670.0

        base_features.nearest_liquidity_long = 2670.0

        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=2.0,  # VWAP_FADE uses 2R
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2670.0

    def test_rejects_when_only_target_below_required_rr(
        self, base_features, base_htf_bias
    ):
        """Rejects when only available target is below required R:R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0

        # Both targets below 3R
        base_features.nearest_liquidity_long = 2675.0
        base_features.prior_session_high = 2678.0

        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            htf_bias=base_htf_bias,
            min_rr=3.0,
        )

        assert tp_price is None
        assert rejection is not None
        assert "No structural target" in rejection


class TestContinuationEligibility:
    """Test is_continuation_eligible() routing logic."""

    def test_vwap_reclaim_with_a_plus_htf_is_eligible(self, base_htf_bias):
        """VWAP_RECLAIM + A+ HTF + no chop = continuation eligible."""
        from bot_core_svc.signal_engine import is_continuation_eligible

        base_htf_bias.confidence = "A+"
        base_htf_bias.chop_detected = False
        base_htf_bias.conflict_detected = False
        assert is_continuation_eligible("VWAP_RECLAIM", base_htf_bias) is True

    def test_vwap_fade_not_eligible(self, base_htf_bias):
        """VWAP_FADE never uses continuation mode."""
        from bot_core_svc.signal_engine import is_continuation_eligible

        base_htf_bias.confidence = "A+"
        assert is_continuation_eligible("VWAP_FADE", base_htf_bias) is False

    def test_chop_disqualifies_continuation(self, base_htf_bias):
        """Chop detected = not eligible for continuation."""
        from bot_core_svc.signal_engine import is_continuation_eligible

        base_htf_bias.confidence = "A+"
        base_htf_bias.chop_detected = True
        assert is_continuation_eligible("VWAP_RECLAIM", base_htf_bias) is False

    def test_non_a_plus_disqualifies_continuation(self, base_htf_bias):
        """Only A+ HTF qualifies for continuation mode."""
        from bot_core_svc.signal_engine import is_continuation_eligible

        base_htf_bias.confidence = "A"
        assert is_continuation_eligible("VWAP_RECLAIM", base_htf_bias) is False

    def test_conflict_disqualifies_continuation(self, base_htf_bias):
        """Conflict detected = not eligible for continuation."""
        from bot_core_svc.signal_engine import is_continuation_eligible

        base_htf_bias.confidence = "A+"
        base_htf_bias.chop_detected = False
        base_htf_bias.conflict_detected = True
        assert is_continuation_eligible("VWAP_RECLAIM", base_htf_bias) is False


class TestContinuationTP1Validation:
    """Test TP1 structural target validation at 1.5R minimum."""

    def test_accepts_target_at_exactly_1_5r(self, base_features, base_htf_bias):
        """Continuation mode accepts target at exactly 1.5R."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2650.0, 2640.0  # Risk = 10
        base_features.nearest_liquidity_long = 2665.0  # 1.5R
        base_htf_bias.htf_range_high = 2700.0  # For expansion path

        tp_plan, rejection = validate_continuation_tp(
            "long", entry, sl, base_features, base_htf_bias
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2665.0
        assert abs(tp_plan.rr_tp1 - 1.5) < 0.01  # Floating point tolerance

    def test_rejects_target_below_1_5r(self, base_features, base_htf_bias):
        """Continuation mode rejects when all targets below 1.5R."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2650.0, 2640.0  # Risk = 10
        base_features.nearest_liquidity_long = 2660.0  # Only 1R
        base_features.prior_session_high = None
        base_htf_bias.htf_range_high = None
        base_htf_bias.untouched_liquidity_high = None
        base_htf_bias.nearest_fvg_high = None

        tp_plan, rejection = validate_continuation_tp(
            "long", entry, sl, base_features, base_htf_bias
        )

        assert tp_plan is None
        assert rejection is not None
        assert "CONTINUATION_TP1_BELOW_MIN_RR" in rejection

    def test_uses_nearest_valid_target_as_tp1(self, base_features, base_htf_bias):
        """Continuation mode uses nearest valid target >= 1.5R as TP1."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2650.0, 2640.0  # Risk = 10, 1.5R = 2665.0
        base_features.nearest_liquidity_long = 2670.0  # 2R - nearest valid
        base_features.prior_session_high = 2690.0  # 4R - further away
        base_htf_bias.htf_range_high = 2700.0  # For expansion

        tp_plan, rejection = validate_continuation_tp(
            "long", entry, sl, base_features, base_htf_bias
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2670.0  # Should use nearest (2R, not 4R)

    def test_short_accepts_target_at_1_5r(self, base_features, base_htf_bias):
        """Continuation mode works for shorts at 1.5R."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2640.0, 2650.0  # Risk = 10
        base_features.nearest_liquidity_short = 2625.0  # 1.5R
        base_htf_bias.htf_range_low = 2600.0  # For expansion path

        tp_plan, rejection = validate_continuation_tp(
            "short", entry, sl, base_features, base_htf_bias
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == 2625.0
        assert abs(tp_plan.rr_tp1 - 1.5) < 0.01


class TestExpansionPathValidation:
    """Test expansion path validation (Step B of continuation mode)."""

    def test_expansion_valid_when_htf_range_extends(self, base_features, base_htf_bias):
        """Valid expansion when htf_range_high > tp1."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2650.0, 2640.0
        base_features.nearest_liquidity_long = 2665.0  # TP1 at 1.5R
        base_htf_bias.htf_range_high = 2700.0  # Beyond TP1 - provides expansion

        tp_plan, rejection = validate_continuation_tp(
            "long", entry, sl, base_features, base_htf_bias
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.expansion_path_valid is True
        assert tp_plan.tp2 == 2700.0

    def test_expansion_valid_when_untouched_liquidity_beyond(
        self, base_features, base_htf_bias
    ):
        """Valid expansion when untouched_liquidity_high > tp1."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2650.0, 2640.0
        base_features.nearest_liquidity_long = 2665.0  # TP1 at 1.5R
        base_htf_bias.htf_range_high = None
        base_htf_bias.untouched_liquidity_high = 2690.0  # Beyond TP1

        tp_plan, rejection = validate_continuation_tp(
            "long", entry, sl, base_features, base_htf_bias
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.expansion_path_valid is True

    def test_rejects_when_no_expansion_path(self, base_features, base_htf_bias):
        """Reject when no expansion potential beyond TP1."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2650.0, 2640.0
        base_features.nearest_liquidity_long = 2665.0  # TP1 at 1.5R
        # All HTF targets below or at TP1 (no expansion)
        base_htf_bias.htf_range_high = 2660.0  # Below TP1
        base_htf_bias.untouched_liquidity_high = None
        base_htf_bias.nearest_fvg_high = None

        tp_plan, rejection = validate_continuation_tp(
            "long", entry, sl, base_features, base_htf_bias
        )

        assert tp_plan is None
        assert rejection is not None
        assert "CONTINUATION_NO_EXPANSION_PATH" in rejection

    def test_expansion_valid_for_shorts_when_range_extends(
        self, base_features, base_htf_bias
    ):
        """Shorts: expansion valid when htf_range_low < tp1."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2640.0, 2650.0
        base_features.nearest_liquidity_short = 2625.0  # TP1 at 1.5R
        base_htf_bias.htf_range_low = 2600.0  # Below TP1 - provides expansion

        tp_plan, rejection = validate_continuation_tp(
            "short", entry, sl, base_features, base_htf_bias
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.expansion_path_valid is True
        assert tp_plan.tp2 == 2600.0


class TestContinuationHTFOppositionBlock:
    """Test HTF opposition FVG blocking in continuation mode (FIX #3)."""

    def test_long_blocked_by_bearish_fvg_in_path(self, base_features, base_htf_bias):
        """Long continuation rejected when bearish FVG blocks path to TP2."""
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2650.0, 2640.0  # Risk = 10, long direction
        base_features.nearest_liquidity_long = 2665.0  # TP1 at 1.5R
        base_htf_bias.htf_range_high = 2700.0  # TP2 would be here

        # Bearish FVG blocks path - high is below TP2
        base_htf_bias.opposing_fvg_high = 2695.0  # Between TP1 and TP2
        base_htf_bias.opposing_fvg_low = 2685.0

        tp_plan, rejection = validate_continuation_tp(
            "long", entry, sl, base_features, base_htf_bias
        )

        assert tp_plan is None
        assert rejection is not None
        assert "HTF_OPPOSITION" in rejection

    def test_short_blocked_by_bullish_fvg_in_path(self, base_features, base_htf_bias):
        """Short continuation rejected when BULLISH FVG blocks path to TP2.

        This test verifies the fix for the bug where short trades incorrectly
        checked bearish FVG (opposing_fvg_low) instead of bullish FVG
        (opposing_fvg_bullish_high).

        Per schema:
        - opposing_fvg_high/low = bearish FVG (blocks LONG TPs)
        - opposing_fvg_bullish_high/low = bullish FVG (blocks SHORT TPs)
        """
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2640.0, 2650.0  # Risk = 10, short direction
        base_features.nearest_liquidity_short = 2625.0  # TP1 at 1.5R
        base_htf_bias.htf_range_low = 2600.0  # TP2 would be here

        # Bullish FVG blocks path - high is above TP2 (support zone in the way)
        base_htf_bias.opposing_fvg_bullish_high = 2610.0  # Between TP1 and TP2
        base_htf_bias.opposing_fvg_bullish_low = 2605.0

        tp_plan, rejection = validate_continuation_tp(
            "short", entry, sl, base_features, base_htf_bias
        )

        assert tp_plan is None
        assert rejection is not None
        assert "HTF_OPPOSITION" in rejection

    def test_short_not_blocked_by_bearish_fvg(self, base_features, base_htf_bias):
        """Short continuation NOT blocked by bearish FVG (only bullish FVG blocks shorts).

        This verifies that fixing the bug doesn't cause false rejections.
        Bearish FVGs oppose long trades, not short trades.
        """
        from bot_core_svc.signal_engine import validate_continuation_tp

        entry, sl = 2640.0, 2650.0  # Risk = 10, short direction
        base_features.nearest_liquidity_short = 2625.0  # TP1 at 1.5R
        base_htf_bias.htf_range_low = 2600.0  # TP2 at 4R (provides +2.5R delta)

        # Bearish FVG present BUT should NOT block short trades
        base_htf_bias.opposing_fvg_high = 2620.0
        base_htf_bias.opposing_fvg_low = 2615.0
        # No bullish FVG
        base_htf_bias.opposing_fvg_bullish_high = None
        base_htf_bias.opposing_fvg_bullish_low = None

        tp_plan, rejection = validate_continuation_tp(
            "short", entry, sl, base_features, base_htf_bias
        )

        # Should succeed - bearish FVG doesn't block shorts
        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp2 == 2600.0


class TestSignalMessageTPPlanFields:
    """Test that SignalMessage properly stores TP plan data."""

    def test_continuation_mode_populates_tp_plan_fields(self):
        """SignalMessage includes TP plan fields for continuation mode."""
        from bot_core_svc.signal_engine import signal_to_message
        from scp_shared.rule_engine.signal import Signal

        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Continuation setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"month": 11},
        )
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            nearest_liquidity_long=2665.0,  # TP1 at 1.5R
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=9.0,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2700.0,  # Expansion beyond TP1
            untouched_liquidity_high=2710.0,
        )

        msg = signal_to_message(signal, features, htf_bias)

        # Verify TP plan fields are populated
        assert msg.tp_mode == "continuation"
        assert msg.tp_price == 2665.0  # TP1
        assert msg.tp2_price == 2700.0  # TP2 (nearest beyond TP1)
        assert msg.rr_tp1 is not None
        assert msg.rr_tp1 > 1.4  # ~1.5R
        assert msg.rr_potential is not None
        assert msg.rr_potential > msg.rr_tp1  # Potential higher than TP1
        assert msg.be_after_tp1 is True
        assert msg.tp_target_source is not None

    def test_static_mode_populates_basic_fields(self):
        """SignalMessage includes TP plan fields for static mode."""
        from bot_core_svc.signal_engine import signal_to_message
        from scp_shared.rule_engine.signal import Signal

        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"rejection_candle": 2.0},
            rationale="Fade setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"month": 11, "htf_aligned": True, "dxy_aligned": True},
        )
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            nearest_liquidity_long=2655.0,  # Valid target >3R with FADE SL
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=9.0,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
        )

        msg = signal_to_message(signal, features, htf_bias)

        # Verify static mode fields
        assert msg.tp_mode == "static"
        assert msg.tp2_price is None  # No TP2 in static mode
        assert msg.be_after_tp1 is False  # Static doesn't move to BE

    def test_diagnostics_include_tp_plan_data(self):
        """Diagnostics field includes tp_plan nested object."""
        from bot_core_svc.signal_engine import signal_to_message
        from scp_shared.rule_engine.signal import Signal

        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Continuation setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"month": 11, "some_field": "data"},
        )
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            nearest_liquidity_long=2665.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=9.0,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2700.0,
        )

        msg = signal_to_message(signal, features, htf_bias)

        # Verify diagnostics enhanced with tp_plan
        assert msg.diagnostics is not None
        assert "tp_plan" in msg.diagnostics
        assert msg.diagnostics["tp_plan"]["tp_mode"] == "continuation"
        assert msg.diagnostics["tp_plan"]["tp1"] == 2665.0
        assert msg.diagnostics["tp_plan"]["tp2"] == 2700.0
        assert msg.diagnostics["tp_plan"]["expansion_path_valid"] is True
        # Original diagnostics preserved
        assert msg.diagnostics["month"] == 11
        assert msg.diagnostics["some_field"] == "data"
