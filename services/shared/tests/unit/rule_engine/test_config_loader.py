"""Unit tests for RuleEngine config loader.

Tests loading, parsing, and validation of scoring_config.yaml.
"""

from pathlib import Path

import pytest
import yaml
from scp_shared.common.exceptions import ConfigError
from scp_shared.rule_engine.config_loader import (
    ScoringConfig,
    load_scoring_config,
    validate_scoring_config,
)


class TestLoadScoringConfig:
    """Test loading scoring configuration from YAML."""

    def test_load_default_scoring_config(self) -> None:
        """Test loading the default scoring_config.yaml file."""
        config = load_scoring_config()

        assert isinstance(config, ScoringConfig)
        assert config.setup_types is not None
        assert config.confidence is not None
        assert config.validation is not None
        assert config.factors is not None

    def test_load_from_custom_path(self, tmp_path: Path) -> None:
        """Test loading config from a custom path."""
        custom_config = tmp_path / "custom_scoring.yaml"
        config_data = {
            "setup_types": {
                "VWAP_RECLAIM": {
                    "min_score": 8,
                    "weights": {"structure_alignment": 2},
                }
            },
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
            "validation": {"dxy_corr_threshold": -0.6, "sessions": [], "tiers": {}},
            "factors": {},
        }

        with open(custom_config, "w") as f:
            yaml.dump(config_data, f)

        config = load_scoring_config(str(custom_config))

        assert config.setup_types["VWAP_RECLAIM"]["min_score"] == 8
        assert "structure_alignment" in config.setup_types["VWAP_RECLAIM"]["weights"]

    def test_load_nonexistent_file_raises_error(self) -> None:
        """Test that loading a nonexistent file raises ConfigError."""
        with pytest.raises(ConfigError, match="not found"):
            load_scoring_config("/nonexistent/path/config.yaml")

    def test_load_invalid_yaml_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid YAML raises ConfigError."""
        invalid_yaml = tmp_path / "invalid.yaml"
        with open(invalid_yaml, "w") as f:
            f.write("invalid: yaml: content:\n  - broken")

        with pytest.raises(ConfigError, match="Failed to parse"):
            load_scoring_config(str(invalid_yaml))


class TestScoringConfigStructure:
    """Test ScoringConfig data structure."""

    def test_scoring_config_contains_setup_types(self) -> None:
        """Test that config contains all required setup types."""
        config = load_scoring_config()

        assert "VWAP_RECLAIM" in config.setup_types
        assert "VWAP_FADE" in config.setup_types
        assert "DXY_CONTINUATION" in config.setup_types

    def test_setup_type_has_min_score(self) -> None:
        """Test that each setup type has a min_score."""
        config = load_scoring_config()

        for setup_name, setup_config in config.setup_types.items():
            assert "min_score" in setup_config, f"{setup_name} missing min_score"
            assert isinstance(setup_config["min_score"], int | float)

    def test_setup_type_has_weights(self) -> None:
        """Test that each setup type has weights dict."""
        config = load_scoring_config()

        for setup_name, setup_config in config.setup_types.items():
            assert "weights" in setup_config, f"{setup_name} missing weights"
            assert isinstance(setup_config["weights"], dict)

    def test_vwap_reclaim_min_score_is_8(self) -> None:
        """Test VWAP_RECLAIM min_score is 8 per spec."""
        config = load_scoring_config()

        assert config.setup_types["VWAP_RECLAIM"]["min_score"] == 8

    def test_vwap_fade_min_score_is_8(self) -> None:
        """Test VWAP_FADE min_score is 8 (aligned with other setup types)."""
        config = load_scoring_config()

        assert config.setup_types["VWAP_FADE"]["min_score"] == 8

    def test_dxy_continuation_min_score_is_8(self) -> None:
        """Test DXY_CONTINUATION min_score is 8 per spec."""
        config = load_scoring_config()

        assert config.setup_types["DXY_CONTINUATION"]["min_score"] == 8


class TestConfidenceThresholds:
    """Test confidence threshold configuration."""

    def test_confidence_thresholds_exist(self) -> None:
        """Test that confidence thresholds are defined."""
        config = load_scoring_config()

        assert "a_plus" in config.confidence
        assert "watch" in config.confidence
        assert "reject" in config.confidence

    def test_a_plus_threshold_is_8(self) -> None:
        """Test A+ threshold is 8.0 per spec."""
        config = load_scoring_config()

        assert config.confidence["a_plus"] == 8.0

    def test_watch_threshold_is_6(self) -> None:
        """Test Watch threshold is 6.0 per spec."""
        config = load_scoring_config()

        assert config.confidence["watch"] == 6.0

    def test_reject_threshold_is_0(self) -> None:
        """Test Reject threshold is 0.0 per spec."""
        config = load_scoring_config()

        assert config.confidence["reject"] == 0.0


class TestValidationConfig:
    """Test validation configuration."""

    def test_dxy_correlation_threshold(self) -> None:
        """Test DXY correlation threshold is -0.6 per spec."""
        config = load_scoring_config()

        assert config.validation["dxy_corr_threshold"] == -0.6

    def test_sessions_defined(self) -> None:
        """Test that trading sessions are defined."""
        config = load_scoring_config()

        assert "sessions" in config.validation
        assert isinstance(config.validation["sessions"], list)

    def test_tiers_defined(self) -> None:
        """Test that enforcer tiers are defined."""
        config = load_scoring_config()

        assert "tiers" in config.validation
        assert isinstance(config.validation["tiers"], dict)

    def test_all_enforcer_tiers_present(self) -> None:
        """Test all SOP enforcer tiers are defined."""
        config = load_scoring_config()
        expected_tiers = ["Conservative", "Early Mild", "Mild", "Offensive"]

        for tier in expected_tiers:
            assert tier in config.validation["tiers"], f"Missing tier: {tier}"

    def test_tier_has_allowed_setups(self) -> None:
        """Test that each tier specifies allowed setups."""
        config = load_scoring_config()

        for tier_name, tier_config in config.validation["tiers"].items():
            assert (
                "allowed_setups" in tier_config
            ), f"{tier_name} missing allowed_setups"
            assert isinstance(tier_config["allowed_setups"], list)


class TestValidateScoringConfig:
    """Test scoring config validation logic."""

    def test_validate_valid_config(self) -> None:
        """Test that a valid config passes validation."""
        config_data = {
            "setup_types": {
                "VWAP_RECLAIM": {"min_score": 8, "weights": {"factor1": 2}}
            },
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
            "validation": {"dxy_corr_threshold": -0.6, "sessions": [], "tiers": {}},
            "factors": {},
        }

        # Should not raise
        validate_scoring_config(config_data)

    def test_validate_missing_setup_types_raises_error(self) -> None:
        """Test that missing setup_types raises ConfigError."""
        config_data = {
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
            "validation": {"dxy_corr_threshold": -0.6},
            "factors": {},
        }

        with pytest.raises(ConfigError, match="Missing required key: setup_types"):
            validate_scoring_config(config_data)

    def test_validate_missing_confidence_raises_error(self) -> None:
        """Test that missing confidence raises ConfigError."""
        config_data = {
            "setup_types": {},
            "validation": {"dxy_corr_threshold": -0.6},
            "factors": {},
        }

        with pytest.raises(ConfigError, match="Missing required key: confidence"):
            validate_scoring_config(config_data)

    def test_validate_missing_validation_raises_error(self) -> None:
        """Test that missing validation raises ConfigError."""
        config_data = {
            "setup_types": {},
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
            "factors": {},
        }

        with pytest.raises(ConfigError, match="Missing required key: validation"):
            validate_scoring_config(config_data)

    def test_validate_invalid_min_score_type_raises_error(self) -> None:
        """Test that non-numeric min_score raises ConfigError."""
        config_data = {
            "setup_types": {"VWAP_RECLAIM": {"min_score": "eight", "weights": {}}},
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
            "validation": {"dxy_corr_threshold": -0.6},
            "factors": {},
        }

        with pytest.raises(ConfigError, match="min_score must be numeric"):
            validate_scoring_config(config_data)

    def test_validate_negative_min_score_raises_error(self) -> None:
        """Test that negative min_score raises ConfigError."""
        config_data = {
            "setup_types": {"VWAP_RECLAIM": {"min_score": -5, "weights": {}}},
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
            "validation": {"dxy_corr_threshold": -0.6},
            "factors": {},
        }

        with pytest.raises(ConfigError, match="min_score must be non-negative"):
            validate_scoring_config(config_data)


class TestFactorsConfig:
    """Test factors configuration."""

    def test_factors_defined(self) -> None:
        """Test that factors dict is defined."""
        config = load_scoring_config()

        assert "factors" in config.__dict__
        assert isinstance(config.factors, dict)

    def test_factors_have_descriptions(self) -> None:
        """Test that each factor has a description."""
        config = load_scoring_config()

        for factor_name, factor_config in config.factors.items():
            assert "description" in factor_config, f"{factor_name} missing description"
            assert isinstance(factor_config["description"], str)

    def test_factors_have_max_points(self) -> None:
        """Test that each factor has max_points."""
        config = load_scoring_config()

        for factor_name, factor_config in config.factors.items():
            assert "max_points" in factor_config, f"{factor_name} missing max_points"
            assert isinstance(factor_config["max_points"], int | float)
