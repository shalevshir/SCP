# HTF Break of Structure (BOS) Detection

## Overview

The Break of Structure (BOS) detection module identifies trend continuation signals in Higher Timeframe (HTF) price data. A BOS occurs when price closes beyond a prior swing high or low, confirming that the trend is intact and likely to continue.

## Module Location

```
rule_engine/htf/structure/bos.py
```

## Function Signature

```python
def detect_bos(
    df: pd.DataFrame,
    swing_highs: list[int],
    swing_lows: list[int],
) -> pd.Series:
    """Detect Break of Structure events."""
```

## Concept: Break of Structure

### Bullish BOS
- **Condition**: Price closes **strictly above** (`>`) a prior swing high
- **Meaning**: Uptrend continuation confirmed
- **Indicates**: Buyers are in control, pushing prices to new highs

### Bearish BOS
- **Condition**: Price closes **strictly below** (`<`) a prior swing low
- **Meaning**: Downtrend continuation confirmed
- **Indicates**: Sellers are in control, pushing prices to new lows

### Key Distinction from CHoCH
- **BOS**: Confirms existing trend (continuation)
- **CHoCH** (Change of Character): Signals potential trend reversal

## Algorithm

### Detection Rules

1. **Strict Inequality Required**
   - Bullish BOS: `close > swing_high` (NOT `>=`)
   - Bearish BOS: `close < swing_low` (NOT `<=`)
   - Equality does NOT count as BOS

2. **Prior Swings Only**
   - Only compare to swings BEFORE the current bar
   - Future swings are not considered

3. **Ambiguous Case Rejection**
   - If `close` breaks BOTH a prior swing high AND swing low → NO label
   - Indicates volatility/liquidity sweep, not true structural continuation

4. **Single Label**
   - Multiple breaks in same direction → one BOS label
   - Don't track which specific swing was broken

5. **Index Alignment**
   - Returned Series index matches DataFrame index exactly
   - Ensures time-alignment with input candles

### Edge Cases Handled

- Empty swing lists → all `None`
- Empty DataFrame → empty Series
- Missing columns → `ValueError`
- First bars (no prior swings) → `None`
- Equality at swing level → `None` (strict inequality required)

## Usage Examples

### Basic Usage

```python
from rule_engine.htf.structure import detect_swings, detect_bos
import pandas as pd

# Load HTF data
df = pd.DataFrame({
    'high': [100, 102, 105, 103, 101, 103, 108, 106],
    'low': [98, 99, 102, 100, 98, 100, 105, 103],
    'close': [99, 101, 104, 102, 100, 102, 107, 105]
})

# Step 1: Detect swings
swing_highs, swing_lows = detect_swings(df, lookback=2)

# Step 2: Detect BOS
bos = detect_bos(df, swing_highs, swing_lows)

# Step 3: Find BOS events
for i, label in enumerate(bos):
    if pd.notna(label):
        print(f"Index {i}: {label} at close={df.iloc[i]['close']}")
```

### With Real HTF Data

```python
from data_layer.loader import HistoricalDataLoader
from rule_engine.htf.structure import detect_swings, detect_bos

# Load 1H data
loader = HistoricalDataLoader("data/gc_dx_ohlcv")
data_1h = loader.load(["GC"], "1h", start, end)
df = data_1h["GC"]

# Detect swings on 1H timeframe
swing_highs, swing_lows = detect_swings(df, lookback=5)

# Detect BOS
bos = detect_bos(df, swing_highs, swing_lows)

# Filter for BOS events
bos_events = bos[bos.notna()]
print(f"Found {len(bos_events)} BOS events on 1H timeframe")
```

### Integration with HTF Bias

```python
from rule_engine.htf.calculator import compute_htf_bias
from rule_engine.htf.structure import detect_swings, detect_bos

# Detect structure
swing_highs_1h, swing_lows_1h = detect_swings(df_1h, lookback=5)
bos_1h = detect_bos(df_1h, swing_highs_1h, swing_lows_1h)

# Use in HTF bias calculation
bos_detected = bos_1h.iloc[-1] is not None  # Most recent bar has BOS?

# Factor into HTF bias scoring
if bos_detected:
    print("BOS confirmed - trend continuation likely")
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `df` | `pd.DataFrame` | Yes | DataFrame with 'close', 'high', 'low' columns |
| `swing_highs` | `list[int]` | Yes | List of integer indices where swing highs occurred |
| `swing_lows` | `list[int]` | Yes | List of integer indices where swing lows occurred |

## Returns

Returns a `pd.Series` with the same index as the input DataFrame:
- `"bullish_bos"`: Close strictly above prior swing high
- `"bearish_bos"`: Close strictly below prior swing low
- `None` (or `NaN`): No BOS or ambiguous case

**Note**: pandas represents `None` as `NaN`. Use `pd.isna()` or `pd.notna()` to check for missing values.

## Validation Rules

### Input Validation
- DataFrame must contain 'close', 'high', 'low' columns (raises `ValueError` if missing)
- `swing_highs` and `swing_lows` must be lists of integers

### Detection Logic
- **Strict inequality**: Must use `>` and `<`, not `>=` or `<=`
- **Prior swings only**: Only compare to swings before current bar
- **Ambiguous rejection**: If breaks both directions → `None`
- **Single label**: Multiple breaks → one label

## Edge Cases

| Case | Behavior |
|------|----------|
| Empty DataFrame | Returns empty Series |
| Empty swing lists | Returns all `None` |
| Missing columns | Raises `ValueError` |
| First bars | `None` (no prior swings to break) |
| Equality | `None` (strict inequality required) |
| Breaks both directions | `None` (ambiguous/volatility) |
| Multiple breaks | Single BOS label |
| Custom DataFrame index | Preserved in output |

## Checking for BOS Events

```python
# Check if specific bar has BOS
if pd.notna(bos.iloc[6]):
    print(f"BOS at index 6: {bos.iloc[6]}")

# Count total BOS events
bullish_bos_count = (bos == "bullish_bos").sum()
bearish_bos_count = (bos == "bearish_bos").sum()

# Filter for BOS bars only
bos_bars = df[bos.notna()]

# Get most recent BOS
most_recent_bos = bos[bos.notna()].iloc[-1] if bos.notna().any() else None
```

## Performance Characteristics

- **Time Complexity**: O(n × s) where n = bars, s = swings
- **Space Complexity**: O(n) for result Series
- **Typical Performance**: < 2ms for 1000 bars with 20 swings
- **Optimization**: Uses generator expressions for efficiency

## Integration with Other Modules

### Upstream Dependencies

**Requires**:
- `detect_swings()` from `rule_engine.htf.structure.swings`

### Downstream Consumers

**Used By**:
1. **HTF Bias Calculator** - Confirms trend continuation
2. **CHoCH Detection** - Complementary analysis (BOS vs CHoCH)
3. **Trade Validation** - Validates trend alignment

### Example Integration Flow

```python
# Complete structure analysis flow
from rule_engine.htf.structure import detect_swings, detect_bos

# 1. Detect swings
swing_highs, swing_lows = detect_swings(df, lookback=5)

# 2. Detect BOS
bos = detect_bos(df, swing_highs, swing_lows)

# 3. Use in decision making
most_recent = bos.iloc[-1]
if most_recent == "bullish_bos":
    print("✓ Bullish trend continuation confirmed")
elif most_recent == "bearish_bos":
    print("✓ Bearish trend continuation confirmed")
else:
    print("⚠ No clear BOS - check for CHoCH or consolidation")
```

## Comparison with Other Concepts

| Concept | Trigger | Meaning |
|---------|---------|---------|
| **BOS** | Close beyond prior swing | Trend continuation |
| **CHoCH** | Break opposite swing first | Trend reversal |
| **Liquidity Sweep** | Wick beyond swing, close back inside | False breakout |
| **Inside Bar** | Stays within prior range | Consolidation |

## Testing

### Test Coverage
- 20 comprehensive test cases
- 100% code coverage
- All edge cases tested

### Running Tests

```bash
# Run BOS detection tests
pytest tests/unit/rule_engine/htf/structure/test_bos.py -v

# Run with coverage
pytest tests/unit/rule_engine/htf/structure/test_bos.py --cov=rule_engine.htf.structure.bos
```

### Key Test Scenarios
- Bullish and bearish BOS detection
- Strict inequality enforcement (equality doesn't count)
- Ambiguous case rejection (breaks both directions)
- Empty data handling
- Index preservation
- Integration with `detect_swings()`

## Configuration

### Recommended Settings

| Timeframe | Lookback | Rationale |
|-----------|----------|-----------|
| 1H | 5 | Standard HTF analysis |
| 15M | 3-5 | Faster confirmation |

### Tuning Guidelines

- **More restrictive**: Use larger lookback → fewer, more significant swings
- **More sensitive**: Use smaller lookback → more swings, more BOS events
- **Default (5)**: Good balance for HTF (1H, 15M)

## Logging

The function logs detection results at DEBUG level:

```python
logger.debug(
    f"Detected {bullish_count} bullish BOS and {bearish_count} bearish BOS "
    f"in {len(df)} bars ({len(swing_highs)} swing highs, {len(swing_lows)} swing lows)"
)
```

Enable debug logging:

```python
import logging
logging.getLogger('rule_engine.htf.structure.bos').setLevel(logging.DEBUG)
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

1. **Always use with detect_swings()**
   ```python
   swing_highs, swing_lows = detect_swings(df, lookback=5)
   bos = detect_bos(df, swing_highs, swing_lows)
   ```

2. **Check for NaN properly**
   ```python
   # Good
   if pd.notna(bos.iloc[i]):
       print(f"BOS detected: {bos.iloc[i]}")
   
   # Bad
   if bos.iloc[i] is not None:  # Won't work, pandas uses NaN
   ```

3. **Use with HTF data only**
   - Designed for 1H and 15M timeframes
   - Not recommended for 1M (too noisy)

4. **Consider ambiguous cases**
   ```python
   if bos.iloc[i] == "bullish_bos":
       # Clear bullish continuation
   elif bos.iloc[i] == "bearish_bos":
       # Clear bearish continuation
   elif pd.isna(bos.iloc[i]):
       # Could be: no break, ambiguous, or equality
       # Check context for clarification
   ```

## See Also

- [HTF Swing Detection](./htf-swing-detection.md)
- [CHoCH Detection](./htf-choch-detection.md) (coming soon)
- [HTF Structure Analysis](./htf-structure.md) (coming soon)
- [Liquidity Sweep Detection](./htf-liquidity-sweeps.md) (coming soon)

## References

- Notion Task: [Implement BOS detection](https://www.notion.so/2b42bd6fbda680888409d0cfcce590ed)
- Epic: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)
- Module: `rule_engine/htf/structure/bos.py`
- Tests: `tests/unit/rule_engine/htf/structure/test_bos.py`

