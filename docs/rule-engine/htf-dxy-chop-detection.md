# HTF DXY Chop Detection

## Overview

DXY chop detection identifies when the Dollar Index (DXY) is exhibiting wick-to-wick behavior, indicating a ranging/choppy market condition with low directional conviction. When DXY chop is detected, the HTF bias is automatically forced to neutral to prevent trades during uncertain market conditions.

## What is "Chop"?

**Chop** (or "ranging") occurs when price action shows large wicks relative to the candle body, indicating indecision and back-and-forth movement between buyers and sellers. This wick-to-wick behavior signals that neither bulls nor bears have control.

### Visual Example

```
Chop Candle (Large Wicks):        Trending Candle (Small Wicks):
       |                                    ----
       |  ← Upper wick                      |   ← Small wick
     ----                                  ----
     |  |  ← Small body                    |  |  ← Large body
     ----                                  |  |
       |  ← Lower wick                     ----
       |                                    |   ← Small wick
                                           ----
```

### Wick Ratio Formula

```python
upper_wick = high - max(open, close)
lower_wick = min(open, close) - low
body_size = abs(close - open)

wick_ratio = (upper_wick + lower_wick) / body_size
```

**Interpretation:**
- **High ratio (≥ 0.5)**: Chop candle - wicks dominate the body
- **Low ratio (< 0.5)**: Trending candle - body dominates the wicks
- **Infinite ratio**: Doji candle (zero body) - always treated as chop

## Detection Logic

### Parameters

- **`wick_threshold`** (default: 0.5)
  - Minimum wick ratio to consider a candle as "chop"
  - Higher values = stricter chop detection
  - Lower values = more sensitive chop detection

- **`min_chop_candles`** (default: 3)
  - Number of consecutive chop candles required to trigger chop condition
  - Default of 3 prevents false signals from single chop candles

### Detection Process

1. **Calculate wick ratio** for each candle
2. **Identify chop candles** (ratio ≥ threshold)
3. **Count consecutive chop candles**
4. **Trigger chop condition** when count ≥ min_chop_candles

### Consecutive Counting Rules

- **Counter increments** when chop candle appears
- **Counter resets to 0** when non-chop candle appears
- **Chop triggered** from the Nth candle onwards (N = min_chop_candles)

### Example Sequence

```
Candle:  1     2     3     4     5     6     7
Type:    chop  chop  chop  trend chop  chop  chop
Count:   1     2     3     0     1     2     3
Chop?    No    No    Yes   No    No    No    Yes
         ↑     ↑     ↑           ↑     ↑     ↑
         Need 3 consecutive      Reset Count reaches 3
```

## Function API

```python
from rule_engine.htf.dxy import detect_dxy_chop

def detect_dxy_chop(
    dxy_df: pd.DataFrame,
    wick_threshold: float = 0.5,
    min_chop_candles: int = 3,
) -> pd.Series:
    """Detect DXY chop (ranging) conditions.
    
    Args:
        dxy_df: DataFrame with DXY OHLC data (high, low, open, close)
        wick_threshold: Minimum wick ratio to consider chop (default 0.5)
        min_chop_candles: Consecutive chop candles needed (default 3)
    
    Returns:
        Series with boolean dxy_chop flag
    
    Raises:
        ValueError: If required columns missing or invalid parameters
    """
```

## Usage Examples

### Basic Usage

```python
import pandas as pd
from rule_engine.htf.dxy import detect_dxy_chop

# Load DXY 1H data
dxy_df = pd.DataFrame({
    "high": [101.0, 101.5, 102.0, 102.5, 103.0],
    "low": [99.0, 99.5, 100.0, 100.5, 101.0],
    "open": [100.0, 100.5, 101.0, 101.5, 102.0],
    "close": [100.2, 100.7, 101.2, 101.7, 102.2],
})

# Detect chop
chop_flags = detect_dxy_chop(dxy_df)
print(chop_flags)
# Output:
# 0    False  (1st candle, not enough consecutive)
# 1    False  (2nd candle, not enough consecutive)
# 2     True  (3rd candle, chop triggered)
# 3     True  (4th candle, still in chop)
# 4     True  (5th candle, still in chop)
```

### Custom Parameters

```python
# More sensitive: lower threshold
chop_sensitive = detect_dxy_chop(dxy_df, wick_threshold=0.3)

# Stricter: require 5 consecutive candles
chop_strict = detect_dxy_chop(dxy_df, wick_threshold=0.5, min_chop_candles=5)

# Very strict: high threshold + long sequence
chop_very_strict = detect_dxy_chop(dxy_df, wick_threshold=1.0, min_chop_candles=5)
```

### Integration with HTF Calculator

```python
from rule_engine.htf.calculator import compute_htf_bias

# Compute HTF bias with DXY chop detection
htf_bias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
    dxy_1h=dxy_df,  # Pass DXY DataFrame for chop detection
    timestamp=current_timestamp
)

# Check if chop detected
if htf_bias.dxy_chop_detected:
    print("⚠️ DXY chop detected - HTF bias forced to neutral")
    print(f"Bias: {htf_bias.bias}")  # Will be "neutral"
    print(f"Direction: {htf_bias.direction}")  # Will be "neutral"
    print(f"Score: {htf_bias.score}")  # Capped at 5.0
```

## Effect on HTF Bias

When DXY chop is detected, the HTF calculator automatically applies the following overrides:

### Before Chop Detection

```python
HTFBias(
    bias="bullish",
    direction="long",
    score=8.5,
    confidence="high",
    dxy_chop_detected=False,
    ...
)
```

### After Chop Detection

```python
HTFBias(
    bias="neutral",           # ← Forced to neutral
    direction="neutral",      # ← Forced to neutral
    score=5.0,                # ← Capped at 5.0
    confidence="medium",      # ← Downgraded
    dxy_chop_detected=True,   # ← Flag set
    ...
)
```

### Override Logic

The override applies regardless of how strong the original bias was:

```python
# Original: Strong bullish (HH + bullish EMAs + DXY aligned)
# DXY chop detected
# Result: Neutral (chop overrides all other signals)
```

## Configuration

DXY chop detection parameters can be configured in your trading system:

```yaml
# config/dxy_chop.yaml
chop_detection:
  enabled: true
  wick_threshold: 0.5      # Default threshold
  min_chop_candles: 3      # Default consecutive count
  
  # Optional: Different thresholds per session
  sessions:
    london:
      wick_threshold: 0.4  # More sensitive during London
    new_york:
      wick_threshold: 0.6  # Less sensitive during NY
```

## Validation and Edge Cases

### Input Validation

```python
# ✓ Valid
detect_dxy_chop(df, wick_threshold=0.5, min_chop_candles=3)

# ✗ Invalid threshold
detect_dxy_chop(df, wick_threshold=0)      # ValueError: must be > 0
detect_dxy_chop(df, wick_threshold=-0.5)   # ValueError: must be > 0

# ✗ Invalid min_candles
detect_dxy_chop(df, min_chop_candles=0)    # ValueError: must be >= 1
```

### Edge Cases

**Doji Candles (Zero Body)**
```python
# Doji: open == close
# Treated as infinite wick ratio → always chop
doji_df = pd.DataFrame({
    "high": [101.0], "low": [99.0],
    "open": [100.0], "close": [100.0]  # Same as open
})
result = detect_dxy_chop(doji_df, min_chop_candles=1)
# result[0] == True (doji always treated as chop)
```

**NaN Values**
```python
# NaN in data → treated as non-chop, doesn't break sequence
nan_df = pd.DataFrame({
    "high": [101.0, float('nan'), 102.0],
    "low": [99.0, 99.5, 100.0],
    "open": [100.0, 100.5, 101.0],
    "close": [100.2, 100.7, 101.2]
})
result = detect_dxy_chop(nan_df)
# result[1] == False (NaN treated as non-chop)
```

**Insufficient Data**
```python
# Less data than min_chop_candles
small_df = pd.DataFrame({
    "high": [101.0, 101.5],
    "low": [99.0, 99.5],
    "open": [100.0, 100.5],
    "close": [100.2, 100.7]
})
result = detect_dxy_chop(small_df, min_chop_candles=3)
# All False (need 3 candles, only have 2)
```

**Empty DataFrame**
```python
empty_df = pd.DataFrame(columns=["high", "low", "open", "close"])
result = detect_dxy_chop(empty_df)
# Empty Series returned
```

## Testing

Comprehensive test coverage (22 tests):

```bash
# Run DXY chop detection tests
uv run pytest tests/unit/rule_engine/htf/dxy/test_dxy_chop.py -v

# Run HTF calculator integration tests
uv run pytest tests/unit/rule_engine/htf/test_htf_calculator.py -v
```

**Test Categories:**
- Basic detection logic
- Consecutive counting accuracy
- Threshold variations
- Edge cases (doji, NaN, empty data)
- Input validation
- HTF calculator integration
- Neutral bias override

## Performance Considerations

- **Computational Cost**: O(n) where n = number of candles
- **Memory**: Minimal (single Series stored)
- **Vectorized**: Uses pandas operations for efficiency

## Troubleshooting

### Common Issues

**Issue:** Chop not detected despite visible wicks
```python
# Solution: Lower threshold or check data quality
result = detect_dxy_chop(df, wick_threshold=0.3)  # More sensitive
```

**Issue:** Too many false chop signals
```python
# Solution: Increase threshold or require more consecutive candles
result = detect_dxy_chop(df, wick_threshold=0.7, min_chop_candles=4)
```

**Issue:** Chop detected but HTF bias not neutral
```python
# Solution: Ensure dxy_1h DataFrame passed to compute_htf_bias
htf_bias = compute_htf_bias(f1h, f15m, dxy_1h=dxy_df)  # Must pass dxy_1h
```

## Related Documentation

- [HTF Bias Engine](htf-bias-engine.md) - Overall HTF calculation
- [DXY Correlation](../feature-engine/dxy-correlation.md) - DXY correlation feature
- [Rule Engine Integration](integration.md) - Full system integration

## Changelog

### v1.0.0 (2025-11-24)
- Initial implementation of DXY chop detection
- Wick-to-body ratio calculation with configurable threshold
- Consecutive chop candle counting
- HTF calculator integration
- Automatic neutral bias forcing
- Comprehensive test suite (22 unit + 7 integration tests)
- DoD: ✓ All requirements met

---

**Task**: Add DXY chop detection  
**Status**: ✅ Complete  
**Story**: Add DXY Chop Detection, Correlation & Inversion Logic

