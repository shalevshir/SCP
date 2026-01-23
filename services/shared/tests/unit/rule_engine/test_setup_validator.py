"""Unit tests for config-driven setup validator.

Tests the setup validation system that uses expressions from setups.yaml
to determine if a setup is valid for given market conditions.

Following TDD approach - these tests are written BEFORE implementation.
"""

from typing import Any


class TestSetupConfig:
    """Tests for setup configuration loading."""

    def test_load_setups_config(self) -> None:
        """Test loading setups.yaml configuration."""
        from scp_shared.rule_engine.setup_validator import load_setups_config

        config = load_setups_config()

        assert "setups" in config
        assert "VWAP_RECLAIM" in config["setups"]
        assert "VWAP_FADE" in config["setups"]
        assert "DXY_CONTINUATION" in config["setups"]

    def test_setup_has_required_fields(self) -> None:
        """Test each setup has required fields."""
        from scp_shared.rule_engine.setup_validator import load_setups_config

        config = load_setups_config()

        for setup_name, setup_config in config["setups"].items():
            assert "enabled" in setup_config, f"{setup_name} missing 'enabled'"
            assert "min_score" in setup_config, f"{setup_name} missing 'min_score'"
            assert "constraints" in setup_config, f"{setup_name} missing 'constraints'"
            assert "weights" in setup_config, f"{setup_name} missing 'weights'"

    def test_constraint_has_required_fields(self) -> None:
        """Test each constraint has required fields."""
        from scp_shared.rule_engine.setup_validator import load_setups_config

        config = load_setups_config()

        for setup_name, setup_config in config["setups"].items():
            for constraint_name, constraint in setup_config["constraints"].items():
                assert (
                    "expression" in constraint
                ), f"{setup_name}.{constraint_name} missing 'expression'"
                assert (
                    "reject_reason" in constraint
                ), f"{setup_name}.{constraint_name} missing 'reject_reason'"


class TestSetupValidator:
    """Tests for SetupValidator class."""

    def test_is_setup_enabled(self) -> None:
        """Test checking if a setup is enabled."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()

        # All setups should be enabled by default
        assert validator.is_setup_enabled("VWAP_RECLAIM") is True
        assert validator.is_setup_enabled("VWAP_FADE") is True
        assert validator.is_setup_enabled("DXY_CONTINUATION") is True

    def test_unknown_setup_returns_false(self) -> None:
        """Test that unknown setup returns False for enabled check."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()

        assert validator.is_setup_enabled("UNKNOWN_SETUP") is False

    def test_get_enabled_setups(self) -> None:
        """Test getting list of enabled setups."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()

        enabled = validator.get_enabled_setups()

        assert "VWAP_RECLAIM" in enabled
        assert "VWAP_FADE" in enabled
        assert "DXY_CONTINUATION" in enabled


class TestVWAPReclaimValidation:
    """Tests for VWAP_RECLAIM setup validation."""

    def _create_base_context(self) -> dict[str, Any]:
        """Create a base context that passes all VWAP_RECLAIM constraints."""
        return {
            "structure_1h": "HH",
            "structure_label": "HH",  # For structure_label_available constraint
            "last_structure_label": "HH",
            "structure_clarity": 0.6,
            "close": 2650.0,
            "vwap": 2645.0,  # 0.19% deviation
            "vwap_deviation_normalized": 0.6,  # >= 0.5 ATR threshold
            "bos_direction": "long",
            "bos_age": None,  # No BOS age (fresh or not applicable)
            "direction": "long",
            "conflict_detected": False,
            "choch_detected": False,  # Required by direction_bos_alignment constraint
            "choch_direction": None,
            # Additional fields needed for scoring (but not constraints)
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.7,
        }

    def test_valid_vwap_reclaim_passes(self) -> None:
        """Test that valid VWAP_RECLAIM setup passes validation."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()

        result = validator.validate_setup("VWAP_RECLAIM", context)

        assert result.is_valid is True
        assert result.reject_reason is None

    def test_missing_structure_1h_rejects(self) -> None:
        """Test that missing structure_1h rejects VWAP_RECLAIM."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["structure_1h"] = None

        result = validator.validate_setup("VWAP_RECLAIM", context)

        assert result.is_valid is False
        assert "HTF 1H structure missing" in result.reject_reason

    def test_empty_structure_1h_rejects(self) -> None:
        """Test that empty string structure_1h rejects VWAP_RECLAIM."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["structure_1h"] = ""

        result = validator.validate_setup("VWAP_RECLAIM", context)

        assert result.is_valid is False
        assert "HTF 1H structure missing" in result.reject_reason

    def test_low_clarity_allowed_with_penalty(self) -> None:
        """Test that low clarity is allowed (not hard rejection) for VWAP_RECLAIM.

        Low clarity results in score penalties via calculate_structure_quality_penalty,
        not hard rejection. This matches the old behavior where clarity was a
        quality flag, not a safety gate.
        """
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["structure_clarity"] = 0.3  # Low but not rejected

        result = validator.validate_setup("VWAP_RECLAIM", context)

        # Should pass (low clarity is a penalty, not rejection for VWAP_RECLAIM)
        assert result.is_valid is True

    def test_insufficient_vwap_deviation_rejects(self) -> None:
        """Test that insufficient VWAP deviation rejects VWAP_RECLAIM."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["close"] = 2645.5  # Very close to VWAP
        context["vwap"] = 2645.0  # Only 0.02% deviation
        context["vwap_deviation_normalized"] = 0.3  # < 0.5 ATR threshold

        result = validator.validate_setup("VWAP_RECLAIM", context)

        assert result.is_valid is False
        assert "VWAP deviation" in result.reject_reason

    def test_bos_direction_conflict_rejects(self) -> None:
        """Test that BOS direction conflict rejects VWAP_RECLAIM."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["bos_direction"] = "short"  # Conflicts with direction=long
        context["bos_age"] = 5  # Recent BOS (not stale)

        result = validator.validate_setup("VWAP_RECLAIM", context)

        assert result.is_valid is False
        assert "BOS direction" in result.reject_reason

    def test_structure_conflict_rejects(self) -> None:
        """Test that structure conflict rejects VWAP_RECLAIM."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["conflict_detected"] = True

        result = validator.validate_setup("VWAP_RECLAIM", context)

        assert result.is_valid is False
        assert "conflict" in result.reject_reason.lower()


class TestVWAPFadeValidation:
    """Tests for VWAP_FADE setup validation."""

    def _create_base_context(self) -> dict[str, Any]:
        """Create a base context that passes all VWAP_FADE constraints."""
        return {
            "direction": "long",
            "htf_liquidity_sweep_detected": True,
            "liquidity_sweep": False,
            "body": 2.0,
            "lower_wick": 3.5,  # > 1.3x body for long fade
            "upper_wick": 0.5,
            "structure_clarity": 0.5,
            "choch_detected": True,
            "trend_confidence": 0.7,
            "last_structure_label": "LH",  # Required for long fade
            "rsi": 35.0,  # Below 40 (oversold)
            "close": 2640.0,
            "vwap": 2650.0,  # 0.38% deviation
            "vwap_deviation": 0.5,  # > 0.25 threshold
        }

    def test_valid_vwap_fade_long_passes(self) -> None:
        """Test that valid long VWAP_FADE setup passes validation."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()

        result = validator.validate_setup("VWAP_FADE", context)

        assert result.is_valid is True
        assert result.reject_reason is None

    def test_valid_vwap_fade_short_passes(self) -> None:
        """Test that valid short VWAP_FADE setup passes validation."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = {
            "direction": "short",
            "htf_liquidity_sweep_detected": True,
            "liquidity_sweep": False,
            "body": 2.0,
            "lower_wick": 0.5,
            "upper_wick": 3.5,  # > 1.3x body for short fade
            "structure_clarity": 0.5,
            "choch_detected": True,
            "trend_confidence": 0.7,
            "last_structure_label": "HL",  # Required for short fade
            "rsi": 65.0,  # Above 60 (overbought)
            "close": 2660.0,
            "vwap": 2650.0,  # 0.38% deviation
            "vwap_deviation": 0.5,  # > 0.25 threshold
        }

        result = validator.validate_setup("VWAP_FADE", context)

        assert result.is_valid is True

    def test_no_liquidity_sweep_rejects(self) -> None:
        """Test that missing liquidity sweep rejects VWAP_FADE."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["htf_liquidity_sweep_detected"] = False
        context["liquidity_sweep"] = False

        result = validator.validate_setup("VWAP_FADE", context)

        assert result.is_valid is False
        assert "sweep" in result.reject_reason.lower()

    def test_no_rejection_wick_long_rejects(self) -> None:
        """Test that missing rejection wick rejects long VWAP_FADE."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["lower_wick"] = 1.0  # Not > 1.3x body (2.0)

        result = validator.validate_setup("VWAP_FADE", context)

        assert result.is_valid is False
        assert "wick" in result.reject_reason.lower()

    def test_wrong_structure_label_long_rejects(self) -> None:
        """Test that wrong structure label rejects long VWAP_FADE."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["last_structure_label"] = "HH"  # Should be LH for long fade

        result = validator.validate_setup("VWAP_FADE", context)

        assert result.is_valid is False
        reason_lower = result.reject_reason.lower()
        assert "LH" in result.reject_reason or "structure" in reason_lower

    def test_rsi_not_extreme_rejects(self) -> None:
        """Test that non-extreme RSI rejects VWAP_FADE."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["rsi"] = 50.0  # Not < 40 or > 60

        result = validator.validate_setup("VWAP_FADE", context)

        assert result.is_valid is False
        assert "RSI" in result.reject_reason

    def test_small_vwap_deviation_rejects(self) -> None:
        """Test that small VWAP deviation rejects VWAP_FADE."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["close"] = 2650.5  # Only 0.02% deviation
        context["vwap"] = 2650.0
        context["vwap_deviation"] = 0.1  # < 0.25 threshold

        result = validator.validate_setup("VWAP_FADE", context)

        assert result.is_valid is False
        assert "VWAP deviation" in result.reject_reason


class TestDXYContinuationValidation:
    """Tests for DXY_CONTINUATION setup validation."""

    def _create_base_context(self) -> dict[str, Any]:
        """Create a base context that passes all DXY_CONTINUATION constraints."""
        return {
            "direction": "long",
            "dxy_corr_1m": -0.5,
            "dxy_corr_5m": -0.4,
            "dxy_corr": -0.65,
            "dxy_structure": "LL",  # DXY bearish for gold long
            "bars_since_bos": 10,
            "htf_bos_detected": True,
            "structure_clarity": 0.6,
            "is_chop": False,
            "last_structure_label": "HH",  # Gold bullish
        }

    def test_valid_dxy_continuation_long_passes(self) -> None:
        """Test that valid long DXY_CONTINUATION setup passes validation."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()

        result = validator.validate_setup("DXY_CONTINUATION", context)

        assert result.is_valid is True
        assert result.reject_reason is None

    def test_valid_dxy_continuation_short_passes(self) -> None:
        """Test that valid short DXY_CONTINUATION setup passes validation."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = {
            "direction": "short",
            "dxy_corr_1m": -0.5,
            "dxy_corr_5m": -0.4,
            "dxy_corr": -0.65,
            "dxy_structure": "HH",  # DXY bullish for gold short
            "bars_since_bos": 10,
            "htf_bos_detected": True,
            "structure_clarity": 0.6,
            "is_chop": False,
            "last_structure_label": "LH",  # Gold bearish
        }

        result = validator.validate_setup("DXY_CONTINUATION", context)

        assert result.is_valid is True

    def test_weak_correlation_rejects(self) -> None:
        """Test that weak DXY correlation rejects DXY_CONTINUATION."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["dxy_corr_1m"] = -0.2  # Too weak
        context["dxy_corr_5m"] = -0.2  # Too weak
        context["dxy_corr"] = -0.4  # Also too weak

        result = validator.validate_setup("DXY_CONTINUATION", context)

        assert result.is_valid is False
        assert "correlation" in result.reject_reason.lower()

    def test_single_strong_correlation_passes(self) -> None:
        """Test that single strong correlation passes DXY_CONTINUATION."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["dxy_corr_1m"] = None  # Not available
        context["dxy_corr_5m"] = None  # Not available
        context["dxy_corr"] = -0.7  # Strong single correlation

        result = validator.validate_setup("DXY_CONTINUATION", context)

        assert result.is_valid is True

    def test_wrong_dxy_structure_long_rejects(self) -> None:
        """Test that wrong DXY structure rejects long DXY_CONTINUATION."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["dxy_structure"] = "HH"  # Should be LL/LH for long

        result = validator.validate_setup("DXY_CONTINUATION", context)

        assert result.is_valid is False
        assert "DXY structure" in result.reject_reason

    def test_chop_rejects(self) -> None:
        """Test that chop condition rejects DXY_CONTINUATION."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["is_chop"] = True

        result = validator.validate_setup("DXY_CONTINUATION", context)

        assert result.is_valid is False
        assert "chop" in result.reject_reason.lower()

    def test_wrong_gold_structure_long_rejects(self) -> None:
        """Test that wrong gold structure rejects long DXY_CONTINUATION."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        context = self._create_base_context()
        context["last_structure_label"] = "LL"  # Should be HH/HL for long

        result = validator.validate_setup("DXY_CONTINUATION", context)

        assert result.is_valid is False
        assert "Gold structure" in result.reject_reason


class TestSetupValidatorParity:
    """Tests ensuring config-driven validation produces same results as hardcoded logic.

    These tests verify that the new config-driven system matches the existing
    hardcoded setup detectors for the same inputs.
    """

    def test_vwap_reclaim_parity_valid(self) -> None:
        """Test VWAP_RECLAIM config validation matches hardcoded for valid case."""
        import pandas as pd

        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()

        # Test fallback: structure_label -> last_structure_label
        features = pd.Series(
            {
                "structure_label": None,
                "last_structure_label": "HH",  # Should fallback to this
                "structure_clarity": 0.7,
                "close": 2655.0,
                "vwap": 2650.0,
                "bos_direction": "long",
                "direction": "long",
            }
        )

        from scp_shared.rule_engine.htf.types import HTFBias

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",
            conflict_detected=False,
        )

        # Use build_setup_context to get proper fallback logic
        from scp_shared.rule_engine.scoring import build_setup_context

        context = build_setup_context(features, htf_bias)

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid is True

    def test_vwap_reclaim_parity_reject_no_1h(self) -> None:
        """Test VWAP_RECLAIM config validation matches hardcoded for rejection."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()

        # Context that should fail both old and new validation
        context = {
            "structure_1h": None,  # This is checked in validate_reclaim_context
            "structure_label": None,  # Expression needs both variables present
            "last_structure_label": "HH",
            "structure_clarity": 0.7,
            "close": 2655.0,
            "vwap": 2650.0,
            "bos_direction": "long",
            "direction": "long",
            "conflict_detected": False,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid is False

    def test_vwap_fade_parity_valid(self) -> None:
        """Test VWAP_FADE config validation matches hardcoded for valid case."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()

        # Context that should pass both old and new validation
        context = {
            "direction": "long",
            "htf_liquidity_sweep_detected": True,
            "liquidity_sweep": False,
            "body": 2.0,
            "lower_wick": 4.0,  # > 1.3x body
            "upper_wick": 0.5,
            "structure_clarity": 0.5,
            "choch_detected": True,
            "trend_confidence": 0.7,
            "last_structure_label": "LH",
            "rsi": 35.0,
            "close": 2640.0,
            "vwap": 2650.0,
            "vwap_deviation": 0.5,  # > 0.25 threshold
        }

        result = validator.validate_setup("VWAP_FADE", context)
        assert result.is_valid is True


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_fields(self) -> None:
        """Test ValidationResult has expected fields."""
        from scp_shared.rule_engine.setup_validator import ValidationResult

        result = ValidationResult(is_valid=True, reject_reason=None)

        assert result.is_valid is True
        assert result.reject_reason is None

    def test_validation_result_with_rejection(self) -> None:
        """Test ValidationResult with rejection reason."""
        from scp_shared.rule_engine.setup_validator import ValidationResult

        result = ValidationResult(
            is_valid=False,
            reject_reason="RSI not at extreme levels",
            failed_constraint="rsi_extreme",
        )

        assert result.is_valid is False
        assert "RSI" in result.reject_reason
        assert result.failed_constraint == "rsi_extreme"


class TestGetSetupParams:
    """Tests for getting setup parameters."""

    def test_get_vwap_reclaim_params(self) -> None:
        """Test getting VWAP_RECLAIM params."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        params = validator.get_setup_params("VWAP_RECLAIM")

        assert params is not None
        assert "bos_recency_threshold" in params
        assert params["bos_recency_threshold"] == 15
        assert "expansion_gate" in params

    def test_get_vwap_fade_params(self) -> None:
        """Test getting VWAP_FADE params."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        params = validator.get_setup_params("VWAP_FADE")

        assert params is not None
        assert "wick_body_ratio" in params
        assert params["wick_body_ratio"] == 1.3
        assert "rsi_oversold" in params

    def test_get_unknown_setup_params_returns_none(self) -> None:
        """Test getting params for unknown setup returns None."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        params = validator.get_setup_params("UNKNOWN_SETUP")

        assert params is None


class TestGetSetupWeights:
    """Tests for getting setup factor weights."""

    def test_get_vwap_reclaim_weights(self) -> None:
        """Test getting VWAP_RECLAIM weights."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        weights = validator.get_setup_weights("VWAP_RECLAIM")

        assert weights is not None
        assert "structure_alignment" in weights
        assert weights["structure_alignment"] == 2.5
        assert "vwap_relation" in weights

    def test_get_vwap_fade_weights(self) -> None:
        """Test getting VWAP_FADE weights."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        weights = validator.get_setup_weights("VWAP_FADE")

        assert weights is not None
        assert "vwap_deviation" in weights
        assert weights["vwap_deviation"] == 3.0

    def test_get_unknown_setup_weights_returns_none(self) -> None:
        """Test getting weights for unknown setup returns None."""
        from scp_shared.rule_engine.setup_validator import SetupValidator

        validator = SetupValidator()
        weights = validator.get_setup_weights("UNKNOWN_SETUP")

        assert weights is None
