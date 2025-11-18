"""Structure label computation for swing point detection.

This module provides functionality to identify swing highs and lows in price
action and label them as HH (Higher High), HL (Higher Low), LH (Lower High),
or LL (Lower Low) for structure analysis.
"""

import pandas as pd


def calculate_structure_labels(
    df: pd.DataFrame,
    swing_window: int = 5,
    high_column: str = "high",
    low_column: str = "low",
) -> pd.Series:
    """Calculate structure labels (HH/HL/LH/LL) for swing points.

    Identifies swing highs and lows using a rolling window approach, then
    labels them based on their relationship to previous swing points:
    - HH: Higher High (swing high above previous swing high)
    - HL: Higher Low (swing low above previous swing low)
    - LH: Lower High (swing high below previous swing high)
    - LL: Lower Low (swing low below previous swing low)

    Args:
        df: DataFrame with OHLCV data. Must contain high and low columns.
        swing_window: Number of periods to look back/forward to identify
                     swing points. Default is 5.
        high_column: Name of the high price column. Default is "high".
        low_column: Name of the low price column. Default is "low".

    Returns:
        Series containing structure labels indexed same as input DataFrame.
        Values are: "HH", "HL", "LH", "LL", or pd.NA for non-swing points.

    Raises:
        ValueError: If required columns are missing.
        ValueError: If swing_window is less than 2.

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 102, 101, 103, 102, 104],
        ...     'low': [99, 100, 99, 101, 100, 102]
        ... })
        >>> labels = calculate_structure_labels(df, swing_window=2)
        >>> print(labels)
    """
    # Validate inputs
    if swing_window < 2:
        raise ValueError(f"swing_window must be >= 2, got {swing_window}")

    required_cols = {high_column, low_column}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    # Initialize result series with NA values
    labels = pd.Series(index=df.index, dtype="object")

    # Need at least swing_window * 2 + 1 rows to identify swing points
    if len(df) < swing_window * 2 + 1:
        return labels

    # Identify swing highs: local maxima
    # A swing high is a point where high is the maximum in the window
    swing_highs = pd.Series(index=df.index, dtype=bool)
    for i in range(swing_window, len(df) - swing_window):
        idx = df.index[i]
        window_highs = df[high_column].iloc[i - swing_window : i + swing_window + 1]
        if df[high_column].iloc[i] == window_highs.max():
            swing_highs.loc[idx] = True

    # Identify swing lows: local minima
    # A swing low is a point where low is the minimum in the window
    swing_lows = pd.Series(index=df.index, dtype=bool)
    for i in range(swing_window, len(df) - swing_window):
        idx = df.index[i]
        window_lows = df[low_column].iloc[i - swing_window : i + swing_window + 1]
        if df[low_column].iloc[i] == window_lows.min():
            swing_lows.loc[idx] = True

    # Track previous swing high and low values
    prev_swing_high: float | None = None
    prev_swing_low: float | None = None

    # Label swing points
    # Process both highs and lows, prioritizing the one that occurs first
    # If both occur at same index, use the more significant one
    for i in df.index:
        is_swing_high = swing_highs.loc[i]
        is_swing_low = swing_lows.loc[i]

        if is_swing_high:
            current_high = df.loc[i, high_column]
            if prev_swing_high is not None:
                if current_high > prev_swing_high:
                    labels.loc[i] = "HH"
                elif current_high < prev_swing_high:
                    labels.loc[i] = "LH"
                # If equal, keep previous label or use HH as default
                else:
                    labels.loc[i] = "HH"
            else:
                # First swing high - label as HH
                labels.loc[i] = "HH"
            prev_swing_high = current_high

        if is_swing_low:
            current_low = df.loc[i, low_column]
            # Only label if not already labeled by swing high
            if pd.isna(labels.loc[i]):
                if prev_swing_low is not None:
                    if current_low > prev_swing_low:
                        labels.loc[i] = "HL"
                    elif current_low < prev_swing_low:
                        labels.loc[i] = "LL"
                    # If equal, keep previous label or use HL as default
                    else:
                        labels.loc[i] = "HL"
                else:
                    # First swing low - label as HL
                    labels.loc[i] = "HL"
            prev_swing_low = current_low

    return labels

