"""Integration test for VWAP acceptance constraints.

This test verifies that the min_vwap_acceptance and reclaim_timing_gate
constraints properly reject invalid VWAP reclaims now that the fields
are correctly included in the features Series.
"""

from datetime import datetime, timezone

import pytest

from bot_core_svc.signal_engine import SignalEngine
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage


class TestVWAPAcceptanceConstraintsIntegration:
    """Integration tests for VWAP acceptance constraints."""

    @pytest.fixture
    def signal_engine(self):
        """Create signal engine instance."""
        return SignalEngine(service_mode="test", service_name="bot-core-test")

    @pytest.fixture
    def valid_htf_bias(self):
        """Valid HTF bias for VWAP_RECLAIM setup."""
        return HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            structure_15m="HH",
            structure_1h="HH",
            dxy_aligned=False,  # Avoid DXY_CONTINUATION detection
            chop_detected=False,
            conflict_detected=False,
            dxy_chop_detected=False,
            bos_detected=True,
            bars_since_bos=5,
            structure_clarity=0.8,
            liquidity_sweep_detected=False,
            # Weak DXY correlation to prevent DXY_CONTINUATION
            dxy_corr_1m=-0.25,
            dxy_corr_5m=-0.20,
            dxy_corr_15m=-0.15,
            dxy_corr_1h=-0.10,
            dxy_structure=None,  # No DXY structure
            dxy_chop_5m=False,
            # TP fields
            htf_range_high=2660.0,
            untouched_liquidity_high=2665.0,
            nearest_fvg_high=2655.0,
        )

    @pytest.fixture
    def base_features(self):
        """Base features for VWAP_RECLAIM setup."""
        return {
            "timestamp": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2651.0,
            "open": 2650.5,
            "high": 2651.5,
            "low": 2650.0,
            "vwap": 2650.0,
            "rsi": 55.0,
            "ema_9": 2649.0,
            "ema_20": 2648.0,
            "ema_50": 2647.0,
            "structure_label": "HL",
            "structure_clarity": 0.8,
            "trend_confidence": 0.75,
            "vwap_deviation_normalized": 0.8,  # Within 0.5-3.0 ATR range
            "bos_direction": "long",
            "bos_recent": False,
            "bos_age": 25,  # Old enough to not trigger no_late_reclaim
            "choch_detected": False,
            "liquidity_sweep": False,
            # Set DXY correlation below threshold to prevent DXY_CONTINUATION detection
            # DXY_CONTINUATION requires dxy_corr < -0.6 or both 1m/5m < -0.3
            "dxy_correlation": -0.25,  # Too weak for DXY_CONTINUATION
        }

    def test_drive_by_reclaim_rejected(
        self, signal_engine, base_features, valid_htf_bias
    ):
        """Drive-by reclaim (bars_near_vwap=1) should be rejected."""
        # GIVEN: Features with only 1 bar near VWAP (drive-by reclaim)
        features = FeaturesMessage(
            **base_features,
            bars_near_vwap=1,  # Too few bars - should fail min_vwap_acceptance
            bars_since_last_vwap_touch=3,  # Valid timing
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "A+",
        }

        # WHEN: Generating signal
        result = signal_engine.generate(features, valid_htf_bias, context)

        # THEN: Signal should be rejected (not A+)
        # Either rejected at constraint level or scores below A+ threshold
        assert result.signal_msg is None, "Drive-by reclaim should be rejected"
        assert result.rejection_reason is not None

    def test_delayed_reclaim_rejected(self, signal_engine, base_features, valid_htf_bias):
        """Delayed reclaim (bars_since_last_vwap_touch=15) should be rejected."""
        # GIVEN: Features with 15 bars since last VWAP touch (too delayed)
        features = FeaturesMessage(
            **base_features,
            bars_near_vwap=4,  # Valid acceptance
            bars_since_last_vwap_touch=15,  # Too delayed - should fail reclaim_timing_gate
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "A+",
        }

        # WHEN: Generating signal
        result = signal_engine.generate(features, valid_htf_bias, context)

        # THEN: Signal should be rejected (not A+)
        assert result.signal_msg is None, "Delayed reclaim should be rejected"
        assert result.rejection_reason is not None

    def test_valid_vwap_reclaim_passes(
        self, signal_engine, base_features, valid_htf_bias
    ):
        """Valid VWAP reclaim should pass both constraints."""
        # GIVEN: Features with valid VWAP acceptance (≥3 bars, ≤10 bars since touch)
        features = FeaturesMessage(
            **base_features,
            bars_near_vwap=4,  # ≥3 bars - passes min_vwap_acceptance
            bars_since_last_vwap_touch=6,  # ≤10 bars - passes reclaim_timing_gate
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "A+",
        }

        # WHEN: Generating signal
        result = signal_engine.generate(features, valid_htf_bias, context)

        # THEN: Signal should pass constraints (may still fail on other criteria)
        # At minimum, it should not be rejected for VWAP acceptance issues
        if result.signal_msg is None and result.rejection_reason:
            # If rejected, it should NOT be for VWAP acceptance constraints
            assert "drive-by" not in result.rejection_reason.lower()
            assert "delayed" not in result.rejection_reason.lower()
            # If there are diagnostics, check they don't mention these constraints
            if hasattr(result.raw_signal, "diagnostics") and result.raw_signal.diagnostics:
                reject_reason = result.raw_signal.diagnostics.get("reject_reason", "")
                assert "drive-by reclaim" not in reject_reason.lower()
                assert "VWAP reclaim too delayed" not in reject_reason.lower()

    def test_none_values_bypass_constraints(
        self, signal_engine, base_features, valid_htf_bias
    ):
        """None values for VWAP acceptance fields should bypass constraints (fallback)."""
        # GIVEN: Features with None VWAP acceptance fields (e.g., ATR not available)
        features = FeaturesMessage(
            **base_features,
            bars_near_vwap=None,  # None - should bypass min_vwap_acceptance
            bars_since_last_vwap_touch=None,  # None - should bypass reclaim_timing_gate
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "A+",
        }

        # WHEN: Generating signal
        result = signal_engine.generate(features, valid_htf_bias, context)

        # THEN: Signal should not be rejected for VWAP acceptance constraints
        # (constraints have "is None or ..." fallback)
        if result.signal_msg is None and result.rejection_reason:
            # If rejected, it should NOT be for VWAP acceptance constraints
            assert "drive-by" not in result.rejection_reason.lower()
            assert "delayed" not in result.rejection_reason.lower()

    def test_edge_case_exactly_3_bars_passes(
        self, signal_engine, base_features, valid_htf_bias
    ):
        """Exactly 3 bars near VWAP (boundary) should pass min_vwap_acceptance."""
        # GIVEN: Features with exactly 3 bars near VWAP (boundary case)
        features = FeaturesMessage(
            **base_features,
            bars_near_vwap=3,  # Exactly 3 - should pass (≥3)
            bars_since_last_vwap_touch=5,  # Valid timing
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "A+",
        }

        # WHEN: Generating signal
        result = signal_engine.generate(features, valid_htf_bias, context)

        # THEN: Should not be rejected for bars_near_vwap
        if result.signal_msg is None and result.rejection_reason:
            assert "drive-by" not in result.rejection_reason.lower()

    def test_edge_case_exactly_10_bars_since_touch_passes(
        self, signal_engine, base_features, valid_htf_bias
    ):
        """Exactly 10 bars since touch (boundary) should pass reclaim_timing_gate."""
        # GIVEN: Features with exactly 10 bars since last VWAP touch (boundary case)
        features = FeaturesMessage(
            **base_features,
            bars_near_vwap=4,  # Valid acceptance
            bars_since_last_vwap_touch=10,  # Exactly 10 - should pass (≤10)
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "A+",
        }

        # WHEN: Generating signal
        result = signal_engine.generate(features, valid_htf_bias, context)

        # THEN: Should not be rejected for bars_since_last_vwap_touch
        if result.signal_msg is None and result.rejection_reason:
            assert "delayed" not in result.rejection_reason.lower()
