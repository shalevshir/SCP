"""RECLAIM_SENTINEL - final gatekeeper for VWAP reclaim signals.

Rejects any reclaim signal that doesn't meet all requirements:
1. Price crossed VWAP from below in last N bars
2. Liquidity sweep exists
3. Displacement candle present (body > avg)
4. Structure is clean (clarity >= 0.7, no chop)
"""

from __future__ import annotations

import pandas as pd
from common.logger import get_logger

from rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


def reclaim_sentinel(
    features: pd.Series,
    htf_bias: HTFBias,
    vwap_history: pd.Series,
    price_history: pd.DataFrame,
    lookback: int = 5,
    displacement_lookback: int = 10,
) -> tuple[bool, str | None]:
    """Final validation before VWAP_RECLAIM signal.

    Args:
        features: Current bar features (must contain 'close', 'vwap')
        htf_bias: HTFBias object with structure metrics
        vwap_history: Series of VWAP values for last N bars
        price_history: DataFrame with OHLC for last N bars
        lookback: Bars to check for VWAP cross (default: 5)
        displacement_lookback: Bars to calculate avg body size (default: 10)

    Returns:
        Tuple of (is_valid, rejection_reason)

    Rejects if:
    1. Price hasn't crossed VWAP from below in last N bars
    2. No sweep exists (htf_bias.liquidity_sweep_detected)
    3. No displacement candle exists (body > avg)
    4. Structure not clean (clarity < 0.7 or chop detected)
    """
    # Check 1: Price crossed VWAP from below
    if len(price_history) < lookback or len(vwap_history) < lookback:
        return False, "Insufficient price/VWAP history"

    # Get recent data
    recent_prices = price_history.iloc[-lookback:]
    recent_vwap = vwap_history.iloc[-lookback:]

    # Check if price was below VWAP and then crossed above
    crossed_from_below = False
    reclaim_bar_idx = None

    for i in range(len(recent_prices) - 1):
        curr_close = recent_prices["close"].iloc[i]
        next_close = recent_prices["close"].iloc[i + 1]
        curr_vwap = recent_vwap.iloc[i]
        next_vwap = recent_vwap.iloc[i + 1]

        # Crossed from below to above
        if curr_close < curr_vwap and next_close > next_vwap:
            crossed_from_below = True
            reclaim_bar_idx = i + 1
            break

    if not crossed_from_below:
        return False, "Price hasn't crossed VWAP from below in last 5 bars"

    # Check 2: Liquidity sweep
    if not htf_bias.liquidity_sweep_detected:
        return False, "No liquidity sweep detected"

    # Check 3: Displacement candle
    if reclaim_bar_idx is not None:
        # Calculate displacement relative to full history
        full_reclaim_idx = len(price_history) - lookback + reclaim_bar_idx
        is_displacement = detect_displacement_candle(
            price_history, full_reclaim_idx, lookback=displacement_lookback
        )

        if not is_displacement:
            return False, "No displacement candle detected (body not > avg)"
    else:
        return False, "Cannot identify reclaim bar for displacement check"

    # Check 4: Structure quality
    if htf_bias.structure_clarity < 0.7:
        return (
            False,
            f"Structure clarity too low: {htf_bias.structure_clarity:.2f} < 0.7",
        )

    if htf_bias.chop_detected:
        return False, "Choppy structure detected"

    # All checks passed
    logger.info("RECLAIM_SENTINEL: All checks passed - valid reclaim")
    return True, None


def detect_displacement_candle(
    df: pd.DataFrame,
    reclaim_bar_idx: int,
    lookback: int = 10,
) -> bool:
    """Check if the reclaim bar is a valid displacement candle.

    A displacement candle has a body larger than the average body size
    of the previous N bars, indicating strong conviction in the move.

    Args:
        df: DataFrame with OHLC data
        reclaim_bar_idx: Index of the bar that crossed above VWAP
        lookback: Number of bars to calculate average body size

    Returns:
        True if reclaim bar body > average body size

    Example:
        >>> is_displacement = detect_displacement_candle(df, 50, lookback=10)
        >>> if is_displacement:
        ...     print("Strong displacement confirmed")
    """
    # Validate index
    if reclaim_bar_idx < 0 or reclaim_bar_idx >= len(df):
        logger.warning(f"Invalid reclaim_bar_idx: {reclaim_bar_idx}")
        return False

    # Calculate body size for reclaim bar
    reclaim_open = df["open"].iloc[reclaim_bar_idx]
    reclaim_close = df["close"].iloc[reclaim_bar_idx]
    reclaim_body = abs(reclaim_close - reclaim_open)

    # Calculate average body size of previous bars
    start_idx = max(0, reclaim_bar_idx - lookback)
    prev_bars = df.iloc[start_idx:reclaim_bar_idx]

    if len(prev_bars) == 0:
        logger.warning("No previous bars for displacement check")
        return False

    avg_body = (prev_bars["close"] - prev_bars["open"]).abs().mean()

    # Displacement requires body > average
    is_displacement = reclaim_body > avg_body

    logger.debug(
        f"Displacement check: reclaim_body={reclaim_body:.2f}, "
        f"avg_body={avg_body:.2f}, is_displacement={is_displacement}"
    )

    return is_displacement
