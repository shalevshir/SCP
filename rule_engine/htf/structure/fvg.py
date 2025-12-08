"""Fair Value Gap (FVG) detection.

FVGs are 3-candle price imbalances indicating institutional order flow
and potential support/resistance zones.

Task: Implement FVG detection
Epic: Full HTF Bias Engine Upgrade
Status: In Progress
"""

from __future__ import annotations

import pandas as pd

from common.logger import get_logger

logger = get_logger(__name__)


def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Detect Fair Value Gaps in price data.
    
    A Fair Value Gap (FVG) is a 3-candle pattern showing price imbalance where
    there's a gap between candle 1 and candle 3 that candle 2 doesn't fill.
    
    Args:
        df: DataFrame with 'high', 'low' columns (minimum 3 rows)
    
    Returns:
        DataFrame with columns:
        - fvg_index: Integer index where FVG formed (at candle 3, position i)
        - fvg_type: 'bullish' or 'bearish'
        - fvg_high: Upper boundary of gap
        - fvg_low: Lower boundary of gap
        - filled: False (initial state, use check_fvg_filled to update)
        - fill_index: None (initial state, use check_fvg_filled to update)
    
    Raises:
        ValueError: If required columns ('high', 'low') are missing
    
    Logic:
        Bullish FVG (gap up):
        - candle_1.high < candle_3.low (gap exists between 1 and 3)
        - candle_2.high < candle_3.low (candle 2 doesn't fill from above)
        - candle_2.low > candle_1.high (candle 2 doesn't fill from below)
        
        Bearish FVG (gap down):
        - candle_1.low > candle_3.high (gap exists between 1 and 3)
        - candle_2.low > candle_3.high (candle 2 doesn't fill from below)
        - candle_2.high < candle_1.low (candle 2 doesn't fill from above)
    
    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 101, 105],
        ...     'low': [98, 100.5, 103]
        ... })
        >>> fvg_df = detect_fvg(df)
        >>> fvg_df.iloc[0]['fvg_type']
        'bullish'
    """
    # Validate required columns
    required_cols = {'high', 'low'}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )
    
    # Initialize empty result DataFrame with proper columns
    result_columns = ['fvg_index', 'fvg_type', 'fvg_high', 'fvg_low', 'filled', 'fill_index']
    
    # Need at least 3 candles to form FVG
    if len(df) < 3:
        return pd.DataFrame(columns=result_columns)
    
    # Store detected FVGs
    fvgs = []
    
    # Iterate through each potential FVG position (starting at index 2)
    for i in range(2, len(df)):
        # Get the three candles
        candle_1_high = df['high'].iloc[i-2]
        candle_1_low = df['low'].iloc[i-2]
        candle_2_high = df['high'].iloc[i-1]
        candle_2_low = df['low'].iloc[i-1]
        candle_3_high = df['high'].iloc[i]
        candle_3_low = df['low'].iloc[i]
        
        # Check for Bullish FVG (gap up)
        # Gap must exist: candle_1.high < candle_3.low
        if candle_1_high < candle_3_low:
            # Candle 2 must NOT overlap the gap
            # - Candle 2 high must be below candle 3 low (stays below the gap)
            # - Candle 2 low must be above candle 1 high (stays above the gap)
            if candle_2_high < candle_3_low and candle_2_low > candle_1_high:
                fvgs.append({
                    'fvg_index': i,
                    'fvg_type': 'bullish',
                    'fvg_high': candle_3_low,  # Top of gap
                    'fvg_low': candle_1_high,   # Bottom of gap
                    'filled': False,
                    'fill_index': None
                })
        
        # Check for Bearish FVG (gap down)
        # Gap must exist: candle_1.low > candle_3.high
        elif candle_1_low > candle_3_high:
            # Candle 2 must NOT overlap the gap
            # - Candle 2 low must be above candle 3 high (stays above the gap)
            # - Candle 2 high must be below candle 1 low (stays below the gap)
            if candle_2_low > candle_3_high and candle_2_high < candle_1_low:
                fvgs.append({
                    'fvg_index': i,
                    'fvg_type': 'bearish',
                    'fvg_high': candle_1_low,   # Top of gap
                    'fvg_low': candle_3_high,   # Bottom of gap
                    'filled': False,
                    'fill_index': None
                })
    
    # Create DataFrame from results
    fvg_df = pd.DataFrame(fvgs, columns=result_columns) if fvgs else pd.DataFrame(columns=result_columns)
    
    logger.debug(
        f"Detected {len(fvg_df)} FVGs in {len(df)} bars: "
        f"{(fvg_df['fvg_type'] == 'bullish').sum()} bullish, "
        f"{(fvg_df['fvg_type'] == 'bearish').sum()} bearish"
    )
    
    return fvg_df


def check_fvg_filled(
    df: pd.DataFrame,
    fvg_df: pd.DataFrame
) -> pd.DataFrame:
    """Check which FVGs have been filled by subsequent price action.
    
    Updates the 'filled' and 'fill_index' columns of the FVG DataFrame based
    on whether subsequent price action has returned to fill the gap.
    
    Args:
        df: Original OHLC DataFrame used to detect FVGs
        fvg_df: DataFrame returned by detect_fvg()
    
    Returns:
        Updated fvg_df with 'filled' and 'fill_index' columns updated
    
    Logic:
        - Bullish FVG filled: Any subsequent candle's low <= fvg_low
        - Bearish FVG filled: Any subsequent candle's high >= fvg_high
        - Once filled, marks 'filled' = True and records 'fill_index'
        - Only records the FIRST fill
    
    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 101, 105, 107, 102],
        ...     'low': [98, 100.5, 103, 105, 99]
        ... })
        >>> fvg_df = detect_fvg(df)
        >>> fvg_df = check_fvg_filled(df, fvg_df)
        >>> fvg_df.iloc[0]['filled']
        True
    """
    # Return empty DataFrame if no FVGs
    if len(fvg_df) == 0:
        return fvg_df
    
    # Create a copy to avoid modifying original
    fvg_df = fvg_df.copy()
    
    # Check each FVG
    for idx, fvg in fvg_df.iterrows():
        fvg_index = int(fvg['fvg_index'])
        fvg_type = fvg['fvg_type']
        fvg_high = fvg['fvg_high']
        fvg_low = fvg['fvg_low']
        
        # Check all bars after FVG formation
        for i in range(fvg_index + 1, len(df)):
            if fvg_type == 'bullish':
                # Bullish FVG is filled if price returns down into the gap
                # Check if low touches or goes below the gap's lower boundary
                if df['low'].iloc[i] <= fvg_low:
                    fvg_df.at[idx, 'filled'] = True
                    fvg_df.at[idx, 'fill_index'] = i
                    break  # Record first fill only
            
            elif fvg_type == 'bearish':
                # Bearish FVG is filled if price returns up into the gap
                # Check if high touches or goes above the gap's upper boundary
                if df['high'].iloc[i] >= fvg_high:
                    fvg_df.at[idx, 'filled'] = True
                    fvg_df.at[idx, 'fill_index'] = i
                    break  # Record first fill only
    
    filled_count = fvg_df['filled'].sum()
    logger.debug(
        f"Checked {len(fvg_df)} FVGs: {filled_count} filled, "
        f"{len(fvg_df) - filled_count} unfilled"
    )
    
    return fvg_df


# ============================================================================
# Incremental FVG State Tracking (for backtesting)
# ============================================================================


from dataclasses import dataclass
from datetime import datetime


@dataclass
class FVGState:
    """State of a single FVG.
    
    Attributes:
        fvg_id: Unique identifier for this FVG
        timestamp: When the FVG was created
        direction: "bullish" or "bearish"
        top: Upper boundary of the gap
        bottom: Lower boundary of the gap
        filled: Whether this FVG has been filled
        fill_timestamp: When the FVG was filled (if filled)
    """
    fvg_id: str
    timestamp: datetime
    direction: str
    top: float
    bottom: float
    filled: bool = False
    fill_timestamp: datetime | None = None


class FVGStateTracker:
    """Incremental FVG state tracker for backtesting.
    
    Tracks FVG creation and fill status without lookahead bias.
    """
    
    def __init__(self):
        """Initialize empty FVG tracker."""
        self.fvgs: dict[str, FVGState] = {}
        self._next_id = 0
    
    def update(self, df: pd.DataFrame, current_timestamp: pd.Timestamp | datetime) -> None:
        """Update FVG state with new data.
        
        Args:
            df: OHLC DataFrame (must include historical context for detection)
            current_timestamp: Current timestamp (no lookahead)
        """
        # Convert timestamp
        if isinstance(current_timestamp, datetime):
            current_timestamp = pd.Timestamp(current_timestamp)
        
        # Only process data up to current timestamp
        df_filtered = df[df.index <= current_timestamp]
        
        if len(df_filtered) < 3:
            return  # Need at least 3 candles
        
        # Detect FVGs in the filtered data
        try:
            fvg_df = detect_fvg(df_filtered)
            
            if len(fvg_df) == 0:
                return
            
            # Add new FVGs
            for _, row in fvg_df.iterrows():
                fvg_timestamp = row['timestamp']
                
                # Only add FVGs that we haven't seen before
                fvg_key = f"{fvg_timestamp}_{row['direction']}"
                if fvg_key not in self.fvgs:
                    self.fvgs[fvg_key] = FVGState(
                        fvg_id=f"fvg_{self._next_id}",
                        timestamp=fvg_timestamp,
                        direction=row['direction'],
                        top=row['top'],
                        bottom=row['bottom'],
                        filled=False,
                    )
                    self._next_id += 1
            
            # Check for fills on existing unfilled FVGs
            fvg_df_filled = check_fvg_filled(df_filtered, fvg_df)
            
            for _, row in fvg_df_filled.iterrows():
                fvg_timestamp = row['timestamp']
                fvg_key = f"{fvg_timestamp}_{row['direction']}"
                
                if fvg_key in self.fvgs and row['filled']:
                    if not self.fvgs[fvg_key].filled:
                        self.fvgs[fvg_key].filled = True
                        # Try to get fill timestamp from fill_index
                        if pd.notna(row.get('fill_index')):
                            fill_idx = int(row['fill_index'])
                            if fill_idx < len(df_filtered):
                                self.fvgs[fvg_key].fill_timestamp = df_filtered.index[fill_idx]
        
        except Exception as e:
            logger.debug(f"Error updating FVG state: {e}")
    
    def get_active_fvgs(self, current_timestamp: pd.Timestamp | datetime) -> list[FVGState]:
        """Get all unfilled FVGs at current timestamp.
        
        Args:
            current_timestamp: Current timestamp
            
        Returns:
            List of unfilled FVGState objects
        """
        if isinstance(current_timestamp, datetime):
            current_timestamp = pd.Timestamp(current_timestamp)
        
        active_fvgs = []
        for fvg in self.fvgs.values():
            # FVG must be created before current time and not filled
            if pd.Timestamp(fvg.timestamp) <= current_timestamp and not fvg.filled:
                active_fvgs.append(fvg)
        
        return active_fvgs
    
    def get_fvg_count(self) -> tuple[int, int]:
        """Get count of total and active FVGs.
        
        Returns:
            Tuple of (total_fvgs, active_fvgs)
        """
        total = len(self.fvgs)
        active = sum(1 for fvg in self.fvgs.values() if not fvg.filled)
        return total, active

