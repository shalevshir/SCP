"""VWAP trend validation.

Trend is valid only if price stays above/below VWAP for N candles.

Task: Add VWAP trend validation
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

import pandas as pd
from common.logger import get_logger

logger = get_logger(__name__)


def validate_vwap_trend(
    df: pd.DataFrame,
    min_candles: int = 3,
) -> pd.Series:
    """Validate VWAP trend based on price position.

    Confirms trend validity when price consistently stays above or below VWAP
    for a minimum number of consecutive candles. This indicates sustained
    institutional positioning in one direction.

    Args:
        df: DataFrame with required columns:
            - 'close': Close price for each bar
            - 'vwap': Volume-weighted average price for each bar
        min_candles: Minimum consecutive candles needed for confirmation.
                    Default is 3. Must be >= 1.

    Returns:
        Series with boolean values indicating if trend is confirmed at each bar:
            - True: Price has stayed above/below VWAP for min_candles
            - False: Price hasn't maintained consistent position vs VWAP

    Raises:
        ValueError: If required columns ('close', 'vwap') are missing
        ValueError: If min_candles is less than 1

    Logic:
        - Bullish confirmed: close > vwap for last N candles
        - Bearish confirmed: close < vwap for last N candles
        - Not confirmed: crosses within last N candles or close == vwap
        - NaN handling: NaN in close or vwap results in False for affected bars
        - Warm-up period: First N-1 bars always False (insufficient history)

    Example:
        >>> from feature_engine.vwap import calculate_vwap
        >>> df['vwap'] = calculate_vwap(df, session_reset=True)
        >>> df['trend_confirmed'] = validate_vwap_trend(df, min_candles=3)
        >>> print(f"Confirmed bars: {df['trend_confirmed'].sum()}")
    """
    # Validate required columns
    required_cols = {"close", "vwap"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Validate min_candles parameter
    if min_candles < 1:
        raise ValueError(f"min_candles must be >= 1, got {min_candles}")

    # Handle edge case: DataFrame shorter than min_candles
    if len(df) < min_candles:
        return pd.Series(False, index=df.index)

    # Determine price position relative to VWAP
    # Using strict inequality: close must be > or < VWAP (not equal)
    above_vwap = df["close"] > df["vwap"]
    below_vwap = df["close"] < df["vwap"]

    # Count consecutive candles in same position using rolling window
    # The sum will equal min_candles only if ALL candles in window are on same side
    above_streak = above_vwap.rolling(window=min_candles, min_periods=min_candles).sum()
    below_streak = below_vwap.rolling(window=min_candles, min_periods=min_candles).sum()

    # Trend confirmed if all N candles are on same side
    # For bullish: above_streak == min_candles means all N candles are above
    # For bearish: below_streak == min_candles means all N candles are below
    bullish_confirmed = above_streak == min_candles
    bearish_confirmed = below_streak == min_candles

    # Either bullish OR bearish confirmed = trend confirmed
    trend_confirmed = bullish_confirmed | bearish_confirmed

    # Convert to boolean (handles any NaN that might propagate from rolling)
    # NaN in close or vwap will cause NaN in above_vwap/below_vwap,
    # which will cause NaN in rolling sums, resulting in False comparison
    trend_confirmed = trend_confirmed.fillna(False)

    return trend_confirmed
