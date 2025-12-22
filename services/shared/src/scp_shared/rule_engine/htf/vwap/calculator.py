"""HTF VWAP calculation.

Compute VWAP on 1H timeframe and validate trend alignment vs price.

Task: Add HTF VWAP calculation
Epic: Full HTF Bias Engine Upgrade
"""

from __future__ import annotations

import pandas as pd
from scp_shared.common.logger import get_logger
from scp_shared.indicators.vwap import calculate_vwap

logger = get_logger(__name__)


def calculate_htf_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate 1H VWAP and related metrics.

    Uses the existing VWAP calculation from feature_engine and adds
    derived metrics useful for HTF bias analysis: distance from VWAP
    and VWAP slope (rate of change).

    Args:
        df: DataFrame with OHLCV data. Must contain columns:
            - ts_event: Timestamp for each bar
            - high: High price
            - low: Low price
            - close: Close price
            - volume: Trading volume

    Returns:
        DataFrame with original columns plus:
            - vwap: Volume-weighted average price
            - vwap_distance: Price distance from VWAP (close - vwap)
                Positive = price above VWAP, Negative = price below VWAP
            - vwap_slope: VWAP rate of change (vwap[i] - vwap[i-1])
                First value is NaN (no prior bar)

    Raises:
        ValueError: If DataFrame is empty
        ValueError: If required columns are missing

    Example:
        >>> df_1h = load_gold_data(timeframe='1h')
        >>> df_1h = calculate_htf_vwap(df_1h)
        >>> print(df_1h[['close', 'vwap', 'vwap_distance', 'vwap_slope']].tail())

    Notes:
        - VWAP resets at daily session boundaries (session_reset=True)
        - Typical price used: (high + low + close) / 3
        - Zero volume bars are handled with epsilon to prevent division errors
        - NaN values in price columns are forward-filled where possible
    """
    # Validate input
    if df.empty:
        raise ValueError("DataFrame is empty")

    required_cols = {"ts_event", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Create a copy to avoid modifying original
    result = df.copy()

    # Calculate VWAP using existing feature_engine function
    # This handles session reset, zero volume, NaN values, etc.
    result["vwap"] = calculate_vwap(result, session_reset=True)

    # Calculate vwap_distance: close - vwap
    # Positive when price is above VWAP (bullish)
    # Negative when price is below VWAP (bearish)
    result["vwap_distance"] = result["close"] - result["vwap"]

    # Calculate vwap_slope: rate of change of VWAP
    # Indicates whether VWAP is trending up or down
    result["vwap_slope"] = result["vwap"].diff()

    return result
