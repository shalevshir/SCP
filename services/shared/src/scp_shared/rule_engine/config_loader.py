"""Configuration loader for RuleEngine scoring.

This module provides functionality to load and validate the config/setups.yaml
file that defines setup types, weights, thresholds, constraints, and validation rules.

Migration Note:
    Previously loaded from scoring_config.yaml. Now uses the unified setups.yaml
    which includes both constraints (for setup detection) and weights (for scoring).
    Maps 'setups' key to 'setup_types' for backward compatibility with existing code.
"""

from pathlib import Path
from typing import Any

import yaml
from scp_shared.common.exceptions import ConfigError


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
        config_path: Path to setups config file. If None, loads default
                    config/setups.yaml from project root or /config
                    (for Docker containers).

    Returns:
        ScoringConfig object containing parsed configuration

    Raises:
        ConfigError: If file not found or YAML parsing fails

    Example:
        >>> config = load_scoring_config()
        >>> min_score = config.setup_types["VWAP_RECLAIM"]["min_score"]
        >>> print(f"VWAP_RECLAIM min score: {min_score}")

    Note:
        Now loads from config/setups.yaml (unified config) instead of
        scoring_config.yaml. Maps 'setups' key to 'setup_types' for
        backward compatibility.
    """
    # Determine config file path
    if config_path is None:
        # Try multiple locations:
        # 1. /config/setups.yaml (Docker container mount)
        # 2. config/setups.yaml from project root (local development)
        docker_config = Path("/config/setups.yaml")
        if docker_config.exists():
            config_path = str(docker_config)
        else:
            # Navigate from services/shared/src/scp_shared/rule_engine to project root
            project_root = Path(__file__).parent.parent.parent.parent.parent.parent
            config_path = str(project_root / "config" / "setups.yaml")

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

    # Map 'setups' to 'setup_types' for backward compatibility
    if "setups" in config_data and "setup_types" not in config_data:
        config_data["setup_types"] = config_data["setups"]

    return ScoringConfig(config_data)


def validate_scoring_config(config_data: dict[str, Any]) -> None:
    """Validate scoring configuration structure and values.

    Args:
        config_data: Dictionary containing configuration data

    Raises:
        ConfigError: If validation fails

    Validation checks:
        - Required top-level keys present (setups or setup_types, confidence)
        - Each setup type has min_score and weights
        - min_score values are numeric and non-negative
        - weights are dictionaries
        - confidence thresholds are numeric

    Note:
        Accepts both 'setups' (new format) and 'setup_types' (legacy format).
        'validation' key is optional (not used by setups.yaml).
    """
    # Check for setups or setup_types
    if "setups" not in config_data and "setup_types" not in config_data:
        raise ConfigError(
            "Missing required key: 'setups' or 'setup_types'",
            found_keys=list(config_data.keys()),
        )

    # Check confidence key
    if "confidence" not in config_data:
        raise ConfigError(
            "Missing required key: 'confidence'",
            found_keys=list(config_data.keys()),
        )

    # Validate setup_types/setups structure (support both keys)
    setup_types = config_data.get("setup_types") or config_data.get("setups")
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

    # Validate validation section (optional - not in setups.yaml)
    if "validation" in config_data:
        validation = config_data["validation"]
        if not isinstance(validation, dict):
            raise ConfigError(
                "validation must be a dictionary",
                found_type=type(validation).__name__,
            )
