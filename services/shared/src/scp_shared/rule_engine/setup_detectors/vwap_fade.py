"""VWAP Fade setup detector with strict structure validation.

This module implements comprehensive validation for VWAP fade setups,
requiring liquidity sweep, rejection candle, structure clarity, no chop,
trend weakening, and correct directional swing context.
"""

from typing import Optional

import pandas as pd
from scp_shared.common.logger import get_logger
from scp_shared.rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


def detect_vwap_fade(
    features: pd.Series, htf_bias: HTFBias, df: Optional[pd.DataFrame] = None
) -> bool:
    """Detect VWAP_FADE setup with relaxed thresholds for increased signal flow.

    Requirements (ALL must pass, thresholds significantly loosened to allow more candidates):
        1. Liquidity sweep detected (quality signal, will be penalized via scoring if missing)
        2. Rejection candle present (wick > 1.3x body, loosened from 1.5x/2x)
        3. Structure clarity >= 0.4 threshold (lowered from 0.5/0.6)
        4. No noise zone (handled via score penalty in scoring.py)
        5. CHoCH or trend-weakening detected (trend_conf < 0.65, loosened from 0.6/0.5)
        6. Correct directional swing context (SAFETY - must remain):
           - Long fade: requires LH (Lower High) - price weakening
           - Short fade: requires HL (Higher Low) - price strengthening
        7. RSI extreme (<40 or >60, loosened from <35/>65, originally <30/>70)
        8. Significant VWAP deviation (>0.25%, loosened from 0.3%/0.5%)

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
    # Thresholds (further loosened to allow more candidates - quality handled via scoring)
    CLARITY_THRESHOLD = 0.4  # Lowered from 0.5 (was 0.6 originally)
    WICK_BODY_RATIO = 1.3  # Lowered from 1.5 (was 2.0 originally)
    TREND_CONF_THRESHOLD = 0.65  # Increased from 0.6 (easier to meet)
    RSI_OVERSOLD = 40  # Raised from 35 (was 30 originally)
    RSI_OVERBOUGHT = 60  # Lowered from 65 (was 70 originally)
    VWAP_DEVIATION_THRESHOLD = 0.25  # Lowered from 0.3% (was 0.5% originally)

    direction = htf_bias.direction
    
    # Handle None values explicitly (features may have None instead of missing keys)
    structure_clarity = features.get("structure_clarity")
    if structure_clarity is None:
        structure_clarity = 0.0
    
    rsi = features.get("rsi")
    if rsi is None:
        rsi = 50.0
    
    vwap = features.get("vwap") or 0
    close = features.get("close") or 0
    choch_detected = features.get("choch_detected", False)
    
    trend_confidence = features.get("trend_confidence", 1.0)
    last_structure_label = features.get("last_structure_label")

    # Check sweep from both HTFBias AND features (1M features have sweep)
    sweep_from_features = features.get("liquidity_sweep", False)
    sweep_detected_any = htf_bias.liquidity_sweep_detected or sweep_from_features

    # Log all values at start for debugging
    logger.info(
        f"VWAP_FADE prereq check: "
        f"dir={direction}, sweep={sweep_detected_any} "
        f"(htf={htf_bias.liquidity_sweep_detected}, feat={sweep_from_features}), "
        f"clarity={structure_clarity:.2f}, rsi={rsi:.1f}, "
        f"choch={choch_detected}, trend_conf={trend_confidence:.2f}, "
        f"struct_label={last_structure_label}"
    )

    # Validate direction (must be long or short)
    if direction not in ("long", "short"):
        logger.debug(f"VWAP_FADE rejected: invalid direction {direction}")
        return False

    # 1. Liquidity sweep requirement (already computed above as sweep_detected_any)
    if not sweep_detected_any:
        logger.debug("VWAP_FADE rejected: no liquidity sweep detected")
        return False

    # 2. Rejection candle requirement (loosened wick ratio)
    open_price = features.get("open", 0)
    high = features.get("high", 0)
    low = features.get("low", 0)

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
        has_rejection_wick = lower_wick > max(body * WICK_BODY_RATIO, min_wick_threshold)
    elif direction == "short":
        has_rejection_wick = upper_wick > max(body * WICK_BODY_RATIO, min_wick_threshold)

    if not has_rejection_wick:
        logger.debug(
            f"VWAP_FADE rejected: no rejection wick "
            f"(direction={direction}, body={body:.2f}, "
            f"upper_wick={upper_wick:.2f}, lower_wick={lower_wick:.2f}, "
            f"need wick > {WICK_BODY_RATIO}x body)"
        )
        return False

    # 3. Structure clarity requirement (lowered threshold)
    if structure_clarity < CLARITY_THRESHOLD:
        logger.debug(
            f"VWAP_FADE rejected: low structure clarity "
            f"(clarity={structure_clarity:.2f}, need >= {CLARITY_THRESHOLD})"
        )
        return False

    # 4. Noise zone now handled as score penalty (not hard-block)
    # See calculate_noise_penalty() in scoring.py for setup-aware noise handling

    # 5. CHoCH or trend-weakening requirement (loosened threshold)
    has_weakening_signal = choch_detected or trend_confidence < TREND_CONF_THRESHOLD

    if not has_weakening_signal:
        logger.debug(
            f"VWAP_FADE rejected: no trend weakening signal "
            f"(choch={choch_detected}, trend_confidence={trend_confidence:.2f}, "
            f"need trend_conf < {TREND_CONF_THRESHOLD})"
        )
        return False

    # 6. Correct directional swing context requirement
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

    # 7. RSI extreme requirement (loosened thresholds)
    if not (rsi < RSI_OVERSOLD or rsi > RSI_OVERBOUGHT):
        logger.debug(
            f"VWAP_FADE rejected: RSI not extreme "
            f"(rsi={rsi:.1f}, need <{RSI_OVERSOLD} or >{RSI_OVERBOUGHT})"
        )
        return False

    # 8. Significant VWAP deviation requirement (loosened threshold)
    if vwap == 0:
        logger.debug("VWAP_FADE rejected: VWAP data missing")
        return False

    vwap_deviation_pct = abs((close - vwap) / vwap * 100)
    if vwap_deviation_pct <= VWAP_DEVIATION_THRESHOLD:
        logger.debug(
            f"VWAP_FADE rejected: insufficient VWAP deviation "
            f"(deviation={vwap_deviation_pct:.2f}%, need >{VWAP_DEVIATION_THRESHOLD}%)"
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


