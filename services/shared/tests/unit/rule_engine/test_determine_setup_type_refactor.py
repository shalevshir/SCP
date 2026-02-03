"""Tests for refactored determine_setup_type using config-driven validation.

Following TDD - write tests BEFORE refactoring the function.
"""

import pandas as pd
import pytest
from datetime import datetime, timezone

from scp_shared.rule_engine.htf.types import HTFBias


class TestDetermineSetupTypeRefactor:
    """Test that refactored determine_setup_type matches original behavior."""

    def _create_features(self, **overrides):
        """Create feature series with defaults."""
        defaults = {
            "timestamp": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "open": 2648.0,
            "high": 2652.0,
            "low": 2645.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "dxy_corr": -0.7,
            "structure_clarity": 0.7,
            "last_structure_label": "HH",
            "structure_label": "HH",
            "direction": "long",  # Required by valid_direction constraints
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def _create_htf_bias(self, **overrides):
        """Create HTF bias with defaults."""
        defaults = {
            "bias": "bullish",
            "direction": "long",
            "score": 8.0,
            "confidence": "high",
            "structure_15m": "HH",
            "structure_1h": "HH",
            "dxy_alignment": True,
            "chop_detected": False,
            "structure_clarity": 0.7,
            "bos_detected": True,
            "bars_since_bos": 5,
            "liquidity_sweep_detected": True,
            "conflict_detected": False,
            "dxy_corr_1m": -0.6,
            "dxy_corr_5m": -0.5,
        }
        defaults.update(overrides)
        return HTFBias(**defaults)

    def test_vwap_reclaim_detected(self):
        """Test that valid VWAP_RECLAIM is detected by refactored code."""
        from scp_shared.rule_engine.scoring import determine_setup_type

        features = self._create_features()
        htf_bias = self._create_htf_bias()

        setup_type = determine_setup_type(features, htf_bias)

        assert setup_type == "VWAP_RECLAIM"

    def test_vwap_fade_detected(self):
        """Test that valid VWAP_FADE is detected by refactored code."""
        from scp_shared.rule_engine.scoring import determine_setup_type

        # VWAP_FADE requires specific conditions
        # Make it fail VWAP_RECLAIM by having empty structure_1h
        features = self._create_features(
            rsi=35.0,  # < 40
            close=2640.0,
            vwap=2650.0,  # > 0.25% deviation
            last_structure_label="LH",  # For long fade
            structure_label="LH",
            choch_detected=True,
            trend_confidence=0.5,  # < 0.65
            open=2642.0,
            high=2644.0,
            low=2636.0,  # Creates lower wick > 1.3x body
        )
        htf_bias = self._create_htf_bias(
            direction="long",
            structure_1h="",  # Empty - fails VWAP_RECLAIM but not FADE
        )

        setup_type = determine_setup_type(features, htf_bias)

        assert setup_type == "VWAP_FADE"

    def test_dxy_continuation_detected(self):
        """Test that valid DXY_CONTINUATION is detected by refactored code."""
        from scp_shared.rule_engine.scoring import determine_setup_type

        # DXY_CONTINUATION requires strong correlation
        # Make it fail VWAP_RECLAIM by having empty structure_1h
        features = self._create_features(
            dxy_corr=-0.7,
            structure_clarity=0.6,
            is_chop=False,
            last_structure_label="HH",  # Gold bullish for long
            structure_label="HH",
        )
        htf_bias = self._create_htf_bias(
            dxy_corr_1m=-0.5,
            dxy_corr_5m=-0.4,
            dxy_structure="LL",  # DXY bearish for gold long
            bars_since_bos=10,
            structure_1h="",  # Empty - fails VWAP_RECLAIM but not DXY_CONTINUATION
        )

        setup_type = determine_setup_type(features, htf_bias)

        assert setup_type == "DXY_CONTINUATION"

    def test_rejected_no_valid_setup(self):
        """Test that invalid conditions return REJECTED."""
        from scp_shared.rule_engine.scoring import determine_setup_type

        # Create conditions that fail all setups
        # Remove structure_label to fail VWAP_RECLAIM
        # Set structure_clarity low to fail DXY_CONTINUATION (>= 0.5 required)
        features = self._create_features(
            structure_label=None,
            last_structure_label=None,
            structure_clarity=0.3,  # < 0.5 fails DXY_CONTINUATION
        )
        htf_bias = self._create_htf_bias()

        setup_type = determine_setup_type(features, htf_bias)

        assert setup_type == "REJECTED"

    def test_missing_structure_1h_fallback_to_dxy(self):
        """Test that missing structure_1h falls back to DXY_CONTINUATION.

        With config-driven system, each setup has independent constraints.
        Missing structure_1h only blocks VWAP_RECLAIM, not DXY_CONTINUATION.
        """
        from scp_shared.rule_engine.scoring import determine_setup_type

        # DXY_CONTINUATION doesn't require structure_1h but requires:
        # - dxy_structure for dxy_structure_required constraint
        # - last_structure_label for gold_structure_required constraint
        # - bars_since_bos or htf_bos_detected for bos_confirmation_required
        features = self._create_features(
            dxy_corr=-0.7,
            is_chop=False,
            structure_clarity=0.6,
            last_structure_label="HH",  # Gold bullish for long direction
        )
        htf_bias = self._create_htf_bias(
            structure_1h=None,  # Fails VWAP_RECLAIM
            dxy_corr_1m=-0.5,
            dxy_corr_5m=-0.4,
            dxy_structure="LL",  # DXY bearish supports gold long
            bars_since_bos=10,  # Recent BOS for confirmation
        )

        setup_type = determine_setup_type(features, htf_bias)

        # Should fallback to DXY_CONTINUATION since it doesn't need structure_1h
        assert setup_type == "DXY_CONTINUATION"

    def test_disabled_setup_skipped(self, tmp_path):
        """Test that disabled setups are skipped."""
        from scp_shared.rule_engine import scoring
        from scp_shared.rule_engine.setup_validator import SetupValidator

        # Create a config with VWAP_RECLAIM disabled
        config_file = tmp_path / "setups.yaml"
        config_file.write_text(
            """
setups:
  VWAP_RECLAIM:
    enabled: false
    min_score: 8.0
    constraints: {}
    weights: {}
    params: {}
  
  VWAP_FADE:
    enabled: true
    min_score: 8.0
    constraints:
      always_true:
        expression: "True"
        reject_reason: "Never"
    weights:
      vwap_deviation: 3.0
    params: {}
  
  DXY_CONTINUATION:
    enabled: true
    min_score: 8.0
    constraints:
      always_true:
        expression: "True"
        reject_reason: "Never"
    weights:
      dxy_corr: 3.0
    params: {}

confidence:
  a_plus: 8.0
"""
        )

        # Temporarily replace validator
        old_validator = getattr(scoring, "_validator", None)
        try:
            scoring._validator = SetupValidator(config_path=str(config_file))

            features = self._create_features()
            htf_bias = self._create_htf_bias()

            setup_type = scoring.determine_setup_type(features, htf_bias)

            # Should not return VWAP_RECLAIM since it's disabled
            assert setup_type != "VWAP_RECLAIM"
        finally:
            # Restore original validator
            scoring._validator = old_validator


class TestBuildSetupContext:
    """Test the helper function that builds context from features and HTF bias."""

    def test_build_context_includes_all_fields(self):
        """Test that build_setup_context includes all required fields."""
        from scp_shared.rule_engine.scoring import build_setup_context

        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "structure_clarity": 0.7,
                "last_structure_label": "HH",
                "direction": "long",
                "bos_direction": "long",
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_15m="HH",
            structure_1h="HH",
            dxy_alignment=True,
            chop_detected=False,
            conflict_detected=False,
        )

        context = build_setup_context(features, htf_bias)

        # Should have fields from both features and htf_bias
        assert "close" in context
        assert "vwap" in context
        assert "structure_1h" in context
        assert "conflict_detected" in context

    def test_build_context_handles_missing_fields(self):
        """Test that build_setup_context handles missing optional fields."""
        from scp_shared.rule_engine.scoring import build_setup_context

        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )

        context = build_setup_context(features, htf_bias)

        # Should not crash, should use defaults/None for missing fields
        assert context["close"] == 2650.0
        assert context["vwap"] == 2645.0
