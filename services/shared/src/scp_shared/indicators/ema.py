"""
Exponential Moving Average (EMA) calculation module.

This module provides functions to compute EMA for a given DataFrame,
with support for multiple periods and custom price columns.

EMA Formula:
    EMA = Price × α + EMA_prev × (1 - α)
    where α = 2 / (period + 1)
"""

import pandas as pd


def calculate_ema(
    df: pd.DataFrame, period: int = 20, price_column: str = "close"
) -> pd.Series:
    """Calculate Exponential Moving Average (EMA) using pandas .ewm() method.

    EMA gives more weight to recent prices, making it more responsive to
    price changes than Simple Moving Average (SMA). It's commonly used
    for trend identification and trading signals.

    Args:
        df: DataFrame with price data. Must contain the specified price column.
        period: Number of periods for EMA calculation. Default is 20 (medium-term).
               Common values: 9 (fast), 20 (medium), 50 (slow).
               Must be >= 1.
        price_column: Name of the column containing price data.
                     Default is "close".

    Returns:
        Series containing EMA values, indexed same as input DataFrame.
        First value equals the first price (seed value).
        No NaN values in output.

    Raises:
        ValueError: If period < 1
        ValueError: If price_column is not found in DataFrame

    Examples:
        >>> import pandas as pd
        >>> from feature_engine import calculate_ema
        >>> df = pd.DataFrame({
        ...     'close': [22.27, 22.19, 22.08, 22.17, 22.18, 22.13]
        ... })
        >>> df['ema_10'] = calculate_ema(df, period=10)
        >>> df['ema_20'] = calculate_ema(df, period=20)
        >>> print(df)

    Notes:
        - Uses pandas .ewm(span=period, adjust=False).mean()
        - adjust=False gives standard EMA formula (matches TA-Lib)
        - Alpha (smoothing factor) = 2 / (period + 1)
        - Fully vectorized, no Python loops
        - More responsive than SMA to recent price changes
        - Used in SOP for trend identification (9, 20, 50 periods)
    """
    # Validate period
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    # Validate price column exists
    if price_column not in df.columns:
        raise ValueError(f"Column '{price_column}' not found in DataFrame")

    # Extract price series
    prices = df[price_column]

    # Calculate EMA using pandas exponential weighted mean
    # span=period is equivalent to alpha = 2/(period+1)
    # adjust=False gives the standard EMA formula matching TA-Lib
    ema = prices.ewm(span=period, adjust=False).mean()

    return ema


def calculate_ema_multiple(
    df: pd.DataFrame, periods: list[int] = None, price_column: str = "close"
) -> pd.DataFrame:
    """Calculate multiple EMAs at once for SOP trend analysis.

    Convenience function to calculate several EMA periods simultaneously.
    Useful for analyzing trend alignment and generating crossover signals.

    Args:
        df: DataFrame with price data. Must contain the specified price column.
        periods: List of periods to calculate. Default is [9, 20, 50] (SOP periods).
                - 9: Fast EMA (short-term trend)
                - 20: Medium EMA (intermediate trend)
                - 50: Slow EMA (long-term trend)
        price_column: Name of the column containing price data.
                     Default is "close".

    Returns:
        DataFrame with EMA columns named 'ema_{period}' for each period.
        Has same index as input DataFrame.
        Example columns: 'ema_9', 'ema_20', 'ema_50'

    Examples:
        >>> import pandas as pd
        >>> from feature_engine import calculate_ema_multiple
        >>> df = pd.DataFrame({
        ...     'close': [100 + i for i in range(100)]
        ... })
        >>> emas = calculate_ema_multiple(df, periods=[9, 20, 50])
        >>> print(emas.columns)
        Index(['ema_9', 'ema_20', 'ema_50'], dtype='object')

        >>> # Detect bullish alignment (fast > medium > slow)
        >>> bullish = (
        ...     (emas['ema_9'] > emas['ema_20']) &
        ...     (emas['ema_20'] > emas['ema_50'])
        ... )

    Trading Use Cases:
        - Trend alignment: All EMAs trending in same direction
        - Crossovers: Fast EMA crosses above slow EMA = bullish signal
        - Support/Resistance: EMAs act as dynamic support in uptrend
        - Divergence: Price and EMA moving in opposite directions
    """
    if periods is None:
        periods = [9, 20, 50]  # Default SOP periods

    result = pd.DataFrame(index=df.index)

    for period in periods:
        ema = calculate_ema(df, period=period, price_column=price_column)
        result[f"ema_{period}"] = ema

    return result
