"""Helper functions for working with MultiTimeframeData.

This module provides utility functions to extract and convert data from
MultiTimeframeData objects for use in backtesting and analysis.
"""

from datetime import datetime

import pandas as pd
from common.logger import get_logger
from common.types import Candle

from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar

logger = get_logger(__name__)


def extract_execution_dataframes(
    multi_tf_data: MultiTimeframeData,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract 1m GC and DXY DataFrames from MultiTimeframeData.
    
    Converts synchronized bars to pandas DataFrames with DatetimeIndex
    for use with BacktestProcessor and other components that expect
    DataFrame input.
    
    Args:
        multi_tf_data: MultiTimeframeData with synchronized bars
        
    Returns:
        Tuple of (gc_df, dxy_df) with DatetimeIndex and OHLCV columns
        
    Example:
        >>> from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
        >>> sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
        >>> multi_tf_data = sync_layer.load(start, end)
        >>> gc_df, dxy_df = extract_execution_dataframes(multi_tf_data)
        >>> print(gc_df.head())
    """
    if not multi_tf_data.synchronized_bars:
        # Return empty DataFrames with correct schema
        empty_df = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"]
        ).set_index(pd.DatetimeIndex([], name="timestamp", tz="UTC"))
        return empty_df.copy(), empty_df.copy()
    
    timestamps = [bar.execution_timestamp for bar in multi_tf_data.synchronized_bars]
    
    gc_data = {
        "open": [bar.execution_1m[0].open for bar in multi_tf_data.synchronized_bars],
        "high": [bar.execution_1m[0].high for bar in multi_tf_data.synchronized_bars],
        "low": [bar.execution_1m[0].low for bar in multi_tf_data.synchronized_bars],
        "close": [bar.execution_1m[0].close for bar in multi_tf_data.synchronized_bars],
        "volume": [bar.execution_1m[0].volume for bar in multi_tf_data.synchronized_bars],
    }
    
    dxy_data = {
        "open": [bar.execution_1m[1].open for bar in multi_tf_data.synchronized_bars],
        "high": [bar.execution_1m[1].high for bar in multi_tf_data.synchronized_bars],
        "low": [bar.execution_1m[1].low for bar in multi_tf_data.synchronized_bars],
        "close": [bar.execution_1m[1].close for bar in multi_tf_data.synchronized_bars],
        "volume": [bar.execution_1m[1].volume for bar in multi_tf_data.synchronized_bars],
    }
    
    gc_df = pd.DataFrame(
        gc_data, index=pd.DatetimeIndex(timestamps, name="timestamp", tz="UTC")
    )
    dxy_df = pd.DataFrame(
        dxy_data, index=pd.DatetimeIndex(timestamps, name="timestamp", tz="UTC")
    )
    
    logger.debug(
        f"Extracted execution DataFrames: {len(gc_df)} rows, "
        f"timeframe={multi_tf_data.execution_timeframe}"
    )
    
    return gc_df, dxy_df


def candles_to_dataframe(
    candles: list[Candle],
    timeframe: str,
) -> pd.DataFrame:
    """Convert list of Candle objects to DataFrame with DatetimeIndex.
    
    Args:
        candles: List of Candle objects
        timeframe: Timeframe string (for logging)
        
    Returns:
        DataFrame with DatetimeIndex and OHLCV columns
        
    Example:
        >>> candles = [Candle(...), Candle(...)]
        >>> df = candles_to_dataframe(candles, "15m")
        >>> print(df.head())
    """
    if not candles:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"]
        ).set_index(pd.DatetimeIndex([], name="timestamp", tz="UTC"))
    
    data = {
        "timestamp": [c.timestamp for c in candles],
        "open": [c.open for c in candles],
        "high": [c.high for c in candles],
        "low": [c.low for c in candles],
        "close": [c.close for c in candles],
        "volume": [c.volume for c in candles],
    }
    
    df = pd.DataFrame(data)
    df = df.set_index("timestamp")
    df.index.name = "timestamp"
    df = df.sort_index()
    
    logger.debug(f"Converted {len(candles)} candles to DataFrame (timeframe={timeframe})")
    
    return df


def extract_htf_candles_by_timeframe(
    multi_tf_data: MultiTimeframeData,
    timeframe: str,
) -> tuple[list[Candle], list[Candle]]:
    """Extract HTF candles for a specific timeframe.
    
    Extracts all available HTF candles for the specified timeframe,
    filtering out None values (missing data) and deduplicating by timestamp.
    
    Since multiple execution bars may reference the same HTF candle (forward-fill
    alignment), this function deduplicates to return only unique candles based on
    their timestamp. This ensures technical indicators are computed on correct data
    without artificial inflation from duplicate values.
    
    Args:
        multi_tf_data: MultiTimeframeData with synchronized bars
        timeframe: HTF timeframe to extract ("15m" or "1h")
        
    Returns:
        Tuple of (gc_candles, dxy_candles) for the specified timeframe.
        Lists contain only unique candles (deduplicated by timestamp).
        Lists may be empty if no HTF data available for that timeframe.
        
    Example:
        >>> gc_15m, dxy_15m = extract_htf_candles_by_timeframe(multi_tf_data, "15m")
        >>> print(f"Found {len(gc_15m)} unique 15m GC candles")
    """
    if timeframe not in multi_tf_data.htf_timeframes:
        logger.warning(
            f"Timeframe {timeframe} not in HTF timeframes {multi_tf_data.htf_timeframes}"
        )
        return [], []
    
    # Use dict keyed by timestamp to deduplicate (same timestamp = same candle)
    gc_candles_dict: dict[datetime, Candle] = {}
    dxy_candles_dict: dict[datetime, Candle] = {}
    
    for bar in multi_tf_data.synchronized_bars:
        if timeframe == "15m" and bar.htf_15m:
            gc_candle = bar.htf_15m[0]
            dxy_candle = bar.htf_15m[1]
            # Only add if we haven't seen this timestamp before
            if gc_candle.timestamp not in gc_candles_dict:
                gc_candles_dict[gc_candle.timestamp] = gc_candle
                dxy_candles_dict[dxy_candle.timestamp] = dxy_candle
        elif timeframe == "1h" and bar.htf_1h:
            gc_candle = bar.htf_1h[0]
            dxy_candle = bar.htf_1h[1]
            # Only add if we haven't seen this timestamp before
            if gc_candle.timestamp not in gc_candles_dict:
                gc_candles_dict[gc_candle.timestamp] = gc_candle
                dxy_candles_dict[dxy_candle.timestamp] = dxy_candle
    
    # Convert to sorted lists (by timestamp) for consistent ordering
    gc_candles = sorted(gc_candles_dict.values(), key=lambda c: c.timestamp)
    dxy_candles = sorted(dxy_candles_dict.values(), key=lambda c: c.timestamp)
    
    logger.debug(
        f"Extracted {len(gc_candles)} unique {timeframe} candles "
        f"(GC: {len(gc_candles)}, DXY: {len(dxy_candles)})"
    )
    
    return gc_candles, dxy_candles


def build_htf_dataframe_from_candles(
    candles: list[Candle],
    timeframe: str,
) -> pd.DataFrame | None:
    """Build DataFrame from HTF candles for structure detection.
    
    This is a convenience wrapper around candles_to_dataframe that
    handles empty lists gracefully.
    
    Args:
        candles: List of HTF candles
        timeframe: Timeframe string
        
    Returns:
        DataFrame with OHLC columns, or None if candles list is empty
    """
    if not candles:
        return None
    
    df = candles_to_dataframe(candles, timeframe)
    return df

