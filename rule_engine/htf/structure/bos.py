"""Break of Structure (BOS) detection.

A BOS occurs when price closes beyond the prior swing high/low.
Required for trend continuation validation.

Task: Implement BOS detection
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

import pandas as pd

from common.logger import get_logger

logger = get_logger(__name__)


def detect_bos(
    df: pd.DataFrame,
    swing_highs: list[int],
    swing_lows: list[int],
) -> pd.Series:
    """Detect Break of Structure events.

    A BOS occurs when price closes beyond a prior swing high/low, indicating
    trend continuation. Uses strict inequality rules and rejects ambiguous cases.

    Args:
        df: DataFrame with OHLC data (must have 'close', 'high', 'low' columns)
        swing_highs: List of integer indices where swing highs occurred
        swing_lows: List of integer indices where swing lows occurred

    Returns:
        Series with BOS labels indexed to match df.index:
        - "bullish_bos": Close > prior swing high (strict >)
        - "bearish_bos": Close < prior swing low (strict <)
        - None: No BOS or ambiguous case (breaks both directions)

    Raises:
        ValueError: If required columns are missing

    Logic:
        - Bullish BOS: close > prior swing high (strict inequality)
        - Bearish BOS: close < prior swing low (strict inequality)
        - Ambiguous: If close breaks both directions → None (volatility/sweep)
        - Equality: close == swing level does NOT count as BOS
        - Multiple breaks: Single label regardless of how many swings broken
        - Prior only: Only compares to swings BEFORE current bar

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 102, 105, 103, 101, 103, 108],
        ...     'low': [98, 99, 102, 100, 98, 100, 105],
        ...     'close': [99, 101, 104, 102, 100, 102, 107]
        ... })
        >>> swing_highs = [2]  # Swing high at index 2 (high=105)
        >>> swing_lows = []
        >>> bos = detect_bos(df, swing_highs, swing_lows)
        >>> bos.iloc[6]  # close=107 > 105
        'bullish_bos'
    """
    # Validate required columns
    required_cols = {"close", "high", "low"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required column(s): {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    # Initialize result Series matching DataFrame index
    bos_labels = pd.Series(None, index=df.index, dtype="object")

    # Handle empty DataFrame
    if len(df) == 0:
        return bos_labels

    # Handle empty swing lists
    if not swing_highs and not swing_lows:
        return bos_labels

    # Track counts for logging
    bullish_count = 0
    bearish_count = 0

    # Iterate through each bar
    for i in range(len(df)):
        close = df["close"].iloc[i]

        # Check if breaks any PRIOR swing high (strict >)
        breaks_high = any(
            swing_idx < i and close > df["high"].iloc[swing_idx]
            for swing_idx in swing_highs
        )

        # Check if breaks any PRIOR swing low (strict <)
        breaks_low = any(
            swing_idx < i and close < df["low"].iloc[swing_idx]
            for swing_idx in swing_lows
        )

        # Apply labeling rules
        if breaks_high and breaks_low:
            # Ambiguous: breaks both directions → volatility/liquidity sweep
            # Leave as None
            pass
        elif breaks_high:
            bos_labels.iloc[i] = "bullish_bos"
            bullish_count += 1
        elif breaks_low:
            bos_labels.iloc[i] = "bearish_bos"
            bearish_count += 1
        # else: remains None

    logger.debug(
        f"Detected {bullish_count} bullish BOS and {bearish_count} bearish BOS "
        f"in {len(df)} bars ({len(swing_highs)} swing highs, {len(swing_lows)} swing lows)"
    )

    return bos_labels

