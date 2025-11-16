# EMA (Exponential Moving Average)

[← Back to Feature Engine](./README.md)

**Purpose:** Identify trends and generate trading signals by giving more weight to recent prices.

**Formula:**
```
EMA = Price × α + EMA_prev × (1 - α)
where α (smoothing factor) = 2 / (period + 1)
```

## Basic Usage

```python
from feature_engine import calculate_ema, calculate_ema_multiple
import pandas as pd

# Load your price data
df = pd.DataFrame({
    'close': [22.27, 22.19, 22.08, 22.17, 22.18, 22.13, ...]
})

# Calculate single EMA
df['ema_20'] = calculate_ema(df, period=20)

# Calculate SOP periods (9, 20, 50)
emas = calculate_ema_multiple(df, periods=[9, 20, 50])
df['ema_9'] = emas['ema_9']
df['ema_20'] = emas['ema_20']
df['ema_50'] = emas['ema_50']

# Custom periods
df['ema_14'] = calculate_ema(df, period=14)
df['ema_100'] = calculate_ema(df, period=100)
```

## API Reference

### calculate_ema()

```python
def calculate_ema(
    df: pd.DataFrame,
    period: int = 20,
    price_column: str = "close"
) -> pd.Series
```

**Parameters:**

- `df` (pd.DataFrame): DataFrame containing price data
  - Must contain the specified price column
  
- `period` (int, default=20): Number of periods for EMA calculation
  - Must be >= 1
  - Common values:
    - 9: Fast EMA (short-term, responsive)
    - 20: Medium EMA (intermediate-term, balanced)
    - 50: Slow EMA (long-term, smooth)
    - 200: Very slow EMA (major trend)
  
- `price_column` (str, default="close"): Name of the column containing price data
  - Can use 'close', 'high', 'low', 'open', or any price column
  - Most commonly used with closing prices

**Returns:**

- `pd.Series`: EMA values with same index as input DataFrame
  - First value equals first price (seed)
  - No NaN values (unlike RSI which has initial window)
  - All values are valid from the start

**Raises:**

- `ValueError`: If period < 1
- `ValueError`: If price_column not found in DataFrame

### calculate_ema_multiple()

```python
def calculate_ema_multiple(
    df: pd.DataFrame,
    periods: List[int] = [9, 20, 50],
    price_column: str = "close"
) -> pd.DataFrame
```

**Parameters:**

- `df` (pd.DataFrame): DataFrame containing price data
- `periods` (List[int], default=[9, 20, 50]): List of periods to calculate
  - Default SOP periods: 9 (fast), 20 (medium), 50 (slow)
- `price_column` (str, default="close"): Price column to use

**Returns:**

- `pd.DataFrame`: DataFrame with columns `ema_{period}` for each period
  - Example: `ema_9`, `ema_20`, `ema_50`
  - Same index as input DataFrame

## Advanced Examples

### Using with Real Market Data

```python
import pandas as pd
from feature_engine import calculate_ema_multiple

# Load real GC (Gold) data
df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])
gc_data = df[df['symbol'] == 'GCZ5'].copy()

# Calculate SOP EMAs
emas = calculate_ema_multiple(gc_data, periods=[9, 20, 50])
gc_data = pd.concat([gc_data, emas], axis=1)

# Identify trend conditions
gc_data['uptrend'] = gc_data['close'] > gc_data['ema_20']
gc_data['downtrend'] = gc_data['close'] < gc_data['ema_20']

# Bullish alignment: fast > medium > slow
gc_data['bullish_alignment'] = (
    (gc_data['ema_9'] > gc_data['ema_20']) &
    (gc_data['ema_20'] > gc_data['ema_50'])
)

# Bearish alignment: fast < medium < slow
gc_data['bearish_alignment'] = (
    (gc_data['ema_9'] < gc_data['ema_20']) &
    (gc_data['ema_20'] < gc_data['ema_50'])
)
```

### EMA Crossover Strategy

```python
# Golden Cross / Death Cross
df['ema_50'] = calculate_ema(df, period=50)
df['ema_200'] = calculate_ema(df, period=200)

# Golden Cross: 50 EMA crosses above 200 EMA (bullish)
df['golden_cross'] = (
    (df['ema_50'] > df['ema_200']) &
    (df['ema_50'].shift(1) <= df['ema_200'].shift(1))
)

# Death Cross: 50 EMA crosses below 200 EMA (bearish)
df['death_cross'] = (
    (df['ema_50'] < df['ema_200']) &
    (df['ema_50'].shift(1) >= df['ema_200'].shift(1))
)

# Entry signals
df['long_entry'] = df['golden_cross']
df['short_entry'] = df['death_cross']
```

### EMA as Dynamic Support/Resistance

```python
# EMAs act as dynamic support in uptrends, resistance in downtrends
df['ema_20'] = calculate_ema(df, period=20)

# Price bouncing off EMA support (bullish)
df['bounce_off_support'] = (
    (df['low'] <= df['ema_20'] * 1.001) &  # Price touched EMA
    (df['close'] > df['ema_20']) &         # But closed above
    (df['close'] > df['open'])             # And was bullish candle
)

# Price rejected at EMA resistance (bearish)
df['rejected_at_resistance'] = (
    (df['high'] >= df['ema_20'] * 0.999) &  # Price touched EMA
    (df['close'] < df['ema_20']) &          # But closed below
    (df['close'] < df['open'])              # And was bearish candle
)
```

### Multi-Timeframe EMA Analysis

```python
from feature_engine import calculate_ema

# Calculate EMA on different timeframes
for timeframe in ['1m', '15m', '1h']:
    df_tf = load_data(timeframe)
    df_tf['ema_20'] = calculate_ema(df_tf, period=20)
    
    # Higher timeframe EMA as major trend filter
    print(f"{timeframe} trend: {df_tf['ema_20'].iloc[-1]}")
```

### EMA Divergence Detection

```python
# Price making higher highs but EMA flattening = potential reversal
df['ema_20'] = calculate_ema(df, period=20)

# Calculate slope of EMA (rate of change)
df['ema_slope'] = df['ema_20'].diff()

# Price higher high
df['price_higher_high'] = (
    (df['close'] > df['close'].shift(1)) &
    (df['close'].shift(1) > df['close'].shift(2))
)

# EMA slope decreasing (flattening)
df['ema_flattening'] = df['ema_slope'] < df['ema_slope'].shift(1)

# Bearish divergence
df['bearish_divergence'] = df['price_higher_high'] & df['ema_flattening']
```

## Edge Cases Handled

1. **Single Row:** First EMA value equals first price
2. **Small Dataset:** Works with any number of rows >= 1
3. **No NaN Values:** All values valid from start (no initial window)
4. **Custom Price Column:** Can use high, low, open, or any price column
5. **Multiple Periods:** Efficiently calculates multiple EMAs at once

## Performance Characteristics

- **Time Complexity:** O(n) - single pass through data
- **Memory:** O(n) - stores result series
- **Implementation:** Uses pandas `.ewm()` (optimized C code)
- **Fully Vectorized:** No Python loops
- **Suitable for:** Real-time streaming data and large datasets

## Testing and Validation

EMA implementation is validated with:
- ✅ ±0.01 precision match vs TA-Lib
- ✅ Manual calculation verification
- ✅ Multiple periods (9, 20, 50, custom) tested
- ✅ Crossover detection validated
- ✅ Trend alignment tested
- ✅ All edge cases covered
- ✅ All tests in `tests/unit/test_ema.py`

Run EMA tests:
```bash
pytest tests/unit/test_ema.py -v
```

## Trading Use Cases

### 1. Trend Identification

```python
df['ema_20'] = calculate_ema(df, period=20)

# Price above EMA = uptrend
df['uptrend'] = df['close'] > df['ema_20']

# Price below EMA = downtrend  
df['downtrend'] = df['close'] < df['ema_20']

# Trend strength: distance from EMA
df['trend_strength'] = abs(df['close'] - df['ema_20']) / df['ema_20'] * 100
```

### 2. EMA + VWAP + RSI (SOP Integration)

```python
from feature_engine import calculate_ema, calculate_vwap, calculate_rsi

# Calculate all SOP indicators
df['vwap'] = calculate_vwap(df, session_reset=True)
df['rsi'] = calculate_rsi(df, period=14)
df['ema_20'] = calculate_ema(df, period=20)

# High-confidence long setup
df['strong_long_setup'] = (
    (df['close'] > df['vwap']) &      # Price above VWAP (structure)
    (df['close'] > df['ema_20']) &    # Price above EMA (trend)
    (df['rsi'] > 30) &                # RSI not oversold
    (df['rsi'] < 70)                  # RSI not overbought
)

# High-confidence short setup
df['strong_short_setup'] = (
    (df['close'] < df['vwap']) &      # Price below VWAP (structure)
    (df['close'] < df['ema_20']) &    # Price below EMA (trend)
    (df['rsi'] > 30) &                # RSI not oversold
    (df['rsi'] < 70)                  # RSI not overbought
)
```

### 3. EMA Ribbon (Multiple EMAs)

```python
# Calculate EMA ribbon
emas = calculate_ema_multiple(df, periods=[9, 12, 15, 20, 26, 35, 50])

# Strong uptrend: All EMAs aligned from fast to slow
df['ribbon_bullish'] = (
    (emas['ema_9'] > emas['ema_12']) &
    (emas['ema_12'] > emas['ema_15']) &
    (emas['ema_15'] > emas['ema_20']) &
    (emas['ema_20'] > emas['ema_26']) &
    (emas['ema_26'] > emas['ema_35']) &
    (emas['ema_35'] > emas['ema_50'])
)

# Strong downtrend: All EMAs aligned from slow to fast
df['ribbon_bearish'] = (
    (emas['ema_9'] < emas['ema_12']) &
    (emas['ema_12'] < emas['ema_15']) &
    (emas['ema_15'] < emas['ema_20']) &
    (emas['ema_20'] < emas['ema_26']) &
    (emas['ema_26'] < emas['ema_35']) &
    (emas['ema_35'] < emas['ema_50'])
)
```

### 4. EMA Distance for Entries

```python
df['ema_20'] = calculate_ema(df, period=20)

# Price too far from EMA = don't chase
df['distance_from_ema'] = (df['close'] - df['ema_20']) / df['ema_20'] * 100

# Only enter when price within 1% of EMA (pullback entry)
df['valid_entry'] = abs(df['distance_from_ema']) < 1.0

# Wait for pullback to EMA
df['pullback_to_ema'] = (
    (df['uptrend']) &                           # In uptrend
    (abs(df['distance_from_ema']) < 0.5) &     # Price near EMA
    (df['distance_from_ema'].shift(1) > 1.0)   # Was far before
)
```

## Best Practices

### EMA-Specific

1. **Period Selection**
   - Use 9 for fast signals in active markets
   - Use 20 as default for balanced trend identification
   - Use 50 for longer-term trend confirmation
   - Use 200 for major trend (daily/weekly charts)

2. **EMA vs SMA**
   - EMA: More responsive, better for trending markets
   - SMA: Smoother, better for ranging markets
   - SOP uses EMA for trend identification

3. **Combine Multiple Periods**
   - Fast EMA for signals
   - Slow EMA for trend filter
   - Only trade in direction of slow EMA

4. **Avoid Common Mistakes**
   - Don't enter trades far from EMA (wait for pullback)
   - Don't fight the EMA trend (price below EMA 20 = don't go long)
   - Don't rely on EMA crossovers alone (add confirmation)

### Integration with SOP

1. **Trend Filter**
   - Only take longs when price > EMA 20
   - Only take shorts when price < EMA 20
   - EMA feeds into SOP trend score

2. **Entry Timing**
   - Wait for pullback to EMA in strong trend
   - Enter when price bounces off EMA support
   - Combine with VWAP for structure + trend confirmation

3. **Exit Signals**
   - Exit longs when price crosses below EMA
   - Exit shorts when price crosses above EMA
   - Or when fast EMA crosses slow EMA (opposite direction)

## Troubleshooting

**Issue:** EMA not matching TA-Lib

**Solution:** Ensure `adjust=False` in pandas `.ewm()`. This gives the standard EMA formula.

---

**Issue:** EMA too sensitive (too many signals)

**Solution:** Increase period (use 50 instead of 9) or add confirmation (VWAP, RSI, volume).

---

**Issue:** EMA too slow (missing entries)

**Solution:** Decrease period (use 9 or 12 instead of 20) or use multiple EMAs for crossovers.

---

**Issue:** Want to calculate EMA on different price

**Solution:** Use `price_column` parameter:
```python
df['ema_high'] = calculate_ema(df, period=20, price_column='high')
df['ema_low'] = calculate_ema(df, period=20, price_column='low')
```

## Comparison: EMA vs VWAP vs RSI

| Indicator | Purpose | Best For | Key Signal |
|-----------|---------|----------|------------|
| **EMA** | Trend direction | Identifying trend and pullbacks | Price vs EMA position |
| **VWAP** | Fair value | Structure and institutional flow | Price vs VWAP position |
| **RSI** | Momentum | Overbought/oversold conditions | 70/30 levels |

**Combined SOP Signal:**
- Price > VWAP (structure) ✓
- Price > EMA 20 (trend) ✓  
- 30 < RSI < 70 (momentum healthy) ✓
- = High-quality long setup (8+/10 score)

## Further Reading

- [VWAP Documentation](./vwap.md) - Volume-weighted average price
- [RSI Documentation](./rsi.md) - Relative Strength Index
- [Feature Engine Overview](./README.md) - All indicators
- [Data Layer Guide](../10-data-layer.md) - OHLCV data structures

---

**Related Documentation:**
- [Feature Engine Overview](./README.md)
- [Development Workflow](../05-development-workflow.md)
- [Testing Guide](../06-testing.md)

