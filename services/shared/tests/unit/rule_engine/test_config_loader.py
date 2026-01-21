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
        """Test loading the default setups.yaml file."""
        config = load_scoring_config()

        assert isinstance(config, ScoringConfig)
        assert config.setup_types is not None
        assert config.confidence is not None
        # validation and factors are optional (not in setups.yaml)

    def test_load_from_custom_path(self, tmp_path: Path) -> None:
        """Test loading config from a custom path."""
        custom_config = tmp_path / "custom_scoring.yaml"
        config_data = {
            "setups": {
                "VWAP_RECLAIM": {
                    "enabled": True,
                    "min_score": 8,
                    "constraints": {},
                    "weights": {"structure_alignment": 2},
                }
            },
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
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
    """Test validation configuration (optional - not in setups.yaml)."""

    def test_validation_optional(self) -> None:
        """Test that validation field is optional (not required by setups.yaml)."""
        config = load_scoring_config()

        # validation field is optional in new setups.yaml format
        # Only check if it exists, don't require it
        if hasattr(config, "validation") and config.validation:
            assert isinstance(config.validation, dict)


class TestValidateScoringConfig:
    """Test scoring config validation logic."""

    def test_validate_valid_config(self) -> None:
        """Test that a valid config passes validation."""
        config_data = {
            "setups": {
                "VWAP_RECLAIM": {
                    "enabled": True,
                    "min_score": 8,
                    "constraints": {},
                    "weights": {"factor1": 2},
                }
            },
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
        }

        # Should not raise
        validate_scoring_config(config_data)

    def test_validate_missing_setup_types_raises_error(self) -> None:
        """Test that missing setups/setup_types raises ConfigError."""
        config_data = {
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
        }

        with pytest.raises(ConfigError, match="Missing required key: 'setups' or 'setup_types'"):
            validate_scoring_config(config_data)

    def test_validate_missing_confidence_raises_error(self) -> None:
        """Test that missing confidence raises ConfigError."""
        config_data = {
            "setups": {},
        }

        with pytest.raises(ConfigError, match="Missing required key: 'confidence'"):
            validate_scoring_config(config_data)

    def test_validate_accepts_setups_key(self) -> None:
        """Test that 'setups' key is accepted (new format)."""
        config_data = {
            "setups": {
                "VWAP_RECLAIM": {
                    "enabled": True,
                    "min_score": 8,
                    "constraints": {},
                    "weights": {},
                }
            },
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
        }

        # Should not raise
        validate_scoring_config(config_data)

    def test_validate_invalid_min_score_type_raises_error(self) -> None:
        """Test that non-numeric min_score raises ConfigError."""
        config_data = {
            "setups": {"VWAP_RECLAIM": {"min_score": "eight", "weights": {}}},
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
        }

        with pytest.raises(ConfigError, match="min_score must be numeric"):
            validate_scoring_config(config_data)

    def test_validate_negative_min_score_raises_error(self) -> None:
        """Test that negative min_score raises ConfigError."""
        config_data = {
            "setups": {"VWAP_RECLAIM": {"min_score": -5, "weights": {}}},
            "confidence": {"a_plus": 8.0, "watch": 6.0, "reject": 0.0},
        }

        with pytest.raises(ConfigError, match="min_score must be non-negative"):
            validate_scoring_config(config_data)


class TestFactorsConfig:
    """Test factors configuration (optional - not in setups.yaml)."""

    def test_factors_optional(self) -> None:
        """Test that factors field is optional (not required by setups.yaml)."""
        config = load_scoring_config()

        # factors field is optional in new setups.yaml format
        # Only check if it exists, don't require it
        if hasattr(config, "factors") and config.factors:
            assert isinstance(config.factors, dict)
