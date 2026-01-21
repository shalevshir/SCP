"""Configuration loader for validation layer.

This module loads and parses the validation.yaml configuration file,
building SessionConfig objects for SessionValidator initialization.
"""

from datetime import date, time
from pathlib import Path

import yaml
from scp_shared.common.logger import get_logger
from scp_shared.validation.session_validator import SeasonRule, SessionConfig

logger = get_logger(__name__)


def load_session_config(config_path: str | None = None) -> SessionConfig:
    """Load SessionConfig from validation.yaml.

    Args:
        config_path: Optional path to validation config file.
                    If None, uses default location.

    Returns:
        SessionConfig with all season rules and holidays

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config format is invalid

    Example:
        >>> config = load_session_config()
        >>> validator = SessionValidator(config)
    """
    if config_path is None:
        # Default to config/validation.yaml in project root
        config_path = Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "validation.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Validation config not found: {config_path}")

    logger.info(f"Loading validation config from {config_path}")

    with open(config_path) as f:
        config_data = yaml.safe_load(f)

    # Parse timezone
    timezone = config_data.get("timezone", "Europe/London")

    # Parse default session rule
    default_session_data = config_data.get("default_session", {})
    default_rule = _parse_season_rule(
        default_session_data, "Default", months=list(range(1, 13))
    )

    # Parse season-specific rules
    seasons_data = config_data.get("seasons", [])
    if seasons_data is None:
        seasons_data = []
    seasons = tuple(_parse_season_rule(season_data) for season_data in seasons_data)

    # Parse holidays
    holidays_data = config_data.get("holidays", [])
    holidays = frozenset(_parse_date(date_str) for date_str in holidays_data)

    logger.info(
        f"Loaded validation config: {len(seasons)} seasons, "
        f"{len(holidays)} holidays, timezone={timezone}"
    )

    return SessionConfig(
        timezone=timezone,
        default_rule=default_rule,
        seasons=seasons,
        holidays=holidays,
    )


def _parse_season_rule(
    rule_data: dict, name: str | None = None, months: list[int] | None = None
) -> SeasonRule:
    """Parse a season rule from config data.

    Args:
        rule_data: Dict containing season rule configuration
        name: Optional override for rule name
        months: Optional override for months list

    Returns:
        SeasonRule object
    """
    rule_name = name or rule_data.get("name", "Unnamed")

    # Parse months
    if months is None:
        months = rule_data.get("months", [])
    months_set = frozenset(months)

    # Parse time window
    window_start_str = rule_data.get("window_start", "10:00")
    window_end_str = rule_data.get("window_end", "13:00")
    window_start = _parse_time(window_start_str)
    window_end = _parse_time(window_end_str)

    # Parse allowed tiers
    allowed_tiers_list = rule_data.get("allowed_tiers", [])
    allowed_tiers = frozenset(allowed_tiers_list)

    # Parse allowed setups
    allowed_setups_list = rule_data.get("allowed_setups", [])
    allowed_setups = frozenset(allowed_setups_list)

    # Parse scoring thresholds
    min_score = float(rule_data.get("min_score", 8.0))
    max_losses = int(rule_data.get("max_losses", 2))

    # Parse DXY correlation threshold
    dxy_correlation_max = float(rule_data.get("dxy_correlation_max", -0.6))

    return SeasonRule(
        name=rule_name,
        months=months_set,
        window_start=window_start,
        window_end=window_end,
        allowed_tiers=allowed_tiers,
        allowed_setups=allowed_setups,
        min_score=min_score,
        max_losses=max_losses,
        dxy_correlation_max=dxy_correlation_max,
    )


def _parse_time(time_str: str) -> time:
    """Parse time string in HH:MM format.

    Args:
        time_str: Time string (e.g., "10:00", "13:30")

    Returns:
        time object

    Raises:
        ValueError: If time format is invalid
    """
    try:
        hour, minute = time_str.split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM") from e


def _parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format.

    Args:
        date_str: Date string (e.g., "2024-12-25")

    Returns:
        date object

    Raises:
        ValueError: If date format is invalid
    """
    try:
        year, month, day = date_str.split("-")
        return date(int(year), int(month), int(day))
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD") from e


def load_dxy_handling_config(config_path: str | None = None) -> dict:
    """Load DXY unavailability handling configuration.

    Args:
        config_path: Optional path to validation config file

    Returns:
        Dict mapping setup types to handling strategy
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "validation.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path) as f:
        config_data = yaml.safe_load(f)

    dxy_handling = config_data.get("dxy_handling", {})
    on_missing = dxy_handling.get("on_missing", {})

    return on_missing


def load_ceo_directive_config(config_path: str | None = None) -> dict:
    """Load CEO directive configuration.

    Args:
        config_path: Optional path to validation config file

    Returns:
        Dict with CEO directive settings
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "validation.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path) as f:
        config_data = yaml.safe_load(f)

    ceo_directive = config_data.get("ceo_directive", {})

    return {
        "override_file": ceo_directive.get("override_file", "./config/dev.local.json"),
        "early_mild_enabled": ceo_directive.get("early_mild_enabled", False),
        "daily_reset": ceo_directive.get("daily_reset", True),
    }

