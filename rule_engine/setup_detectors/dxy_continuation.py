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
    """DXY continuation detection with loosened thresholds.

    Requires the following conditions (thresholds loosened for better signal detection):
        1. Strong inverse correlation (at least one of 1m or 5m < -0.3)
        2. DXY trending (LL/LH for gold longs, HH/HL for gold shorts)
        3. Gold BOS recency <= 15 bars (increased from 10)
        4. Clean micro pullback (HL for longs, LH for shorts) - optional if no df
        5. Displacement candle (displacement_strength >= 1.0, lowered from 1.2)
        6. Pullback recency <= 8 bars (increased from 5)
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
    # Thresholds (loosened for better signal detection)
    CORR_THRESHOLD = -0.3
    BOS_STALENESS_LIMIT = 15  # Increased from 10
    CLARITY_THRESHOLD = 0.4  # Lowered from 0.5
    DISPLACEMENT_THRESHOLD = 1.0  # Lowered from 1.2
    PULLBACK_RECENCY_LIMIT = 8  # Increased from 5

    # Log all values at start for debugging
    corr_1m = htf_bias.dxy_corr_1m
    corr_5m = htf_bias.dxy_corr_5m
    dxy_structure = htf_bias.dxy_structure
    direction = htf_bias.direction
    
    # Get structure metrics from features (1M) as primary source (warms up faster)
    structure_clarity = features.get("structure_clarity", 0.0)
    
    # Get BOS age from features (more responsive) or fall back to htf_bias
    bos_age = features.get("bos_age")
    bos_recent = features.get("bos_recent", False)
    if bos_age is not None and not pd.isna(bos_age):
        bars_since_bos = int(bos_age)
    else:
        bars_since_bos = htf_bias.bars_since_bos

    logger.info(
        f"DXY_CONT prereq check: "
        f"corr_1m={corr_1m}, corr_5m={corr_5m}, "
        f"dxy_struct={dxy_structure}, dir={direction}, "
        f"bars_since_bos={bars_since_bos}, clarity={structure_clarity:.2f}"
    )

    # 1. Correlation check: AT LEAST ONE of 1m or 5m must show strong inverse correlation
    if corr_1m is None or corr_5m is None:
        logger.debug("DXY continuation rejected: missing correlation data")
        return False

    # Loosened: only require ONE of the correlations to meet threshold
    if not (corr_1m < CORR_THRESHOLD or corr_5m < CORR_THRESHOLD):
        logger.debug(
            f"DXY continuation rejected: weak correlation "
            f"(1m={corr_1m:.2f}, 5m={corr_5m:.2f}, need at least one < {CORR_THRESHOLD})"
        )
        return False

    # 2. DXY structural trend must align with trade direction
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
        logger.debug(f"DXY continuation rejected: invalid direction {direction}")
        return False

    # 3. Gold BOS recency check (loosened from 10 to 15)
    if bars_since_bos is None or bars_since_bos > BOS_STALENESS_LIMIT:
        logger.debug(
            f"DXY continuation rejected: BOS too old or missing "
            f"(bars_since_bos={bars_since_bos}, limit={BOS_STALENESS_LIMIT})"
        )
        return False

    # 3.5. Structure clarity check (lowered from 0.5 to 0.4)
    if structure_clarity < CLARITY_THRESHOLD:
        logger.debug(
            f"DXY continuation rejected: low clarity "
            f"(clarity={structure_clarity:.2f}, need >= {CLARITY_THRESHOLD})"
        )
        return False

    # 4. Micro pullback structure (requires DataFrame) - skip if not provided
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
        # Skip micro pullback check if no DataFrame - don't fail
        logger.debug("DXY continuation: skipping micro pullback check (no DataFrame)")

    # 5. Chop filters: Use structure fields directly for more granular control
    # Check is_chop from features (rapid alternations)
    is_chop = features.get("is_chop", False)
    if is_chop:
        logger.debug("DXY continuation rejected: rapid alternations (is_chop=True)")
        return False

    # 5b. Noise zone now handled as score penalty (not hard-block)
    # See calculate_noise_penalty() in scoring.py for setup-aware noise handling

    # Also check DXY 5M chop from HTF bias
    if htf_bias.dxy_chop_5m:
        logger.debug("DXY continuation rejected: DXY 5M in chop")
        return False

    # 5c. Gold structure label alignment (trend-following setup)
    # Long continuations need bullish gold structure (HH or HL)
    # Short continuations need bearish gold structure (LH or LL)
    last_structure_label = features.get("last_structure_label")
    if last_structure_label is not None:
        if direction == "long" and last_structure_label not in ("HH", "HL"):
            logger.debug(
                f"DXY continuation rejected: gold structure {last_structure_label} "
                f"contradicts long direction (need HH or HL)"
            )
            return False
        elif direction == "short" and last_structure_label not in ("LH", "LL"):
            logger.debug(
                f"DXY continuation rejected: gold structure {last_structure_label} "
                f"contradicts short direction (need LH or LL)"
            )
            return False

    # 6. Displacement candle check (loosened from 1.2 to 1.0)
    current_candle_open = features.get("open")
    current_candle_close = features.get("close")
    current_candle_high = features.get("high")
    current_candle_low = features.get("low")

    if all(
        v is not None
        for v in [
            current_candle_open,
            current_candle_close,
            current_candle_high,
            current_candle_low,
        ]
    ):
        atr = features.get("atr")
        if atr is None or atr == 0:
            candle_range = current_candle_high - current_candle_low
            atr = candle_range if candle_range > 0 else 1.0

        displacement = calculate_displacement_strength(
            current_candle_open,
            current_candle_close,
            current_candle_high,
            current_candle_low,
            atr,
        )

        if displacement < DISPLACEMENT_THRESHOLD:
            logger.debug(
                f"DXY continuation rejected: weak displacement "
                f"(strength={displacement:.2f}, need >= {DISPLACEMENT_THRESHOLD})"
            )
            return False
    else:
        logger.debug("DXY continuation: skipping displacement check (missing OHLC)")

    # 7. Pullback recency check (loosened from 5 to 8)
    if df is not None and len(df) >= 5:
        bars_since_pullback = calculate_bars_since_pullback(df, direction)
        if bars_since_pullback is None or bars_since_pullback > PULLBACK_RECENCY_LIMIT:
            logger.debug(
                f"DXY continuation rejected: pullback too old "
                f"(bars_since_pullback={bars_since_pullback}, limit={PULLBACK_RECENCY_LIMIT})"
            )
            return False
    else:
        logger.debug("DXY continuation: skipping pullback recency check (no DataFrame)")

    # All checks passed
    logger.info(
        f"DXY continuation DETECTED: corr_1m={corr_1m:.2f}, corr_5m={corr_5m:.2f}, "
        f"dxy_structure={dxy_structure}, bars_since_bos={bars_since_bos}, "
        f"direction={direction}"
    )
    return True
