"""Micro-timeframe feature computations for continuation detection.

This module provides functions to detect pullback structures, displacement strength,
and pullback recency on the execution timeframe (1M/5M).
"""

from typing import Optional

import pandas as pd
from common.logger import get_logger

logger = get_logger(__name__)


def detect_micro_pullback(df: pd.DataFrame, direction: str) -> Optional[str]:
    """Detect HL (longs) or LH (shorts) pullback on execution timeframe.

    Looks at the last 3-5 candles to identify a clean pullback structure:
    - Long: HL pattern (Higher Low after a high)
    - Short: LH pattern (Lower High after a low)

    Args:
        df: DataFrame with OHLC data (at least 3 candles required)
        direction: Trade direction ("long" or "short")

    Returns:
        "HL" if higher low detected, "LH" if lower high detected, None otherwise

    Example:
        >>> df = pd.DataFrame({"high": [100, 102, 101], "low": [98, 100, 99]})
        >>> detect_micro_pullback(df, "long")
        'HL'
    """
    if len(df) < 3:
        logger.debug("Micro pullback detection requires at least 3 candles")
        return None

    # Get last 5 candles (or fewer if not available)
    lookback = min(5, len(df))
    recent = df.tail(lookback)

    highs = recent["high"].values
    lows = recent["low"].values

    if direction == "long":
        # HL: Recent low is higher than previous low
        # Pattern: low[0] < low[1] < low[2] (ascending lows = HL)
        if len(lows) >= 2:
            # Check if most recent low is higher than previous low
            if lows[-1] > lows[-2]:
                logger.debug(
                    f"HL pullback detected: recent_low={lows[-1]:.2f} > "
                    f"prev_low={lows[-2]:.2f}"
                )
                return "HL"
        return None

    elif direction == "short":
        # LH: Recent high is lower than previous high
        # Pattern: high[0] > high[1] > high[2] (descending highs = LH)
        if len(highs) >= 2:
            # Check if most recent high is lower than previous high
            if highs[-1] < highs[-2]:
                logger.debug(
                    f"LH pullback detected: recent_high={highs[-1]:.2f} < "
                    f"prev_high={highs[-2]:.2f}"
                )
                return "LH"
        return None

    else:
        logger.warning(f"Invalid direction for pullback detection: {direction}")
        return None


def calculate_displacement_strength(
    candle_open: float,
    candle_close: float,
    candle_high: float,
    candle_low: float,
    atr: float,
) -> float:
    """Calculate body/ATR ratio for displacement detection.

    Displacement is a strong directional candle with minimal wicks.
    A ratio >= 1.2 indicates strong displacement (body is 1.2x ATR).

    Args:
        candle_open: Candle open price
        candle_close: Candle close price
        candle_high: Candle high price
        candle_low: Candle low price
        atr: Average True Range for normalization

    Returns:
        Displacement strength ratio (body size / ATR)

    Example:
        >>> calculate_displacement_strength(100, 105, 105.5, 99.5, 3.0)
        1.67  # Strong displacement
    """
    if atr <= 0:
        logger.warning(f"Invalid ATR value: {atr}, returning 0.0")
        return 0.0

    # Calculate body size (directional move)
    body = abs(candle_close - candle_open)

    # Calculate displacement ratio
    displacement = body / atr

    logger.debug(
        f"Displacement: body={body:.2f}, atr={atr:.2f}, ratio={displacement:.2f}"
    )

    return displacement


def calculate_bars_since_pullback(df: pd.DataFrame, direction: str) -> Optional[int]:
    """Count bars since last valid pullback structure.

    Scans recent candles backwards to find the most recent pullback
    and counts how many bars have elapsed since then.

    Args:
        df: DataFrame with OHLC data
        direction: Trade direction ("long" or "short")

    Returns:
        Number of bars since last pullback, or None if no recent pullback found

    Example:
        >>> df = pd.DataFrame({"high": [100, 102, 101, 103], "low": [98, 100, 99, 101]})
        >>> calculate_bars_since_pullback(df, "long")
        2  # Pullback detected 2 bars ago
    """
    if len(df) < 3:
        logger.debug("Need at least 3 candles to detect pullback recency")
        return None

    # Look back up to 10 bars for a pullback
    lookback = min(10, len(df))
    recent = df.tail(lookback)

    highs = recent["high"].values
    lows = recent["low"].values

    # Scan backwards from most recent candle
    for i in range(len(recent) - 2, 0, -1):
        if direction == "long":
            # Check for HL pattern: low[i] > low[i-1]
            if lows[i] > lows[i - 1]:
                bars_since = len(recent) - 1 - i
                logger.debug(
                    f"Pullback found {bars_since} bars ago "
                    f"(low[{i}]={lows[i]:.2f} > low[{i-1}]={lows[i-1]:.2f})"
                )
                return bars_since

        elif direction == "short":
            # Check for LH pattern: high[i] < high[i-1]
            if highs[i] < highs[i - 1]:
                bars_since = len(recent) - 1 - i
                logger.debug(
                    f"Pullback found {bars_since} bars ago "
                    f"(high[{i}]={highs[i]:.2f} < high[{i-1}]={highs[i-1]:.2f})"
                )
                return bars_since

    logger.debug(f"No pullback found in last {lookback} bars for {direction} trade")
    return None





