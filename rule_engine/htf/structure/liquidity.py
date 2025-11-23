"""Liquidity sweep detection.

A sweep is a wick that violates prior liquidity but closes back inside.
Required for fade logic & trend invalidation.

Task: Implement liquidity sweep detection
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

import pandas as pd

from common.logger import get_logger

logger = get_logger(__name__)


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    swing_highs: list[int],
    swing_lows: list[int],
) -> tuple[pd.Series, pd.Series]:
    """Detect liquidity sweep events.

    A liquidity sweep occurs when a candle's wick breaks through a prior swing
    level (taking liquidity) but the close is back inside the range. This often
    indicates a false breakout, stop hunt, or potential reversal setup.

    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        swing_highs: List of integer indices where swing highs occurred
        swing_lows: List of integer indices where swing lows occurred

    Returns:
        Tuple of (sweep_events, sweep_success):
        - sweep_events: Series with sweep labels ("sweep_high", "sweep_low", None)
        - sweep_success: Series indicating if sweep was successful (True/False/None)

    Raises:
        ValueError: If required columns are missing or swing lists are not lists

    Logic:
        - Sweep high: high > prior swing high AND close < prior swing high
        - Sweep low: low < prior swing low AND close > prior swing low
        - Most recent swing only: Check only most recent swing before current bar
        - Ambiguous rejection: If sweeps both high and low → None
        - Success tracking: Based on next bar's close position
          * Successful: Next close continues beyond swept level
          * Failed: Next close stays inside range (reversal/fade opportunity)
          * None: Last bar (no next bar to evaluate)

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 105, 103, 108],
        ...     'low': [98, 102, 100, 103],
        ...     'close': [99, 104, 102, 104]  # Index 3: sweep high
        ... })
        >>> swing_highs, swing_lows = [1], []
        >>> sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        >>> sweep_events.iloc[3]
        'sweep_high'
    """
    # Validate required columns
    required_cols = {"high", "low", "close"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    # Validate swing lists are lists
    if not isinstance(swing_highs, list) or not isinstance(swing_lows, list):
        raise ValueError("swing_highs and swing_lows must be lists")

    # Initialize result Series with None values
    sweep_events = pd.Series(None, index=df.index, dtype="object")
    sweep_success = pd.Series(None, index=df.index, dtype="object")

    # Handle empty DataFrame
    if len(df) == 0:
        return sweep_events, sweep_success

    # Track counts for logging
    sweep_high_count = 0
    sweep_low_count = 0
    success_count = 0
    total_sweeps = 0

    # Iterate through each bar
    for i in range(len(df)):
        # Find most recent swing high before current bar
        prior_swing_high_idx = None
        prior_swing_high_val = None
        for sh_idx in swing_highs:
            if sh_idx < i:  # Must be before current bar
                if prior_swing_high_idx is None or sh_idx > prior_swing_high_idx:
                    prior_swing_high_idx = sh_idx
                    prior_swing_high_val = df["high"].iloc[sh_idx]

        # Find most recent swing low before current bar
        prior_swing_low_idx = None
        prior_swing_low_val = None
        for sl_idx in swing_lows:
            if sl_idx < i:  # Must be before current bar
                if prior_swing_low_idx is None or sl_idx > prior_swing_low_idx:
                    prior_swing_low_idx = sl_idx
                    prior_swing_low_val = df["low"].iloc[sl_idx]

        # Check for sweep high condition
        sweeps_high = False
        if prior_swing_high_val is not None:
            high = df["high"].iloc[i]
            close = df["close"].iloc[i]
            # Sweep high: wick breaks high, but close doesn't (strict inequality)
            if high > prior_swing_high_val and close < prior_swing_high_val:
                sweeps_high = True

        # Check for sweep low condition
        sweeps_low = False
        if prior_swing_low_val is not None:
            low = df["low"].iloc[i]
            close = df["close"].iloc[i]
            # Sweep low: wick breaks low, but close doesn't (strict inequality)
            if low < prior_swing_low_val and close > prior_swing_low_val:
                sweeps_low = True

        # Label sweep events (reject ambiguous cases)
        if sweeps_high and sweeps_low:
            # Ambiguous: sweeps both directions → no label (whipsaw/chop)
            sweep_events.iloc[i] = None
        elif sweeps_high:
            sweep_events.iloc[i] = "sweep_high"
            sweep_high_count += 1
            total_sweeps += 1
        elif sweeps_low:
            sweep_events.iloc[i] = "sweep_low"
            sweep_low_count += 1
            total_sweeps += 1

    # Second pass: Determine success based on next bar's close
    for i in range(len(df)):
        if pd.notna(sweep_events.iloc[i]):
            # Check if there's a next bar
            if i + 1 < len(df):
                next_close = df["close"].iloc[i + 1]

                if sweep_events.iloc[i] == "sweep_high":
                    # Get the most recent swept high value (by index, not value)
                    prior_swing_high_idx = None
                    prior_swing_high_val = None
                    for sh_idx in swing_highs:
                        if sh_idx < i:
                            if prior_swing_high_idx is None or sh_idx > prior_swing_high_idx:
                                prior_swing_high_idx = sh_idx
                                prior_swing_high_val = df["high"].iloc[sh_idx]
                    
                    if prior_swing_high_val is not None:
                        # Success if next close continues beyond swept high
                        if next_close > prior_swing_high_val:
                            sweep_success.iloc[i] = True
                            success_count += 1
                        else:
                            sweep_success.iloc[i] = False

                elif sweep_events.iloc[i] == "sweep_low":
                    # Get the most recent swept low value (by index, not value)
                    prior_swing_low_idx = None
                    prior_swing_low_val = None
                    for sl_idx in swing_lows:
                        if sl_idx < i:
                            if prior_swing_low_idx is None or sl_idx > prior_swing_low_idx:
                                prior_swing_low_idx = sl_idx
                                prior_swing_low_val = df["low"].iloc[sl_idx]
                    
                    if prior_swing_low_val is not None:
                        # Success if next close continues beyond swept low
                        if next_close < prior_swing_low_val:
                            sweep_success.iloc[i] = True
                            success_count += 1
                        else:
                            sweep_success.iloc[i] = False
            else:
                # Last bar - cannot determine success yet
                sweep_success.iloc[i] = None

    logger.debug(
        f"Detected {sweep_high_count} high sweeps and {sweep_low_count} low sweeps "
        f"in {len(df)} bars. Success rate: {success_count}/{total_sweeps}"
    )

    return sweep_events, sweep_success

