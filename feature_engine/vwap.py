"""VWAP (Volume-Weighted Average Price) calculation.

This module provides functionality to calculate VWAP for OHLCV data,
with support for session/day resets.

VWAP Formula:
    VWAP = Σ(Typical Price × Volume) / Σ(Volume)
    where Typical Price = (High + Low + Close) / 3
"""

import numpy as np
import pandas as pd


def calculate_vwap(
    df: pd.DataFrame, session_reset: bool = True, session_column: str = "ts_event"
) -> pd.Series:
    """Calculate Volume-Weighted Average Price (VWAP).

    Args:
        df: DataFrame with OHLCV data. Must contain columns:
            - high: High price
            - low: Low price
            - close: Close price
            - volume: Trading volume
            - ts_event (or custom session_column): Timestamp for session detection
        session_reset: If True, reset VWAP calculation at session boundaries
                      (detected by day changes in session_column).
                      If False, calculate cumulative VWAP across entire dataset.
        session_column: Name of the timestamp column for session detection.
                       Default is "ts_event".

    Returns:
        Series containing VWAP values, indexed same as input DataFrame.

    Raises:
        ValueError: If required columns are missing from DataFrame.
        ValueError: If session_column is not a valid datetime column when
                   session_reset=True.

    Example:
        >>> df = pd.DataFrame({
        ...     'ts_event': pd.date_range('2025-01-01 09:00', periods=3, freq='1min'),
        ...     'high': [101.0, 102.0, 103.0],
        ...     'low': [99.0, 100.0, 101.0],
        ...     'close': [100.5, 101.5, 102.5],
        ...     'volume': [1000, 1500, 2000]
        ... })
        >>> vwap = calculate_vwap(df, session_reset=False)
        >>> print(vwap)
    """
    # Validate required columns
    required_cols = {"high", "low", "close", "volume"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    if session_reset and session_column not in df.columns:
        raise ValueError(
            f"Session column '{session_column}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}"
        )

    # Calculate typical price
    typical_price = (df["high"] + df["low"] + df["close"]) / 3

    # Handle NaN in typical price by forward filling or using close price
    if typical_price.isna().any():
        typical_price = typical_price.fillna(df["close"])

    # Handle zero or NaN volumes by replacing with a small epsilon
    # This prevents division by zero and NaN propagation
    volume = df["volume"].copy()
    volume = volume.fillna(0)
    volume = volume.replace(0, np.finfo(float).eps)

    # Calculate price × volume
    pv = typical_price * volume

    if session_reset:
        # Parse session column to datetime if not already
        if not pd.api.types.is_datetime64_any_dtype(df[session_column]):
            try:
                session_dates = pd.to_datetime(df[session_column])
            except Exception as e:
                raise ValueError(
                    f"Could not parse '{session_column}' as datetime: {e}"
                ) from e
        else:
            session_dates = df[session_column]

        # Extract date to identify session boundaries
        session_groups = session_dates.dt.date

        # Calculate cumulative sums within each session group
        cum_pv = pv.groupby(session_groups).cumsum()
        cum_volume = volume.groupby(session_groups).cumsum()
    else:
        # Calculate cumulative sums across entire dataset
        cum_pv = pv.cumsum()
        cum_volume = volume.cumsum()

    # Calculate VWAP
    vwap = cum_pv / cum_volume

    # Restore original index
    vwap.index = df.index

    return vwap


def calculate_vwap_deviation(
    df: pd.DataFrame, close_column: str = "close", vwap_column: str = "vwap"
) -> pd.Series:
    """Calculate VWAP deviation percentage for fade setup detection.

    Computes the absolute percentage deviation of close price from VWAP.
    Significant deviations indicate potential fade opportunities (counter-trend
    setups when price is far from fair value).

    Args:
        df: DataFrame containing close and vwap columns.
        close_column: Name of the close price column. Default is "close".
        vwap_column: Name of the VWAP column. Default is "vwap".

    Returns:
        Series containing absolute percentage deviation values, indexed same
        as input DataFrame. Formula: abs((close - vwap) / vwap * 100)

    Raises:
        ValueError: If required columns are missing.
        ValueError: If VWAP values are NaN, zero, or negative (division error).

    Example:
        >>> df = pd.DataFrame({
        ...     'close': [2650.0, 2655.0, 2645.0],
        ...     'vwap': [2645.0, 2645.0, 2645.0]
        ... })
        >>> deviation = calculate_vwap_deviation(df)
        >>> print(deviation)
    """
    # Validate required columns
    required_cols = {close_column, vwap_column}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    close = df[close_column]
    vwap = df[vwap_column]

    # Check for NaN, zero, or negative VWAP values
    # Note: NaN <= 0 evaluates to False, so we must check NaN separately
    if vwap.isna().any():
        raise ValueError(
            "VWAP values must be positive. Found NaN values."
        )
    if (vwap <= 0).any():
        raise ValueError(
            "VWAP values must be positive. Found zero or negative values."
        )

    # Calculate percentage deviation: abs((close - vwap) / vwap * 100)
    deviation = abs((close - vwap) / vwap * 100)

    return deviation
