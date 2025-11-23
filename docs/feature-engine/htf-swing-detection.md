# HTF Swing Detection

## Overview

The swing detection module identifies swing highs and lows in price data for Higher Timeframe (HTF) analysis. It provides the foundation for Break of Structure (BOS), Change of Character (CHoCH), and liquidity sweep detection.

## Module Location

```
rule_engine/htf/structure/swings.py
```

## Function Signature

```python
def detect_swings(
    df: pd.DataFrame,
    lookback: int = 5,
) -> tuple[list[int], list[int]]:
    """Detect swing highs and lows in price data."""
```

## Algorithm

### Swing High Detection
A **swing high** is a local maximum where the `high` price is greater than or equal to all prices in a surrounding window:
- Window size: `2 * lookback + 1` bars
- Current bar must be at the center of the window
- Current bar's high must be >= all other highs in the window

### Swing Low Detection
A **swing low** is a local minimum where the `low` price is less than or equal to all prices in a surrounding window:
- Window size: `2 * lookback + 1` bars
- Current bar must be at the center of the window
- Current bar's low must be <= all other lows in the window

### Boundary Exclusion
The first `lookback` bars and last `lookback` bars **cannot** be swing points because they lack sufficient context on both sides.

## Usage Examples

### Basic Usage

```python
from rule_engine.htf.structure.swings import detect_swings
import pandas as pd

# Load 1H data
df = pd.DataFrame({
    'high': [100, 102, 105, 103, 101, 103, 106, 104],
    'low': [98, 99, 102, 100, 98, 100, 103, 101]
})

# Detect swings with 2-bar lookback
swing_highs, swing_lows = detect_swings(df, lookback=2)

print(f"Swing highs at indices: {swing_highs}")  # [2]
print(f"Swing lows at indices: {swing_lows}")    # [4]
```

### With Real HTF Data

```python
from rule_engine.htf.structure import detect_swings
from data_layer.loader import HistoricalDataLoader

# Load 1H data
loader = HistoricalDataLoader("data/gc_dx_ohlcv")
data_1h = loader.load(["GC"], "1h", start, end)

# Detect swings on 1H timeframe
swing_highs, swing_lows = detect_swings(
    data_1h["GC"],
    lookback=5  # 5-bar confirmation
)

# Use swings for BOS detection
from rule_engine.htf.structure.bos import detect_bos
bos_events = detect_bos(data_1h["GC"], swing_highs, swing_lows)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `df` | `pd.DataFrame` | Required | DataFrame with 'high' and 'low' columns |
| `lookback` | `int` | 5 | Number of bars before and after for confirmation |

## Returns

Returns a tuple of two lists:
- `swing_highs`: List of integer indices where swing highs occur
- `swing_lows`: List of integer indices where swing lows occur

**Note**: Returns integer positions (0-based), not DataFrame index values.

## Validation Rules

### Input Validation
- `df` must contain 'high' and 'low' columns (raises `ValueError` if missing)
- `lookback` must be >= 1 (raises `ValueError` if invalid)

### Data Requirements
- Minimum rows: `2 * lookback + 1`
- If insufficient data, returns empty lists `([], [])`

## Edge Cases Handled

| Case | Behavior |
|------|----------|
| Empty DataFrame | Returns `([], [])` |
| Insufficient data | Returns `([], [])` |
| Missing columns | Raises `ValueError` |
| Invalid lookback | Raises `ValueError` |
| Flat prices (all equal) | All interior bars are swing points |
| All increasing | No swings (no interior peaks) |
| All decreasing | No swings (no interior troughs) |
| Duplicate values | Includes all bars at same level |
| Custom DataFrame index | Returns integer positions, not index values |

## Performance Characteristics

- **Time Complexity**: O(n * w) where n = number of bars, w = window size (2*lookback+1)
- **Space Complexity**: O(n) for storing swing indices
- **Typical Performance**: < 1ms for 1000 bars with lookback=5

## Integration with Other Modules

### Downstream Consumers

1. **BOS Detection** (`rule_engine/htf/structure/bos.py`)
   - Uses swing indices to detect Break of Structure
   - Identifies when price closes beyond prior swing high/low

2. **CHoCH Detection** (`rule_engine/htf/structure/choch.py`)
   - Uses swing indices to detect Change of Character
   - Identifies trend reversals

3. **Liquidity Sweeps** (`rule_engine/htf/structure/liquidity.py`)
   - Uses swing indices to identify liquidity pools
   - Detects wick violations of swing levels

### Example Integration

```python
from rule_engine.htf.structure import detect_swings
from rule_engine.htf.structure.bos import detect_bos

# Step 1: Detect swings
swing_highs, swing_lows = detect_swings(df, lookback=5)

# Step 2: Use swings for BOS detection
bos_events = detect_bos(df, swing_highs, swing_lows)
```

## Comparison with FeatureEngine Structure

| Feature | HTF Swing Detection | FeatureEngine Structure |
|---------|---------------------|-------------------------|
| **Output** | Index lists | Labeled Series (HH, HL, LH, LL) |
| **Purpose** | Identify swing points | Label market structure |
| **Usage** | Foundation for structure analysis | Direct structure classification |
| **State** | Stateless (vectorized) | Can be stateful (incremental) |

The HTF swing detection provides **raw swing points** that can be consumed by multiple structure analysis modules, while FeatureEngine structure provides **semantic labels** about the market structure.

## Testing

### Test Coverage
- 18 comprehensive test cases
- 100% code coverage
- All edge cases tested

### Running Tests

```bash
# Run swing detection tests
pytest tests/unit/rule_engine/htf/structure/test_swings.py -v

# Run with coverage
pytest tests/unit/rule_engine/htf/structure/test_swings.py --cov=rule_engine.htf.structure.swings
```

### Key Test Scenarios
- Basic swing detection (clear peaks and troughs)
- Multiple lookback values (1, 3, 5)
- Edge cases (empty, insufficient data, missing columns)
- Boundary conditions (first/last bars excluded)
- Special patterns (flat, increasing, decreasing)
- DataFrame index handling

## Configuration

### Recommended Lookback Values

| Timeframe | Recommended Lookback | Rationale |
|-----------|---------------------|-----------|
| 1H | 5 | Balances confirmation with responsiveness |
| 15M | 3-5 | Faster confirmation for lower timeframe |
| 1M | Not recommended | Too noisy, use FeatureEngine structure |

### Tuning Guidelines

- **Smaller lookback** (1-2): More sensitive, more swings detected
- **Larger lookback** (5-10): More significant swings only, fewer false positives
- **Default (5)**: Good balance for HTF analysis (1H, 15M)

## Logging

The function logs detection results at DEBUG level:

```python
logger.debug(
    f"Detected {len(swing_highs)} swing highs and {len(swing_lows)} swing lows "
    f"in {len(df)} bars (lookback={lookback})"
)
```

Enable debug logging to see detection statistics:

```python
import logging
logging.getLogger('rule_engine.htf.structure.swings').setLevel(logging.DEBUG)
```

## Error Handling

### Common Errors

**Missing Column Error**:
```python
ValueError: Missing required column(s): {'high'}. Available columns: ['close', 'volume']
```
**Solution**: Ensure DataFrame has 'high' and 'low' columns.

**Invalid Lookback Error**:
```python
ValueError: lookback must be >= 1
```
**Solution**: Use lookback >= 1.

## Best Practices

1. **Use appropriate lookback for timeframe**
   - 1H: lookback=5 (standard)
   - 15M: lookback=3-5 (slightly faster)

2. **Handle empty results**
   ```python
   highs, lows = detect_swings(df, lookback=5)
   if not highs and not lows:
       logger.warning("No swings detected - data may be insufficient or flat")
   ```

3. **Validate data before detection**
   ```python
   if len(df) < 2 * lookback + 1:
       logger.warning(f"Insufficient data: need {2*lookback+1} bars, got {len(df)}")
   ```

4. **Use with HTF data only**
   - Designed for 1H and 15M timeframes
   - Not suitable for 1M (use FeatureEngine structure instead)

## See Also

- [HTF Structure Analysis](./htf-structure.md)
- [BOS Detection](./htf-bos-detection.md) (coming soon)
- [CHoCH Detection](./htf-choch-detection.md) (coming soon)
- [FeatureEngine Structure](./structure.md)

## References

- Notion Task: [Implement swing identification](https://www.notion.so/2b42bd6fbda680af8811ec757faffe73)
- Epic: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)
- Module: `rule_engine/htf/structure/swings.py`
- Tests: `tests/unit/rule_engine/htf/structure/test_swings.py`

