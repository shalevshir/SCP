"""Indicator validation for dashboard display.

This module provides SOP-compliant validation status for dashboard indicators.

Architecture: Zero code duplication - calls existing validation from rule_engine.
"""

from typing import Optional

import pandas as pd

from common.logger import get_logger
from rule_engine.config_loader import load_scoring_config
from rule_engine.htf.types import HTFBias

logger = get_logger(__name__)

# Cached scoring config
_config: Optional[dict] = None


def _get_config() -> dict:
    """Get scoring config (cached)."""
    global _config
    if _config is None:
        _config = load_scoring_config()
    return _config


def validate_rsi(rsi_value: Optional[float], htf_bias: Optional[HTFBias]) -> str:
    """Validate RSI according to SOP rules.

    Args:
        rsi_value: RSI value (0-100) or None
        htf_bias: Current HTF bias (for setup type context)

    Returns:
        "VALID", "WEAK", "INVALID", or "N/A"
    """
    if rsi_value is None or pd.isna(rsi_value):
        return "N/A"

    # Continuation zone (mid-reset): 40-60
    if 40 <= rsi_value <= 60:
        return "VALID"

    # Extreme zones (fade setups): <30 or >70
    if rsi_value < 30 or rsi_value > 70:
        return "VALID"  # Valid for fade setups

    # Weak zones: 30-40 or 60-70
    return "WEAK"


def validate_dxy_corr(corr_value: Optional[float]) -> str:
    """Validate DXY correlation according to SOP rules.

    Args:
        corr_value: DXY correlation (-1 to 1) or None

    Returns:
        "VALID", "WEAK", "INVALID", or "N/A"
    """
    if corr_value is None or pd.isna(corr_value):
        return "N/A"

    # Strong inverse correlation (SOP threshold)
    if corr_value < -0.6:
        return "VALID"

    # Moderate inverse correlation
    if -0.6 <= corr_value < -0.4:
        return "WEAK"

    # Weak or positive correlation (not aligned with Gold/DXY relationship)
    return "INVALID"


def validate_vwap_relation(
    close: Optional[float],
    vwap: Optional[float],
    htf_bias: Optional[HTFBias],
) -> str:
    """Validate VWAP relation according to SOP rules.

    Args:
        close: Current close price
        vwap: Current VWAP value
        htf_bias: Current HTF bias

    Returns:
        "VALID", "WEAK", "INVALID", or "N/A"
    """
    if close is None or vwap is None or vwap == 0:
        return "N/A"

    if pd.isna(close) or pd.isna(vwap):
        return "N/A"

    if not htf_bias or htf_bias.direction == "neutral":
        # No directional bias, just show position
        deviation_pct = abs((close - vwap) / vwap * 100)
        if deviation_pct < 0.1:
            return "WEAK"  # Too close to VWAP
        return "VALID"  # Has clear position

    # Bullish bias: price should be above VWAP
    if htf_bias.direction == "long":
        if close > vwap:
            return "VALID"
        elif close > vwap * 0.999:  # Within 0.1%
            return "WEAK"
        else:
            return "INVALID"

    # Bearish bias: price should be below VWAP
    if htf_bias.direction == "short":
        if close < vwap:
            return "VALID"
        elif close < vwap * 1.001:  # Within 0.1%
            return "WEAK"
        else:
            return "INVALID"

    return "N/A"


def validate_ema_stack(
    ema_9: Optional[float],
    ema_20: Optional[float],
    ema_50: Optional[float],
    htf_bias: Optional[HTFBias],
) -> str:
    """Validate EMA stack according to SOP rules.

    Args:
        ema_9: EMA 9 value
        ema_20: EMA 20 value
        ema_50: EMA 50 value
        htf_bias: Current HTF bias

    Returns:
        "VALID", "WEAK", "INVALID", or "N/A"
    """
    if ema_9 is None or ema_20 is None or ema_50 is None:
        return "N/A"

    if pd.isna(ema_9) or pd.isna(ema_20) or pd.isna(ema_50):
        return "N/A"

    if not htf_bias or htf_bias.direction == "neutral":
        # No bias, just check if stack exists
        if ema_9 > ema_20 > ema_50 or ema_9 < ema_20 < ema_50:
            return "VALID"
        return "WEAK"

    # Bullish bias: 9 > 20 > 50
    if htf_bias.direction == "long":
        if ema_9 > ema_20 > ema_50:
            return "VALID"
        elif ema_9 > ema_20:  # Partial alignment
            return "WEAK"
        else:
            return "INVALID"

    # Bearish bias: 9 < 20 < 50
    if htf_bias.direction == "short":
        if ema_9 < ema_20 < ema_50:
            return "VALID"
        elif ema_9 < ema_20:  # Partial alignment
            return "WEAK"
        else:
            return "INVALID"

    return "N/A"


def validate_structure(
    structure_value: Optional[str],
    htf_bias: Optional[HTFBias],
) -> str:
    """Validate structure label according to SOP rules.

    Args:
        structure_value: Structure label (HH/HL/LH/LL/None/nan)
        htf_bias: Current HTF bias

    Returns:
        "VALID", "WEAK", "INVALID", or "N/A"
    """
    # Check for missing/invalid values
    if structure_value is None:
        return "N/A"

    if isinstance(structure_value, float) and pd.isna(structure_value):
        return "N/A"

    if str(structure_value).lower() in ["none", "nan", "n/a", ""]:
        return "N/A"

    # No HTF bias, just check if structure exists
    if not htf_bias or htf_bias.direction == "neutral":
        if structure_value in ["HH", "HL", "LH", "LL"]:
            return "VALID"
        return "N/A"

    # Check alignment with HTF bias
    bullish_structure = structure_value in ["HH", "HL"]
    bearish_structure = structure_value in ["LH", "LL"]

    if htf_bias.direction == "long":
        if bullish_structure:
            return "VALID"
        elif bearish_structure:
            return "INVALID"

    if htf_bias.direction == "short":
        if bearish_structure:
            return "VALID"
        elif bullish_structure:
            return "INVALID"

    return "N/A"


def get_all_indicator_validations(
    features: pd.Series,
    htf_bias: Optional[HTFBias],
) -> dict[str, str]:
    """Get validation status for all indicators.

    Args:
        features: Current feature values
        htf_bias: Current HTF bias

    Returns:
        Dict mapping indicator names to validation status strings
    """
    validations = {}

    # Validate each indicator
    validations["rsi"] = validate_rsi(features.get("rsi"), htf_bias)
    validations["dxy_corr"] = validate_dxy_corr(features.get("dxy_corr"))
    validations["vwap"] = validate_vwap_relation(
        features.get("close"),
        features.get("vwap"),
        htf_bias,
    )
    validations["ema_stack"] = validate_ema_stack(
        features.get("ema_9"),
        features.get("ema_20"),
        features.get("ema_50"),
        htf_bias,
    )
    validations["structure"] = validate_structure(
        features.get("structure_label"),
        htf_bias,
    )

    return validations


def get_validation_badge_class(status: str) -> str:
    """Get Bootstrap badge class for validation status.

    Args:
        status: Validation status ("VALID", "WEAK", "INVALID", "N/A")

    Returns:
        Bootstrap badge class string
    """
    if status == "VALID":
        return "badge bg-success"
    elif status == "WEAK":
        return "badge bg-warning text-dark"
    elif status == "INVALID":
        return "badge bg-danger"
    else:  # N/A
        return "badge bg-secondary"


def get_validation_tooltip(
    indicator: str,
    status: str,
    value: Optional[float],
) -> str:
    """Get tooltip text explaining validation status.

    Args:
        indicator: Indicator name
        status: Validation status
        value: Current indicator value

    Returns:
        Tooltip text
    """
    if status == "N/A":
        return f"{indicator}: Warming up or no data"

    if indicator == "rsi":
        if status == "VALID":
            return "RSI in continuation zone (40-60) or extreme (<30/>70)"
        elif status == "WEAK":
            return "RSI in weak zone (30-40 or 60-70)"
        else:
            return "RSI outside optimal zones"

    if indicator == "dxy_corr":
        if status == "VALID":
            return f"Strong inverse correlation ({value:.3f} < -0.6)" if value else "Strong inverse correlation"
        elif status == "WEAK":
            return f"Moderate correlation ({value:.3f})" if value else "Moderate correlation"
        else:
            return f"Weak/positive correlation ({value:.3f} > -0.4)" if value else "Weak/positive correlation"

    if indicator == "vwap":
        if status == "VALID":
            return "Price position aligns with HTF bias"
        elif status == "WEAK":
            return "Price too close to VWAP"
        else:
            return "Price position conflicts with HTF bias"

    if indicator == "ema_stack":
        if status == "VALID":
            return "EMAs fully aligned with HTF bias"
        elif status == "WEAK":
            return "EMAs partially aligned"
        else:
            return "EMAs misaligned with HTF bias"

    if indicator == "structure":
        if status == "VALID":
            return "Structure aligns with HTF bias"
        elif status == "INVALID":
            return "Structure conflicts with HTF bias"
        else:
            return "No swing point detected"

    return f"{indicator}: {status}"

