"""Seasonality rules and period detection.

Adds month-based HTF scoring modifiers from SOP.

Task: Add seasonality module
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from scp_shared.common.logger import get_logger

logger = get_logger(__name__)

SeasonalityPeriod = Literal["september", "october", "november_december", "other"]


def get_seasonality_period(timestamp: datetime) -> SeasonalityPeriod:
    """Determine seasonality period from timestamp.

    Args:
        timestamp: Current timestamp

    Returns:
        Seasonality period classification

    Logic:
        - September: Stricter thresholds (historically volatile)
        - October: Neutral baseline
        - November-December: Relaxed thresholds (trending months)
        - Other: Standard thresholds

    DoD:
        - September → stricter thresholds
        - November–December → relaxed thresholds
        - October → neutral baseline
        - Seasonality attribute included in HTF output
    """
    month = timestamp.month

    if month == 9:
        period: SeasonalityPeriod = "september"
    elif month == 10:
        period = "october"
    elif month in (11, 12):
        period = "november_december"
    else:
        period = "other"

    logger.debug(
        "Seasonality period detected: %s | month=%d | timestamp=%s",
        period,
        month,
        timestamp.isoformat(),
    )

    return period


def get_seasonality_config(period: SeasonalityPeriod) -> dict:
    """Get seasonality-specific configuration.

    Args:
        period: Seasonality period

    Returns:
        Configuration dict with thresholds and adjustments

    Example:
        >>> config = get_seasonality_config("september")
        >>> config["min_score_threshold"]
        8.5
        >>> config["dxy_corr_threshold"]
        -0.65
    """
    # SOP-defined seasonality configurations
    configs = {
        "september": {
            "min_score_threshold": 8.5,
            "dxy_corr_threshold": -0.65,
            "max_losses": 1,
            "description": "September - Defensive mode (stricter thresholds)",
        },
        "october": {
            "min_score_threshold": 8.0,
            "dxy_corr_threshold": -0.6,
            "max_losses": 2,
            "description": "October - Neutral baseline",
        },
        "november_december": {
            "min_score_threshold": 8.0,
            "dxy_corr_threshold": -0.55,
            "max_losses": 2,
            "description": "November-December - Trend season (relaxed DXY correlation)",
        },
        "other": {
            "min_score_threshold": 8.0,
            "dxy_corr_threshold": -0.6,
            "max_losses": 2,
            "description": "Standard months - Baseline thresholds",
        },
    }

    config = configs[period]

    logger.debug(
        "Seasonality config retrieved: %s | min_score=%.1f | dxy_corr=%.2f | max_losses=%d",
        period,
        config["min_score_threshold"],
        config["dxy_corr_threshold"],
        config["max_losses"],
    )

    return config
