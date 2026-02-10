"""Unit tests for DXY_CONTINUATION SL/TP calculation (TDD).

These tests implement the spec from dxy_continuation_implementation_spec_sop_aligned.md:
- Structural SL with ATR floor
- Two-stage TP (TP1 at 1R, TP2 at HTF target)
- Degraded mode handling
"""

from datetime import datetime, timezone

import pytest
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage

# These imports will fail until we implement the functions
from bot_core_svc.signal_engine import (
    calculate_sl_price_dxy_continuation,
    validate_dxy_continuation_tp,
)


class TestDXYContinuationSLCalculation:
    """Tests for structural SL with ATR floor.

    SL Model (from spec):
    - Long: sl = min(sl_struct, sl_atr) - choose farther stop
    - Short: sl = max(sl_struct, sl_atr) - choose farther stop
    - sl_struct = swing_hl_low - buffer (longs) / swing_lh_high + buffer (shorts)
    - sl_atr = entry ± (k_atr * atr)
    - k_atr = 1.7 (default)
    - sl_buffer_points = 0.3 (default)
    """

    def test_long_uses_structural_sl_when_farther(self) -> None:
        """Long: sl_struct < sl_atr → use sl_struct (farther from entry)."""
        # Setup: swing_hl_low=2640, entry=2650, atr=3.0, k_atr=1.7
        # sl_struct = 2640 - 0.3 = 2639.7
        # sl_atr = 2650 - (1.7 * 3.0) = 2644.9
        # Expected: sl = 2639.7 (farther from entry)
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=3.0,
            swing_hl_low=2640.0,  # HL swing low for structural SL
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="long",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
        )

        assert sl_price == pytest.approx(2639.7, abs=0.01)
        assert diagnostics["sl_struct"] == pytest.approx(2639.7, abs=0.01)
        assert diagnostics["sl_atr"] == pytest.approx(2644.9, abs=0.01)
        assert diagnostics["sl_method"] == "structural_with_atr_floor"
        assert diagnostics["degraded_mode"] is False

    def test_long_uses_atr_sl_when_farther(self) -> None:
        """Long: sl_atr < sl_struct → use sl_atr (farther from entry)."""
        # Setup: swing_hl_low=2648, entry=2650, atr=5.0, k_atr=1.7
        # sl_struct = 2648 - 0.3 = 2647.7
        # sl_atr = 2650 - (1.7 * 5.0) = 2641.5
        # Expected: sl = 2641.5 (farther from entry)
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=5.0,
            swing_hl_low=2648.0,  # Close to entry, so ATR-based SL is farther
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="long",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
        )

        assert sl_price == pytest.approx(2641.5, abs=0.01)
        assert diagnostics["sl_struct"] == pytest.approx(2647.7, abs=0.01)
        assert diagnostics["sl_atr"] == pytest.approx(2641.5, abs=0.01)
        assert diagnostics["sl_method"] == "structural_with_atr_floor"
        assert diagnostics["degraded_mode"] is False

    def test_short_uses_structural_sl_when_farther(self) -> None:
        """Short: sl_struct > sl_atr → use sl_struct (farther from entry)."""
        # Setup: swing_lh_high=2660, entry=2650, atr=3.0, k_atr=1.7
        # sl_struct = 2660 + 0.3 = 2660.3
        # sl_atr = 2650 + (1.7 * 3.0) = 2655.1
        # Expected: sl = 2660.3 (farther from entry)
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=3.0,
            swing_lh_high=2660.0,  # LH swing high for structural SL
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="short",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
        )

        assert sl_price == pytest.approx(2660.3, abs=0.01)
        assert diagnostics["sl_struct"] == pytest.approx(2660.3, abs=0.01)
        assert diagnostics["sl_atr"] == pytest.approx(2655.1, abs=0.01)
        assert diagnostics["sl_method"] == "structural_with_atr_floor"
        assert diagnostics["degraded_mode"] is False

    def test_short_uses_atr_sl_when_farther(self) -> None:
        """Short: sl_atr > sl_struct → use sl_atr (farther from entry)."""
        # Setup: swing_lh_high=2652, entry=2650, atr=5.0, k_atr=1.7
        # sl_struct = 2652 + 0.3 = 2652.3
        # sl_atr = 2650 + (1.7 * 5.0) = 2658.5
        # Expected: sl = 2658.5 (farther from entry)
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=5.0,
            swing_lh_high=2652.0,  # Close to entry, so ATR-based SL is farther
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="short",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
        )

        assert sl_price == pytest.approx(2658.5, abs=0.01)
        assert diagnostics["sl_struct"] == pytest.approx(2652.3, abs=0.01)
        assert diagnostics["sl_atr"] == pytest.approx(2658.5, abs=0.01)
        assert diagnostics["sl_method"] == "structural_with_atr_floor"
        assert diagnostics["degraded_mode"] is False

    def test_degraded_mode_when_swing_missing_long(self) -> None:
        """Long: Use ATR-only and flag degraded_mode=True when swing missing."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=4.0,
            swing_hl_low=None,  # Missing micro swing
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="long",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
        )

        # ATR-only: 2650 - (1.7 * 4.0) = 2643.2
        assert sl_price == pytest.approx(2643.2, abs=0.01)
        assert diagnostics["sl_struct"] is None
        assert diagnostics["sl_atr"] == pytest.approx(2643.2, abs=0.01)
        assert diagnostics["sl_method"] == "atr_only"
        assert diagnostics["degraded_mode"] is True

    def test_degraded_mode_when_swing_missing_short(self) -> None:
        """Short: Use ATR-only and flag degraded_mode=True when swing missing."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=4.0,
            swing_lh_high=None,  # Missing micro swing
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="short",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
        )

        # ATR-only: 2650 + (1.7 * 4.0) = 2656.8
        assert sl_price == pytest.approx(2656.8, abs=0.01)
        assert diagnostics["sl_struct"] is None
        assert diagnostics["sl_atr"] == pytest.approx(2656.8, abs=0.01)
        assert diagnostics["sl_method"] == "atr_only"
        assert diagnostics["degraded_mode"] is True

    def test_min_sl_floor_applied_long(self) -> None:
        """Long: Apply min_sl_points when calculated SL too tight."""
        # Setup: swing close to entry, small ATR
        # sl_struct = 2649.5 - 0.3 = 2649.2 (only 0.8 from entry)
        # sl_atr = 2650 - (1.7 * 0.5) = 2649.15 (only 0.85 from entry)
        # min_sl_points = 2.5
        # Expected: sl = 2650 - 2.5 = 2647.5 (floor applied)
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=0.5,  # Very small ATR
            swing_hl_low=2649.5,  # Very close to entry
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="long",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
            min_sl_points=2.5,
        )

        assert sl_price == pytest.approx(2647.5, abs=0.01)
        assert "min_floor_applied" in diagnostics["sl_method"]

    def test_min_sl_floor_applied_short(self) -> None:
        """Short: Apply min_sl_points when calculated SL too tight."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=0.5,
            swing_lh_high=2650.5,  # Very close to entry
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="short",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
            min_sl_points=2.5,
        )

        assert sl_price == pytest.approx(2652.5, abs=0.01)
        assert "min_floor_applied" in diagnostics["sl_method"]

    def test_atr_missing_uses_min_sl_fallback(self) -> None:
        """When ATR is missing, use min_sl_points as fallback."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=None,  # ATR not available
            swing_hl_low=None,  # Swing also missing
        )

        sl_price, diagnostics = calculate_sl_price_dxy_continuation(
            direction="long",
            entry_price=2650.0,
            features=features,
            k_atr=1.7,
            sl_buffer_points=0.3,
            min_sl_points=2.5,
        )

        assert sl_price == pytest.approx(2647.5, abs=0.01)
        assert diagnostics["degraded_mode"] is True


class TestDXYContinuationTPCalculation:
    """Tests for two-stage TP model.

    TP Model (from spec):
    - TP1 = entry + 1.0R (take 40% partial)
    - TP2 = min(HTF_target, entry + 4.0R) or default 3.0R
    - Rejection gates: TP2 >= 2R, TP2 > TP1 + 0.5R
    """

    def test_tp1_always_at_1r_long(self) -> None:
        """TP1 = entry + 1.0R for longs."""
        # Entry: 2650, SL: 2645, Risk: 5.0, TP1: 2655.0
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2680.0,  # Valid HTF target for TP2
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == pytest.approx(2655.0, abs=0.01)
        assert tp_plan.rr_tp1 == pytest.approx(1.0, abs=0.01)

    def test_tp1_always_at_1r_short(self) -> None:
        """TP1 = entry - 1.0R for shorts."""
        # Entry: 2650, SL: 2655, Risk: 5.0, TP1: 2645.0
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bearish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_low=2620.0,  # Valid HTF target for TP2
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="short",
            entry_price=2650.0,
            sl_price=2655.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp1 == pytest.approx(2645.0, abs=0.01)
        assert tp_plan.rr_tp1 == pytest.approx(1.0, abs=0.01)

    def test_tp2_uses_htf_target_beyond_tp1_long(self) -> None:
        """TP2 = nearest HTF target that is beyond TP1 (long)."""
        # Entry: 2650, SL: 2645, Risk: 5.0
        # TP1: 2655.0 (1R)
        # HTF target: 2668.0 (3.6R) - valid, beyond TP1
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2668.0,
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp2 == pytest.approx(2668.0, abs=0.01)
        assert tp_plan.rr_potential == pytest.approx(3.6, abs=0.1)

    def test_tp2_capped_at_4r_long(self) -> None:
        """TP2 capped at entry + 4R even if HTF target is farther (long)."""
        # Entry: 2650, SL: 2645, Risk: 5.0
        # Max TP2: 2650 + 4*5 = 2670 (4R)
        # HTF target: 2700 (10R) - should be capped
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2700.0,  # Far beyond 4R cap
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp2 == pytest.approx(2670.0, abs=0.01)  # Capped at 4R
        assert tp_plan.rr_potential == pytest.approx(4.0, abs=0.1)

    def test_tp2_defaults_to_3r_when_no_htf_target(self) -> None:
        """TP2 = entry + 3R when no HTF target available."""
        # Entry: 2650, SL: 2645, Risk: 5.0
        # Default TP2: 2650 + 3*5 = 2665 (3R)
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=None,  # No HTF target
            untouched_liquidity_high=None,
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp2 == pytest.approx(2665.0, abs=0.01)  # Default 3R
        assert tp_plan.rr_potential == pytest.approx(3.0, abs=0.1)

    def test_tp2_rejects_when_below_2r_minimum(self) -> None:
        """Reject if TP2 < 2.0R (continuation not worth it)."""
        # Entry: 2650, SL: 2645, Risk: 5.0
        # TP1: 2655 (1R)
        # HTF target: 2658 (1.6R) - below 2R minimum
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2658.0,  # Only 1.6R - should reject
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert tp_plan is None
        assert rejection is not None
        assert "2.0R minimum" in rejection or "continuation not worth" in rejection.lower()

    def test_tp2_rejects_when_delta_below_half_r(self) -> None:
        """Reject if TP2 < TP1 + 0.5R (runner has no space)."""
        # Entry: 2650, SL: 2645, Risk: 5.0
        # TP1: 2655 (1R)
        # Min TP2 for delta: 2655 + 0.5*5 = 2657.5 (1.5R)
        # But also TP2 must be >= 2R = 2660
        # HTF target: 2656 (1.2R) - fails both gates
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2656.0,  # Only 0.2R beyond TP1
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert tp_plan is None
        assert rejection is not None
        # Should fail either delta or 2R minimum gate
        assert "runner" in rejection.lower() or "2.0R" in rejection or "0.5R" in rejection

    def test_htf_target_behind_tp1_uses_default(self) -> None:
        """If HTF target is behind TP1, use default 3R instead."""
        # Entry: 2650, SL: 2645, Risk: 5.0
        # TP1: 2655 (1R)
        # HTF target: 2653 (0.6R) - behind TP1!
        # Should use default: 2665 (3R)
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2653.0,  # Behind TP1
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        # Should use default 3R since HTF target is behind TP1
        assert tp_plan.tp2 == pytest.approx(2665.0, abs=0.01)

    def test_tp_plan_has_continuation_mode_fields(self) -> None:
        """TPPlan has tp_mode=continuation, be_after_tp1=True."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_high=2680.0,
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp_mode == "continuation"
        assert tp_plan.be_after_tp1 is True

    def test_invalid_sl_long_rejected(self) -> None:
        """Long trade rejected when SL >= entry."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="long",
            entry_price=2650.0,
            sl_price=2655.0,  # Invalid: SL above entry for long
            features=features,
            htf_bias=htf_bias,
        )

        assert tp_plan is None
        assert rejection is not None
        assert "Invalid SL" in rejection

    def test_invalid_sl_short_rejected(self) -> None:
        """Short trade rejected when SL <= entry."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bearish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="short",
            entry_price=2650.0,
            sl_price=2645.0,  # Invalid: SL below entry for short
            features=features,
            htf_bias=htf_bias,
        )

        assert tp_plan is None
        assert rejection is not None
        assert "Invalid SL" in rejection


class TestDXYContinuationTPShort:
    """Short-specific TP tests."""

    def test_tp2_uses_htf_target_beyond_tp1_short(self) -> None:
        """TP2 = nearest HTF target that is beyond TP1 (short)."""
        # Entry: 2650, SL: 2655, Risk: 5.0
        # TP1: 2645.0 (1R)
        # HTF target: 2632.0 (3.6R) - valid, beyond TP1
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bearish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_low=2632.0,
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="short",
            entry_price=2650.0,
            sl_price=2655.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp2 == pytest.approx(2632.0, abs=0.01)
        assert tp_plan.rr_potential == pytest.approx(3.6, abs=0.1)

    def test_tp2_capped_at_4r_short(self) -> None:
        """TP2 capped at entry - 4R even if HTF target is farther (short)."""
        # Entry: 2650, SL: 2655, Risk: 5.0
        # Min TP2: 2650 - 4*5 = 2630 (4R)
        # HTF target: 2600 (10R) - should be capped
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bearish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_low=2600.0,  # Far beyond 4R cap
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="short",
            entry_price=2650.0,
            sl_price=2655.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp2 == pytest.approx(2630.0, abs=0.01)  # Capped at 4R
        assert tp_plan.rr_potential == pytest.approx(4.0, abs=0.1)

    def test_tp2_defaults_to_3r_short(self) -> None:
        """TP2 = entry - 3R when no HTF target available (short)."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bearish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_low=None,
            untouched_liquidity_low=None,
        )

        tp_plan, rejection = validate_dxy_continuation_tp(
            direction="short",
            entry_price=2650.0,
            sl_price=2655.0,
            features=features,
            htf_bias=htf_bias,
        )

        assert rejection is None
        assert tp_plan is not None
        # Default: 2650 - 3*5 = 2635
        assert tp_plan.tp2 == pytest.approx(2635.0, abs=0.01)
        assert tp_plan.rr_potential == pytest.approx(3.0, abs=0.1)


class TestDegradedModeMetrics:
    """Tests for degraded mode metrics tracking.

    Per spec: Degraded mode must be loud, rare, and measurable.
    - dxy_continuation_total: Incremented for every DXY_CONTINUATION attempt
    - dxy_continuation_degraded_total: Incremented when micro swing missing
    - WARNING log emitted on degraded mode
    """

    def test_degraded_mode_increments_counter(self) -> None:
        """Verify degraded mode increments the degraded counter."""
        from unittest.mock import patch

        from bot_core_svc import metrics

        # Reset counters for test isolation
        with patch.object(metrics.dxy_continuation_degraded_total, "inc") as mock_inc:
            features = FeaturesMessage(
                timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                close=2650.0,
                atr=4.0,
                swing_hl_low=None,  # Missing micro swing triggers degraded mode
            )

            sl_price, diagnostics = calculate_sl_price_dxy_continuation(
                direction="long",
                entry_price=2650.0,
                features=features,
            )

            # Verify degraded mode detected and metric incremented
            assert diagnostics["degraded_mode"] is True
            mock_inc.assert_called_once()

    def test_normal_mode_does_not_increment_degraded_counter(self) -> None:
        """Verify normal mode (with swing data) does NOT increment degraded counter."""
        from unittest.mock import patch

        from bot_core_svc import metrics

        with patch.object(metrics.dxy_continuation_degraded_total, "inc") as mock_inc:
            features = FeaturesMessage(
                timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                close=2650.0,
                atr=4.0,
                swing_hl_low=2640.0,  # Has swing data - normal mode
            )

            sl_price, diagnostics = calculate_sl_price_dxy_continuation(
                direction="long",
                entry_price=2650.0,
                features=features,
            )

            # Verify NOT degraded and metric NOT incremented
            assert diagnostics["degraded_mode"] is False
            mock_inc.assert_not_called()

    def test_degraded_mode_logs_warning(self, caplog) -> None:
        """Verify WARNING log is emitted on degraded mode (using caplog)."""
        import logging

        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            atr=4.0,
            swing_hl_low=None,  # Missing micro swing
        )

        with caplog.at_level(logging.WARNING):
            sl_price, diagnostics = calculate_sl_price_dxy_continuation(
                direction="long",
                entry_price=2650.0,
                features=features,
            )

        # Verify warning logged
        assert diagnostics["degraded_mode"] is True
        assert any("DEGRADED MODE" in record.message for record in caplog.records)
        assert any("micro swing missing" in record.message for record in caplog.records)
