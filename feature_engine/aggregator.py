"""
Feature Engine Aggregator module.

This module provides the aggregate_features() function that combines all
technical indicators (VWAP, RSI, EMA, DXY correlation) into a unified
DataFrame with modular configuration.
"""

import pandas as pd

from feature_engine.dxy_correlation import calculate_dxy_correlation
from feature_engine.ema import calculate_ema_multiple
from feature_engine.rsi import calculate_rsi
from feature_engine.vwap import calculate_vwap

# SOP-defined allowed timeframes for validation
ALLOWED_TIMEFRAMES = ["1s", "1m", "15m", "1h"]

# Default indicator configuration (SOP standard parameters)
DEFAULT_INDICATORS = {
    "vwap": {"session_reset": True},
    "rsi": {"period": 14},
    "ema": {"periods": [9, 20, 50]},
    "dxy_correlation": {"window": 50},
}


def aggregate_features(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    indicators: dict | None = None,
) -> pd.DataFrame:
    """Aggregate all technical indicators into a unified DataFrame.

    Combines VWAP, RSI, EMA, and DXY correlation indicators with modular
    configuration. Allows flexible selection of indicators and customization
    of their parameters.

    Args:
        gc_df: DataFrame containing Gold (GC) OHLCV data.
               Must have columns: open, high, low, close, volume.
        dxy_df: DataFrame containing DXY (Dollar Index) price data.
                Must have columns: close, ts_event.
        timeframe: Target timeframe for validation. Must be one of:
                   ["1s", "1m", "15m", "1h"].
        indicators: Optional dictionary to configure which indicators to calculate.
                    If None, all indicators are calculated with default parameters.
                    
                    Configuration options:
                    - Set to False or None to skip: {"rsi": False}
                    - Set to True for defaults: {"rsi": True}
                    - Set to dict for custom params: {"rsi": {"period": 21}}
                    
                    Default configuration (when indicators=None):
                    {
                        "vwap": {"session_reset": True},
                        "rsi": {"period": 14},
                        "ema": {"periods": [9, 20, 50]},
                        "dxy_correlation": {"window": 50}
                    }

    Returns:
        DataFrame containing all original GC columns plus requested feature
        columns. Feature columns added:
        - vwap: Volume-Weighted Average Price
        - rsi: Relative Strength Index
        - ema_9, ema_20, ema_50: Exponential Moving Averages
        - dxy_corr: Rolling Pearson correlation with DXY

    Raises:
        ValueError: If timeframe is not in ALLOWED_TIMEFRAMES.
        ValueError: If required GC columns are missing.
        TypeError: If inputs are not pandas DataFrames.
        DataSourceError: If GC/DXY alignment fails (propagated from
                        calculate_dxy_correlation).

    Examples:
        >>> import pandas as pd
        >>> from feature_engine.aggregator import aggregate_features
        >>> 
        >>> # Load data
        >>> gc_df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv',
        ...                      parse_dates=['ts_event'])
        >>> dxy_df = pd.read_csv('data/gc_dx_ohlcv/DX_ohlcv-1m.csv',
        ...                       parse_dates=['ts_event'])
        >>> 
        >>> # All indicators with defaults
        >>> features = aggregate_features(gc_df, dxy_df, "1m")
        >>> print(features.columns)
        Index(['ts_event', 'open', 'high', 'low', 'close', 'volume',
               'vwap', 'rsi', 'ema_9', 'ema_20', 'ema_50', 'dxy_corr'])
        >>> 
        >>> # Custom configuration: skip VWAP, use RSI(21)
        >>> custom_indicators = {
        ...     "vwap": False,
        ...     "rsi": {"period": 21},
        ...     "ema": True,  # Use defaults
        ...     "dxy_correlation": None  # Skip
        ... }
        >>> features = aggregate_features(gc_df, dxy_df, "1m",
        ...                               indicators=custom_indicators)
        >>> print(features.columns)
        Index(['ts_event', 'open', 'high', 'low', 'close', 'volume',
               'rsi', 'ema_9', 'ema_20', 'ema_50'])

    Notes:
        - All feature columns are numeric (float64) dtype
        - NaN values may appear in warmup periods (expected behavior)
        - Original GC DataFrame index is preserved
        - Returns a copy, not a reference to input DataFrame
    """
    # Validate inputs
    if not isinstance(gc_df, pd.DataFrame):
        raise TypeError("gc_df must be a pandas DataFrame.")
    if not isinstance(dxy_df, pd.DataFrame):
        raise TypeError("dxy_df must be a pandas DataFrame.")

    # Validate timeframe
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise ValueError(
            f"Invalid timeframe: '{timeframe}'. "
            f"Must be one of {ALLOWED_TIMEFRAMES}."
        )

    # Validate required GC columns
    required_gc_cols = ["open", "high", "low", "close", "volume"]
    missing_cols = [col for col in required_gc_cols if col not in gc_df.columns]
    if missing_cols:
        raise ValueError(
            f"GC DataFrame missing required columns: {missing_cols}. "
            f"Required columns: {required_gc_cols}."
        )

    # Use default indicators if none provided
    if indicators is None:
        indicators = DEFAULT_INDICATORS.copy()

    # Start with a copy of GC DataFrame
    result = gc_df.copy()

    # Calculate VWAP if requested
    vwap_config = indicators.get("vwap", True)
    if vwap_config is not False and vwap_config is not None:
        if isinstance(vwap_config, dict):
            params = vwap_config
        else:
            params = DEFAULT_INDICATORS["vwap"]
        result["vwap"] = calculate_vwap(gc_df, **params)

    # Calculate RSI if requested
    rsi_config = indicators.get("rsi", True)
    if rsi_config is not False and rsi_config is not None:
        if isinstance(rsi_config, dict):
            params = rsi_config
        else:
            params = DEFAULT_INDICATORS["rsi"]
        result["rsi"] = calculate_rsi(gc_df, **params)

    # Calculate EMA if requested
    ema_config = indicators.get("ema", True)
    if ema_config is not False and ema_config is not None:
        if isinstance(ema_config, dict):
            params = ema_config
        else:
            params = DEFAULT_INDICATORS["ema"]
        
        # calculate_ema_multiple returns DataFrame with cols: ema_9, ema_20, ema_50
        ema_df = calculate_ema_multiple(gc_df, **params)
        
        # Add each EMA column to result
        for col in ema_df.columns:
            result[col] = ema_df[col]

    # Calculate DXY correlation if requested
    dxy_corr_config = indicators.get("dxy_correlation", True)
    if dxy_corr_config is not False and dxy_corr_config is not None:
        if isinstance(dxy_corr_config, dict):
            params = dxy_corr_config
        else:
            params = DEFAULT_INDICATORS["dxy_correlation"]
        
        # Calculate correlation (returns Series with timestamp index)
        dxy_corr_series = calculate_dxy_correlation(gc_df, dxy_df, **params)
        
        # Align correlation with GC DataFrame by mapping timestamp to value
        # Handles index mismatch: GC (RangeIndex) vs correlation (DatetimeIndex)
        if "ts_event" in gc_df.columns:
            # Create a dictionary mapping timestamp to correlation value
            corr_dict = dxy_corr_series.to_dict()
            # Map correlation values to GC timestamps
            result["dxy_corr"] = result["ts_event"].map(corr_dict)
        else:
            # Fallback: if no ts_event column, just reindex
            # This will only work if indexes are already aligned
            result["dxy_corr"] = dxy_corr_series.reindex(result.index)

    return result

