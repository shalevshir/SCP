"""RSI (Relative Strength Index) calculation.

This module provides functionality to calculate RSI using Wilder's smoothing method,
which is the industry-standard approach used by most trading platforms.

RSI Formula:
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss

Wilder's Smoothing:
    First average = Simple moving average of period
    Subsequent averages = (Previous Average × (period-1) + Current Value) / period
"""

import numpy as np
import pandas as pd


def calculate_rsi(
    df: pd.DataFrame, period: int = 14, price_column: str = "close"
) -> pd.Series:
    """Calculate Relative Strength Index (RSI) using Wilder's smoothing method.

    Args:
        df: DataFrame with price data. Must contain the specified price column.
        period: Number of periods for RSI calculation. Default is 14
               (industry standard). Must be >= 2.
        price_column: Name of the column containing price data.
                     Default is "close".

    Returns:
        Series containing RSI values (0-100 scale), indexed same as input
        DataFrame. First 'period' values will be NaN as they are part of
        the initial calculation window.

    Raises:
        ValueError: If period < 2
        ValueError: If price_column is not found in DataFrame

    Example:
        >>> df = pd.DataFrame({
        ...     'close': [44.0, 44.5, 44.3, 44.8, 45.2, 45.0, 45.5, 46.0,
        ...               45.8, 46.5, 47.0, 46.8, 47.5, 48.0, 48.5]
        ... })
        >>> rsi = calculate_rsi(df, period=14)
        >>> print(rsi.iloc[14])  # First valid RSI after initial window

    Notes:
        - Uses Wilder's smoothing (alpha = 1/period) for average gain/loss
        - Returns NaN for first 'period' rows (initial calculation window)
        - RSI ranges from 0 (oversold) to 100 (overbought)
        - Traditional interpretation: RSI > 70 = overbought, RSI < 30 = oversold
        - All gains (no losses) produces RSI = 100
        - All losses (no gains) produces RSI = 0
    """
    # Validate inputs
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")

    if price_column not in df.columns:
        raise ValueError(
            f"Column '{price_column}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}"
        )

    # Extract price series
    prices = df[price_column].copy()

    # Calculate price changes (deltas)
    delta = prices.diff()

    # Separate gains and losses
    gains = delta.clip(lower=0)  # Positive changes only
    losses = -delta.clip(upper=0)  # Negative changes (made positive)

    # Initialize result series with NaN
    rsi = pd.Series(index=df.index, dtype=np.float64)

    # Not enough data to calculate RSI
    if len(prices) < period + 1:
        return rsi

    # Calculate initial averages using Simple Moving Average for first period
    # We need period values after the first diff (which loses one value)
    # So the first RSI is at index 'period' (0-indexed)
    first_avg_gain = gains.iloc[1 : period + 1].mean()
    first_avg_loss = losses.iloc[1 : period + 1].mean()

    # Initialize tracking variables for Wilder's smoothing
    avg_gain = first_avg_gain
    avg_loss = first_avg_loss

    # Calculate first RSI value
    if avg_loss == 0:
        rsi.iloc[period] = 100.0 if avg_gain > 0 else 50.0
    else:
        rs = avg_gain / avg_loss
        rsi.iloc[period] = 100.0 - (100.0 / (1.0 + rs))

    # Apply Wilder's smoothing for subsequent values
    # Wilder's formula: new_avg = (prev_avg * (period-1) + current_value) / period
    for i in range(period + 1, len(prices)):
        avg_gain = (avg_gain * (period - 1) + gains.iloc[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses.iloc[i]) / period

        # Calculate RSI
        if avg_loss == 0:
            rsi.iloc[i] = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi.iloc[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi
