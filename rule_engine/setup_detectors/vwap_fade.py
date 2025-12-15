"""VWAP Fade setup detector with strict structure validation.

This module implements comprehensive validation for VWAP fade setups,
requiring liquidity sweep, rejection candle, structure clarity, no chop,
trend weakening, and correct directional swing context.
"""

from typing import Optional

import pandas as pd
from common.logger import get_logger

from rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


def detect_vwap_fade(
    features: pd.Series, htf_bias: HTFBias, df: Optional[pd.DataFrame] = None
) -> bool:
    """Detect VWAP_FADE setup with strict structure requirements.

    Requirements (ALL must pass):
        1. Liquidity sweep detected
        2. Rejection candle present (strong wick)
        3. Structure clarity >= 0.6 threshold
        4. No chop (is_chop=False)
        5. CHoCH or trend-weakening detected
        6. Correct directional swing context:
           - Long fade: requires LH (Lower High) - price weakening
           - Short fade: requires HL (Higher Low) - price strengthening
        7. RSI extreme (<30 or >70)
        8. Significant VWAP deviation (>0.5%)

    Args:
        features: Feature series containing market data
        htf_bias: HTFBias object with HTF analysis
        df: Optional DataFrame for historical data (unused currently)

    Returns:
        True if all fade conditions are met, False otherwise

    Example:
        >>> is_fade = detect_vwap_fade(features, htf_bias, df)
        >>> if is_fade:
        ...     print("Valid VWAP fade setup detected")
    """
    direction = htf_bias.direction

    # Validate direction (must be long or short)
    if direction not in ("long", "short"):
        logger.debug(f"VWAP_FADE rejected: invalid direction {direction}")
        return False

    # 1. Liquidity sweep requirement
    if not htf_bias.liquidity_sweep_detected:
        logger.debug("VWAP_FADE rejected: no liquidity sweep detected")
        return False

    # 2. Rejection candle requirement
    # Check for strong wick in the direction of the fade
    open_price = features.get("open", 0)
    high = features.get("high", 0)
    low = features.get("low", 0)
    close = features.get("close", 0)

    if high == 0 or low == 0 or high < low:
        logger.debug("VWAP_FADE rejected: invalid OHLC data")
        return False

    body = abs(close - open_price)
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    # For very small bodies (doji-like), use minimum threshold
    min_wick_threshold = high * 0.001 if body < 0.01 else body

    # Long fade: need lower wick rejection (bounce from oversold)
    # Short fade: need upper wick rejection (pullback from overbought)
    has_rejection_wick = False
    if direction == "long":
        has_rejection_wick = lower_wick > max(body * 2, min_wick_threshold)
    elif direction == "short":
        has_rejection_wick = upper_wick > max(body * 2, min_wick_threshold)

    if not has_rejection_wick:
        logger.debug(
            f"VWAP_FADE rejected: no rejection wick "
            f"(direction={direction}, body={body:.2f}, "
            f"upper_wick={upper_wick:.2f}, lower_wick={lower_wick:.2f})"
        )
        return False

    # 3. Structure clarity requirement
    structure_clarity = features.get("structure_clarity", 0.0)
    if structure_clarity < 0.6:
        logger.debug(
            f"VWAP_FADE rejected: low structure clarity "
            f"(clarity={structure_clarity:.2f}, need >= 0.6)"
        )
        return False

    # 4. No chop requirement
    is_chop = features.get("is_chop", False)
    if is_chop:
        logger.debug("VWAP_FADE rejected: chop detected (is_chop=True)")
        return False

    # 4b. No noise zone requirement (ATR-based tight range detection)
    is_noise_zone = features.get("is_noise_zone", False)
    if is_noise_zone:
        logger.debug("VWAP_FADE rejected: noise zone detected (is_noise_zone=True)")
        return False

    # 5. CHoCH or trend-weakening requirement
    choch_detected = features.get("choch_detected", False)
    trend_confidence = features.get("trend_confidence", 1.0)

    has_weakening_signal = choch_detected or trend_confidence < 0.5

    if not has_weakening_signal:
        logger.debug(
            f"VWAP_FADE rejected: no trend weakening signal "
            f"(choch={choch_detected}, trend_confidence={trend_confidence:.2f})"
        )
        return False

    # 6. Correct directional swing context requirement
    last_structure_label = features.get("last_structure_label")

    if direction == "long":
        # Long fade: need LH (lower high) to confirm weakening uptrend
        if last_structure_label != "LH":
            logger.debug(
                f"VWAP_FADE (long) rejected: need LH structure, got {last_structure_label}"
            )
            return False
    elif direction == "short":
        # Short fade: need HL (higher low) to confirm strengthening into resistance
        if last_structure_label != "HL":
            logger.debug(
                f"VWAP_FADE (short) rejected: need HL structure, got {last_structure_label}"
            )
            return False

    # 7. RSI extreme requirement
    rsi = features.get("rsi", 50.0)
    if not (rsi < 30 or rsi > 70):
        logger.debug(f"VWAP_FADE rejected: RSI not extreme (rsi={rsi:.1f}, need <30 or >70)")
        return False

    # 8. Significant VWAP deviation requirement
    vwap = features.get("vwap", 0)
    if vwap == 0:
        logger.debug("VWAP_FADE rejected: VWAP data missing")
        return False

    vwap_deviation_pct = abs((close - vwap) / vwap * 100)
    if vwap_deviation_pct <= 0.5:
        logger.debug(
            f"VWAP_FADE rejected: insufficient VWAP deviation "
            f"(deviation={vwap_deviation_pct:.2f}%, need >0.5%)"
        )
        return False

    # All checks passed
    logger.info(
        f"VWAP_FADE DETECTED: direction={direction}, "
        f"structure_label={last_structure_label}, clarity={structure_clarity:.2f}, "
        f"rsi={rsi:.1f}, vwap_dev={vwap_deviation_pct:.2f}%, "
        f"choch={choch_detected}, trend_conf={trend_confidence:.2f}"
    )
    return True
