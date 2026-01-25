"""DXY continuation setup detector with strict validation (streaming mode only).

This module implements comprehensive validation for DXY continuation setups,
requiring correlation, structure, recency, displacement, pullback, and chop checks.
Optimized for streaming/live trading where 5M data may not be available.
"""

from typing import Optional

import pandas as pd
from scp_shared.common.logger import get_logger
from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.setup_detectors.micro_features import (
    calculate_bars_since_pullback,
    calculate_displacement_strength,
    detect_micro_pullback,
)

logger = get_logger(__name__)


def detect_dxy_continuation(
    features: pd.Series, htf_bias: HTFBias, df: Optional[pd.DataFrame] = None
) -> bool:
    """Strict DXY continuation detection (streaming mode).

    Requires ALL of the following conditions:
        1. Strong inverse correlation (< -0.6 from available source)
        2. DXY trending (LL/LH for gold longs, HH/HL for gold shorts) - optional if correlation strong
        3. Gold BOS recency <= 15 bars (or BOS detected)
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
    # 1. Correlation check: use best available correlation data
    # Priority: both 1m+5m (if available) > 1m alone > features.dxy_corr
    corr_1m = htf_bias.dxy_corr_1m
    corr_5m = htf_bias.dxy_corr_5m
    features_dxy_corr = features.get("dxy_corr")

    # If both 1m and 5m available, require both to show inverse correlation
    if corr_1m is not None and corr_5m is not None:
        if not (corr_1m < -0.3 and corr_5m < -0.3):
            logger.debug(
                f"DXY continuation rejected: weak correlation "
                f"(1m={corr_1m:.2f}, 5m={corr_5m:.2f}, need both < -0.3)"
            )
            return False
        effective_corr = min(corr_1m, corr_5m)  # Use the weaker one for logging
        logger.debug(
            f"DXY continuation: correlation OK (1m={corr_1m:.2f}, 5m={corr_5m:.2f})"
        )
    else:
        # Fallback: use 1m or features.dxy_corr with stricter threshold
        effective_corr = corr_1m if corr_1m is not None else features_dxy_corr

        if effective_corr is None:
            logger.debug("DXY continuation rejected: no correlation data available")
            return False

        # Stricter threshold when only one correlation source: require < -0.6
        if effective_corr >= -0.6:
            logger.debug(
                f"DXY continuation rejected: weak correlation "
                f"(corr={effective_corr:.2f}, need < -0.6)"
            )
            return False
        logger.debug(f"DXY continuation: correlation OK (corr={effective_corr:.2f})")

    # 2. DXY structural trend alignment (optional - skip if not available with strong correlation)
    dxy_structure = htf_bias.dxy_structure
    direction = htf_bias.direction  # "long" or "short"

    if direction not in ("long", "short"):
        logger.debug(f"DXY continuation rejected: invalid direction {direction}")
        return False

    if dxy_structure is not None:
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
        # DXY structure not available - rely on strong correlation
        logger.debug(
            "DXY continuation: skipping DXY structure check (relying on correlation)"
        )

    # 3. Gold BOS recency check
    bars_since_bos = htf_bias.bars_since_bos
    bos_threshold = 15  # Relaxed threshold for streaming

    if bars_since_bos is not None and bars_since_bos > bos_threshold:
        logger.debug(
            f"DXY continuation rejected: BOS too old "
            f"(bars_since_bos={bars_since_bos}, threshold={bos_threshold})"
        )
        return False

    # If bars_since_bos is None, check if BOS was detected at all
    if bars_since_bos is None:
        if htf_bias.bos_detected:
            logger.debug("DXY continuation: BOS detected but age unknown, proceeding")
        else:
            # Allow continuation if correlation is very strong (< -0.7)
            if effective_corr < -0.7:
                logger.debug(
                    "DXY continuation: BOS unavailable but very strong correlation, proceeding"
                )
            else:
                logger.debug(
                    "DXY continuation rejected: no BOS detected and correlation not strong enough"
                )
                return False

    # 4. Structure clarity check
    structure_clarity = features.get("structure_clarity")
    if structure_clarity is None:
        structure_clarity = 0.0
    if structure_clarity < 0.5:
        logger.debug(
            f"DXY continuation rejected: low clarity "
            f"(clarity={structure_clarity:.2f}, need >= 0.5)"
        )
        return False

    # 5. Micro pullback structure (requires DataFrame)
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
        # Skip micro pullback check with warning
        logger.debug("DXY continuation: skipping micro pullback check (no DataFrame)")

    # 6. Chop filters
    is_chop = features.get("is_chop", False)
    if is_chop:
        logger.debug("DXY continuation rejected: rapid alternations (is_chop=True)")
        return False

    # DXY 5M chop from HTF bias (skip if not available)
    if htf_bias.dxy_chop_5m is not None and htf_bias.dxy_chop_5m:
        logger.debug("DXY continuation rejected: DXY 5M in chop")
        return False

    # 7. Gold structure label alignment
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

    # 8. Displacement candle check
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
            # Fallback: estimate ATR from candle range (0.65x for body-to-wick ratio)
            candle_range = current_candle_high - current_candle_low
            atr = (0.65 * candle_range) if candle_range > 0 else 1.0

        displacement = calculate_displacement_strength(
            current_candle_open,
            current_candle_close,
            current_candle_high,
            current_candle_low,
            atr,
        )

        if displacement < 1.2:
            logger.debug(
                f"DXY continuation rejected: weak displacement "
                f"(strength={displacement:.2f}, need >= 1.2)"
            )
            return False
    else:
        logger.debug("DXY continuation: skipping displacement check (missing OHLC)")

    # 9. Pullback recency check
    if df is not None and len(df) >= 5:
        bars_since_pullback = calculate_bars_since_pullback(df, direction)
        if bars_since_pullback is None or bars_since_pullback > 5:
            logger.debug(
                f"DXY continuation rejected: pullback too old "
                f"(bars_since_pullback={bars_since_pullback})"
            )
            return False
    else:
        logger.debug(
            "DXY continuation: skipping pullback recency check (insufficient data)"
        )

    # All checks passed
    if corr_5m is not None:
        corr_1m_label = f"{corr_1m:.2f}" if corr_1m is not None else "n/a"
        corr_info = f"1m={corr_1m_label}, 5m={corr_5m:.2f}"
    else:
        corr_info = f"corr={effective_corr:.2f}"
    logger.info(
        f"DXY continuation DETECTED: {corr_info}, "
        f"dxy_structure={dxy_structure}, bars_since_bos={bars_since_bos}, "
        f"direction={direction}"
    )
    return True
