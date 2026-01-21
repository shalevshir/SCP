"""DXY chop detection.

SOP Definition of Chop:
- Wick-to-wick behavior (large wicks relative to body, ratio >= 1.0)
- Price containment within a narrow range (ATR-based)
- No directional progression (no HH/HL or LL/LH sequences)

Chop requires ALL THREE conditions:
1. Large wicks (indecision candles)
2. Range-bound price action
3. Failure to make directional progress
"""

from __future__ import annotations

import pandas as pd

from scp_shared.common.logger import get_logger

logger = get_logger(__name__)


def _calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR).
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        length: ATR period (default 14)
    
    Returns:
        ATR series
    """
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Use EMA for smoother ATR (Wilder's smoothing)
    atr = true_range.ewm(span=length, adjust=False).mean()
    
    return atr


def _detect_directional_progress(
    high: pd.Series, low: pd.Series, lookback: int = 3
) -> pd.Series:
    """Detect if price is making directional progress (HH/HL or LL/LH).
    
    Args:
        high: High prices
        low: Low prices
        lookback: Number of candles to check for progression
    
    Returns:
        Series with True if making directional progress (NOT chop)
    """
    n = len(high)
    has_progress = pd.Series(False, index=high.index)
    
    if n < lookback:
        return has_progress
    
    for i in range(lookback - 1, n):
        # Get recent highs and lows
        recent_highs = high.iloc[max(0, i - lookback + 1):i + 1].values
        recent_lows = low.iloc[max(0, i - lookback + 1):i + 1].values
        
        if len(recent_highs) < 2:
            continue
        
        # Check for HH/HL pattern (bullish progression)
        hh_count = sum(1 for j in range(1, len(recent_highs)) if recent_highs[j] > recent_highs[j-1])
        hl_count = sum(1 for j in range(1, len(recent_lows)) if recent_lows[j] > recent_lows[j-1])
        
        # Check for LL/LH pattern (bearish progression)
        ll_count = sum(1 for j in range(1, len(recent_lows)) if recent_lows[j] < recent_lows[j-1])
        lh_count = sum(1 for j in range(1, len(recent_highs)) if recent_highs[j] < recent_highs[j-1])
        
        comparisons = len(recent_highs) - 1
        
        # Bullish progression: majority HH AND majority HL
        is_bullish = (hh_count >= comparisons * 0.5) and (hl_count >= comparisons * 0.5)
        
        # Bearish progression: majority LL AND majority LH
        is_bearish = (ll_count >= comparisons * 0.5) and (lh_count >= comparisons * 0.5)
        
        has_progress.iloc[i] = is_bullish or is_bearish
    
    return has_progress


def detect_dxy_chop(
    dxy_df: pd.DataFrame,
    wick_threshold: float = 1.0,
    min_chop_candles: int = 3,
    range_multiplier: float = 1.5,
    atr_length: int = 14,
) -> pd.Series:
    """Detect DXY chop (ranging) conditions - SOP compliant.

    Args:
        dxy_df: DataFrame with DXY OHLC data
        wick_threshold: Minimum wick-to-body ratio to consider indecision (default 1.0)
        min_chop_candles: Consecutive chop candles needed to trigger
        range_multiplier: Range must be < ATR * multiplier to be range-bound (default 1.5)
        atr_length: ATR calculation period (default 14)

    Returns:
        Series with boolean dxy_chop flag

    SOP-Compliant Logic:
        Chop requires ALL THREE conditions:
        1. Wick condition: Large wicks relative to body (ratio >= threshold)
        2. Range constraint: Price contained within narrow range (< ATR * multiplier)
        3. Directional failure: No HH/HL or LL/LH progression

    This prevents flagging healthy pullbacks in trending markets as chop.
    """
    # Validate parameters
    if wick_threshold <= 0:
        raise ValueError(f"wick_threshold must be > 0, got {wick_threshold}")
    if min_chop_candles < 1:
        raise ValueError(f"min_chop_candles must be >= 1, got {min_chop_candles}")
    if range_multiplier <= 0:
        raise ValueError(f"range_multiplier must be > 0, got {range_multiplier}")

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

    high = dxy_df["high"]
    low = dxy_df["low"]
    close = dxy_df["close"]
    open_price = dxy_df["open"]

    # ========================================
    # CONDITION 1: Wick ratio (indecision)
    # ========================================
    upper_wick = high - pd.concat([open_price, close], axis=1).max(axis=1)
    lower_wick = pd.concat([open_price, close], axis=1).min(axis=1) - low
    body_size = (close - open_price).abs()

    wick_ratio = pd.Series(index=dxy_df.index, dtype=float)
    
    # Doji candles (zero body) → infinite ratio → always indecision
    zero_body_mask = body_size == 0
    wick_ratio[zero_body_mask] = float("inf")
    
    # Normal ratio for non-zero bodies
    non_zero_mask = ~zero_body_mask
    wick_ratio[non_zero_mask] = (
        upper_wick[non_zero_mask] + lower_wick[non_zero_mask]
    ) / body_size[non_zero_mask]
    
    has_large_wicks = wick_ratio >= wick_threshold
    has_large_wicks = has_large_wicks.fillna(False)

    # ========================================
    # CONDITION 2: Range constraint (containment)
    # ========================================
    # Rolling range over recent candles
    window = min(min_chop_candles, len(dxy_df))
    rolling_high = high.rolling(window=window, min_periods=1).max()
    rolling_low = low.rolling(window=window, min_periods=1).min()
    rolling_range = rolling_high - rolling_low
    
    # Calculate ATR for range comparison
    atr = _calculate_atr(high, low, close, length=atr_length)
    
    # Range-bound = rolling range < ATR * multiplier
    # This means price is contained, not expanding
    is_range_bound = rolling_range < (atr * range_multiplier)
    is_range_bound = is_range_bound.fillna(False)

    # ========================================
    # CONDITION 3: Directional failure
    # ========================================
    # Check if price is making directional progress
    has_directional_progress = _detect_directional_progress(high, low, lookback=min_chop_candles)
    
    # Chop = NO directional progress
    no_directional_progress = ~has_directional_progress

    # ========================================
    # COMBINED: All three conditions required
    # ========================================
    is_chop_candle = has_large_wicks & is_range_bound & no_directional_progress

    # Count consecutive chop candles
    consecutive_count = pd.Series(0, index=dxy_df.index, dtype=int)
    count = 0

    for i in range(len(dxy_df)):
        if is_chop_candle.iloc[i]:
            count += 1
        else:
            count = 0
        consecutive_count.iloc[i] = count

    # Chop triggered when consecutive count >= min_chop_candles
    dxy_chop = consecutive_count >= min_chop_candles

    logger.debug(
        f"DXY chop detection: {dxy_chop.sum()} / {len(dxy_chop)} candles in chop "
        f"(wick_thresh={wick_threshold}, range_mult={range_multiplier}, "
        f"min_candles={min_chop_candles})"
    )

    return dxy_chop.rename("dxy_chop")
