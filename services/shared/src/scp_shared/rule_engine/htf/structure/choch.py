"""Change of Character (CHoCH) detection.

Change-of-character occurs when the market breaks the opposite side first.
Used to flip trend from bullish ↔ bearish.

Task: Implement CHoCH detection
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

import pandas as pd
from scp_shared.common.logger import get_logger

logger = get_logger(__name__)


def detect_choch(
    df: pd.DataFrame,
    swing_highs: list[int],
    swing_lows: list[int],
) -> pd.Series:
    """Detect Change of Character (CHoCH) events.

    CHoCH signals potential trend reversals when price breaks the opposite swing
    direction from the current trend. Tracks internal trend state to identify
    when the market character changes.

    Args:
        df: DataFrame with OHLC data (must have 'close', 'high', 'low' columns)
        swing_highs: List of integer indices where swing highs occurred
        swing_lows: List of integer indices where swing lows occurred

    Returns:
        Series with CHoCH labels indexed to match df.index:
        - "bullish_choch": Bearish trend breaks prior swing high (reversal to bullish)
        - "bearish_choch": Bullish trend breaks prior swing low (reversal to bearish)
        - None: No CHoCH, or first break establishing initial trend

    Raises:
        ValueError: If required columns are missing

    Logic:
        - Tracks current trend state internally (bullish/bearish/neutral)
        - Bullish CHoCH: In bearish trend, close > prior swing high (strict >)
        - Bearish CHoCH: In bullish trend, close < prior swing low (strict <)
        - First break: Establishes initial trend direction, not CHoCH
        - Ambiguous: If close breaks both directions → None
        - Equality: close == swing level does NOT count as CHoCH

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 98, 96, 94, 92, 90, 88, 86, 102],
        ...     'low': [98, 96, 94, 92, 90, 88, 86, 84, 99],
        ...     'close': [99, 97, 95, 93, 91, 89, 87, 85, 101]
        ... })
        >>> swing_highs = [0]  # Swing high at index 0 (high=100)
        >>> swing_lows = [7]   # Swing low at index 7 (low=84)
        >>> choch = detect_choch(df, swing_highs, swing_lows)
        >>> choch.iloc[8]  # close=101 > 100 while in bearish trend
        'bullish_choch'
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
    choch_labels = pd.Series(None, index=df.index, dtype="object")

    # Handle empty DataFrame
    if len(df) == 0:
        return choch_labels

    # Handle empty swing lists
    if not swing_highs and not swing_lows:
        return choch_labels

    # Track current trend state
    current_trend = "neutral"  # Start with no established trend

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

        # Handle ambiguous cases first (breaks both directions)
        if breaks_high and breaks_low:
            # Ambiguous: breaks both → no label
            pass

        # CHoCH logic: breaking OPPOSITE direction from current trend
        elif current_trend == "bearish" and breaks_high:
            # In downtrend, broke a high → CHoCH (reversal to bullish)
            choch_labels.iloc[i] = "bullish_choch"
            current_trend = "bullish"  # Update trend
            bullish_count += 1

        elif current_trend == "bullish" and breaks_low:
            # In uptrend, broke a low → CHoCH (reversal to bearish)
            choch_labels.iloc[i] = "bearish_choch"
            current_trend = "bearish"  # Update trend
            bearish_count += 1

        # First break from neutral: establishes initial trend (not CHoCH)
        elif current_trend == "neutral":
            if breaks_high:
                current_trend = "bullish"  # Establish bullish trend
            elif breaks_low:
                current_trend = "bearish"  # Establish bearish trend

        # else: Same direction break (BOS) or no break → no CHoCH label

    logger.debug(
        f"Detected {bullish_count} bullish CHoCH and {bearish_count} bearish CHoCH "
        f"in {len(df)} bars ({len(swing_highs)} swing highs, {len(swing_lows)} swing lows)"
    )

    return choch_labels
