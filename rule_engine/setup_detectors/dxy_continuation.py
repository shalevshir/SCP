"""DXY continuation setup detector with strict validation.

This module implements comprehensive validation for DXY continuation setups,
requiring correlation, structure, recency, displacement, pullback, and chop checks.
"""

from typing import Optional

import pandas as pd
from common.logger import get_logger

from rule_engine.htf.types import HTFBias
from rule_engine.setup_detectors.micro_features import (
    calculate_bars_since_pullback,
    calculate_displacement_strength,
    detect_micro_pullback,
)

logger = get_logger(__name__)


def detect_dxy_continuation(
    features: pd.Series, htf_bias: HTFBias, df: Optional[pd.DataFrame] = None
) -> bool:
    """Strict DXY continuation detection.

    Requires ALL of the following conditions:
        1. Strong inverse correlation (1m & 5m < -0.3)
        2. DXY trending (LL/LH for gold longs, HH/HL for gold shorts)
        3. Gold BOS recency <= 10 bars
        4. Clean micro pullback (HL for longs, LH for shorts)
        5. Displacement candle (displacement_strength >= 1.2)
        6. Pullback recency <= 5 bars
        7. No chop (DXY 5M or gold micro)

    Args:
        features: Feature series containing market data
        htf_bias: HTFBias object with HTF analysis
        df: Optional DataFrame for micro structure analysis

    Returns:
        True if all continuation conditions are met, False otherwise

    Example:
        >>> is_continuation = detect_dxy_continuation(features, htf_bias, df)
        >>> if is_continuation:
        ...     print("Valid DXY continuation setup detected")
    """
    # 1. Correlation check: both 1m and 5m must show strong inverse correlation
    corr_1m = htf_bias.dxy_corr_1m
    corr_5m = htf_bias.dxy_corr_5m

    if corr_1m is None or corr_5m is None:
        logger.debug("DXY continuation rejected: missing correlation data")
        return False

    if not (corr_1m < -0.3 and corr_5m < -0.3):
        logger.debug(
            f"DXY continuation rejected: weak correlation (1m={corr_1m:.2f}, 5m={corr_5m:.2f})"
        )
        return False

    # 2. DXY structural trend must align with trade direction
    dxy_structure = htf_bias.dxy_structure
    direction = htf_bias.direction  # "long" or "short"

    if direction == "long":
        # Longs require DXY bearish structure (LL or LH)
        if dxy_structure not in ("LL", "LH"):
            logger.debug(
                f"DXY continuation rejected: DXY structure {dxy_structure} "
                f"does not support long (need LL/LH)"
            )
            return False
    elif direction == "short":
        # Shorts require DXY bullish structure (HH or HL)
        if dxy_structure not in ("HH", "HL"):
            logger.debug(
                f"DXY continuation rejected: DXY structure {dxy_structure} "
                f"does not support short (need HH/HL)"
            )
            return False
    else:
        logger.debug(
            f"DXY continuation rejected: invalid direction {direction}"
        )
        return False

    # 3. Gold BOS recency check
    bars_since_bos = htf_bias.bars_since_bos
    if bars_since_bos is None or bars_since_bos > 10:
        logger.debug(
            f"DXY continuation rejected: BOS too old or missing "
            f"(bars_since_bos={bars_since_bos})"
        )
        return False

    # 4. Micro pullback structure (requires DataFrame)
    if df is not None and len(df) >= 3:
        micro_structure = detect_micro_pullback(df, direction)
        expected_structure = "HL" if direction == "long" else "LH"

        if micro_structure != expected_structure:
            logger.debug(
                f"DXY continuation rejected: invalid micro pullback "
                f"(got {micro_structure}, need {expected_structure})"
            )
            return False
    else:
        # If no DataFrame provided, skip micro pullback check with warning
        logger.warning(
            "DXY continuation: skipping micro pullback check (no DataFrame provided)"
        )

    # 5. Chop filters: reject if either DXY 5M or gold micro chop detected
    if htf_bias.dxy_chop_5m:
        logger.debug("DXY continuation rejected: DXY 5M in chop")
        return False

    if htf_bias.chop_detected:
        logger.debug("DXY continuation rejected: Gold micro chop detected")
        return False

    # 6. Displacement candle check
    # Get current candle from features
    current_candle_open = features.get("open")
    current_candle_close = features.get("close")
    current_candle_high = features.get("high")
    current_candle_low = features.get("low")

    if all(
        v is not None
        for v in [current_candle_open, current_candle_close, current_candle_high, current_candle_low]
    ):
        # Calculate ATR from features if available
        atr = features.get("atr")
        if atr is None or atr == 0:
            # Fallback: estimate ATR from recent candle range
            candle_range = current_candle_high - current_candle_low
            atr = candle_range if candle_range > 0 else 1.0

        displacement = calculate_displacement_strength(
            current_candle_open, current_candle_close,
            current_candle_high, current_candle_low, atr
        )

        if displacement < 1.2:
            logger.debug(
                f"DXY continuation rejected: weak displacement "
                f"(strength={displacement:.2f}, need >= 1.2)"
            )
            return False
    else:
        logger.warning(
            "DXY continuation: skipping displacement check (missing OHLC data)"
        )

    # 7. Pullback recency check
    if df is not None and len(df) >= 5:
        bars_since_pullback = calculate_bars_since_pullback(df, direction)
        if bars_since_pullback is None or bars_since_pullback > 5:
            logger.debug(
                f"DXY continuation rejected: pullback too old "
                f"(bars_since_pullback={bars_since_pullback})"
            )
            return False
    else:
        logger.warning(
            "DXY continuation: skipping pullback recency check (insufficient data)"
        )

    # All checks passed
    logger.info(
        f"DXY continuation DETECTED: corr_1m={corr_1m:.2f}, corr_5m={corr_5m:.2f}, "
        f"dxy_structure={dxy_structure}, bars_since_bos={bars_since_bos}, "
        f"direction={direction}"
    )
    return True
