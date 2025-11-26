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

    CRITICAL: Labels are delayed by swing_window bars to prevent lookahead bias.
    When a swing point is detected at position i, its label appears at position
    i + swing_window. This matches the incremental StructureState behavior.

    Args:
        df: DataFrame with OHLCV data. Must contain high and low columns.
        swing_window: Number of periods to look back/forward to identify
                     swing points. Labels are delayed by this many bars.
                     Default is 5.
        high_column: Name of the high price column. Default is "high".
        low_column: Name of the low price column. Default is "low".

    Returns:
        Series containing structure labels indexed same as input DataFrame.
        Values are: "HH", "HL", "LH", "LL", or pd.NA for non-swing points.
        - First swing_window * 2 positions: pd.NA (warmup period)
        - Last swing_window positions: pd.NA (not enough future confirmation)
        - Labels appear swing_window bars after swing point detection

    Raises:
        ValueError: If required columns are missing.
        ValueError: If swing_window is less than 2.

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 102, 101, 103, 102, 104],
        ...     'low': [99, 100, 99, 101, 100, 102]
        ... })
        >>> labels = calculate_structure_labels(df, swing_window=2)
        >>> # Swing detected at position i appears at position i + 2
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

    # Identify swing highs and lows, then delay labels by swing_window bars
    # to prevent lookahead bias. Labels appear swing_window bars after the
    # swing point is confirmed, matching the incremental StructureState behavior.
    
    # Track detected swing points and their labels (before delay)
    # Format: (swing_detection_idx, label, value)
    # The label will be assigned to position swing_detection_idx + swing_window
    swing_detections: list[tuple[int, str, float]] = []
    
    # Track previous swing high and low values
    prev_swing_high: float | None = None
    prev_swing_low: float | None = None
    
    # Detect swing points and determine their labels
    # We iterate through positions where we can detect swings AND where the delayed
    # label will not exceed the valid range (last swing_window positions must be None).
    # For position i, we check if it's a swing point using window [i-swing_window : i+swing_window+1]
    # The delayed label appears at position i + swing_window, which must be < len(df) - swing_window
    # Therefore: i + swing_window < len(df) - swing_window → i < len(df) - 2*swing_window
    for i in range(swing_window, len(df) - 2 * swing_window):
        idx = df.index[i]
        center_high = df.loc[idx, high_column]
        center_low = df.loc[idx, low_column]
        
        # Check if center point is a swing high (local maximum)
        # Use >= to match StructureState logic (all other values <= center)
        window_highs = df[high_column].iloc[i - swing_window : i + swing_window + 1]
        is_swing_high = all(
            center_high >= window_highs.iloc[j]
            for j in range(len(window_highs))
            if j != swing_window
        )
        
        # Check if center point is a swing low (local minimum)
        # Use <= to match StructureState logic (all other values >= center)
        window_lows = df[low_column].iloc[i - swing_window : i + swing_window + 1]
        is_swing_low = all(
            center_low <= window_lows.iloc[j]
            for j in range(len(window_lows))
            if j != swing_window
        )
        
        label: str | None = None
        
        # Process swing high (takes priority over swing low)
        if is_swing_high:
            if prev_swing_high is not None:
                if center_high > prev_swing_high:
                    label = "HH"
                elif center_high < prev_swing_high:
                    label = "LH"
                else:
                    label = "HH"  # Equal - default to HH
            else:
                # First swing high - label as HH
                label = "HH"
            prev_swing_high = center_high
            
            # Store detection: will assign label at position i + swing_window
            if label:
                swing_detections.append((i, label, center_high))
        
        # Process swing low (only if not already processed as swing high)
        elif is_swing_low:
            if prev_swing_low is not None:
                if center_low > prev_swing_low:
                    label = "HL"
                elif center_low < prev_swing_low:
                    label = "LL"
                else:
                    label = "HL"  # Equal - default to HL
            else:
                # First swing low - label as HL
                label = "HL"
            prev_swing_low = center_low
            
            # Store detection: will assign label at position i + swing_window
            if label:
                swing_detections.append((i, label, center_low))
    
    # Assign labels with delay: label detected at position i appears at position i + swing_window
    # This matches StructureState behavior where update() at position i returns label for
    # swing detected at position i - swing_window
    for swing_idx, label, _ in swing_detections:
        delayed_idx = swing_idx + swing_window
        # Ensure delayed labels don't exceed len(df) - swing_window - 1
        # (last swing_window positions must remain None per zero-lookahead guarantee)
        if delayed_idx < len(df) - swing_window:
            # Only assign if not already assigned (swing high takes priority over swing low)
            if pd.isna(labels.iloc[delayed_idx]):
                labels.iloc[delayed_idx] = label

    return labels

