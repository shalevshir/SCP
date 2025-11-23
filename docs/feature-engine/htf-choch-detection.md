# HTF Change of Character (CHoCH) Detection

## Overview

The Change of Character (CHoCH) detection module identifies potential trend reversal signals in Higher Timeframe (HTF) price data. A CHoCH occurs when price breaks the opposite swing direction from the current trend, signaling that the market's character is changing and a reversal may be underway.

## Module Location

```
rule_engine/htf/structure/choch.py
```

## Function Signature

```python
def detect_choch(
    df: pd.DataFrame,
    swing_highs: list[int],
    swing_lows: list[int],
) -> pd.Series:
    """Detect Change of Character events."""
```

## Concept: Change of Character

### Bullish CHoCH
- **Condition**: In a bearish trend, price closes **strictly above** (`>`) a prior swing high
- **Meaning**: Potential reversal from bearish to bullish
- **Indicates**: Sellers losing control, buyers stepping in

### Bearish CHoCH
- **Condition**: In a bullish trend, price closes **strictly below** (`<`) a prior swing low
- **Meaning**: Potential reversal from bullish to bearish  
- **Indicates**: Buyers losing control, sellers stepping in

### Key Distinction from BOS

| Concept | Direction | Meaning | Example |
|---------|-----------|---------|---------|
| **CHoCH** | Opposite to trend | Reversal signal | Uptrend breaks prior swing low |
| **BOS** | Same as trend | Continuation signal | Uptrend breaks prior swing high |

## Algorithm

### Trend State Tracking

CHoCH requires internal trend state management:

```python
# Track current trend
current_trend = "neutral"  # Start with no established trend

# Update trend based on breaks
if in_bearish_trend and breaks_high:
    # CHoCH to bullish
    current_trend = "bullish"
elif in_bullish_trend and breaks_low:
    # CHoCH to bearish
    current_trend = "bearish"
elif neutral and breaks_high:
    # Establish bullish trend (not CHoCH)
    current_trend = "bullish"
elif neutral and breaks_low:
    # Establish bearish trend (not CHoCH)
    current_trend = "bearish"
```

### Detection Rules

1. **Strict Inequality Required**
   - Bullish CHoCH: `close > swing_high` (NOT `>=`)
   - Bearish CHoCH: `close < swing_low` (NOT `<=`)
   - Equality does NOT count as CHoCH

2. **Prior Swings Only**
   - Only compare to swings BEFORE the current bar
   - Future swings are not considered

3. **Opposite Direction Requirement**
   - CHoCH only when breaking OPPOSITE direction from current trend
   - Same direction breaks are BOS, not CHoCH

4. **First Break Establishes Trend**
   - First structural break from neutral establishes initial trend
   - This is NOT labeled as CHoCH (no prior trend to change from)

5. **Ambiguous Case Rejection**
   - If `close` breaks BOTH a prior swing high AND swing low → NO label
   - Indicates volatility/liquidity sweep, not clean reversal

6. **Single Label**
   - Multiple breaks in same direction → one CHoCH label
   - Don't track which specific swing was broken

7. **Index Alignment**
   - Returned Series index matches DataFrame index exactly
   - Ensures time-alignment with input candles

### Edge Cases Handled

- Empty swing lists → all `None`
- Empty DataFrame → empty Series
- Missing columns → `ValueError`
- First bars (no prior swings) → `None`
- First break (establishes trend) → `None` (not CHoCH)
- Equality at swing level → `None` (strict inequality required)

## Usage Examples

### Basic Usage

```python
from rule_engine.htf.structure import detect_swings, detect_choch
import pandas as pd

# Load HTF data
df = pd.DataFrame({
    'high': [100, 98, 96, 94, 92, 90, 88, 86, 84, 102],
    'low': [98, 96, 94, 92, 90, 88, 86, 84, 82, 99],
    'close': [99, 97, 95, 93, 91, 89, 87, 85, 83, 101]
})

# Step 1: Detect swings
swing_highs, swing_lows = detect_swings(df, lookback=2)

# Step 2: Detect CHoCH
choch = detect_choch(df, swing_highs, swing_lows)

# Step 3: Find CHoCH events
for i, label in enumerate(choch):
    if pd.notna(label):
        print(f"Index {i}: {label} - potential reversal at close={df.iloc[i]['close']}")
```

### Combined with BOS for Full Picture

```python
from rule_engine.htf.structure import detect_swings, detect_bos, detect_choch

# Load data
df = load_htf_data()

# Detect swings
swing_highs, swing_lows = detect_swings(df, lookback=5)

# Detect both BOS and CHoCH
bos = detect_bos(df, swing_highs, swing_lows)
choch = detect_choch(df, swing_highs, swing_lows)

# Interpret most recent structure
most_recent_bos = bos.iloc[-1] if bos.notna().any() else None
most_recent_choch = choch.iloc[-1] if choch.notna().any() else None

if most_recent_choch:
    print(f"⚠ TREND CHANGE: {most_recent_choch} - potential reversal")
elif most_recent_bos:
    print(f"✓ TREND CONTINUATION: {most_recent_bos} - trend intact")
else:
    print("⏸ CONSOLIDATION: No clear structural signal")
```

### Integration with HTF Bias

```python
from rule_engine.htf.structure import detect_swings, detect_bos, detect_choch

# Detect structure on 1H
swing_highs_1h, swing_lows_1h = detect_swings(df_1h, lookback=5)
bos_1h = detect_bos(df_1h, swing_highs_1h, swing_lows_1h)
choch_1h = detect_choch(df_1h, swing_highs_1h, swing_lows_1h)

# Check for recent CHoCH (reversal warning)
choch_detected = choch_1h.iloc[-1] if len(choch_1h) > 0 else None

if choch_detected:
    # Potential trend reversal - adjust bias accordingly
    print(f"Warning: {choch_detected} detected - trend may be reversing")
    # Reduce confidence in current trend direction
    bias_confidence = "low"
else:
    # No CHoCH - trend more reliable
    bias_confidence = "high"
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `df` | `pd.DataFrame` | Yes | DataFrame with 'close', 'high', 'low' columns |
| `swing_highs` | `list[int]` | Yes | List of integer indices where swing highs occurred |
| `swing_lows` | `list[int]` | Yes | List of integer indices where swing lows occurred |

## Returns

Returns a `pd.Series` with the same index as the input DataFrame:
- `"bullish_choch"`: Bearish trend broke prior swing high (reversal to bullish)
- `"bearish_choch"`: Bullish trend broke prior swing low (reversal to bearish)
- `None` (or `NaN`): No CHoCH, first break, or ambiguous case

**Note**: pandas represents `None` as `NaN`. Use `pd.isna()` or `pd.notna()` to check for missing values.

## Validation Rules

### Input Validation
- DataFrame must contain 'close', 'high', 'low' columns (raises `ValueError` if missing)
- `swing_highs` and `swing_lows` must be lists of integers

### Detection Logic
- **Strict inequality**: Must use `>` and `<`, not `>=` or `<=`
- **Prior swings only**: Only compare to swings before current bar
- **Opposite direction**: CHoCH only when breaking opposite of current trend
- **Ambiguous rejection**: If breaks both directions → `None`
- **Single label**: Multiple breaks → one label
- **Trend tracking**: Maintains internal trend state throughout iteration

## Edge Cases

| Case | Behavior |
|------|----------|
| Empty DataFrame | Returns empty Series |
| Empty swing lists | Returns all `None` |
| Missing columns | Raises `ValueError` |
| First bars | `None` (no prior swings to break) |
| First break | `None` (establishes trend, not CHoCH) |
| Equality | `None` (strict inequality required) |
| Breaks both directions | `None` (ambiguous/volatility) |
| Multiple breaks | Single CHoCH label |
| Custom DataFrame index | Preserved in output |

## Checking for CHoCH Events

```python
# Check if specific bar has CHoCH
if pd.notna(choch.iloc[6]):
    print(f"CHoCH at index 6: {choch.iloc[6]} - trend reversal signal")

# Count total CHoCH events
bullish_choch_count = (choch == "bullish_choch").sum()
bearish_choch_count = (choch == "bearish_choch").sum()

# Filter for CHoCH bars only
choch_bars = df[choch.notna()]

# Get most recent CHoCH
most_recent_choch = choch[choch.notna()].iloc[-1] if choch.notna().any() else None

# Check for recent reversal (last 5 bars)
recent_choch = choch.iloc[-5:].notna().any()
if recent_choch:
    print("⚠ Recent CHoCH detected - trend may have reversed")
```

## Performance Characteristics

- **Time Complexity**: O(n × s) where n = bars, s = swings
- **Space Complexity**: O(n) for result Series + O(1) for trend state
- **Typical Performance**: < 2ms for 1000 bars with 20 swings
- **Optimization**: Uses generator expressions for efficiency

## Integration with Other Modules

### Upstream Dependencies

**Requires**:
- `detect_swings()` from `rule_engine.htf.structure.swings`

### Downstream Consumers

**Used By**:
1. **HTF Bias Calculator** - Detects potential trend changes
2. **Trade Validation** - Warns of possible reversals
3. **Risk Management** - Adjusts position sizing on trend change

### Example Integration Flow

```python
# Complete structure analysis flow
from rule_engine.htf.structure import detect_swings, detect_bos, detect_choch

# 1. Detect swings
swing_highs, swing_lows = detect_swings(df, lookback=5)

# 2. Detect BOS (continuation)
bos = detect_bos(df, swing_highs, swing_lows)

# 3. Detect CHoCH (reversal)
choch = detect_choch(df, swing_highs, swing_lows)

# 4. Make trading decision
most_recent_choch = choch.iloc[-1]
most_recent_bos = bos.iloc[-1]

if most_recent_choch == "bullish_choch":
    print("⚠ REVERSAL: Trend changing to bullish")
    action = "wait_for_confirmation"
elif most_recent_choch == "bearish_choch":
    print("⚠ REVERSAL: Trend changing to bearish")
    action = "wait_for_confirmation"
elif most_recent_bos == "bullish_bos":
    print("✓ CONTINUATION: Bullish trend intact")
    action = "look_for_long_entries"
elif most_recent_bos == "bearish_bos":
    print("✓ CONTINUATION: Bearish trend intact")
    action = "look_for_short_entries"
else:
    print("⏸ NEUTRAL: No clear structural signal")
    action = "stay_flat"
```

## Comparison with Other Concepts

| Concept | Trigger | Meaning | Trade Action |
|---------|---------|---------|--------------|
| **CHoCH** | Break opposite swing | Trend reversal | Wait for confirmation |
| **BOS** | Break same swing | Trend continuation | Enter in trend direction |
| **Liquidity Sweep** | Wick beyond swing, close back | False breakout | Fade the move |
| **Inside Bar** | Stays within prior range | Consolidation | Wait for breakout |

## Decision Matrix

| Current Trend | Break Direction | Result | Interpretation |
|--------------|-----------------|--------|----------------|
| Bullish | Breaks high | BOS | Trend continues up |
| Bullish | Breaks low | **CHoCH** | Potential reversal down |
| Bearish | Breaks low | BOS | Trend continues down |
| Bearish | Breaks high | **CHoCH** | Potential reversal up |
| Neutral | Breaks high | — | Establishes bullish |
| Neutral | Breaks low | — | Establishes bearish |

## Testing

### Test Coverage
- 19 comprehensive test cases
- 100% code coverage
- All edge cases tested
- Trend state logic validated

### Running Tests

```bash
# Run CHoCH detection tests
pytest tests/unit/rule_engine/htf/structure/test_choch.py -v

# Run with coverage
pytest tests/unit/rule_engine/htf/structure/test_choch.py --cov=rule_engine.htf.structure.choch
```

### Key Test Scenarios
- Bullish and bearish CHoCH detection
- Trend state tracking correctness
- First break establishes trend (not CHoCH)
- Strict inequality enforcement
- Ambiguous case rejection
- Empty data handling
- Index preservation
- Integration with `detect_swings()` and `detect_bos()`
- Complementary to BOS (different output)

## Configuration

### Recommended Settings

| Timeframe | Lookback | Rationale |
|-----------|----------|-----------|
| 1H | 5 | Standard HTF analysis |
| 15M | 3-5 | Faster confirmation |

### Tuning Guidelines

- **More restrictive**: Use larger lookback → fewer, more significant swings → fewer CHoCH signals
- **More sensitive**: Use smaller lookback → more swings → more CHoCH signals
- **Default (5)**: Good balance for HTF (1H, 15M)

## Logging

The function logs detection results at DEBUG level:

```python
logger.debug(
    f"Detected {bullish_count} bullish CHoCH and {bearish_count} bearish CHoCH "
    f"in {len(df)} bars ({len(swing_highs)} swing highs, {len(swing_lows)} swing lows)"
)
```

Enable debug logging:

```python
import logging
logging.getLogger('rule_engine.htf.structure.choch').setLevel(logging.DEBUG)
```

## Error Handling

### Common Errors

**Missing Column Error**:
```python
ValueError: Missing required column(s): {'close'}. Available columns: ['high', 'low']
```
**Solution**: Ensure DataFrame has 'close', 'high', and 'low' columns.

**Invalid Swing Indices**:
- Out of bounds indices are silently skipped (handled by `swing_idx < i` check)
- No error raised for invalid indices

## Best Practices

1. **Always use with detect_swings() and detect_bos()**
   ```python
   swing_highs, swing_lows = detect_swings(df, lookback=5)
   bos = detect_bos(df, swing_highs, swing_lows)
   choch = detect_choch(df, swing_highs, swing_lows)
   # Use both for complete picture
   ```

2. **Check for NaN properly**
   ```python
   # Good
   if pd.notna(choch.iloc[i]):
       print(f"CHoCH detected: {choch.iloc[i]}")
   
   # Bad
   if choch.iloc[i] is not None:  # Won't work, pandas uses NaN
   ```

3. **Use with HTF data only**
   - Designed for 1H and 15M timeframes
   - Not recommended for 1M (too noisy)

4. **Wait for confirmation after CHoCH**
   ```python
   if choch.iloc[-1] == "bullish_choch":
       # Don't immediately enter long
       # Wait for pullback or confirmation
       print("Potential reversal to bullish - wait for confirmation")
   ```

5. **Consider CHoCH with other factors**
   ```python
   # CHoCH is a warning signal, not a trade signal
   if choch.iloc[-1] and vwap_confirms and volume_spike:
       print("CHoCH confirmed by VWAP and volume - reversal likely")
   else:
       print("CHoCH detected but lacking confirmation - be cautious")
   ```

## Trading Applications

### Risk Management
```python
# Reduce position size after CHoCH
if choch.iloc[-5:].notna().any():
    position_size *= 0.5  # Cut position size by half
    print("Recent CHoCH - reducing exposure")
```

### Entry Signals
```python
# Wait for pullback after CHoCH
if choch.iloc[-1] == "bullish_choch":
    # Don't chase - wait for pullback to VWAP or demand zone
    entry_type = "wait_for_pullback"
elif bos.iloc[-1] == "bullish_bos":
    # Trend intact - can enter on minor pullback
    entry_type = "enter_on_dip"
```

### Stop Loss Adjustment
```python
# Tighten stops after CHoCH
if choch.iloc[-1]:
    # Move stop to recent swing
    stop_loss = recent_swing_level
    print(f"CHoCH detected - tightening stop to {stop_loss}")
```

## See Also

- [HTF Swing Detection](./htf-swing-detection.md)
- [BOS Detection](./htf-bos-detection.md)
- [HTF Structure Analysis](./htf-structure.md) (coming soon)
- [Liquidity Sweep Detection](./htf-liquidity-sweeps.md) (coming soon)

## References

- Notion Task: [Implement CHoCH detection](https://www.notion.so/2b42bd6fbda680328937dde1384c14c9)
- Epic: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)
- Module: `rule_engine/htf/structure/choch.py`
- Tests: `tests/unit/rule_engine/htf/structure/test_choch.py`

