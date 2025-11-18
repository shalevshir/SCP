# Structure Labels

[← Back to Feature Engine](./README.md)

**Purpose:** Identify swing points in price action and label them as HH (Higher High), HL (Higher Low), LH (Lower High), or LL (Lower Low) for structure analysis.

---

## Overview

Structure labels identify key swing points (local maxima and minima) in price action and classify them based on their relationship to previous swing points. This is essential for structure-first trading analysis per Shir Capital SOP.

### Labels

- **HH (Higher High)**: Swing high above previous swing high (bullish structure)
- **HL (Higher Low)**: Swing low above previous swing low (bullish structure)
- **LH (Lower High)**: Swing high below previous swing high (bearish structure)
- **LL (Lower Low)**: Swing low below previous swing low (bearish structure)

---

## API Reference

### `calculate_structure_labels()`

```python
def calculate_structure_labels(
    df: pd.DataFrame,
    swing_window: int = 5,
    high_column: str = "high",
    low_column: str = "low",
) -> pd.Series
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `df` | `pd.DataFrame` | DataFrame with OHLCV data. Must contain high and low columns. |
| `swing_window` | `int` | Number of periods to look back/forward to identify swing points. Default is 5. Must be >= 2. |
| `high_column` | `str` | Name of the high price column. Default is "high". |
| `low_column` | `str` | Name of the low price column. Default is "low". |

#### Returns

Series containing structure labels indexed same as input DataFrame. Values are: "HH", "HL", "LH", "LL", or pd.NA for non-swing points.

#### Raises

- `ValueError`: If required columns are missing or swing_window < 2.

---

## Algorithm

1. **Swing High Detection**: Identifies local maxima using rolling window
   - A swing high is a point where the high price is the maximum in a window of `swing_window` periods on each side

2. **Swing Low Detection**: Identifies local minima using rolling window
   - A swing low is a point where the low price is the minimum in a window of `swing_window` periods on each side

3. **Labeling**: Compares each swing point to the previous swing point of the same type
   - Higher than previous → HH (highs) or HL (lows)
   - Lower than previous → LH (highs) or LL (lows)

---

## Usage Examples

### Basic Usage

```python
from feature_engine import calculate_structure_labels
import pandas as pd

df = pd.DataFrame({
    'high': [100, 102, 101, 103, 102, 104, 103, 105],
    'low': [99, 100, 99, 101, 100, 102, 101, 103]
})

labels = calculate_structure_labels(df, swing_window=2)
print(labels)
```

### Identifying Bullish Structure

```python
# Find bullish structure patterns (HH/HL)
bullish = df[df['structure_label'].isin(['HH', 'HL'])]
print(f"Bullish structure points: {len(bullish)}")
```

### Identifying Bearish Structure

```python
# Find bearish structure patterns (LH/LL)
bearish = df[df['structure_label'].isin(['LH', 'LL'])]
print(f"Bearish structure points: {len(bearish)}")
```

---

## Requirements

- **Minimum Data**: Need at least `2 * swing_window + 1` rows to identify swing points
- **Data Quality**: High and low columns must be valid numeric values
- **Sorted Data**: Data should be sorted chronologically for accurate swing detection

---

## Edge Cases

- **Insufficient Data**: Returns all NA labels if data length < `2 * swing_window + 1`
- **Flat Markets**: Equal swing points are labeled as HH/HL (bullish default)
- **Simultaneous Highs/Lows**: If both occur at same index, swing high takes precedence

---

## Integration with Rule Engine

Structure labels are used in Rule Engine scoring for:

- **Structure Alignment Factor**: Awards points when price action matches HTF bias
- **Setup Type Determination**: Helps identify continuation vs fade setups
- **HTF Bias Confirmation**: Validates higher timeframe structure

---

## Related Documentation

- [Feature Engine Overview](./README.md)
- [Integration Layer](./integration.md)
- [Rule Engine Scoring](../../rule_engine/scoring.py)

