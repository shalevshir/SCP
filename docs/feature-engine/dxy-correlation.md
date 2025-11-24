# DXY Correlation

[← Back to Feature Engine](./README.md)

**Purpose:** Measure the relationship between Gold (GC) and Dollar Index (DXY) prices using rolling Pearson correlation for market environment analysis.

**Formula:**
```
Pearson Correlation = Σ((GC - GC_mean) × (DXY - DXY_mean)) / 
                      √(Σ(GC - GC_mean)² × Σ(DXY - DXY_mean)²)
```

Rolling correlation computed over a configurable window (default 50 periods).

> **Enhanced Version Available**: For more robust correlation analysis, see [Multi-Window DXY Correlation](dxy-multiwindow-correlation.md) which analyzes correlation across 15/30/60 minute windows with weighted scoring. This provides smoother signals and reduces noise compared to single-window correlation.

## Basic Usage

```python
from feature_engine import calculate_dxy_correlation
import pandas as pd

# Load GC and DXY data
gc_df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])
dxy_df = pd.read_csv('data/gc_dx_ohlcv/DX_ohlcv-1m.csv', parse_dates=['ts_event'])

# Filter to specific symbol
gc_data = gc_df[gc_df['symbol'] == 'GCZ5'].copy()

# Calculate rolling correlation (default window=50)
correlation = calculate_dxy_correlation(gc_data, dxy_df, window=50)

# Add to DataFrame
gc_data['dxy_correlation'] = correlation

# Identify strong negative correlation periods
gc_data['strong_negative'] = gc_data['dxy_correlation'] < -0.6
```

## API Reference

### calculate_dxy_correlation()

```python
def calculate_dxy_correlation(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    window: int = 50,
    gc_price_column: str = "close",
    dxy_price_column: str = "close",
    timestamp_column: str = "ts_event"
) -> pd.Series
```

**Parameters:**

- `gc_df` (pd.DataFrame): DataFrame containing Gold (GC) price data
  - Must contain `timestamp_column` and `gc_price_column`
  
- `dxy_df` (pd.DataFrame): DataFrame containing Dollar Index (DXY) price data
  - Must contain `timestamp_column` and `dxy_price_column`
  
- `window` (int, default=50): Number of periods for rolling correlation
  - Must be >= 2
  - Default 50 per SOP requirements
  - Larger window = smoother, less responsive
  - Smaller window = more responsive, more noise

- `gc_price_column` (str, default="close"): Name of GC price column
  - Typically "close" for closing prices
  
- `dxy_price_column` (str, default="close"): Name of DXY price column
  - Typically "close" for closing prices
  
- `timestamp_column` (str, default="ts_event"): Name of timestamp column
  - Used for inner join alignment
  - Must be datetime-compatible

**Returns:**

- `pd.Series`: Rolling correlation values (-1.0 to +1.0)
  - Indexed by aligned timestamps (inner join)
  - First (window-1) values are NaN (initial calculation window)
  - Correlation interpretation:
    - **-1.0**: Perfect negative correlation (GC up, DXY down)
    - **< -0.6**: Strong negative correlation (typical GC-DXY relationship)
    - **0.0**: No correlation
    - **+1.0**: Perfect positive correlation (GC and DXY move together)

**Raises:**

- `ValueError`: If window < 2
- `ValueError`: If required columns missing
- `ValueError`: If timestamp cannot be parsed as datetime

## Advanced Examples

### Using with Real Market Data

```python
import pandas as pd
from feature_engine import calculate_dxy_correlation

# Load real GC and DXY data
gc_df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])
dxy_df = pd.read_csv('data/gc_dx_ohlcv/DX_ohlcv-1m.csv', parse_dates=['ts_event'])

# Filter to specific symbol
gc_data = gc_df[gc_df['symbol'] == 'GCZ5'].copy()

# Calculate correlation
correlation = calculate_dxy_correlation(gc_data, dxy_df, window=50)
gc_data['dxy_correlation'] = correlation

# Identify correlation regimes
gc_data['strong_negative'] = gc_data['dxy_correlation'] < -0.6
gc_data['weak_negative'] = (gc_data['dxy_correlation'] < 0) & (gc_data['dxy_correlation'] >= -0.6)
gc_data['positive'] = gc_data['dxy_correlation'] > 0

# Count periods
print(f"Strong negative: {gc_data['strong_negative'].sum()}")
print(f"Weak negative: {gc_data['weak_negative'].sum()}")
print(f"Positive: {gc_data['positive'].sum()}")
```

### Multiple Window Analysis

```python
# Compare different correlation windows
gc_data['corr_20'] = calculate_dxy_correlation(gc_data, dxy_df, window=20)
gc_data['corr_50'] = calculate_dxy_correlation(gc_data, dxy_df, window=50)
gc_data['corr_100'] = calculate_dxy_correlation(gc_data, dxy_df, window=100)

# Short-term vs long-term correlation
gc_data['corr_divergence'] = gc_data['corr_20'] - gc_data['corr_100']

# When short-term correlation differs from long-term
gc_data['corr_regime_change'] = abs(gc_data['corr_divergence']) > 0.3
```

### Custom Price Columns

```python
# Use high prices instead of close
correlation_high = calculate_dxy_correlation(
    gc_data,
    dxy_df,
    window=50,
    gc_price_column='high',
    dxy_price_column='high'
)

# Use low prices
correlation_low = calculate_dxy_correlation(
    gc_data,
    dxy_df,
    window=50,
    gc_price_column='low',
    dxy_price_column='low'
)
```

### Custom Timestamp Column

```python
# If timestamp column has different name
gc_renamed = gc_data.rename(columns={'ts_event': 'timestamp'})
dxy_renamed = dxy_df.rename(columns={'ts_event': 'timestamp'})

correlation = calculate_dxy_correlation(
    gc_renamed,
    dxy_renamed,
    window=50,
    timestamp_column='timestamp'
)
```

## Edge Cases Handled

1. **No Overlapping Timestamps:** Returns empty Series
2. **Insufficient Data:** Returns all NaN when data < window
3. **Alignment Mismatches:** Inner join safely handles missing timestamps
4. **Missing Columns:** Clear error messages with column names
5. **Invalid Window:** Validates window >= 2

## Performance Characteristics

- **Time Complexity:** O(n) - single pass through aligned data
- **Memory:** O(n) - stores result series
- **Implementation:** Uses pandas `.rolling().corr()` (optimized)
- **Fully Vectorized:** No Python loops
- **Suitable for:** Real-time streaming data and large datasets

## Testing and Validation

DXY correlation implementation is validated with:
- ✅ Negative correlation (< -0.6) on known inverse segments
- ✅ Tested across 1m and 15m timeframes
- ✅ Inner join alignment handling
- ✅ Multiple window sizes (10, 20, 50, 100)
- ✅ Edge cases (empty data, no overlap, insufficient data)
- ✅ All tests in `tests/unit/test_dxy_correlation.py`

Run DXY correlation tests:
```bash
pytest tests/unit/test_dxy_correlation.py -v
```

## Trading Use Cases

### 1. Market Environment Scoring (SOP Integration)

```python
from feature_engine import calculate_dxy_correlation, calculate_vwap, calculate_rsi, calculate_ema

# Calculate all SOP indicators
gc_data['vwap'] = calculate_vwap(gc_data, session_reset=True)
gc_data['rsi'] = calculate_rsi(gc_data, period=14)
gc_data['ema_20'] = calculate_ema(gc_data, period=20)
gc_data['dxy_correlation'] = calculate_dxy_correlation(gc_data, dxy_df, window=50)

# Market environment score (DXY correlation component)
# Strong negative correlation = predictable relationship = higher score
gc_data['env_score'] = 0
gc_data.loc[gc_data['dxy_correlation'] < -0.6, 'env_score'] = 2  # Strong negative
gc_data.loc[(gc_data['dxy_correlation'] < 0) & (gc_data['dxy_correlation'] >= -0.6), 'env_score'] = 1  # Weak negative
gc_data.loc[gc_data['dxy_correlation'] >= 0, 'env_score'] = 0  # Positive or no correlation

# Combined SOP signal (Structure + Trend + Momentum + Environment)
gc_data['sop_score'] = (
    (gc_data['close'] > gc_data['vwap']).astype(int) * 4 +      # Structure: 4 points
    (gc_data['close'] > gc_data['ema_20']).astype(int) * 2 +    # Trend: 2 points
    ((gc_data['rsi'] > 30) & (gc_data['rsi'] < 70)).astype(int) * 1 +  # Momentum: 1 point
    gc_data['env_score']  # Environment: 0-2 points
)

gc_data['trade_signal'] = gc_data['sop_score'] >= 8
```

### 2. Correlation Regime Detection

```python
# Identify when correlation regime changes
gc_data['dxy_correlation'] = calculate_dxy_correlation(gc_data, dxy_df, window=50)

# Strong negative correlation regime
gc_data['negative_regime'] = gc_data['dxy_correlation'] < -0.6

# Regime change detection
gc_data['regime_change'] = (
    gc_data['negative_regime'] != gc_data['negative_regime'].shift(1)
)

# Trade only in strong negative correlation regime (predictable relationship)
gc_data['tradeable'] = gc_data['negative_regime']
```

### 3. Correlation Divergence Signals

```python
# Short-term vs long-term correlation
gc_data['corr_short'] = calculate_dxy_correlation(gc_data, dxy_df, window=20)
gc_data['corr_long'] = calculate_dxy_correlation(gc_data, dxy_df, window=100)

# Divergence: short-term correlation weakening while long-term stays strong
gc_data['corr_divergence'] = (
    (gc_data['corr_short'] > gc_data['corr_long']) &  # Short-term less negative
    (gc_data['corr_long'] < -0.6)  # Long-term still strongly negative
)

# Potential reversal signal when correlation breaks down
gc_data['reversal_signal'] = gc_data['corr_divergence']
```

### 4. Risk Assessment

```python
# Use correlation for position sizing
gc_data['dxy_correlation'] = calculate_dxy_correlation(gc_data, dxy_df, window=50)

# Strong negative correlation = predictable relationship = can size larger
# Weak or positive correlation = unpredictable = size smaller
gc_data['position_multiplier'] = 1.0
gc_data.loc[gc_data['dxy_correlation'] < -0.6, 'position_multiplier'] = 1.2  # Size up
gc_data.loc[gc_data['dxy_correlation'] > -0.3, 'position_multiplier'] = 0.8  # Size down
```

## Best Practices

### DXY Correlation-Specific

1. **Window Selection**
   - Use 50 for standard analysis (SOP default)
   - Use 20 for faster signals (more responsive)
   - Use 100 for smoother, longer-term trends

2. **Interpretation**
   - **< -0.6**: Strong negative correlation (typical GC-DXY relationship)
   - **-0.6 to 0**: Weak negative to no correlation
   - **> 0**: Positive correlation (unusual, may indicate regime change)

3. **Alignment**
   - Always ensure timestamps are properly aligned
   - Inner join handles mismatches safely
   - Missing data is excluded (no forward-fill)

4. **Combine with Other Indicators**
   - DXY correlation alone is not sufficient for trading
   - Use with VWAP for structure confirmation
   - Use with EMA for trend direction
   - Use with RSI for momentum

### General Indicator Best Practices

1. **Data Quality**
   - Ensure GC and DXY data have overlapping timestamps
   - Verify timestamp column is datetime type
   - Handle symbol filtering before calculation

2. **Window Size**
   - Larger window = smoother, less noise
   - Smaller window = more responsive, more signals
   - Balance based on trading timeframe

3. **Integration with SOP**
   - DXY correlation feeds into environment score
   - Combine with Structure (VWAP) + Trend (EMA) + Momentum (RSI)
   - Never trade on single indicator alone

## Troubleshooting

**Issue:** All NaN values in correlation output

**Solution:** Check that:
- GC and DXY DataFrames have overlapping timestamps
- Window size is not larger than available data
- Timestamp column is properly parsed as datetime

---

**Issue:** Correlation always positive (unexpected)

**Solution:** 
- Verify data alignment (inner join may be excluding key periods)
- Check that GC and DXY data are from same time periods
- Consider using different window size

---

**Issue:** Correlation not showing expected negative values

**Solution:**
- Gold and Dollar correlation can vary by market conditions
- Check specific time periods (correlation is not always negative)
- Use longer window (100) to smooth out short-term noise
- Verify data quality (no data errors or gaps)

---

**Issue:** Empty Series returned

**Solution:**
- No overlapping timestamps between GC and DXY DataFrames
- Check timestamp column names match
- Verify timestamp formats are compatible
- Ensure both DataFrames have data in same time range

## Comparison: DXY Correlation vs Other Indicators

| Indicator | Purpose | Best For | Key Signal |
|-----------|---------|----------|------------|
| **DXY Correlation** | Market environment | Risk assessment, regime detection | < -0.6 (strong negative) |
| **VWAP** | Fair value | Structure confirmation | Price vs VWAP position |
| **RSI** | Momentum | Overbought/oversold | 70/30 levels |
| **EMA** | Trend | Trend direction | Price vs EMA position |

**Combined SOP Signal:**
- Price > VWAP (structure) ✓
- Price > EMA 20 (trend) ✓  
- 30 < RSI < 70 (momentum healthy) ✓
- DXY correlation < -0.6 (environment predictable) ✓
- = High-quality setup (8+/10 score)

## Further Reading

- [VWAP Documentation](./vwap.md) - Volume-weighted average price
- [RSI Documentation](./rsi.md) - Relative Strength Index
- [EMA Documentation](./ema.md) - Exponential Moving Average
- [Feature Engine Overview](./README.md) - All indicators
- [Data Layer Guide](../10-data-layer.md) - OHLCV data structures

---

**Related Documentation:**
- [Feature Engine Overview](./README.md)
- [Development Workflow](../05-development-workflow.md)
- [Testing Guide](../06-testing.md)

