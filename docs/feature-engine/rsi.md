# RSI (Relative Strength Index)

[← Back to Feature Engine](./README.md)

**Purpose:** Measure momentum and identify overbought/oversold conditions using price change velocity.

**Formula:**
```
RSI = 100 - (100 / (1 + RS))
where RS = Average Gain / Average Loss

Wilder's Smoothing (after initial SMA):
avg = (prev_avg × (period-1) + current_value) / period
```

#### Basic Usage

```python
from feature_engine import calculate_rsi
import pandas as pd

# Load your price data
df = pd.DataFrame({
    'close': [44.0, 44.5, 44.3, 44.8, 45.2, ...]  # Your price series
})

# Calculate RSI with default 14-period
rsi = calculate_rsi(df, period=14)

# Calculate RSI with custom period
rsi_9 = calculate_rsi(df, period=9)  # Faster, more sensitive
rsi_21 = calculate_rsi(df, period=21)  # Slower, smoother

# Use different price column (e.g., 'high' instead of 'close')
rsi_high = calculate_rsi(df, period=14, price_column='high')

# Add RSI to DataFrame
df['rsi'] = rsi
df['rsi_9'] = rsi_9
```

#### API Reference

```python
def calculate_rsi(
    df: pd.DataFrame,
    period: int = 14,
    price_column: str = "close"
) -> pd.Series
```

**Parameters:**

- `df` (pd.DataFrame): DataFrame containing price data
  - Must contain the specified price column
  
- `period` (int, default=14): Number of periods for RSI calculation
  - Must be >= 2
  - Common values: 9 (fast), 14 (standard), 21 (slow)
  - Smaller period = more sensitive to price changes
  - Larger period = smoother, less noise

- `price_column` (str, default="close"): Name of the column containing price data
  - Can use 'close', 'high', 'low', or any price column
  - Most commonly used with closing prices

**Returns:**

- `pd.Series`: RSI values (0-100 scale) with same index as input
  - First `period` values will be NaN (initial calculation window)
  - Valid RSI range: 0 to 100
  - Traditional interpretation:
    - RSI > 70: Overbought (potential reversal down)
    - RSI < 30: Oversold (potential reversal up)
    - RSI = 50: Neutral momentum

**Raises:**

- `ValueError`: If period < 2
- `ValueError`: If price_column not found in DataFrame

#### Advanced Examples

**Using with Real Market Data:**

```python
import pandas as pd
from feature_engine import calculate_rsi

# Load real GC (Gold) data
df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])
gc_data = df[df['symbol'] == 'GCZ5'].copy()

# Calculate RSI
gc_data['rsi'] = calculate_rsi(gc_data, period=14)

# Identify overbought/oversold conditions
gc_data['overbought'] = gc_data['rsi'] > 70
gc_data['oversold'] = gc_data['rsi'] < 30
gc_data['neutral'] = (gc_data['rsi'] >= 30) & (gc_data['rsi'] <= 70)

# Count signals
print(f"Overbought signals: {gc_data['overbought'].sum()}")
print(f"Oversold signals: {gc_data['oversold'].sum()}")
```

**Multi-Period RSI Analysis:**

```python
# Compare different RSI periods
df['rsi_9'] = calculate_rsi(df, period=9)   # Fast
df['rsi_14'] = calculate_rsi(df, period=14)  # Standard
df['rsi_21'] = calculate_rsi(df, period=21)  # Slow

# Detect RSI convergence (all periods agree)
df['all_overbought'] = (
    (df['rsi_9'] > 70) & 
    (df['rsi_14'] > 70) & 
    (df['rsi_21'] > 70)
)

df['all_oversold'] = (
    (df['rsi_9'] < 30) & 
    (df['rsi_14'] < 30) & 
    (df['rsi_21'] < 30)
)
```

**RSI Divergence Detection:**

```python
# Detect bullish divergence: price makes lower low, but RSI makes higher low
# (Simple example - real implementation would need more sophistication)
df['price_lower_low'] = (
    (df['close'] < df['close'].shift(1)) & 
    (df['close'].shift(1) < df['close'].shift(2))
)
df['rsi_higher_low'] = (
    (df['rsi'] > df['rsi'].shift(1)) & 
    (df['rsi'].shift(1) > df['rsi'].shift(2))
)
df['bullish_divergence'] = df['price_lower_low'] & df['rsi_higher_low']
```

#### Edge Cases Handled

1. **Insufficient Data:** Returns all NaN when data length < period + 1
2. **All Gains (No Losses):** RSI = 100
3. **All Losses (No Gains):** RSI = 0
4. **Initial Period:** First `period` values are NaN (calculation window)
5. **Zero Average Loss:** Handled gracefully (RSI = 100)
6. **NaN in Input:** Propagates through calculation as expected

#### Performance Characteristics

- **Time Complexity:** O(n) - single pass after initial SMA
- **Memory:** O(n) - stores result series
- **Optimized:** Uses Wilder's smoothing (iterative, not rolling window)
- **Suitable for:** Real-time streaming data and large datasets

#### Testing and Validation

RSI implementation is validated with:
- ✅ ±0.1 precision match vs TA-Lib (when available)
- ✅ Manual calculation verification
- ✅ Overbought/oversold detection on synthetic data
- ✅ All edge cases tested
- ✅ Multiple periods (9, 14, 21) validated
- ✅ All tests in `tests/unit/test_rsi.py`

Run RSI tests:
```bash
pytest tests/unit/test_rsi.py -v
```

## Trading Use Cases

### 1. Overbought/Oversold Identification

```python
# Classic RSI interpretation
df['rsi'] = calculate_rsi(df, period=14)

# Identify extreme conditions
df['extremely_overbought'] = df['rsi'] > 80  # Very strong, potential exhaustion
df['overbought'] = df['rsi'] > 70            # Traditional overbought
df['oversold'] = df['rsi'] < 30              # Traditional oversold
df['extremely_oversold'] = df['rsi'] < 20    # Very weak, potential bounce
```

### 2. RSI + VWAP Confirmation (SOP Integration)

```python
from feature_engine import calculate_rsi, calculate_vwap

# Calculate both indicators
df['vwap'] = calculate_vwap(df, session_reset=True)
df['rsi'] = calculate_rsi(df, period=14)

# Long setup: Price above VWAP AND RSI not overbought
df['long_setup'] = (df['close'] > df['vwap']) & (df['rsi'] < 70)

# Short setup: Price below VWAP AND RSI not oversold
df['short_setup'] = (df['close'] < df['vwap']) & (df['rsi'] > 30)

# High-confidence long: Oversold + above VWAP (mean reversion + structure)
df['strong_long'] = (df['rsi'] < 30) & (df['close'] > df['vwap'])
```

### 3. RSI Trend Strength

```python
# RSI staying in upper half (50-100) = strong uptrend
# RSI staying in lower half (0-50) = strong downtrend
df['rsi'] = calculate_rsi(df, period=14)
df['bullish_trend'] = df['rsi'] > 50
df['bearish_trend'] = df['rsi'] < 50

# Count consecutive bars above/below 50
df['trend_strength'] = (df['rsi'] > 50).rolling(window=10).sum()
# trend_strength = 10 means all last 10 bars had RSI > 50 (strong bull trend)
```

### 4. RSI as Exit Signal

```python
# Exit longs when RSI reaches overbought
df['rsi'] = calculate_rsi(df, period=14)
df['exit_long'] = df['rsi'] > 70

# Exit shorts when RSI reaches oversold
df['exit_short'] = df['rsi'] < 30

# Dynamic exits: exit when RSI crosses back through 50
df['rsi_cross_down'] = (df['rsi'] < 50) & (df['rsi'].shift(1) >= 50)
df['rsi_cross_up'] = (df['rsi'] > 50) & (df['rsi'].shift(1) <= 50)
```

## Best Practices

### RSI-Specific

1. **Period Selection**
   - Use 14 for standard momentum analysis (most common)
   - Use 9 for faster signals in volatile markets
   - Use 21 for smoother signals, fewer false positives

2. **Overbought/Oversold Levels**
   - Traditional: 70/30 (balanced)
   - Aggressive: 80/20 (fewer signals, stronger conviction)
   - In strong trends, RSI can stay overbought/oversold for extended periods

3. **Combine with Other Indicators**
   - RSI alone is not sufficient for trading decisions
   - Use with VWAP for structure confirmation
   - Use with trend indicators (EMA) for direction
   - Use with volume for confirmation

4. **Avoid Common Mistakes**
   - Don't fade strong trends just because RSI is overbought/oversold
   - RSI > 70 in uptrend can mean "stay long" not "exit"
   - Always confirm with price structure (VWAP, support/resistance)

### General Indicator Best Practices

1. **Calculation**
   - Calculate indicators once and store in DataFrame
   - Avoid recalculating on every iteration
   - Use vectorized operations for analysis

2. **Data Quality**
   - Ensure timestamps are sequential
   - Verify no missing price data in critical periods
   - Handle symbol filtering before calculation

3. **Integration with SOP**
   - RSI feeds into momentum scoring
   - Combine RSI + VWAP + DXY correlation for complete signal
   - Never trade on single indicator alone

