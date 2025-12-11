"""Structure label computation for swing point detection.

This module provides functionality to identify swing highs and lows in price
action and label them as HH (Higher High), HL (Higher Low), LH (Lower High),
or LL (Lower Low) for structure analysis.

Also provides StructureContext for continuous structure state tracking.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

import pandas as pd


@dataclass
class StructureContext:
    """Derived structure state, updated every bar.
    
    Transforms sparse swing labels into continuous structure context available
    on every candle. Forward-fills swing data and computes derived metrics.
    
    Attributes:
        last_structure_label: Most recent swing label (HH/HL/LH/LL)
        last_swing_high: Price of last swing high
        last_swing_low: Price of last swing low
        last_swing_high_idx: Bar index of last swing high
        last_swing_low_idx: Bar index of last swing low
        trend_direction: Derived trend ("bullish", "bearish", "neutral")
        trend_confidence: 0-1 confidence based on label consistency
        structure_clarity: 0-1 swing sequence purity score
        is_chop: True if rapid alternations detected
        structure_conflict_flag: True if mixed signals present
        last_bos_direction: Direction of last Break of Structure
        bos_age: Bars since last BOS event
        choch_detected: True if CHoCH detected on this bar
        choch_direction: Direction of last CHoCH
        choch_age: Bars since last CHoCH event
    """
    
    # Persisted labels
    last_structure_label: str | None = None
    last_swing_high: float | None = None
    last_swing_low: float | None = None
    last_swing_high_idx: int | None = None
    last_swing_low_idx: int | None = None
    
    # Derived trend
    trend_direction: Literal["bullish", "bearish", "neutral"] = "neutral"
    trend_confidence: float = 0.0
    
    # Structure quality
    structure_clarity: float = 0.0
    is_chop: bool = False
    structure_conflict_flag: bool = False
    
    # CHoCH tracking (BOS tracking to be added in Structure Engine v2.0 Part 2)
    choch_detected: bool = False
    choch_direction: str | None = None
    choch_age: int | None = None


class StructureContextTracker:
    """Incremental tracker producing StructureContext per bar.
    
    Maintains rolling state and produces derived structure context on every
    candle update. Uses existing StructureState logic for swing detection.
    
    Args:
        swing_window: Swing detection window size (default 5)
        clarity_window: Window for clarity score computation (default 10)
    """
    
    def __init__(self, swing_window: int = 5, clarity_window: int = 10):
        """Initialize tracker with configuration."""
        self.swing_window = swing_window
        self.clarity_window = clarity_window
        
        # Swing detection buffers (reuse StructureState logic)
        maxlen = swing_window * 2 + 1
        self.high_buffer: deque[float] = deque(maxlen=maxlen)
        self.low_buffer: deque[float] = deque(maxlen=maxlen)
        
        # Track previous swing values for label determination
        self.prev_swing_high: float | None = None
        self.prev_swing_low: float | None = None
        
        # Track swing indices and prices
        self.last_swing_high: float | None = None
        self.last_swing_low: float | None = None
        self.last_swing_high_idx: int | None = None
        self.last_swing_low_idx: int | None = None
        
        # Label history for trend/clarity computation
        self.label_history: deque[str | None] = deque(maxlen=clarity_window)
        self.last_structure_label: str | None = None
        
        # CHoCH tracking (BOS tracking to be added in Structure Engine v2.0 Part 2)
        self.last_choch_direction: str | None = None
        self.last_choch_idx: int | None = None
        
        # Bar counter
        self.bar_count = 0
    
    def update(self, high: float, low: float, close: float) -> StructureContext:
        """Update with new candle and return derived context.
        
        Args:
            high: Candle high price
            low: Candle low price
            close: Candle close price (for future use)
        
        Returns:
            StructureContext with all derived fields populated
        """
        self.bar_count += 1
        
        # Add to swing detection buffers
        self.high_buffer.append(high)
        self.low_buffer.append(low)
        
        # Detect swing point at center of buffer
        new_label = None
        if len(self.high_buffer) >= self.swing_window * 2 + 1:
            new_label = self._detect_swing_label()
        
        # Update label tracking if new swing detected
        if new_label is not None:
            self.last_structure_label = new_label
            self.label_history.append(new_label)
            
            # Update swing indices
            if new_label in ["HH", "LH"]:
                self.last_swing_high_idx = self.bar_count - self.swing_window
                self.last_swing_high = self.high_buffer[self.swing_window]
            elif new_label in ["HL", "LL"]:
                self.last_swing_low_idx = self.bar_count - self.swing_window
                self.last_swing_low = self.low_buffer[self.swing_window]
        
        # Compute derived metrics
        trend_direction, trend_confidence = self._compute_trend()
        structure_clarity = self._compute_clarity()
        is_chop = self._detect_chop()
        structure_conflict_flag = self._detect_conflict()
        
        # Track CHoCH age
        choch_age = None if self.last_choch_idx is None else (self.bar_count - self.last_choch_idx)
        
        # Detect CHoCH on this bar
        choch_detected = False
        if new_label is not None:
            choch_detected = self._detect_choch_event(new_label)
        
        return StructureContext(
            last_structure_label=self.last_structure_label,
            last_swing_high=self.last_swing_high,
            last_swing_low=self.last_swing_low,
            last_swing_high_idx=self.last_swing_high_idx,
            last_swing_low_idx=self.last_swing_low_idx,
            trend_direction=trend_direction,
            trend_confidence=trend_confidence,
            structure_clarity=structure_clarity,
            is_chop=is_chop,
            structure_conflict_flag=structure_conflict_flag,
            choch_detected=choch_detected,
            choch_direction=self.last_choch_direction,
            choch_age=choch_age,
        )
    
    def _detect_swing_label(self) -> str | None:
        """Detect swing label at center of buffer.
        
        Reuses StructureState logic for consistency.
        
        Returns:
            Structure label (HH/HL/LH/LL) or None if no swing detected
        """
        center_idx = self.swing_window
        center_high = self.high_buffer[center_idx]
        center_low = self.low_buffer[center_idx]
        
        # Check if center is swing high (local maximum)
        is_swing_high = all(
            center_high >= self.high_buffer[i]
            for i in range(len(self.high_buffer))
            if i != center_idx
        )
        
        # Check if center is swing low (local minimum)
        is_swing_low = all(
            center_low <= self.low_buffer[i]
            for i in range(len(self.low_buffer))
            if i != center_idx
        )
        
        label = None
        
        # Process swing high (priority over swing low)
        if is_swing_high:
            if self.prev_swing_high is not None:
                if center_high > self.prev_swing_high:
                    label = "HH"
                elif center_high < self.prev_swing_high:
                    label = "LH"
                else:
                    label = "HH"  # Equal - default to HH
            else:
                label = "HH"  # First swing high
            self.prev_swing_high = center_high
        
        # Process swing low
        elif is_swing_low:
            if self.prev_swing_low is not None:
                if center_low > self.prev_swing_low:
                    label = "HL"
                elif center_low < self.prev_swing_low:
                    label = "LL"
                else:
                    label = "HL"  # Equal - default to HL
            else:
                label = "HL"  # First swing low
            self.prev_swing_low = center_low
        
        return label
    
    def _compute_trend(self) -> tuple[Literal["bullish", "bearish", "neutral"], float]:
        """Compute trend direction and confidence from label history.
        
        Returns:
            Tuple of (trend_direction, confidence_score)
        """
        if len(self.label_history) < 2:
            return "neutral", 0.0
        
        # Get valid (non-None) labels
        valid_labels = [l for l in self.label_history if l is not None]
        if len(valid_labels) < 2:
            return "neutral", 0.0
        
        # Count bullish vs bearish labels
        bullish_labels = {"HH", "HL"}
        bearish_labels = {"LH", "LL"}
        
        bullish_count = sum(1 for l in valid_labels if l in bullish_labels)
        bearish_count = sum(1 for l in valid_labels if l in bearish_labels)
        total = len(valid_labels)
        
        # Determine trend
        if bullish_count > bearish_count and bullish_count / total >= 0.6:
            return "bullish", bullish_count / total
        elif bearish_count > bullish_count and bearish_count / total >= 0.6:
            return "bearish", bearish_count / total
        else:
            return "neutral", max(bullish_count, bearish_count) / total
    
    def _compute_clarity(self) -> float:
        """Compute structure clarity score (0-1).
        
        Measures swing sequence purity. Higher score = more consistent structure.
        
        Returns:
            Clarity score 0-1
        """
        if len(self.label_history) < 3:
            return 0.0
        
        valid_labels = [l for l in self.label_history if l is not None]
        if len(valid_labels) < 3:
            return 0.0
        
        # Check for alternations (H→L or L→H)
        alternations = 0
        continuations = 0
        
        for i in range(len(valid_labels) - 1):
            current = valid_labels[i]
            next_label = valid_labels[i + 1]
            
            current_type = current[0]  # 'H' or 'L'
            next_type = next_label[0]
            
            if current_type != next_type:
                alternations += 1
            else:
                continuations += 1
        
        total_transitions = alternations + continuations
        if total_transitions == 0:
            return 0.0
        
        # High clarity = few alternations (trending)
        # Low clarity = many alternations (choppy)
        clarity = continuations / total_transitions
        
        return clarity
    
    def _detect_chop(self) -> bool:
        """Detect if structure is choppy.
        
        Choppy structure = rapid consecutive alternations (H→L→H or L→H→L).
        
        Returns:
            True if chop detected
        """
        if len(self.label_history) < 4:
            return False
        
        valid_labels = [l for l in self.label_history if l is not None]
        if len(valid_labels) < 4:
            return False
        
        # Count consecutive alternations in recent labels
        recent = valid_labels[-6:] if len(valid_labels) >= 6 else valid_labels
        alternation_count = 0
        
        for i in range(len(recent) - 1):
            current = recent[i]
            next_label = recent[i + 1]
            
            # Check if alternation (H→L or L→H)
            if (current[0] == "H" and next_label[0] == "L") or (
                current[0] == "L" and next_label[0] == "H"
            ):
                alternation_count += 1
            else:
                # Reset on continuation
                alternation_count = 0
        
        # Chop if 2+ consecutive alternations
        return alternation_count >= 2
    
    def _detect_conflict(self) -> bool:
        """Detect if there are conflicting structural signals.
        
        Returns:
            True if conflict detected
        """
        # Simple conflict: both HH and LL in recent history
        if len(self.label_history) < 3:
            return False
        
        valid_labels = [l for l in self.label_history if l is not None]
        recent = valid_labels[-5:] if len(valid_labels) >= 5 else valid_labels
        
        has_hh = "HH" in recent
        has_ll = "LL" in recent
        
        return has_hh and has_ll
    
    def _detect_choch_event(self, new_label: str) -> bool:
        """Detect if new label represents a CHoCH event.
        
        CHoCH = Change of Character (trend reversal signal)
        
        Args:
            new_label: Newly detected structure label
        
        Returns:
            True if CHoCH detected
        """
        if len(self.label_history) < 2:
            return False
        
        # Get previous valid labels
        valid_labels = [l for l in self.label_history if l is not None]
        if len(valid_labels) < 2:
            return False
        
        # Check if trend changed
        prev_label = valid_labels[-2]  # Second to last (new_label is last)
        
        # CHoCH: H→L or L→H transition
        if (prev_label[0] == "H" and new_label[0] == "L") or (
            prev_label[0] == "L" and new_label[0] == "H"
        ):
            # Update CHoCH tracking
            self.last_choch_idx = self.bar_count
            self.last_choch_direction = "bullish" if new_label[0] == "H" else "bearish"
            return True
        
        return False


# Timeframe-to-swing-window mapping (optimized for each timeframe's noise level)
TIMEFRAME_SWING_WINDOWS = {
    "1s": 2,   # 1-second: Very noisy, need tight window
    "1m": 2,   # 1-minute: High noise, small swings
    "5m": 3,   # 5-minute: Medium noise, moderate swings
    "15m": 3,  # 15-minute: Medium noise, moderate swings
    "1h": 5,   # 1-hour: Lower noise, larger swings
}


def get_swing_window_for_timeframe(timeframe: str) -> int:
    """Get appropriate swing_window for a given timeframe.
    
    Different timeframes have different noise characteristics:
    - Shorter timeframes (1s, 1m) have high noise → need smaller swing_window (2)
    - Medium timeframes (15m) have moderate noise → use medium swing_window (3)
    - Longer timeframes (1h) have lower noise → can use larger swing_window (5)
    
    Args:
        timeframe: Timeframe string (e.g., "1m", "15m", "1h")
        
    Returns:
        Appropriate swing_window value for the timeframe
        
    Raises:
        ValueError: If timeframe is not recognized
        
    Example:
        >>> get_swing_window_for_timeframe("1m")
        2
        >>> get_swing_window_for_timeframe("1h")
        5
    """
    if timeframe not in TIMEFRAME_SWING_WINDOWS:
        raise ValueError(
            f"Unknown timeframe: {timeframe}. "
            f"Supported timeframes: {list(TIMEFRAME_SWING_WINDOWS.keys())}"
        )
    return TIMEFRAME_SWING_WINDOWS[timeframe]


def calculate_structure_labels(
    df: pd.DataFrame,
    swing_window: int = 5,
    high_column: str = "high",
    low_column: str = "low",
) -> pd.Series:
    """Calculate structure labels (HH/HL/LH/LL) for swing points.

    Identifies swing highs and lows using a rolling window approach, then
    labels them based on their relationship to previous swing points:
    - HH: Higher High (swing high above previous swing high)
    - HL: Higher Low (swing low above previous swing low)
    - LH: Lower High (swing high below previous swing high)
    - LL: Lower Low (swing low below previous swing low)

    CRITICAL: Labels are delayed by swing_window bars to prevent lookahead bias.
    When a swing point is detected at position i, its label appears at position
    i + swing_window. This matches the incremental StructureState behavior.

    Args:
        df: DataFrame with OHLCV data. Must contain high and low columns.
        swing_window: Number of periods to look back/forward to identify
                     swing points. Labels are delayed by this many bars.
                     Default is 5.
        high_column: Name of the high price column. Default is "high".
        low_column: Name of the low price column. Default is "low".

    Returns:
        Series containing structure labels indexed same as input DataFrame.
        Values are: "HH", "HL", "LH", "LL", or pd.NA for non-swing points.
        - First swing_window * 2 positions: pd.NA (warmup period)
        - Last swing_window positions: pd.NA (not enough future confirmation)
        - Labels appear swing_window bars after swing point detection

    Raises:
        ValueError: If required columns are missing.
        ValueError: If swing_window is less than 2.

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 102, 101, 103, 102, 104],
        ...     'low': [99, 100, 99, 101, 100, 102]
        ... })
        >>> labels = calculate_structure_labels(df, swing_window=2)
        >>> # Swing detected at position i appears at position i + 2
    """
    # Validate inputs
    if swing_window < 2:
        raise ValueError(f"swing_window must be >= 2, got {swing_window}")

    required_cols = {high_column, low_column}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    # Initialize result series with NA values
    labels = pd.Series(index=df.index, dtype="object")

    # Need at least swing_window * 2 + 1 rows to identify swing points
    if len(df) < swing_window * 2 + 1:
        return labels

    # Identify swing highs and lows, then delay labels by swing_window bars
    # to prevent lookahead bias. Labels appear swing_window bars after the
    # swing point is confirmed, matching the incremental StructureState behavior.

    # Track detected swing points and their labels (before delay)
    # Format: (swing_detection_idx, label, value)
    # The label will be assigned to position swing_detection_idx + swing_window
    swing_detections: list[tuple[int, str, float]] = []

    # Track previous swing high and low values
    prev_swing_high: float | None = None
    prev_swing_low: float | None = None

    # Detect swing points and determine their labels
    # We iterate through positions where we can detect swings AND where the
    # delayed label will not exceed the valid range (last swing_window positions
    # must be None).
    # For position i, we check if it's a swing point using window
    # [i-swing_window : i+swing_window+1]
    # The delayed label appears at position i + swing_window, which must be
    # < len(df) - swing_window
    # Therefore: i + swing_window < len(df) - swing_window
    # → i < len(df) - 2*swing_window
    for i in range(swing_window, len(df) - 2 * swing_window):
        idx = df.index[i]
        center_high = df.loc[idx, high_column]
        center_low = df.loc[idx, low_column]

        # Check if center point is a swing high (local maximum)
        # Use >= to match StructureState logic (all other values <= center)
        window_highs = df[high_column].iloc[i - swing_window : i + swing_window + 1]
        is_swing_high = all(
            center_high >= window_highs.iloc[j]
            for j in range(len(window_highs))
            if j != swing_window
        )

        # Check if center point is a swing low (local minimum)
        # Use <= to match StructureState logic (all other values >= center)
        window_lows = df[low_column].iloc[i - swing_window : i + swing_window + 1]
        is_swing_low = all(
            center_low <= window_lows.iloc[j]
            for j in range(len(window_lows))
            if j != swing_window
        )

        label: str | None = None

        # Process swing high (takes priority over swing low)
        if is_swing_high:
            if prev_swing_high is not None:
                if center_high > prev_swing_high:
                    label = "HH"
                elif center_high < prev_swing_high:
                    label = "LH"
                else:
                    label = "HH"  # Equal - default to HH
            else:
                # First swing high - label as HH
                label = "HH"
            prev_swing_high = center_high

            # Store detection: will assign label at position i + swing_window
            if label:
                swing_detections.append((i, label, center_high))

        # Process swing low (only if not already processed as swing high)
        elif is_swing_low:
            if prev_swing_low is not None:
                if center_low > prev_swing_low:
                    label = "HL"
                elif center_low < prev_swing_low:
                    label = "LL"
                else:
                    label = "HL"  # Equal - default to HL
            else:
                # First swing low - label as HL
                label = "HL"
            prev_swing_low = center_low

            # Store detection: will assign label at position i + swing_window
            if label:
                swing_detections.append((i, label, center_low))

    # Assign labels with delay: label detected at position i appears at
    # position i + swing_window
    # This matches StructureState behavior where update() at position i returns
    # label for swing detected at position i - swing_window
    for swing_idx, label, _ in swing_detections:
        delayed_idx = swing_idx + swing_window
        # Ensure delayed labels don't exceed len(df) - swing_window - 1
        # (last swing_window positions must remain None per zero-lookahead
        # guarantee)
        if delayed_idx < len(df) - swing_window:
            # Only assign if not already assigned (swing high takes priority
            # over swing low)
            if pd.isna(labels.iloc[delayed_idx]):
                labels.iloc[delayed_idx] = label

    return labels


def compute_structure_context_batch(
    df: pd.DataFrame,
    swing_window: int = 5,
    clarity_window: int = 10,
) -> pd.DataFrame:
    """Compute StructureContext fields for entire DataFrame (batch mode).
    
    Uses StructureContextTracker to produce derived structure fields for
    backtesting. Results match streaming mode exactly.
    
    Args:
        df: DataFrame with OHLC data (must have 'high', 'low', 'close' columns)
        swing_window: Swing detection window (default 5)
        clarity_window: Clarity computation window (default 10)
    
    Returns:
        DataFrame with original index and derived structure columns:
        - last_structure_label: Most recent swing label (forward-filled)
        - trend_direction: Derived trend direction
        - trend_confidence: 0-1 confidence score
        - structure_clarity: 0-1 purity score
        - is_chop: Boolean chop flag
        - structure_conflict_flag: Boolean conflict flag
        - last_swing_high: Last swing high price (forward-filled)
        - last_swing_low: Last swing low price (forward-filled)
        - last_swing_high_idx: Bar index of last swing high
        - last_swing_low_idx: Bar index of last swing low
        - choch_detected: Boolean CHoCH detected on this bar
        - choch_age: Bars since last CHoCH
        
    Note: BOS (Break of Structure) fields will be added in Structure Engine v2.0 Part 2
    
    Raises:
        ValueError: If required columns missing
    
    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 102, 101, 103, 102],
        ...     'low': [98, 100, 99, 101, 100],
        ...     'close': [99, 101, 100, 102, 101]
        ... })
        >>> result = compute_structure_context_batch(df, swing_window=2)
        >>> result['trend_direction']
    """
    # Validate required columns
    required_cols = {"high", "low", "close"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )
    
    # Initialize tracker
    tracker = StructureContextTracker(
        swing_window=swing_window,
        clarity_window=clarity_window,
    )
    
    # Process each row and collect contexts
    contexts = []
    for i in range(len(df)):
        ctx = tracker.update(
            high=df["high"].iloc[i],
            low=df["low"].iloc[i],
            close=df["close"].iloc[i],
        )
        contexts.append(ctx)
    
    # Convert to DataFrame
    result = pd.DataFrame([
        {
            "last_structure_label": ctx.last_structure_label,
            "trend_direction": ctx.trend_direction,
            "trend_confidence": ctx.trend_confidence,
            "structure_clarity": ctx.structure_clarity,
            "is_chop": ctx.is_chop,
            "structure_conflict_flag": ctx.structure_conflict_flag,
            "last_swing_high": ctx.last_swing_high,
            "last_swing_low": ctx.last_swing_low,
            "last_swing_high_idx": ctx.last_swing_high_idx,
            "last_swing_low_idx": ctx.last_swing_low_idx,
            "choch_detected": ctx.choch_detected,
            "choch_age": ctx.choch_age,
        }
        for ctx in contexts
    ], index=df.index)
    
    return result
