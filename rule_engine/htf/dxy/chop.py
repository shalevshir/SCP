"""DXY chop detection.

Chop defined as wick-to-wick behavior in DXY.
Trend becomes neutral when chop > 3 candles.

Task: Add DXY chop detection
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

import pandas as pd
from common.logger import get_logger

logger = get_logger(__name__)


def detect_dxy_chop(
    dxy_df: pd.DataFrame,
    wick_threshold: float = 0.5,
    min_chop_candles: int = 3,
) -> pd.Series:
    """Detect DXY chop (ranging) conditions.

    Args:
        dxy_df: DataFrame with DXY OHLC data
        wick_threshold: Minimum wick size ratio to consider chop
        min_chop_candles: Consecutive chop candles needed to trigger

    Returns:
        Series with boolean dxy_chop flag

    Logic:
        - Chop candle: Large wicks relative to body (wick-to-wick behavior)
        - Chop condition: 3+ consecutive chop candles
        - Effect: Forces HTF bias to neutral when detected

    DoD:
        - Implements wick threshold logic
        - Adds "dxy_chop = True/False" flag
        - HTF bias forced to neutral if chop detected
    """
    # Validate parameters
    if wick_threshold <= 0:
        raise ValueError(f"wick_threshold must be > 0, got {wick_threshold}")
    if min_chop_candles < 1:
        raise ValueError(f"min_chop_candles must be >= 1, got {min_chop_candles}")

    # Validate required columns
    required_cols = {"high", "low", "open", "close"}
    missing_cols = required_cols - set(dxy_df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required column(s): {missing_cols}. "
            f"Available columns: {list(dxy_df.columns)}"
        )

    # Handle empty DataFrame
    if len(dxy_df) == 0:
        return pd.Series(dtype=bool, name="dxy_chop")

    # Calculate wick sizes and body size
    upper_wick = dxy_df["high"] - dxy_df[["open", "close"]].max(axis=1)
    lower_wick = dxy_df[["open", "close"]].min(axis=1) - dxy_df["low"]
    body_size = (dxy_df["close"] - dxy_df["open"]).abs()

    # Calculate wick ratio
    # For doji candles (zero body), treat as infinite ratio (always chop)
    wick_ratio = pd.Series(index=dxy_df.index, dtype=float)
    
    # Handle zero body (doji) - treat as chop
    zero_body_mask = body_size == 0
    wick_ratio[zero_body_mask] = float("inf")
    
    # Calculate normal ratio for non-zero bodies
    non_zero_mask = ~zero_body_mask
    wick_ratio[non_zero_mask] = (
        (upper_wick[non_zero_mask] + lower_wick[non_zero_mask])
        / body_size[non_zero_mask]
    )

    # Identify individual chop candles
    is_chop_candle = wick_ratio >= wick_threshold

    # Handle NaN values - treat as non-chop
    is_chop_candle = is_chop_candle.fillna(False)

    # Count consecutive chop candles
    consecutive_count = pd.Series(0, index=dxy_df.index, dtype=int)
    count = 0
    
    for i in range(len(dxy_df)):
        if is_chop_candle.iloc[i]:
            count += 1
        else:
            count = 0  # Reset counter when non-chop candle appears
        consecutive_count.iloc[i] = count

    # Chop condition triggered when consecutive count >= min_chop_candles
    dxy_chop = consecutive_count >= min_chop_candles

    logger.debug(
        f"DXY chop detection: {dxy_chop.sum()} / {len(dxy_chop)} candles in chop "
        f"(threshold={wick_threshold}, min_candles={min_chop_candles})"
    )

    return dxy_chop.rename("dxy_chop")

