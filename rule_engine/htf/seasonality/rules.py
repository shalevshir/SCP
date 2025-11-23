"""Seasonality rules and period detection.

Adds month-based HTF scoring modifiers from SOP.

Task: Add seasonality module
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from common.logger import get_logger

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
    # TODO: Implement seasonality period detection
    # See task: https://www.notion.so/2b42bd6fbda6806b9ae2f498addb965a
    raise NotImplementedError("Seasonality period detection pending implementation")


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
    # TODO: Implement seasonality configuration
    raise NotImplementedError("Seasonality configuration pending implementation")

