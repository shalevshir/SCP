"""Configuration loader for RuleEngine scoring.

This module provides functionality to load and validate the scoring_config.yaml
file that defines setup types, weights, thresholds, and validation rules.
"""

from pathlib import Path
from typing import Any

import yaml
from common.exceptions import ConfigError


class ScoringConfig:
    """Container for scoring configuration data.

    Attributes:
        setup_types: Dict of setup type names to their config (min_score, weights)
        confidence: Dict of confidence thresholds (a_plus, watch, reject)
        validation: Dict of SOP validation rules (dxy_corr_threshold, sessions, tiers)
        factors: Dict of factor definitions (description, max_points, criteria)
    """

    def __init__(self, config_data: dict[str, Any]) -> None:
        """Initialize ScoringConfig from parsed YAML data.

        Args:
            config_data: Dictionary containing configuration data

        Raises:
            ConfigError: If required keys are missing
        """
        self.setup_types = config_data.get("setup_types", {})
        self.confidence = config_data.get("confidence", {})
        self.validation = config_data.get("validation", {})
        self.factors = config_data.get("factors", {})


def load_scoring_config(config_path: str | None = None) -> ScoringConfig:
    """Load scoring configuration from YAML file.

    Args:
        config_path: Path to scoring config file. If None, loads default
                    config/scoring_config.yaml from project root.

    Returns:
        ScoringConfig object containing parsed configuration

    Raises:
        ConfigError: If file not found or YAML parsing fails

    Example:
        >>> config = load_scoring_config()
        >>> min_score = config.setup_types["VWAP_RECLAIM"]["min_score"]
        >>> print(f"VWAP_RECLAIM min score: {min_score}")
    """
    # Determine config file path
    if config_path is None:
        # Default to config/scoring_config.yaml from project root
        project_root = Path(__file__).parent.parent
        config_path = str(project_root / "config" / "scoring_config.yaml")

    config_file = Path(config_path)

    # Check if file exists
    if not config_file.exists():
        raise ConfigError(
            f"Scoring config file not found: {config_path}",
            config_path=config_path,
        )

    # Load and parse YAML
    try:
        with open(config_file) as f:
            config_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(
            f"Failed to parse YAML config file: {config_path}",
            config_path=config_path,
            error=str(e),
        ) from e
    except Exception as e:
        raise ConfigError(
            f"Failed to read config file: {config_path}",
            config_path=config_path,
            error=str(e),
        ) from e

    # Validate configuration structure
    validate_scoring_config(config_data)

    return ScoringConfig(config_data)


def validate_scoring_config(config_data: dict[str, Any]) -> None:
    """Validate scoring configuration structure and values.

    Args:
        config_data: Dictionary containing configuration data

    Raises:
        ConfigError: If validation fails

    Validation checks:
        - Required top-level keys present (setup_types, confidence, validation)
        - Each setup type has min_score and weights
        - min_score values are numeric and non-negative
        - weights are dictionaries
        - confidence thresholds are numeric
    """
    # Check required top-level keys
    required_keys = ["setup_types", "confidence", "validation"]
    for key in required_keys:
        if key not in config_data:
            raise ConfigError(
                f"Missing required key: {key}",
                required_keys=required_keys,
                found_keys=list(config_data.keys()),
            )

    # Validate setup_types structure
    setup_types = config_data["setup_types"]
    if not isinstance(setup_types, dict):
        raise ConfigError(
            "setup_types must be a dictionary",
            found_type=type(setup_types).__name__,
        )

    for setup_name, setup_config in setup_types.items():
        # Check min_score exists
        if "min_score" not in setup_config:
            raise ConfigError(
                f"Setup type '{setup_name}' missing min_score",
                setup_name=setup_name,
            )

        # Check min_score is numeric
        min_score = setup_config["min_score"]
        if not isinstance(min_score, int | float):
            raise ConfigError(
                f"Setup type '{setup_name}' min_score must be numeric",
                setup_name=setup_name,
                found_type=type(min_score).__name__,
            )

        # Check min_score is non-negative
        if min_score < 0:
            raise ConfigError(
                f"Setup type '{setup_name}' min_score must be non-negative",
                setup_name=setup_name,
                min_score=min_score,
            )

        # Check weights exists
        if "weights" not in setup_config:
            raise ConfigError(
                f"Setup type '{setup_name}' missing weights",
                setup_name=setup_name,
            )

        # Check weights is a dict
        weights = setup_config["weights"]
        if not isinstance(weights, dict):
            raise ConfigError(
                f"Setup type '{setup_name}' weights must be a dictionary",
                setup_name=setup_name,
                found_type=type(weights).__name__,
            )

    # Validate confidence thresholds
    confidence = config_data["confidence"]
    if not isinstance(confidence, dict):
        raise ConfigError(
            "confidence must be a dictionary",
            found_type=type(confidence).__name__,
        )

    # Validate validation section
    validation = config_data["validation"]
    if not isinstance(validation, dict):
        raise ConfigError(
            "validation must be a dictionary",
            found_type=type(validation).__name__,
        )
