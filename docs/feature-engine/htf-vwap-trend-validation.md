# VWAP Trend Validation for HTF Bias

[← Back to HTF Structure Analysis](./README.md)

**Purpose:** Confirms trend validity when price consistently stays above or below VWAP for a minimum number of consecutive candles, indicating sustained institutional positioning.

**Module:** `rule_engine.htf.vwap.trend`

---

## Overview

VWAP (Volume-Weighted Average Price) trend validation is a critical component of the HTF bias calculation that determines whether the current market trend is strong enough to be considered reliable. When price stays consistently on one side of VWAP for N consecutive candles, it signals that institutional participants are maintaining their positioning in one direction.

### Key Concepts

- **Bullish Trend Confirmed**: Close > VWAP for N consecutive candles → Buyers in control
- **Bearish Trend Confirmed**: Close < VWAP for N consecutive candles → Sellers in control
- **No Trend (Neutral)**: Price crosses VWAP frequently → No clear institutional positioning

### Trading Significance

VWAP acts as a dynamic support/resistance level and fair value reference:
- Price above VWAP + confirmation = Strong bullish bias (continuation setups preferred)
- Price below VWAP + confirmation = Strong bearish bias (continuation setups preferred)
- Price crossing VWAP frequently = Weak bias (avoid or wait for clearer structure)

---

## Function API

### `validate_vwap_trend()`

```python
def validate_vwap_trend(
    df: pd.DataFrame,
    min_candles: int = 3,
) -> pd.Series
```

**Parameters:**

- `df` (pd.DataFrame): DataFrame with required columns:
  - `close`: Close price for each bar
  - `vwap`: Volume-weighted average price for each bar
- `min_candles` (int, default=3): Minimum consecutive candles needed for confirmation. Must be >= 1.

**Returns:**

- `pd.Series`: Boolean Series indicating if trend is confirmed at each bar
  - `True`: Price has stayed above/below VWAP for min_candles
  - `False`: Price hasn't maintained consistent position vs VWAP

**Raises:**

- `ValueError`: If required columns ('close', 'vwap') are missing
- `ValueError`: If `min_candles` is less than 1

---

## Algorithm Details

### Step 1: Input Validation

```python
# Validate required columns
required_cols = {"close", "vwap"}
missing = required_cols - set(df.columns)
if missing:
    raise ValueError(f"Missing required columns: {missing}")

# Validate min_candles parameter
if min_candles < 1:
    raise ValueError(f"min_candles must be >= 1, got {min_candles}")
```

### Step 2: Edge Case Handling

```python
# Handle DataFrame shorter than min_candles
if len(df) < min_candles:
    return pd.Series(False, index=df.index)
```

### Step 3: Price Position Determination

```python
# Determine price position relative to VWAP (strict inequality)
above_vwap = df["close"] > df["vwap"]
below_vwap = df["close"] < df["vwap"]
# Note: close == vwap is NOT considered above or below
```

### Step 4: Rolling Window Confirmation

```python
# Count consecutive candles in same position
above_streak = above_vwap.rolling(
    window=min_candles, min_periods=min_candles
).sum()
below_streak = below_vwap.rolling(
    window=min_candles, min_periods=min_candles
).sum()

# Trend confirmed if all N candles are on same side
bullish_confirmed = above_streak == min_candles
bearish_confirmed = below_streak == min_candles

# Either bullish OR bearish confirmed = trend confirmed
trend_confirmed = bullish_confirmed | bearish_confirmed
```

### Step 5: NaN Handling

```python
# Convert to boolean, filling NaN with False
trend_confirmed = trend_confirmed.fillna(False)
```

---

## Usage Examples

### Basic Usage

```python
from feature_engine.vwap import calculate_vwap
from rule_engine.htf.vwap.trend import validate_vwap_trend

# Calculate VWAP first
df['vwap'] = calculate_vwap(df, session_reset=True)

# Validate trend (default 3 candles)
df['trend_confirmed'] = validate_vwap_trend(df, min_candles=3)

# Check current bar
if df['trend_confirmed'].iloc[-1]:
    print("Trend confirmed - proceed with continuation setups")
else:
    print("Trend not confirmed - wait for clearer structure")
```

### HTF Bias Integration

```python
from rule_engine.htf.vwap.trend import validate_vwap_trend
from feature_engine.vwap import calculate_vwap

def compute_htf_bias_with_vwap_validation(df_1h: pd.DataFrame) -> HTFBias:
    """Compute HTF bias with VWAP trend validation."""
    
    # Calculate VWAP
    df_1h['vwap'] = calculate_vwap(df_1h, session_reset=True)
    
    # Validate trend
    df_1h['trend_confirmed'] = validate_vwap_trend(df_1h, min_candles=3)
    
    # Get current state
    current_close = df_1h['close'].iloc[-1]
    current_vwap = df_1h['vwap'].iloc[-1]
    current_confirmed = df_1h['trend_confirmed'].iloc[-1]
    
    # Determine bias direction
    if current_close > current_vwap:
        bias_direction = "bullish"
    elif current_close < current_vwap:
        bias_direction = "bearish"
    else:
        bias_direction = "neutral"
    
    # Adjust confidence based on trend confirmation
    base_score = calculate_base_score(df_1h)
    if current_confirmed:
        final_score = base_score * 1.2  # 20% boost for confirmed trend
        confidence = "high"
    else:
        final_score = base_score * 0.8  # 20% penalty for unconfirmed
        confidence = "low"
    
    return HTFBias(
        direction=bias_direction,
        score=final_score,
        confidence=confidence,
        vwap_trend_confirmed=current_confirmed
    )
```

### Configurable Confirmation Period

```python
# Faster confirmation (more signals, less reliable)
fast = validate_vwap_trend(df, min_candles=2)

# Standard confirmation (balanced)
standard = validate_vwap_trend(df, min_candles=3)

# Stricter confirmation (fewer signals, more reliable)
strict = validate_vwap_trend(df, min_candles=5)

# Compare confirmation counts
print(f"Fast: {fast.sum()} bars confirmed")
print(f"Standard: {standard.sum()} bars confirmed")
print(f"Strict: {strict.sum()} bars confirmed")
```

### Multi-Timeframe Analysis

```python
# Apply validation to different timeframes
timeframes = ['1h', '4h', '1d']
for tf in timeframes:
    df = load_data(f'GC_{tf}.csv')
    df['vwap'] = calculate_vwap(df, session_reset=True)
    df['trend_confirmed'] = validate_vwap_trend(df, min_candles=3)
    
    print(f"{tf} trend confirmed: {df['trend_confirmed'].iloc[-1]}")
```

---

## Trade Filtering Application

### Filter Long Setups

```python
def should_take_long_setup(df: pd.DataFrame) -> bool:
    """Filter long setups based on VWAP trend validation."""
    
    # Calculate VWAP and validate trend
    df['vwap'] = calculate_vwap(df, session_reset=True)
    df['trend_confirmed'] = validate_vwap_trend(df, min_candles=3)
    
    # Get current state
    current_close = df['close'].iloc[-1]
    current_vwap = df['vwap'].iloc[-1]
    current_confirmed = df['trend_confirmed'].iloc[-1]
    
    # Conditions for long setup
    price_above_vwap = current_close > current_vwap
    trend_confirmed = current_confirmed
    
    # Only take long if both conditions met
    return price_above_vwap and trend_confirmed
```

### Filter Short Setups

```python
def should_take_short_setup(df: pd.DataFrame) -> bool:
    """Filter short setups based on VWAP trend validation."""
    
    # Calculate VWAP and validate trend
    df['vwap'] = calculate_vwap(df, session_reset=True)
    df['trend_confirmed'] = validate_vwap_trend(df, min_candles=3)
    
    # Get current state
    current_close = df['close'].iloc[-1]
    current_vwap = df['vwap'].iloc[-1]
    current_confirmed = df['trend_confirmed'].iloc[-1]
    
    # Conditions for short setup
    price_below_vwap = current_close < current_vwap
    trend_confirmed = current_confirmed
    
    # Only take short if both conditions met
    return price_below_vwap and trend_confirmed
```

---

## Edge Cases & Special Scenarios

### 1. Warm-up Period

```python
# First N-1 bars always return False (insufficient history)
df = pd.DataFrame({
    'close': [2645, 2650],
    'vwap':  [2640, 2642]
})

result = validate_vwap_trend(df, min_candles=3)
# result.iloc[0] = False (bar 0)
# result.iloc[1] = False (bar 1)
# Need at least 3 bars for confirmation
```

### 2. Price Equal to VWAP

```python
# close == vwap does NOT count as above or below
df = pd.DataFrame({
    'close': [2645, 2642, 2655],  # Bar 1: close == vwap
    'vwap':  [2640, 2642, 2645]
})

result = validate_vwap_trend(df, min_candles=3)
# result.iloc[2] = False (equality at bar 1 breaks streak)
```

### 3. NaN Handling

```python
# NaN in VWAP or close propagates to False
df = pd.DataFrame({
    'close': [2645, np.nan, 2655, 2660, 2665],
    'vwap':  [2640, 2642, 2645, 2648, 2650]
})

result = validate_vwap_trend(df, min_candles=3)
# Bars with NaN in rolling window = False
# Bar 4: window [2,3,4] no NaN, all above = True
```

### 4. Trend Break and Reset

```python
# Crossing VWAP resets confirmation requirement
df = pd.DataFrame({
    'close': [2645, 2650, 2655, 2640, 2645, 2650, 2655],
    'vwap':  [2640, 2642, 2645, 2642, 2642, 2642, 2642]
})

result = validate_vwap_trend(df, min_candles=3)
# Bar 2: True (3 consecutive above)
# Bar 3: False (breaks below)
# Bar 4-5: False (cross in window)
# Bar 6: True (3 consecutive above again)
```

### 5. Alternating Crosses

```python
# Frequent crosses never confirm trend
df = pd.DataFrame({
    'close': [2645, 2640, 2645, 2640, 2645],
    'vwap':  [2642, 2642, 2642, 2642, 2642]
})

result = validate_vwap_trend(df, min_candles=3)
# All bars: False (never 3 consecutive in same direction)
```

---

## Integration with HTF Bias Score

### Score Adjustment Based on Confirmation

```python
def calculate_final_htf_score(
    base_score: float,
    vwap_trend_confirmed: bool
) -> float:
    """Adjust HTF bias score based on VWAP trend confirmation."""
    
    if vwap_trend_confirmed:
        # Boost score for confirmed trend (stronger conviction)
        return base_score * 1.2  # 20% boost
    else:
        # Reduce score for unconfirmed trend (weaker conviction)
        return base_score * 0.8  # 20% penalty
```

### Trade Filtering

```python
def filter_trades_by_vwap_confirmation(
    df: pd.DataFrame,
    min_candles: int = 3
) -> pd.DataFrame:
    """Filter trade signals to only confirmed VWAP trends."""
    
    # Calculate VWAP and validate trend
    df['vwap'] = calculate_vwap(df, session_reset=True)
    df['trend_confirmed'] = validate_vwap_trend(df, min_candles)
    
    # Filter: only take trades when trend is confirmed
    df['signal_valid'] = df['signal'] & df['trend_confirmed']
    
    return df
```

---

## Performance Characteristics

- **Time Complexity**: O(n) where n is the number of candles
- **Space Complexity**: O(n) for boolean Series storage
- **Vectorized**: Uses pandas/numpy vectorized operations for performance
- **Real-time**: Suitable for live trading (fast computation)

---

## Testing & Validation

### Test Coverage

All 21 unit tests pass, covering:
- **Core Functionality** (5 tests): Bullish/bearish confirmation, crosses, thresholds
- **Edge Cases** (6 tests): Empty data, short DataFrames, invalid parameters
- **NaN Handling** (3 tests): NaN in VWAP, close, or both
- **Validation** (3 tests): Configurable min_candles, index preservation
- **Special Scenarios** (4 tests): Trend breaks, equality, alternating

### Running Tests

```bash
# Run VWAP trend validation tests
uv run pytest tests/unit/rule_engine/htf/vwap/test_vwap_trend.py -v

# Run all HTF tests
uv run pytest tests/unit/rule_engine/htf/ -v

# Run with coverage
uv run pytest tests/unit/rule_engine/htf/vwap/test_vwap_trend.py --cov=rule_engine.htf.vwap.trend
```

---

## Best Practices

### 1. Choose Appropriate min_candles

```python
# Intraday (1m-15m charts): faster confirmation
intraday_confirmed = validate_vwap_trend(df_5m, min_candles=2)

# Swing trading (1h-4h charts): balanced confirmation
swing_confirmed = validate_vwap_trend(df_1h, min_candles=3)

# Position trading (daily charts): stricter confirmation
position_confirmed = validate_vwap_trend(df_1d, min_candles=5)
```

### 2. Combine with Other Indicators

```python
def comprehensive_trend_filter(df: pd.DataFrame) -> bool:
    """Combine VWAP validation with other trend indicators."""
    
    # VWAP trend confirmation
    df['vwap'] = calculate_vwap(df, session_reset=True)
    vwap_confirmed = validate_vwap_trend(df, min_candles=3).iloc[-1]
    
    # Additional trend filters
    ema_aligned = df['close'].iloc[-1] > df['ema_50'].iloc[-1]
    structure_confirmed = df['bos_label'].iloc[-1] is not None
    
    # All conditions must be met
    return vwap_confirmed and ema_aligned and structure_confirmed
```

### 3. Log Confirmation State

```python
logger.info(
    f"VWAP Trend Validation: "
    f"confirmed={trend_confirmed.iloc[-1]}, "
    f"close={df['close'].iloc[-1]:.2f}, "
    f"vwap={df['vwap'].iloc[-1]:.2f}, "
    f"min_candles={min_candles}"
)
```

### 4. Use in Risk Management

```python
def adjust_position_size_by_vwap_trend(
    base_size: float,
    trend_confirmed: bool
) -> float:
    """Adjust position size based on VWAP trend confirmation."""
    
    if trend_confirmed:
        # Increase size for confirmed trends
        return base_size * 1.5
    else:
        # Reduce size for unconfirmed trends
        return base_size * 0.5
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Using VWAP Without Session Reset

**Problem:**
```python
# BAD: Cumulative VWAP across multiple days
df['vwap'] = calculate_vwap(df, session_reset=False)
```

**Solution:**
```python
# GOOD: Reset VWAP daily for intraday analysis
df['vwap'] = calculate_vwap(df, session_reset=True)
```

### Pitfall 2: Ignoring Warm-up Period

**Problem:**
```python
# BAD: Using confirmation on first bars
if df['trend_confirmed'].iloc[0]:  # Always False!
    take_trade()
```

**Solution:**
```python
# GOOD: Check for sufficient history
if len(df) >= min_candles and df['trend_confirmed'].iloc[-1]:
    take_trade()
```

### Pitfall 3: Not Handling NaN Values

**Problem:**
```python
# BAD: Assuming VWAP is always present
trend_confirmed = validate_vwap_trend(df, min_candles=3)
# May have False due to NaN, not actual trend breaks
```

**Solution:**
```python
# GOOD: Clean data before validation
df = df.dropna(subset=['close', 'vwap'])
trend_confirmed = validate_vwap_trend(df, min_candles=3)
```

---

## Related Documentation

- [VWAP Calculation](./vwap.md) - Core VWAP calculation with session reset
- [HTF Structure Analysis](./htf-structure-analysis.md) - Overview of HTF bias components
- [FVG Detection](./htf-fvg-detection.md) - Fair Value Gap detection and scoring
- [Liquidity Sweep Detection](./htf-liquidity-sweep-detection.md) - Liquidity sweep identification

---

## Summary

VWAP trend validation is a critical filter for HTF bias calculation that ensures we only act on trends with sustained institutional participation. By requiring price to stay on one side of VWAP for N consecutive candles, we filter out choppy, indecisive markets and focus on clear directional moves.

**Key Takeaways:**
- ✅ Use `min_candles=3` for balanced confirmation (default)
- ✅ Always calculate VWAP with session reset for intraday analysis
- ✅ Combine with other structural indicators (BOS, CHoCH, swings)
- ✅ Handle NaN values gracefully (function does this automatically)
- ✅ Remember warm-up period: first N-1 bars always return False
- ✅ Confirmed trends = higher conviction = can increase position size
- ✅ Unconfirmed trends = lower conviction = reduce or avoid trades

---

**Last Updated:** November 23, 2025  
**Status:** ✅ Production Ready  
**Test Coverage:** 21/21 tests passing

