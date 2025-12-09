"""Structure event candle extraction.

Extracts actual Candle objects from structure detection results (BOS, CHoCH, sweeps).
Used to pass structure candles to trade creation for proper SL calculation.

Task: Extract structure event candles
Epic: Integrate FVG, Sweeps, BOS, CHoCH
Status: In Progress
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from common.logger import get_logger
from common.types import Candle

logger = get_logger(__name__)


def extract_bos_candle(
    df: pd.DataFrame,
    bos_series: pd.Series,
    current_timestamp: pd.Timestamp | datetime,
) -> Candle | None:
    """Extract the candle where BOS (Break of Structure) occurred.

    Args:
        df: OHLCV DataFrame with DatetimeIndex
        bos_series: Series from detect_bos() with BOS labels
        current_timestamp: Current timestamp to look back from

    Returns:
        Candle object where most recent BOS occurred, or None if not found

    Example:
        >>> bos_candle = extract_bos_candle(df_1h, bos_series, current_ts)
        >>> if bos_candle:
        ...     print(f"BOS at {bos_candle.timestamp}")
    """
    if bos_series is None or len(bos_series) == 0:
        return None

    # Convert current_timestamp to pandas Timestamp
    if isinstance(current_timestamp, datetime):
        current_timestamp = pd.Timestamp(current_timestamp)

    # Find most recent BOS event before or at current timestamp
    bos_events = bos_series[bos_series.notna()]
    bos_events = bos_events[bos_events.index <= current_timestamp]

    if len(bos_events) == 0:
        return None

    # Get the most recent BOS timestamp
    bos_timestamp = bos_events.index[-1]

    # Extract candle from DataFrame
    if bos_timestamp not in df.index:
        logger.warning(f"BOS timestamp {bos_timestamp} not found in DataFrame")
        return None

    row = df.loc[bos_timestamp]

    return Candle(
        timestamp=bos_timestamp.to_pydatetime(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        symbol="GC",  # Default to GC, can be parameterized if needed
        timeframe="1h",  # Default to 1h, can be parameterized if needed
        source="HTF_BOS",
    )


def extract_choch_candle(
    df: pd.DataFrame,
    choch_series: pd.Series,
    current_timestamp: pd.Timestamp | datetime,
) -> Candle | None:
    """Extract the candle where CHoCH (Change of Character) occurred.

    Args:
        df: OHLCV DataFrame with DatetimeIndex
        choch_series: Series from detect_choch() with CHoCH labels
        current_timestamp: Current timestamp to look back from

    Returns:
        Candle object where most recent CHoCH occurred, or None if not found

    Example:
        >>> choch_candle = extract_choch_candle(df_1h, choch_series, current_ts)
        >>> if choch_candle:
        ...     print(f"CHoCH at {choch_candle.timestamp}")
    """
    if choch_series is None or len(choch_series) == 0:
        return None

    # Convert current_timestamp to pandas Timestamp
    if isinstance(current_timestamp, datetime):
        current_timestamp = pd.Timestamp(current_timestamp)

    # Find most recent CHoCH event before or at current timestamp
    choch_events = choch_series[choch_series.notna()]
    choch_events = choch_events[choch_events.index <= current_timestamp]

    if len(choch_events) == 0:
        return None

    # Get the most recent CHoCH timestamp
    choch_timestamp = choch_events.index[-1]

    # Extract candle from DataFrame
    if choch_timestamp not in df.index:
        logger.warning(f"CHoCH timestamp {choch_timestamp} not found in DataFrame")
        return None

    row = df.loc[choch_timestamp]

    return Candle(
        timestamp=choch_timestamp.to_pydatetime(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        symbol="GC",
        timeframe="1h",
        source="HTF_CHOCH",
    )


def extract_sweep_candle(
    df: pd.DataFrame,
    sweep_events: pd.Series,
    current_timestamp: pd.Timestamp | datetime,
) -> Candle | None:
    """Extract the candle where liquidity sweep occurred.

    Args:
        df: OHLCV DataFrame with DatetimeIndex
        sweep_events: Series from detect_liquidity_sweeps() with sweep labels
        current_timestamp: Current timestamp to look back from

    Returns:
        Candle object where most recent sweep occurred, or None if not found

    Example:
        >>> sweep_candle = extract_sweep_candle(df_15m, sweep_events, current_ts)
        >>> if sweep_candle:
        ...     print(f"Sweep at {sweep_candle.timestamp}")
    """
    if sweep_events is None or len(sweep_events) == 0:
        return None

    # Convert current_timestamp to pandas Timestamp
    if isinstance(current_timestamp, datetime):
        current_timestamp = pd.Timestamp(current_timestamp)

    # Find most recent sweep event before or at current timestamp
    sweeps = sweep_events[sweep_events.notna()]
    sweeps = sweeps[sweeps.index <= current_timestamp]

    if len(sweeps) == 0:
        return None

    # Get the most recent sweep timestamp
    sweep_timestamp = sweeps.index[-1]

    # Extract candle from DataFrame
    if sweep_timestamp not in df.index:
        logger.warning(f"Sweep timestamp {sweep_timestamp} not found in DataFrame")
        return None

    row = df.loc[sweep_timestamp]

    return Candle(
        timestamp=sweep_timestamp.to_pydatetime(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        symbol="GC",
        timeframe="15m",  # Sweeps typically on 15m
        source="HTF_SWEEP",
    )


def extract_confirmation_candle(
    df: pd.DataFrame,
    current_timestamp: pd.Timestamp | datetime,
    lookback: int = 1,
) -> Candle | None:
    """Extract confirmation candle for current setup.

    The confirmation candle is typically the candle that confirmed the setup,
    which is usually the current candle or a recent candle.

    Args:
        df: OHLCV DataFrame with DatetimeIndex
        current_timestamp: Current timestamp
        lookback: How many candles to look back (0 = current, 1 = previous)

    Returns:
        Candle object for confirmation candle, or None if not found

    Example:
        >>> conf_candle = extract_confirmation_candle(df_1m, current_ts, lookback=1)
        >>> if conf_candle:
        ...     print(f"Confirmation at {conf_candle.timestamp}")
    """
    # Convert current_timestamp to pandas Timestamp
    if isinstance(current_timestamp, datetime):
        current_timestamp = pd.Timestamp(current_timestamp)

    # Find candles up to and including current timestamp
    available_candles = df[df.index <= current_timestamp]

    if len(available_candles) == 0:
        return None

    # Apply lookback
    if lookback >= len(available_candles):
        lookback = len(available_candles) - 1

    if lookback < 0:
        lookback = 0

    # Get the confirmation candle index
    conf_idx = -1 - lookback  # -1 is most recent, -2 is one before, etc.
    conf_timestamp = available_candles.index[conf_idx]

    row = available_candles.loc[conf_timestamp]

    return Candle(
        timestamp=conf_timestamp.to_pydatetime(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        symbol="GC",
        timeframe="1m",  # Confirmation typically on execution timeframe
        source="CONFIRMATION",
    )


def extract_structure_candles(
    df_1h: pd.DataFrame | None,
    df_15m: pd.DataFrame | None,
    bos_series: pd.Series | None,
    choch_series: pd.Series | None,
    sweep_events: pd.Series | None,
    current_timestamp: pd.Timestamp | datetime,
) -> dict[str, Candle | None]:
    """Extract all structure event candles in one call.

    Convenience function to extract BOS, CHoCH, and sweep candles together.

    Args:
        df_1h: 1h OHLCV DataFrame (for BOS/CHoCH)
        df_15m: 15m OHLCV DataFrame (for sweeps)
        bos_series: Series from detect_bos()
        choch_series: Series from detect_choch()
        sweep_events: Series from detect_liquidity_sweeps()
        current_timestamp: Current timestamp

    Returns:
        Dictionary with keys: 'bos_candle', 'choch_candle', 'sweep_candle'
        Values are Candle objects or None

    Example:
        >>> candles = extract_structure_candles(
        ...     df_1h, df_15m, bos_series, choch_series, sweep_events, current_ts
        ... )
        >>> if candles['bos_candle']:
        ...     print(f"BOS at {candles['bos_candle'].timestamp}")
    """
    result = {
        "bos_candle": None,
        "choch_candle": None,
        "sweep_candle": None,
    }

    # Extract BOS candle
    if df_1h is not None and bos_series is not None:
        result["bos_candle"] = extract_bos_candle(df_1h, bos_series, current_timestamp)

    # Extract CHoCH candle
    if df_1h is not None and choch_series is not None:
        result["choch_candle"] = extract_choch_candle(
            df_1h, choch_series, current_timestamp
        )

    # Extract sweep candle
    if df_15m is not None and sweep_events is not None:
        result["sweep_candle"] = extract_sweep_candle(
            df_15m, sweep_events, current_timestamp
        )

    return result
