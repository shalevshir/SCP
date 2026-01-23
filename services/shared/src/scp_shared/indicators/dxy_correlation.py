"""
DXY Correlation calculation module.

This module provides functions to compute rolling Pearson correlation between
Gold (GC) and Dollar Index (DXY) closing prices for trend analysis.

Gold and Dollar typically have negative correlation: when the dollar strengthens,
gold prices tend to fall, and vice versa. This correlation is used in SOP for
market environment scoring.
"""

import pandas as pd


def calculate_dxy_correlation(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    window: int = 50,
    gc_price_column: str = "close",
    dxy_price_column: str = "close",
    timestamp_column: str = "ts_event",
) -> pd.Series:
    """Calculate rolling Pearson correlation between GC and DXY closing prices.

    Computes the rolling correlation coefficient between Gold (GC) and Dollar
    Index (DXY) prices over a specified window. Gold and Dollar typically have
    negative correlation (< -0.6 on inverse segments), which is used in SOP
    for market environment analysis.

    Args:
        gc_df: DataFrame containing Gold (GC) price data.
               Must contain timestamp_column and gc_price_column.
        dxy_df: DataFrame containing Dollar Index (DXY) price data.
                Must contain timestamp_column and dxy_price_column.
        window: Number of periods for rolling correlation calculation.
               Default is 50 (per SOP requirements).
               Must be >= 2.
        gc_price_column: Name of the column containing GC prices.
                        Default is "close".
        dxy_price_column: Name of the column containing DXY prices.
                         Default is "close".
        timestamp_column: Name of the column containing timestamps.
                         Default is "ts_event".
                         Used for inner join alignment.

    Returns:
        Series containing rolling correlation values, indexed by aligned
        timestamps. First (window-1) values will be NaN as they are part of
        the initial calculation window.

        Correlation values range from -1.0 to +1.0:
        - -1.0: Perfect negative correlation (GC up, DXY down)
        - 0.0: No correlation
        - +1.0: Perfect positive correlation (GC and DXY move together)
        - < -0.6: Strong negative correlation (typical GC-DXY relationship)

    Raises:
        ValueError: If window < 2
        ValueError: If required columns are missing in either DataFrame
        ValueError: If timestamp_column cannot be parsed as datetime

    Examples:
        >>> import pandas as pd
        >>> from feature_engine import calculate_dxy_correlation
        >>> gc_df = pd.DataFrame({
        ...     'ts_event': pd.to_datetime(['2025-01-01 09:00', '2025-01-01 09:01']),
        ...     'close': [2000.0, 2001.0]
        ... })
        >>> dxy_df = pd.DataFrame({
        ...     'ts_event': pd.to_datetime(['2025-01-01 09:00', '2025-01-01 09:01']),
        ...     'close': [100.0, 99.9]
        ... })
        >>> corr = calculate_dxy_correlation(gc_df, dxy_df, window=50)
        >>> print(corr)

    Notes:
        - Uses inner join on timestamp (only overlapping timestamps included)
        - Handles alignment mismatches safely (missing data excluded)
        - Uses pandas .rolling().corr() for Pearson correlation
        - Suitable for 1m and 15m timeframes (per DoD)
        - Typical GC-DXY correlation: < -0.6 on inverse segments

    Trading Use Cases:
        - Market environment scoring in SOP
        - Confirmation of trend direction
        - Risk assessment (strong negative correlation = predictable relationship)
    """
    # Validate window
    if window < 2:
        raise ValueError(f"window must be >= 2, got {window}")

    # Validate required columns in GC DataFrame
    if timestamp_column not in gc_df.columns:
        raise ValueError(f"Column '{timestamp_column}' not found in GC DataFrame")
    if gc_price_column not in gc_df.columns:
        raise ValueError(f"Column '{gc_price_column}' not found in GC DataFrame")

    # Validate required columns in DXY DataFrame
    if timestamp_column not in dxy_df.columns:
        raise ValueError(f"Column '{timestamp_column}' not found in DXY DataFrame")
    if dxy_price_column not in dxy_df.columns:
        raise ValueError(f"Column '{dxy_price_column}' not found in DXY DataFrame")

    # Ensure timestamp column is datetime
    gc_df = gc_df.copy()
    dxy_df = dxy_df.copy()

    if not pd.api.types.is_datetime64_any_dtype(gc_df[timestamp_column]):
        try:
            # Use utc=True to handle tz-aware datetime objects from streaming buffers
            gc_df[timestamp_column] = pd.to_datetime(gc_df[timestamp_column], utc=True)
        except Exception as e:
            raise ValueError(
                f"Could not parse '{timestamp_column}' as datetime in GC DataFrame: {e}"
            ) from e

    if not pd.api.types.is_datetime64_any_dtype(dxy_df[timestamp_column]):
        try:
            # Use utc=True to handle tz-aware datetime objects from streaming buffers
            dxy_df[timestamp_column] = pd.to_datetime(
                dxy_df[timestamp_column], utc=True
            )
        except Exception as e:
            raise ValueError(
                f"Could not parse '{timestamp_column}' as datetime "
                f"in DXY DataFrame: {e}"
            ) from e

    # Select only required columns for merge
    gc_selected = gc_df[[timestamp_column, gc_price_column]].copy()
    gc_selected = gc_selected.rename(columns={gc_price_column: "gc_price"})

    dxy_selected = dxy_df[[timestamp_column, dxy_price_column]].copy()
    dxy_selected = dxy_selected.rename(columns={dxy_price_column: "dxy_price"})

    # Inner join on timestamp (handles alignment mismatches safely)
    # Only rows with matching timestamps are included
    merged = pd.merge(
        gc_selected,
        dxy_selected,
        on=timestamp_column,
        how="inner",
        sort=True,
    )

    # If no overlapping timestamps, return empty Series
    if len(merged) == 0:
        return pd.Series(dtype=float, name="dxy_correlation")

    # Set timestamp as index for rolling calculation
    merged = merged.set_index(timestamp_column)

    # Calculate rolling Pearson correlation
    # Use DataFrame rolling to compute correlation matrix
    rolling_corr = merged[["gc_price", "dxy_price"]].rolling(window=window).corr()

    # Extract correlation between gc_price and dxy_price
    # The correlation matrix has MultiIndex: (timestamp, column_name)
    # We want the correlation of gc_price with dxy_price (off-diagonal element)
    correlation = (
        rolling_corr.loc[(slice(None), "gc_price"), "dxy_price"]
        .droplevel(1)
        .reindex(merged.index)
    )

    # Return as Series with original index
    return correlation.rename("dxy_correlation")


def calculate_multiwindow_dxy_correlation(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    weights: dict[str, float] | None = None,
    gc_price_column: str = "close",
    dxy_price_column: str = "close",
    timestamp_column: str = "ts_event",
) -> pd.DataFrame:
    """Calculate multi-window DXY correlation with weighted scoring.

    Computes rolling correlation between Gold (GC) and Dollar Index (DXY)
    across three timeframes (15min, 30min, 60min) and produces a weighted
    composite score. This provides more robust correlation analysis than
    single-window correlation by capturing both short-term and longer-term
    relationships.

    Args:
        gc_df: DataFrame containing Gold (GC) price data.
               Must contain timestamp_column and gc_price_column.
        dxy_df: DataFrame containing Dollar Index (DXY) price data.
                Must contain timestamp_column and dxy_price_column.
        weights: Dictionary with weights for each window.
                Keys: '15min', '30min', '60min'.
                Must sum to 1.0.
                Default: {'15min': 0.5, '30min': 0.3, '60min': 0.2}
                (prioritizes shorter-term correlation).
        gc_price_column: Name of the column containing GC prices.
                        Default is "close".
        dxy_price_column: Name of the column containing DXY prices.
                         Default is "close".
        timestamp_column: Name of the column containing timestamps.
                         Default is "ts_event".
                         Used for inner join alignment.

    Returns:
        DataFrame with columns:
        - corr_15min: 15-minute rolling correlation
        - corr_30min: 30-minute rolling correlation
        - corr_60min: 60-minute rolling correlation
        - weighted_score: Weighted average of all three windows

        Index is timestamps from aligned data.
        Values are NaN until sufficient data for each window.

    Raises:
        ValueError: If weights don't sum to 1.0
        ValueError: If required columns are missing in either DataFrame
        ValueError: If timestamp_column cannot be parsed as datetime

    Examples:
        >>> import pandas as pd
        >>> from feature_engine import calculate_multiwindow_dxy_correlation
        >>> gc_df = pd.DataFrame({
        ...     'ts_event': pd.date_range('2025-01-01 09:00', periods=100, freq='1min'),
        ...     'close': [2000.0 + i * 0.1 for i in range(100)]
        ... })
        >>> dxy_df = pd.DataFrame({
        ...     'ts_event': pd.date_range('2025-01-01 09:00', periods=100, freq='1min'),
        ...     'close': [100.0 - i * 0.01 for i in range(100)]
        ... })
        >>> result = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)
        >>> print(result.columns)
        Index(['corr_15min', 'corr_30min', 'corr_60min', 'weighted_score'],
              dtype='object')

    Notes:
        - Weighted score only computed when all windows have valid data (60+ periods)
        - Default weights favor shorter timeframes (recent correlation)
        - Uses Pearson correlation for all windows
        - Handles alignment mismatches safely (inner join on timestamps)
        - Strong inverse correlation threshold: < -0.6 (per SOP)

    Trading Use Cases:
        - Robust market environment scoring across multiple timeframes
        - Smoother correlation signal (less noise than single window)
        - Early detection of correlation regime changes
    """
    # Default weights: favor shorter-term correlation
    if weights is None:
        weights = {
            "15min": 0.5,
            "30min": 0.3,
            "60min": 0.2,
        }

    # Validate weights
    weight_sum = sum(weights.values())
    if not (0.99 <= weight_sum <= 1.01):  # Allow small floating point tolerance
        raise ValueError(
            f"Weights must sum to 1.0, got {weight_sum}. " f"Weights: {weights}"
        )

    # Validate required keys
    required_keys = {"15min", "30min", "60min"}
    provided_keys = set(weights.keys())
    if provided_keys != required_keys:
        missing = required_keys - provided_keys
        extra = provided_keys - required_keys
        error_parts = []
        if missing:
            error_parts.append(f"missing keys: {missing}")
        if extra:
            error_parts.append(f"unexpected keys: {extra}")
        raise ValueError(
            f"Weights must contain exactly keys {required_keys}. "
            f"Got {provided_keys}. {', '.join(error_parts)}"
        )

    # Validate required columns (reuse single-window validation logic)
    if timestamp_column not in gc_df.columns:
        raise ValueError(f"Column '{timestamp_column}' not found in GC DataFrame")
    if gc_price_column not in gc_df.columns:
        raise ValueError(f"Column '{gc_price_column}' not found in GC DataFrame")
    if timestamp_column not in dxy_df.columns:
        raise ValueError(f"Column '{timestamp_column}' not found in DXY DataFrame")
    if dxy_price_column not in dxy_df.columns:
        raise ValueError(f"Column '{dxy_price_column}' not found in DXY DataFrame")

    # Calculate correlation for each window
    corr_15min = calculate_dxy_correlation(
        gc_df,
        dxy_df,
        window=15,
        gc_price_column=gc_price_column,
        dxy_price_column=dxy_price_column,
        timestamp_column=timestamp_column,
    )

    corr_30min = calculate_dxy_correlation(
        gc_df,
        dxy_df,
        window=30,
        gc_price_column=gc_price_column,
        dxy_price_column=dxy_price_column,
        timestamp_column=timestamp_column,
    )

    corr_60min = calculate_dxy_correlation(
        gc_df,
        dxy_df,
        window=60,
        gc_price_column=gc_price_column,
        dxy_price_column=dxy_price_column,
        timestamp_column=timestamp_column,
    )

    # If no overlapping timestamps, return empty DataFrame with DatetimeIndex
    if len(corr_15min) == 0:
        return pd.DataFrame(
            columns=["corr_15min", "corr_30min", "corr_60min", "weighted_score"],
            index=pd.DatetimeIndex([]),  # Explicitly create empty DatetimeIndex
        )

    # Combine into single DataFrame
    result = pd.DataFrame(
        {
            "corr_15min": corr_15min,
            "corr_30min": corr_30min,
            "corr_60min": corr_60min,
        }
    )

    # Calculate weighted score
    # Only compute where all three windows have valid data
    result["weighted_score"] = (
        result["corr_15min"] * weights["15min"]
        + result["corr_30min"] * weights["30min"]
        + result["corr_60min"] * weights["60min"]
    )

    return result
