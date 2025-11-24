# HTF Conflict Rules

**Status**: ✅ Complete  
**Module**: `rule_engine/htf/conflicts.py`  
**Task**: [Define conflict rules](https://www.notion.so/2b42bd6fbda6809c9609e5194ae5ecd3)  
**Epic**: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)

---

## Overview

The HTF Conflict Rules system automatically detects conflicting market conditions across multiple timeframes and neutralizes bias to prevent trading during uncertain conditions. This implements the "structure-first" principle from Shir Capital's SOP.

### Purpose

- **Prevent false signals** during multi-timeframe conflicts
- **Enforce discipline** by requiring alignment across timeframes
- **Reduce risk** by avoiding trades during choppy/conflicting conditions
- **Provide transparency** with clear conflict reasons in logs

### Design Philosophy

> "No trade without confirmation. Structure before signal. Discipline before profit."

When 1H and 15M timeframes disagree, or when price action shows chop characteristics, the system forces a neutral bias regardless of signal strength. This prevents overtrading and enforces the SOP requirement for clean, aligned market structure.

---

## Conflict Types

### 1. Structure Conflict

**Condition**: 1H and 15M timeframes show opposing directional bias

**Logic**:
- Bullish 1H (HH or HL) + Bearish 15M (LH or LL) = **Conflict**
- Bearish 1H (LH or LL) + Bullish 15M (HH or HL) = **Conflict**
- Same direction or neutral structures = No conflict

**Reason**: Multi-timeframe alignment is required for high-probability setups. When higher and lower timeframes disagree, there is no clear directional bias.

**Example**:
```python
from rule_engine.htf.conflicts import detect_structure_conflict

# 1H showing Higher Highs (bullish)
# 15M showing Lower Highs (bearish)
is_conflict, reason = detect_structure_conflict(
    structure_1h="HH",
    structure_15m="LH",
)
# Returns: (True, "1H bullish (HH) conflicts with 15M bearish (LH)")
```

**Edge Cases**:
- None/missing structure labels → No conflict (insufficient data)
- Empty strings → No conflict
- Unknown labels → No conflict
- Both timeframes bullish/bearish → No conflict

---

### 2. 15M Price Chop

**Condition**: 15M price action exhibits chop characteristics (wick-to-wick behavior)

**Logic**:
- Calculate wick-to-body ratio for each candle: `(upper_wick + lower_wick) / body_size`
- Chop candle: Ratio >= 0.5 (default threshold)
- Chop condition: 3+ consecutive chop candles (default)
- Check most recent candles for chop

**Reason**: Large wicks relative to body indicate indecision, ranging markets, or whipsaw conditions. These environments produce false signals and should be avoided.

**Example**:
```python
from rule_engine.htf.conflicts import detect_price_chop_15m
import pandas as pd

# Large wicks (20 points) vs small bodies (2 points) = 10:1 ratio
df_15m = pd.DataFrame({
    'high': [2100, 2105, 2110, 2115, 2120],
    'low': [2080, 2085, 2090, 2095, 2100],
    'open': [2095, 2097, 2099, 2101, 2103],
    'close': [2097, 2099, 2101, 2103, 2105],
})

is_chop = detect_price_chop_15m(df_15m)
# Returns: True (5 consecutive chop candles detected)
```

**Parameters**:
- `wick_threshold`: Minimum ratio to consider chop (default: 0.5)
- `min_chop_candles`: Consecutive chop candles needed (default: 3)

**Edge Cases**:
- Doji candles (zero body) → Treated as chop (infinite ratio)
- Empty DataFrame → No chop
- < 3 consecutive → No chop (brief indecision acceptable)
- NaN values → Treated as non-chop

**Tuning Guidelines**:
- Increase `wick_threshold` (e.g., 0.7) for stricter chop detection
- Increase `min_chop_candles` (e.g., 5) to require longer chop periods
- Decrease values for more sensitive chop detection

---

### 3. Liquidity Sweep Against Trend

**Condition**: Recent liquidity sweep opposes the established trend direction

**Logic**:
- Bullish trend + successful sweep_low = **Conflict** (potential reversal)
- Bearish trend + successful sweep_high = **Conflict** (potential reversal)
- Sweep aligned with trend = No conflict (continuation)
- Failed sweeps = No conflict (continuation setup)
- Neutral bias = No conflict

**Reason**: A liquidity sweep against the established trend is a potential reversal signal. It indicates that stops were taken and price may reverse direction, invalidating the current bias.

**Example**:
```python
from rule_engine.htf.conflicts import detect_sweep_against_trend
import pandas as pd

# Recent sweep_low detected at end of series
sweep_events = pd.Series([None, None, "sweep_low"])
sweep_success = pd.Series([None, None, True])

# Current bias is bullish
is_conflict, reason = detect_sweep_against_trend(
    bias="bullish",
    sweep_events=sweep_events,
    sweep_success=sweep_success,
)
# Returns: (True, "Bullish bias with successful sweep_low (reversal signal)")
```

**Sweep Success Tracking**:
- If `sweep_success` provided: Only successful sweeps trigger conflicts
- If `sweep_success` is None: Assume all sweeps are significant
- Failed sweep (False): No conflict (continuation opportunity)
- Unknown (None): No conflict (insufficient confirmation)

**Edge Cases**:
- No recent sweeps → No conflict
- Neutral bias → No conflict (no established trend to oppose)
- Sweep aligns with trend → No conflict
- Multiple sweeps → Check most recent only
- Empty sweep events → No conflict

---

## Integration with HTF Calculator

### Function Signature

```python
def compute_htf_bias(
    features_1h: pd.Series,
    features_15m: pd.Series,
    dxy_1h: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,  # For 15M chop detection
    sweep_events_15m: pd.Series | None = None,  # For sweep detection
    timestamp: pd.Timestamp | None = None,
) -> HTFBias:
```

### Conflict Detection Flow

1. **Compute base bias** using legacy multi-timeframe logic
2. **Check DXY chop** (if `dxy_1h` provided)
3. **Check structure conflict** (Rule 1) - always runs
4. **Check 15M price chop** (Rule 2) - if `df_15m` provided
5. **Check sweep against trend** (Rule 3) - if `sweep_events_15m` provided
6. **Apply neutralization** if any conflict detected:
   - Force `bias = "neutral"`
   - Force `direction = "neutral"`
   - Cap `score` at 5.0
   - Set `conflict_detected = True`
   - Record `conflict_reason`
7. **Continue with seasonality** and other adjustments

### Priority Order

Conflicts are checked in order. **First conflict detected stops further checking** and triggers neutralization:

1. Structure conflict (always checked)
2. 15M chop (if data provided)
3. Sweep against trend (if data provided)

This ensures the most fundamental conflicts (timeframe disagreement) are caught first.

### Critical Implementation Detail: Original Bias Preservation

**Important**: Conflict detection uses the **original bias** (before DXY chop neutralization) for sweep detection.

**Why This Matters**:
- DXY chop detection runs before conflict detection
- If DXY chop is detected, bias is neutralized to "neutral"
- `detect_sweep_against_trend()` returns early when `bias == "neutral"`
- **Without preserving original bias**: Sweep conflicts would be missed when DXY chop occurs
- **With original bias**: Sweep conflicts are correctly detected based on market structure

**Implementation** (`calculator.py` lines 222-224, 284):
```python
# Store original bias before any neutralization
original_bias = bias
original_score = score

# Later: Use original bias for sweep detection
is_conflict, reason = detect_sweep_against_trend(
    bias=original_bias,  # Not the neutralized bias
    sweep_events=sweep_events_15m,
)
```

**Test Coverage**: `test_sweep_conflict_detected_even_with_dxy_chop()` verifies both DXY chop and sweep conflict are detected independently.

---

## HTFBias Output

### New Fields

```python
@dataclass
class HTFBias:
    # ... existing fields ...
    
    # Conflict detection
    conflict_detected: bool = False
    conflict_reason: Optional[str] = None
```

### Example Output

**No Conflict**:
```python
HTFBias(
    bias="bullish",
    direction="long",
    score=8.5,
    confidence="high",
    conflict_detected=False,
    conflict_reason=None,
    # ... other fields ...
)
```

**With Conflict**:
```python
HTFBias(
    bias="neutral",  # Forced neutral
    direction="neutral",
    score=5.0,  # Capped at 5.0
    confidence="low",
    conflict_detected=True,
    conflict_reason="1H bullish (HH) conflicts with 15M bearish (LH)",
    # ... other fields ...
)
```

---

## Usage Examples

### Basic Usage

```python
from rule_engine.htf.calculator import compute_htf_bias

# Minimal - structure conflict only
htf_bias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
)

# With 15M chop detection
htf_bias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
    df_15m=df_15m,  # OHLC data for chop detection
)

# Full conflict detection
htf_bias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
    df_15m=df_15m,
    sweep_events_15m=sweep_events,  # From detect_liquidity_sweeps()
)
```

### Checking for Conflicts

```python
# After computing HTF bias
if htf_bias.conflict_detected:
    logger.warning(f"Trade blocked: {htf_bias.conflict_reason}")
    return  # Skip signal generation
    
# Bias will already be "neutral" if conflict detected
assert htf_bias.bias == "neutral"
assert htf_bias.score <= 5.0
```

### RuleEngine Integration

```python
# In RuleEngine scoring logic
htf_bias = compute_htf_bias(...)

# Conflict automatically handled (bias = neutral, low score)
if htf_bias.bias == "neutral":
    # RuleEngine will assign low score or reject signal
    pass

# Log conflict for analysis
if htf_bias.conflict_detected:
    signal_logger.log_rejection(
        reason=f"HTF conflict: {htf_bias.conflict_reason}"
    )
```

---

## Testing

### Unit Tests

**Location**: `tests/unit/rule_engine/htf/test_conflicts.py`

- **17 tests total**:
  - 6 structure conflict tests
  - 5 chop detection tests
  - 6 sweep against trend tests

**Coverage**: 100% on `conflicts.py` module

### Integration Tests

**Location**: `tests/unit/rule_engine/htf/test_htf_calculator.py`

- **6 integration tests**:
  - Structure conflict neutralizes strong bias
  - 15M chop neutralizes bias
  - Sweep against trend neutralizes bias
  - Multiple conflicts (first recorded)
  - Conflict fields in HTFBias output
  - **Sweep conflict detected even with DXY chop** (regression test for bug fix)

### Test Scenarios

```python
# Test 1: Structure conflict
features_1h_bullish = pd.Series({"structure_label": "HH", ...})
features_15m_bearish = pd.Series({"structure_label": "LH", ...})
result = compute_htf_bias(features_1h_bullish, features_15m_bearish)
assert result.bias == "neutral"
assert result.conflict_detected is True

# Test 2: 15M chop
df_chop = pd.DataFrame(...)  # Large wicks
result = compute_htf_bias(features_1h, features_15m, df_15m=df_chop)
assert result.conflict_reason == "15M price action in chop"

# Test 3: Sweep against trend
sweep_events = pd.Series([None, None, "sweep_low"])
result = compute_htf_bias(
    features_1h_bullish, 
    features_15m_bullish,
    sweep_events_15m=sweep_events
)
assert "sweep" in result.conflict_reason.lower()
```

---

## Performance Considerations

### Computational Cost

- **Structure conflict**: O(1) - simple comparison
- **15M chop**: O(n) where n = length of df_15m (typically < 100 rows)
- **Sweep detection**: O(n) where n = length of sweep_events

**Total overhead**: < 1ms for typical data sizes

### Memory Usage

- Minimal - only stores conflict boolean and reason string
- No heavy DataFrame operations or copies

### Optimization Tips

- Pass only recent data (last 50-100 candles) for chop detection
- Compute sweep events once, reuse for multiple bias calculations
- Structure conflict has zero overhead (no data processing)

---

## Troubleshooting

### Common Issues

**1. Conflict not detected when expected**

Check:
- Structure labels are valid (HH, HL, LH, LL)
- 15M DataFrame has required OHLC columns
- Chop threshold may be too strict (try lowering `wick_threshold`)
- Sweep events are properly formatted (None or "sweep_high"/"sweep_low")

**1a. Sweep conflict not detected when DXY chop present**

**Fixed in v1.0**: Earlier versions had a bug where sweep conflicts were missed if DXY chop was detected first. The fix preserves `original_bias` before DXY chop neutralization and uses it for sweep detection. If using an older version, ensure you have the fix (see "Critical Implementation Detail" section above).

**2. Too many false positives (over-neutralization)**

Adjust:
- Increase `wick_threshold` for chop detection (default: 0.5 → 0.7)
- Increase `min_chop_candles` (default: 3 → 5)
- Require sweep success confirmation (pass `sweep_success` Series)

**3. Missing conflict_reason**

Ensure:
- Using latest version of `compute_htf_bias()`
- HTFBias dataclass includes conflict fields
- Not using legacy `compute_htf_bias_multi_timeframe()` (no conflict detection)

### Debug Logging

Enable debug logging to see conflict detection in action:

```python
import logging
logging.getLogger("rule_engine.htf").setLevel(logging.DEBUG)
```

Output:
```
DEBUG:rule_engine.htf.conflicts:Structure conflict detected: 1H bullish (HH) conflicts with 15M bearish (LH)
WARNING:rule_engine.htf.calculator:Conflict detected - forcing HTF bias to neutral: 1H bullish (HH) conflicts with 15M bearish (LH) (original: bullish, score: 8.0)
```

---

## Configuration

### Default Parameters

```python
# 15M Chop Detection
WICK_THRESHOLD = 0.5  # Ratio of wicks to body
MIN_CHOP_CANDLES = 3  # Consecutive chop candles required

# Customize per market conditions
detect_price_chop_15m(df_15m, wick_threshold=0.7, min_chop_candles=5)
```

### Recommended Settings

| Market Condition | wick_threshold | min_chop_candles | Notes |
|------------------|----------------|------------------|-------|
| **Volatile (VIX > 20)** | 0.7 | 5 | Stricter chop detection |
| **Normal** | 0.5 | 3 | Default (balanced) |
| **Low volatility** | 0.4 | 3 | More sensitive to chop |
| **News events** | 0.8 | 5 | Very strict (avoid whipsaws) |

---

## Future Enhancements

### Planned Features

1. **Configurable conflict weights**: Allow some conflicts to reduce score rather than force neutral
2. **Conflict history tracking**: Record conflict frequency for strategy tuning
3. **Multi-timeframe sweep detection**: Check 1H sweeps in addition to 15M
4. **DXY vs Gold chop correlation**: Detect when both are in chop simultaneously

### Extensibility

To add new conflict rules:

1. Implement detection function in `conflicts.py`:
   ```python
   def detect_new_conflict(...) -> tuple[bool, str | None]:
       # Detection logic
       return is_conflict, reason
   ```

2. Add to `compute_htf_bias()` conflict checking:
   ```python
   if not conflict_detected:
       is_conflict, reason = detect_new_conflict(...)
       if is_conflict:
           conflict_detected = True
           conflict_reason = reason
   ```

3. Add comprehensive tests in `test_conflicts.py`

---

## Related Documentation

- [HTF Module README](../../rule_engine/htf/README.md) - Module overview
- [HTF Seasonality Guide](htf-seasonality.md) - Seasonality rules
- [Structure Detection](../../rule_engine/htf/structure/README.md) - Swing/BOS/CHoCH
- [Liquidity Sweeps](../../rule_engine/htf/structure/liquidity.py) - Sweep detection

---

## Summary

The HTF Conflict Rules system is a critical safety mechanism that enforces multi-timeframe alignment and prevents trading during conflicting or choppy market conditions. By automatically neutralizing bias when conflicts are detected, it upholds the "structure-first" principle and reduces false signals.

**Key Takeaways**:
- ✅ Three conflict types: Structure, Chop, Sweep
- ✅ Automatic neutralization when conflicts detected
- ✅ Transparent conflict reasons in logs
- ✅ Original bias preservation prevents sweep detection bugs
- ✅ Minimal performance overhead
- ✅ Fully tested and production-ready (23 tests including regression)
- ✅ Backward compatible (optional parameters)

**Critical Bug Fix (v1.0)**: 
Sweep conflict detection now correctly uses original bias before DXY chop neutralization, ensuring sweep conflicts are always detected regardless of DXY chop state. See "Critical Implementation Detail" section for technical details.

For implementation details, see `rule_engine/htf/conflicts.py` and the comprehensive test suite in `tests/unit/rule_engine/htf/test_conflicts.py`.

