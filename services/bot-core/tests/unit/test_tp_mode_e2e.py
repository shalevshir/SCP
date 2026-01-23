"""End-to-end tests for TP mode SOP alignment.

Demonstrates complete feature: static vs continuation mode routing,
TP plan generation, and diagnostic data capture.
"""

from datetime import datetime, timezone

import pytest

from bot_core_svc.signal_engine import (
    TPPlan,
    is_continuation_eligible,
    signal_to_message,
    validate_tp_target,
)
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage
from scp_shared.rule_engine.signal import Signal


class TestTPModeEndToEnd:
    """End-to-end demonstration of TP mode routing and execution."""

    def test_static_mode_vwap_fade_flow(self):
        """Complete flow: VWAP_FADE uses static mode with 3R target."""
        # Setup: VWAP_FADE with A+ HTF (still uses static mode)
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            nearest_liquidity_long=2655.0,  # Will be >3R with FADE SL
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=9.0,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
        )

        # Verify NOT eligible for continuation
        assert is_continuation_eligible("VWAP_FADE", htf_bias) is False

        # Validate TP (should use static mode)
        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=2650.0,
            sl_price=2648.5,  # FADE uses 15-tick SL
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_FADE",
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp_mode == "static"
        assert tp_plan.tp1 == 2655.0
        assert tp_plan.tp2 is None  # No TP2 in static mode
        assert tp_plan.be_after_tp1 is False

    def test_continuation_mode_vwap_reclaim_flow(self):
        """Complete flow: VWAP_RECLAIM A+ uses continuation mode with 1.5R TP1."""
        # Setup: VWAP_RECLAIM with A+ HTF
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            nearest_liquidity_long=2665.0,  # 1.5R (would be rejected in static)
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=9.0,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            # Expansion path data
            htf_range_high=2700.0,  # Provides expansion beyond TP1
            untouched_liquidity_high=2710.0,
        )

        # Verify IS eligible for continuation
        assert is_continuation_eligible("VWAP_RECLAIM", htf_bias) is True

        # Validate TP (should use continuation mode)
        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=2650.0,
            sl_price=2640.0,  # Risk = 10
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_RECLAIM",
            min_rr=3.0,  # Ignored in continuation mode
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp_mode == "continuation"
        assert tp_plan.tp1 == 2665.0  # 1.5R accepted!
        assert tp_plan.tp2 == 2700.0  # HTF range high as TP2
        assert abs(tp_plan.rr_tp1 - 1.5) < 0.01
        assert tp_plan.rr_potential > 4.0  # Higher than TP1
        assert tp_plan.be_after_tp1 is True
        assert tp_plan.expansion_path_valid is True
        assert tp_plan.target_source == "nearest_liquidity_long"

    def test_continuation_rejected_without_expansion(self):
        """Continuation mode rejects when no expansion path exists."""
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
            # NO expansion path (all targets at or below TP1)
            htf_range_high=2660.0,  # Below TP1
            untouched_liquidity_high=None,
            nearest_fvg_high=None,
        )

        # Should route to continuation but reject due to no expansion
        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=2650.0,
            sl_price=2640.0,
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_RECLAIM",
            min_rr=3.0,
        )

        assert tp_plan is None
        assert rejection is not None
        assert "CONTINUATION_NO_EXPANSION_PATH" in rejection

    def test_signal_message_includes_tp_plan_diagnostics(self):
        """SignalMessage diagnostics include complete TP plan data."""
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
            rationale="A+ continuation",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"month": 11, "htf_aligned": True},
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
            untouched_liquidity_high=2710.0,
        )

        msg = signal_to_message(signal, features, htf_bias)

        # Verify message fields
        assert msg.tp_mode == "continuation"
        assert msg.tp_price == 2665.0  # TP1
        assert msg.tp2_price == 2700.0
        assert msg.rr_tp1 is not None
        assert msg.rr_potential > msg.rr_tp1
        assert msg.be_after_tp1 is True

        # Verify diagnostics include tp_plan
        assert msg.diagnostics is not None
        assert "tp_plan" in msg.diagnostics
        assert msg.diagnostics["tp_plan"]["tp_mode"] == "continuation"
        assert msg.diagnostics["tp_plan"]["expansion_path_valid"] is True

        # Original diagnostics preserved
        assert msg.diagnostics["month"] == 11
        assert msg.diagnostics["htf_aligned"] is True

    def test_chop_forces_static_mode_even_for_reclaim(self):
        """VWAP_RECLAIM with chop uses static mode (not continuation)."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            nearest_liquidity_long=2680.0,  # Valid at 3R
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=7.0,  # Lower score due to chop
            confidence="A+",
            dxy_aligned=True,
            chop_detected=True,  # CHOP disqualifies continuation
        )

        # Verify NOT eligible due to chop
        assert is_continuation_eligible("VWAP_RECLAIM", htf_bias) is False

        # Should use static mode
        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=2650.0,
            sl_price=2640.0,
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_RECLAIM",
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp_mode == "static"  # Forced to static due to chop
        assert tp_plan.tp1 == 2680.0

    def test_non_a_plus_forces_static_mode(self):
        """VWAP_RECLAIM with A (not A+) uses static mode."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            nearest_liquidity_long=2680.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=7.5,
            confidence="A",  # Not A+
            dxy_aligned=True,
            chop_detected=False,
        )

        # Verify NOT eligible (not A+)
        assert is_continuation_eligible("VWAP_RECLAIM", htf_bias) is False

        # Should use static mode
        tp_plan, rejection = validate_tp_target(
            direction="long",
            entry_price=2650.0,
            sl_price=2640.0,
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_RECLAIM",
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp_mode == "static"

    def test_continuation_mode_short_with_multiple_targets(self):
        """Shorts: continuation mode selects nearest TP1 and furthest TP2."""
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2640.0,
            vwap=2645.0,
            nearest_liquidity_short=2625.0,  # 1.5R - nearest
            prior_session_low=2620.0,  # 2R
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bearish",
            score=9.0,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            htf_range_low=2600.0,  # 4R - furthest
            untouched_liquidity_low=2610.0,  # 3R
        )

        tp_plan, rejection = validate_tp_target(
            direction="short",
            entry_price=2640.0,
            sl_price=2650.0,  # Risk = 10
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_RECLAIM",
            min_rr=3.0,
        )

        assert rejection is None
        assert tp_plan is not None
        assert tp_plan.tp_mode == "continuation"
        # Should use NEAREST valid target as TP1
        assert tp_plan.tp1 == 2625.0  # nearest_liquidity_short (1.5R)
        # Should use nearest HTF target beyond TP1 as TP2
        # HTF targets beyond TP1: [htf_range_low=2600, untouched_liquidity_low=2610]
        # Nearest for shorts = max([2600, 2610]) = 2610
        assert tp_plan.tp2 == 2610.0  # untouched_liquidity_low (nearest HTF beyond TP1)
        assert tp_plan.rr_potential > tp_plan.rr_tp1
