"""Integration tests for config-driven setup detection parity.

These tests verify that the new config-driven setup detection produces
identical results to the existing hardcoded detectors across various
market scenarios.

Following TDD approach - tests written BEFORE refactoring scoring.py.
"""

import pandas as pd
import pytest
from datetime import datetime, timezone

from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.setup_validator import SetupValidator
from scp_shared.rule_engine.setup_detectors.vwap_fade import detect_vwap_fade
from scp_shared.rule_engine.setup_detectors.dxy_continuation import (
    detect_dxy_continuation,
)
from scp_shared.rule_engine.htf.vwap.reclaim import validate_reclaim_context


class TestVWAPReclaimParity:
    """Test config-driven validation matches hardcoded validate_reclaim_context."""

    def _create_htf_bias(self, **overrides):
        """Create HTFBias with sensible defaults."""
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
        }
        defaults.update(overrides)
        return HTFBias(**defaults)

    def _create_features(self, **overrides):
        """Create feature series with sensible defaults."""
        defaults = {
            "timestamp": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2655.0,
            "vwap": 2650.0,
            "structure_clarity": 0.7,
            "bos_direction": "long",
            "direction": "long",
            "conflict_detected": False,
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def test_valid_context_both_pass(self):
        """Test that valid VWAP_RECLAIM context passes both validators."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias()
        features = self._create_features(last_structure_label="HH")

        # Old validation
        old_result = validate_reclaim_context(htf_bias, features)

        # New validation (use build_setup_context for proper fallback logic)
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("VWAP_RECLAIM", context)

        # Both should agree
        assert old_result.context_valid == new_result.is_valid

    def test_missing_structure_1h_both_reject(self):
        """Test that missing structure_1h rejects in both validators."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias(structure_1h=None)
        features = self._create_features()

        # Old validation
        old_result = validate_reclaim_context(htf_bias, features)

        # New validation
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("VWAP_RECLAIM", context)

        # Both should reject
        assert old_result.context_valid is False
        assert new_result.is_valid is False
        assert "structure" in old_result.reason.lower()
        assert "structure" in new_result.reject_reason.lower()

    def test_low_clarity_both_reject(self):
        """Test that low clarity rejects in both validators."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias(structure_clarity=0.3)
        features = self._create_features(structure_clarity=0.3)

        # Old validation
        old_result = validate_reclaim_context(htf_bias, features)

        # New validation
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("VWAP_RECLAIM", context)

        # Both should reject for clarity
        assert old_result.context_valid is False
        assert new_result.is_valid is False

    def test_bos_direction_conflict_both_reject(self):
        """Test that BOS direction conflict rejects in both validators."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias()
        features = self._create_features(bos_direction="short", direction="long")

        # Old validation
        old_result = validate_reclaim_context(htf_bias, features)

        # New validation
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("VWAP_RECLAIM", context)

        # Both should reject
        assert old_result.context_valid is False
        assert new_result.is_valid is False

    def test_structure_conflict_both_reject(self):
        """Test that structure conflict rejects in both validators."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias(conflict_detected=True)
        features = self._create_features()

        # Old validation
        old_result = validate_reclaim_context(htf_bias, features)

        # New validation
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("VWAP_RECLAIM", context)

        # Both should reject
        assert old_result.context_valid is False
        assert new_result.is_valid is False


class TestVWAPFadeParity:
    """Test config-driven validation matches hardcoded detect_vwap_fade."""

    def _create_htf_bias(self, **overrides):
        """Create HTFBias with sensible defaults for fade."""
        defaults = {
            "bias": "bullish",
            "direction": "long",
            "score": 8.0,
            "confidence": "high",
            "structure_15m": "LH",
            "structure_1h": "HH",
            "dxy_alignment": True,
            "chop_detected": False,
            "structure_clarity": 0.5,
            "liquidity_sweep_detected": True,
        }
        defaults.update(overrides)
        return HTFBias(**defaults)

    def _create_features(self, **overrides):
        """Create feature series with sensible defaults for fade."""
        defaults = {
            "direction": "long",
            "liquidity_sweep": False,
            "body": 2.0,
            "lower_wick": 4.0,  # > 1.3x body for long fade
            "upper_wick": 0.5,
            "structure_clarity": 0.5,
            "choch_detected": True,
            "trend_confidence": 0.7,
            "last_structure_label": "LH",  # Required for long fade
            "rsi": 35.0,  # Below 40
            "close": 2640.0,
            "vwap": 2650.0,  # 0.38% deviation
            "open": 2642.0,
            "high": 2644.5,
            "low": 2636.0,
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    @pytest.mark.skip(reason="VWAP_FADE is disabled in production config")
    def test_valid_fade_long_both_pass(self):
        """Test that valid long VWAP_FADE passes both detectors."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias()
        features = self._create_features()

        # Old detection
        old_result = detect_vwap_fade(features, htf_bias, df=None)

        # New validation
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("VWAP_FADE", context)

        # Both should pass
        assert old_result is True
        assert new_result.is_valid is True

    def test_no_sweep_both_reject(self):
        """Test that missing sweep rejects in both detectors."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias(liquidity_sweep_detected=False)
        features = self._create_features(liquidity_sweep=False)

        # Old detection
        old_result = detect_vwap_fade(features, htf_bias, df=None)

        # New validation
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("VWAP_FADE", context)

        # Both should reject
        assert old_result is False
        assert new_result.is_valid is False

    def test_no_rejection_wick_both_reject(self):
        """Test that missing rejection wick rejects in both detectors."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias()
        # Create candle with small lower wick: open=2642, close=2644, low=2641
        # body = 2, lower_wick = 1, need lower_wick > 2.6 for long fade
        features = self._create_features(
            open=2642.0,
            high=2644.5,
            low=2641.0,  # Small lower wick
            close=2644.0,
        )

        # Old detection
        old_result = detect_vwap_fade(features, htf_bias, df=None)

        # New validation (build_setup_context calculates body/wicks automatically)
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("VWAP_FADE", context)

        # Both should reject
        assert old_result is False
        assert new_result.is_valid is False


class TestDXYContinuationParity:
    """Test config-driven validation matches hardcoded detect_dxy_continuation."""

    def _create_htf_bias(self, **overrides):
        """Create HTFBias with sensible defaults for continuation."""
        defaults = {
            "bias": "bullish",
            "direction": "long",
            "score": 8.0,
            "confidence": "high",
            "structure_15m": "HH",
            "structure_1h": "HH",
            "dxy_alignment": True,
            "chop_detected": False,
            "dxy_corr_1m": -0.5,
            "dxy_corr_5m": -0.4,
            "dxy_structure": "LL",  # DXY bearish for gold long
            "bars_since_bos": 10,
            "bos_detected": True,
            "dxy_chop_5m": False,
        }
        defaults.update(overrides)
        return HTFBias(**defaults)

    def _create_features(self, **overrides):
        """Create feature series with sensible defaults for continuation."""
        defaults = {
            "direction": "long",
            "dxy_corr": -0.65,
            "structure_clarity": 0.6,
            "is_chop": False,
            "last_structure_label": "HH",  # Gold bullish
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def test_valid_continuation_long_both_pass(self):
        """Test that valid long DXY_CONTINUATION passes both detectors."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias()
        features = self._create_features()

        # Old detection
        old_result = detect_dxy_continuation(features, htf_bias, df=None)

        # New validation
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("DXY_CONTINUATION", context)

        # Both should pass
        assert old_result is True
        assert new_result.is_valid is True

    def test_weak_correlation_passes_validation_scored_lower(self):
        """Test that weak correlation passes validation (scored lower, not hard rejected).

        Per Enforced Correction (dxy_continuation_config_review_insights.md):
        - Dual correlation strength is SCORING-ONLY, not a hard constraint
        - Only POSITIVE correlation (>= 0.1) causes hard rejection
        - Weak negative correlation (-0.2) should pass validation and score lower
        """
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias(dxy_corr_1m=-0.2, dxy_corr_5m=-0.2)
        features = self._create_features(dxy_corr=-0.4)

        # New validation - weak correlation should PASS (scoring handles quality)
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("DXY_CONTINUATION", context)

        # Should pass validation - correlation is negative (not contradicting)
        assert new_result.is_valid is True

    def test_positive_correlation_hard_rejects(self):
        """Test that positive correlation causes hard rejection.

        Per Enforced Correction: HARD reject only if correlation is POSITIVE.
        """
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        # Positive correlation (>= 0.1) should hard reject
        htf_bias = self._create_htf_bias(dxy_corr_1m=0.15, dxy_corr_5m=0.2)
        features = self._create_features(dxy_corr=0.3)

        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("DXY_CONTINUATION", context)

        # Should REJECT - positive correlation contradicts inverse relationship
        assert new_result.is_valid is False
        assert new_result.failed_constraint == "no_positive_dxy_correlation"

    def test_chop_both_reject(self):
        """Test that chop condition rejects in both detectors."""
        from scp_shared.rule_engine.scoring import build_setup_context

        validator = SetupValidator()

        htf_bias = self._create_htf_bias()
        features = self._create_features(is_chop=True)

        # Old detection
        old_result = detect_dxy_continuation(features, htf_bias, df=None)

        # New validation
        context = build_setup_context(features, htf_bias)
        new_result = validator.validate_setup("DXY_CONTINUATION", context)

        # Both should reject
        assert old_result is False
        assert new_result.is_valid is False


class TestSetupEnableDisable:
    """Test that enabled flag controls setup detection."""

    def test_disabled_setup_always_rejects(self, tmp_path):
        """Test that disabled setup rejects regardless of valid conditions."""
        # Create a temp config with VWAP_FADE disabled
        config_file = tmp_path / "setups.yaml"
        config_file.write_text(
            """
setups:
  VWAP_FADE:
    enabled: false
    min_score: 8.0
    constraints:
      always_true:
        expression: "True"
        reject_reason: "Never happens"
    weights:
      vwap_deviation: 3.0
    params: {}
  
confidence:
  a_plus: 8.0
"""
        )

        validator = SetupValidator(config_path=str(config_file))

        # Even with valid context, should reject because disabled
        context = {"any_field": "any_value"}
        result = validator.validate_setup("VWAP_FADE", context)

        assert result.is_valid is False
        assert "disabled" in result.reject_reason.lower()

    def test_enabled_setup_can_pass(self, tmp_path):
        """Test that enabled setup can pass with valid conditions."""
        # Create a temp config with simple passing constraint
        config_file = tmp_path / "setups.yaml"
        config_file.write_text(
            """
setups:
  TEST_SETUP:
    enabled: true
    min_score: 8.0
    constraints:
      always_true:
        expression: "value > 0"
        reject_reason: "Value not positive"
    weights:
      test_factor: 1.0
    params: {}
  
confidence:
  a_plus: 8.0
"""
        )

        validator = SetupValidator(config_path=str(config_file))

        # Should pass with valid context
        context = {"value": 5}
        result = validator.validate_setup("TEST_SETUP", context)

        assert result.is_valid is True
