"""HTF structural target computation for VWAP_RECLAIM TP selection.

Computes HTF price targets (range boundaries, untouched liquidity, FVG targets)
and obstacles (opposing FVGs) as specified in SOP Section 4.3.

These targets follow the priority hierarchy:
1. HTF range high/low (session high/low)
2. Untouched liquidity (clean HH/LL not swept)
3. Nearest directional FVG completion
4. Nearest swing high/low (fallback only)

Task: Implement HTF target calculation
Epic: VWAP_RECLAIM TP validation
Status: In Progress
"""

from __future__ import annotations

import pandas as pd

from scp_shared.common.logger import get_logger

logger = get_logger(__name__)


def compute_htf_range(
    df: pd.DataFrame,
    current_price: float,
    bos_index: int | None,
) -> tuple[float | None, float | None]:
    """Compute HTF range boundaries for TP selection.

    HTF Range Valid When:
    - HTF structure intact (not broken/accepted through)
    - Formed after most recent BOS
    - Clear swing high and low exist

    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        current_price: Current market price
        bos_index: Index of most recent BOS (None = use entire df)

    Returns:
        Tuple of (htf_range_high, htf_range_low):
        - htf_range_high: Upper boundary (None if broken)
        - htf_range_low: Lower boundary (None if broken)

    Logic:
        - Find max swing high and min swing low since BOS
        - Validate high: if any close > range_high, invalidate high
        - Validate low: if any close < range_low, invalidate low
        - Wick touches are OK, body acceptance invalidates

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [2010, 2050, 2100, 2090],
        ...     'low': [2000, 2040, 2090, 2080],
        ...     'close': [2005, 2045, 2095, 2085]
        ... })
        >>> range_high, range_low = compute_htf_range(df, 2085.0, None)
        >>> range_high
        2100.0
        >>> range_low
        2000.0
    """
    # Validate required columns
    required_cols = {"high", "low", "close"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    # Handle empty or single-bar DataFrame
    if len(df) <= 1:
        return None, None

    # Determine scope based on bos_index
    # When bos_index is provided, use data from that point onwards (inclusive)
    # When None, use entire dataframe
    if bos_index is not None:
        start_idx = bos_index
    else:
        start_idx = 0

    if start_idx >= len(df):
        return None, None

    # Slice to relevant portion
    scoped_df = df.iloc[start_idx:]

    if len(scoped_df) <= 1:
        return None, None

    # Step 1: Find max swing high and min swing low in the scoped range
    range_high = scoped_df["high"].max()
    range_low = scoped_df["low"].min()

    # Find the index (within scoped_df) where max high and min low occur
    range_high_idx = scoped_df["high"].idxmax()
    range_low_idx = scoped_df["low"].idxmin()

    # Step 2: Check for invalidation (body acceptance through boundaries)
    # A boundary is invalidated if any subsequent close exceeds it
    # Wick touches are OK, only closes invalidate

    # Check if range_high is broken (any close above it after it formed)
    if range_high_idx < scoped_df.index[-1]:
        bars_after_high = scoped_df.loc[range_high_idx + 1:]
    else:
        bars_after_high = scoped_df.iloc[0:0]
    if len(bars_after_high) > 0:
        # If any close exceeds range_high, invalidate it
        if (bars_after_high["close"] > range_high).any():
            range_high = None

    # Check if range_low is broken (any close below it after it formed)
    if range_low_idx < scoped_df.index[-1]:
        bars_after_low = scoped_df.loc[range_low_idx + 1:]
    else:
        bars_after_low = scoped_df.iloc[0:0]
    if len(bars_after_low) > 0:
        # If any close is below range_low, invalidate it
        if (bars_after_low["close"] < range_low).any():
            range_low = None

    return range_high, range_low


def compute_untouched_liquidity(
    df: pd.DataFrame,
    current_price: float,
    swept_levels: set[float],
) -> tuple[float | None, float | None]:
    """Identify untouched liquidity pools for TP selection.

    Untouched Liquidity Valid When:
    - No wick or body interaction with the level (unswept)
    - Clearly visible swing high/low
    - Not in swept_levels set

    Args:
        df: DataFrame with 'high', 'low' columns
        current_price: Current market price
        swept_levels: Set of price levels that have been swept

    Returns:
        Tuple of (untouched_liq_high, untouched_liq_low):
        - untouched_liq_high: Nearest unswept swing high above price
        - untouched_liq_low: Nearest unswept swing low below price

    Logic:
        - Detect swing highs (local peaks) and swing lows (local troughs)
        - Find swings above/below current_price
        - Filter out levels in swept_levels
        - Return nearest valid level (closest to current price)

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [2010, 2050, 2100, 2090],
        ...     'low': [2000, 2040, 2090, 2080]
        ... })
        >>> liq_high, liq_low = compute_untouched_liquidity(df, 2085.0, set())
        >>> liq_high
        2100.0
    """
    # Validate required columns
    required_cols = {"high", "low"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    # Handle empty DataFrame
    if len(df) == 0:
        return None, None

    # Simple swing detection: a swing high is a local peak (higher than neighbors)
    # a swing low is a local trough (lower than neighbors)
    # Only consider bars with neighbors on BOTH sides (exclude first and last bars)
    swing_highs = []
    swing_lows = []

    for i in range(1, len(df) - 1):
        # Swing high: higher than both neighbors
        if df["high"].iloc[i] > df["high"].iloc[i - 1] and df["high"].iloc[i] > df[
            "high"
        ].iloc[i + 1]:
            swing_highs.append(df["high"].iloc[i])

        # Swing low: lower than both neighbors
        if df["low"].iloc[i] < df["low"].iloc[i - 1] and df["low"].iloc[i] < df[
            "low"
        ].iloc[i + 1]:
            swing_lows.append(df["low"].iloc[i])

    # Filter for valid liquidity highs (above price, not swept)
    valid_highs = [
        h for h in swing_highs if h > current_price and h not in swept_levels
    ]

    # Filter for valid liquidity lows (below price, not swept)
    valid_lows = [
        low for low in swing_lows if low < current_price and low not in swept_levels
    ]

    # Return nearest valid levels (closest to current price)
    liq_high = min(valid_highs) if valid_highs else None
    liq_low = max(valid_lows) if valid_lows else None

    return liq_high, liq_low


def find_nearest_fvg_targets(
    fvg_df: pd.DataFrame,
    current_price: float,
    direction: str,
) -> tuple[float | None, float | None]:
    """Find nearest FVG target in trade direction.

    FVG Valid When:
    - FVG is in trade direction (bullish for longs, bearish for shorts)
    - FVG is not fully filled
    - FVG is in correct position relative to price

    Args:
        fvg_df: DataFrame from detect_fvg() with columns:
            - fvg_index, fvg_type, fvg_high, fvg_low, filled
        current_price: Current market price
        direction: Trade direction ("long" or "short")

    Returns:
        Tuple of (fvg_high, fvg_low):
        - For longs: nearest bullish FVG above price
        - For shorts: nearest bearish FVG below price
        - Returns (None, None) if no valid FVG exists

    Example:
        >>> fvg_df = pd.DataFrame({
        ...     'fvg_type': ['bullish'],
        ...     'fvg_high': [2110.0],
        ...     'fvg_low': [2100.0],
        ...     'filled': [False]
        ... })
        >>> fvg_high, fvg_low = find_nearest_fvg_targets(fvg_df, 2050.0, "long")
        >>> fvg_high
        2110.0
    """
    # Handle empty DataFrame
    if len(fvg_df) == 0:
        return None, None

    # Validate required columns
    required_cols = {"fvg_type", "fvg_high", "fvg_low", "filled"}
    missing_cols = required_cols - set(fvg_df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(fvg_df.columns)}"
        )

    # Filter for unfilled FVGs
    unfilled_fvgs = fvg_df[fvg_df["filled"] == False]  # noqa: E712

    if len(unfilled_fvgs) == 0:
        return None, None

    # For longs: find bullish FVGs above current price
    if direction == "long":
        valid_fvgs = unfilled_fvgs[
            (unfilled_fvgs["fvg_type"] == "bullish")
            & (unfilled_fvgs["fvg_low"] > current_price)
        ]

        if len(valid_fvgs) == 0:
            return None, None

        # Return nearest FVG (lowest fvg_low above price)
        nearest_idx = valid_fvgs["fvg_low"].idxmin()
        return valid_fvgs.loc[nearest_idx, "fvg_high"], valid_fvgs.loc[
            nearest_idx, "fvg_low"
        ]

    # For shorts: find bearish FVGs below current price
    elif direction == "short":
        valid_fvgs = unfilled_fvgs[
            (unfilled_fvgs["fvg_type"] == "bearish")
            & (unfilled_fvgs["fvg_high"] < current_price)
        ]

        if len(valid_fvgs) == 0:
            return None, None

        # Return nearest FVG (highest fvg_high below price)
        nearest_idx = valid_fvgs["fvg_high"].idxmax()
        return valid_fvgs.loc[nearest_idx, "fvg_high"], valid_fvgs.loc[
            nearest_idx, "fvg_low"
        ]

    else:
        return None, None


def find_opposing_fvgs(
    fvg_df: pd.DataFrame,
    current_price: float,
    tp_price: float,
    direction: str,
) -> dict:
    """Find opposing FVGs that block the path to TP.

    Opposing FVG Blocks TP When:
    - Located between entry (current_price) and TP
    - FVG type opposes trade direction
    - FVG is unfilled

    Args:
        fvg_df: DataFrame from detect_fvg() with FVG data
        current_price: Current market price (entry)
        tp_price: Take profit target price
        direction: Trade direction ("long" or "short")

    Returns:
        Dict with keys:
        - opposing_fvg_high: Bearish FVG upper boundary (blocks longs)
        - opposing_fvg_low: Bearish FVG lower boundary
        - opposing_fvg_bullish_high: Bullish FVG upper (blocks shorts)
        - opposing_fvg_bullish_low: Bullish FVG lower

    Logic:
        For longs (current_price < tp_price):
        - Find bearish FVGs with fvg_low between current_price and tp_price
        
        For shorts (current_price > tp_price):
        - Find bullish FVGs with fvg_high between tp_price and current_price

    Example:
        >>> fvg_df = pd.DataFrame({
        ...     'fvg_type': ['bearish'],
        ...     'fvg_high': [2080.0],
        ...     'fvg_low': [2070.0],
        ...     'filled': [False]
        ... })
        >>> result = find_opposing_fvgs(fvg_df, 2050.0, 2100.0, "long")
        >>> result['opposing_fvg_high']
        2080.0
    """
    # Initialize result dict
    result = {
        "opposing_fvg_high": None,
        "opposing_fvg_low": None,
        "opposing_fvg_bullish_high": None,
        "opposing_fvg_bullish_low": None,
    }

    # Handle empty DataFrame
    if len(fvg_df) == 0:
        return result

    # Validate required columns
    required_cols = {"fvg_type", "fvg_high", "fvg_low", "filled"}
    missing_cols = required_cols - set(fvg_df.columns)
    if missing_cols:
        return result  # Return empty result instead of raising

    # Filter for unfilled FVGs
    unfilled_fvgs = fvg_df[fvg_df["filled"] == False]  # noqa: E712

    if len(unfilled_fvgs) == 0:
        return result

    # For longs: find bearish FVGs in the path
    if direction == "long":
        # Path is from current_price to tp_price (upward)
        blocking_fvgs = unfilled_fvgs[
            (unfilled_fvgs["fvg_type"] == "bearish")
            & (unfilled_fvgs["fvg_low"] > current_price)
            & (unfilled_fvgs["fvg_high"] < tp_price)
        ]

        if len(blocking_fvgs) > 0:
            # Return first blocking FVG (nearest to entry)
            nearest_idx = blocking_fvgs["fvg_low"].idxmin()
            result["opposing_fvg_high"] = blocking_fvgs.loc[nearest_idx, "fvg_high"]
            result["opposing_fvg_low"] = blocking_fvgs.loc[nearest_idx, "fvg_low"]

    # For shorts: find bullish FVGs in the path
    elif direction == "short":
        # Path is from current_price to tp_price (downward)
        blocking_fvgs = unfilled_fvgs[
            (unfilled_fvgs["fvg_type"] == "bullish")
            & (unfilled_fvgs["fvg_high"] < current_price)
            & (unfilled_fvgs["fvg_low"] > tp_price)
        ]

        if len(blocking_fvgs) > 0:
            # Return first blocking FVG (nearest to entry)
            nearest_idx = blocking_fvgs["fvg_high"].idxmax()
            result["opposing_fvg_bullish_high"] = blocking_fvgs.loc[
                nearest_idx, "fvg_high"
            ]
            result["opposing_fvg_bullish_low"] = blocking_fvgs.loc[
                nearest_idx, "fvg_low"
            ]

    return result
