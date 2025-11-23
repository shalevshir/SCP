"""Swing high/low identification.

Identifies swing highs and lows on HTF (1H and 15M) data using n-bar lookback.
Used for BOS, CHoCH, liquidity sweep, and trend validation.

Task: Implement swing identification
Epic: Full HTF Bias Engine Upgrade
Status: In Progress
"""

from __future__ import annotations

import pandas as pd

from common.logger import get_logger

logger = get_logger(__name__)


def detect_swings(
    df: pd.DataFrame,
    lookback: int = 5,
) -> tuple[list[int], list[int]]:
    """Detect swing highs and lows in price data.

    A swing high is a peak where the high is higher than N bars before and after.
    A swing low is a trough where the low is lower than N bars before and after.

    Args:
        df: DataFrame with 'high' and 'low' columns
        lookback: Number of bars to look back and forward for confirmation

    Returns:
        Tuple of (swing_high_indices, swing_low_indices)

    Raises:
        ValueError: If required columns are missing or lookback < 1

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 102, 105, 103, 101],
        ...     'low': [98, 99, 102, 100, 98]
        ... })
        >>> highs, lows = detect_swings(df, lookback=1)
        >>> highs
        [2]  # Index 2 has highest high
    """
    # Validate lookback
    if lookback < 1:
        raise ValueError("lookback must be >= 1")

    # Validate required columns
    required_cols = {"high", "low"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required column(s): {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    # Initialize result lists
    swing_highs: list[int] = []
    swing_lows: list[int] = []

    # Handle empty or insufficient data
    if len(df) < 2 * lookback + 1:
        return swing_highs, swing_lows

    # Detect swing highs: local maxima
    # Iterate through valid range [lookback, len(df) - lookback)
    for i in range(lookback, len(df) - lookback):
        # Extract window around current position
        window_highs = df["high"].iloc[i - lookback : i + lookback + 1]
        
        # Check if current position is maximum in window
        if df["high"].iloc[i] == window_highs.max():
            swing_highs.append(i)

    # Detect swing lows: local minima
    for i in range(lookback, len(df) - lookback):
        # Extract window around current position
        window_lows = df["low"].iloc[i - lookback : i + lookback + 1]
        
        # Check if current position is minimum in window
        if df["low"].iloc[i] == window_lows.min():
            swing_lows.append(i)

    logger.debug(
        f"Detected {len(swing_highs)} swing highs and {len(swing_lows)} swing lows "
        f"in {len(df)} bars (lookback={lookback})"
    )

    return swing_highs, swing_lows

