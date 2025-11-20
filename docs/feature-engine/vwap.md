# VWAP (Volume-Weighted Average Price)

[← Back to Feature Engine](./README.md)

**Purpose:** Calculate the volume-weighted average price, a key indicator for identifying fair value and institutional order flow.

**Formula:**
```
VWAP = Σ(Typical Price × Volume) / Σ(Volume)
where Typical Price = (High + Low + Close) / 3
```

#### Basic Usage

```python
from feature_engine import calculate_vwap
import pandas as pd

# Load your OHLCV data
df = pd.DataFrame({
    'ts_event': pd.date_range('2025-01-01 09:00', periods=100, freq='1min'),
    'high': [...],
    'low': [...],
    'close': [...],
    'volume': [...]
})

# Calculate VWAP with daily session resets (default)
vwap = calculate_vwap(df, session_reset=True)

# Calculate cumulative VWAP (no resets)
vwap_cumulative = calculate_vwap(df, session_reset=False)

# Add VWAP to DataFrame
df['vwap'] = vwap
```

#### API Reference

```python
def calculate_vwap(
    df: pd.DataFrame,
    session_reset: bool = True,
    session_column: str = "ts_event"
) -> pd.Series
```

**Parameters:**

- `df` (pd.DataFrame): DataFrame containing OHLCV data with required columns:
  - `high`: High price for the period
  - `low`: Low price for the period
  - `close`: Close price for the period
  - `volume`: Trading volume for the period
  - `ts_event` (or custom column): Timestamp for session detection

- `session_reset` (bool, default=True): 
  - `True`: Reset VWAP calculation at day boundaries (detects date changes)
  - `False`: Calculate cumulative VWAP across entire dataset

- `session_column` (str, default="ts_event"): 
  - Name of the timestamp column used for session boundary detection
  - Must be datetime or parseable as datetime when `session_reset=True`

**Returns:**

- `pd.Series`: VWAP values with same index as input DataFrame

**Raises:**

- `ValueError`: If required columns are missing
- `ValueError`: If `session_column` not found or not parseable as datetime

#### Advanced Examples

**Using with Real Market Data:**

```python
import pandas as pd
from feature_engine import calculate_vwap

# Load real GC (Gold) data
df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])

# Filter to specific symbol
gc_data = df[df['symbol'] == 'GCZ5'].copy()

# Calculate intraday VWAP (resets daily)
gc_data['vwap'] = calculate_vwap(gc_data, session_reset=True)

# Identify price vs VWAP relationship
gc_data['above_vwap'] = gc_data['close'] > gc_data['vwap']
gc_data['distance_from_vwap'] = gc_data['close'] - gc_data['vwap']
```

**Custom Session Times:**

```python
# For markets with non-standard session times,
# pre-process timestamp to create session groups

df['session_id'] = df['ts_event'].apply(lambda x: 
    x.replace(hour=0, minute=0, second=0) 
    if x.hour >= 17 else 
    (x - pd.Timedelta(days=1)).replace(hour=0, minute=0, second=0)
)

# Use custom session column
vwap = calculate_vwap(df, session_reset=True, session_column='session_id')
```

**Multiple Timeframes:**

```python
# Calculate VWAP on different timeframes
for timeframe in ['1m', '15m', '1h']:
    df = pd.read_csv(f'data/gc_dx_ohlcv/GC_ohlcv-{timeframe}.csv', 
                     parse_dates=['ts_event'])
    df['vwap'] = calculate_vwap(df)
    print(f"{timeframe} VWAP calculated")
```

#### Edge Cases Handled

1. **Zero Volume:** Replaces with epsilon to prevent division by zero
2. **NaN Values:** Forward fills or uses close price for typical price calculation
3. **Single Row:** Returns typical price as VWAP
4. **Session Boundaries:** Correctly resets cumulative calculations at day changes
5. **Index Preservation:** Maintains original DataFrame index in returned Series

#### Performance Characteristics

- **Time Complexity:** O(n) for non-reset mode, O(n log n) for session reset mode
- **Memory:** O(n) additional memory for cumulative calculations
- **Vectorized:** Uses pandas/numpy vectorized operations for performance

#### Testing and Validation

VWAP implementation is validated with:
- ✅ 100% correlation with manual calculation (exceeds ≥99% requirement)
- ✅ Real market data testing (GC 1-minute bars)
- ✅ Comprehensive edge case coverage
- ✅ All tests in `tests/unit/test_vwap.py`

Run VWAP tests:
```bash
pytest tests/unit/test_vwap.py -v
```

## Trading Use Cases

### 1. Fair Value Reference
```python
from feature_engine import calculate_vwap_deviation

# Calculate VWAP deviation percentage
df['vwap_deviation'] = calculate_vwap_deviation(df)

# Filter for significant deviations (>0.5%)
significant_moves = df[df['vwap_deviation'] > 0.5]
```

### VWAP Deviation Function

The `calculate_vwap_deviation()` function computes the absolute percentage deviation of close price from VWAP, which is useful for identifying fade opportunities:

```python
from feature_engine import calculate_vwap_deviation

df['vwap_deviation'] = calculate_vwap_deviation(df)
# Formula: abs((close - vwap) / vwap * 100)
```

**Interpretation:**
- **Low deviation (< 0.5%)**: Price near VWAP, continuation setups more likely
- **High deviation (> 1.0%)**: Price far from VWAP, fade setups more likely
- **Extreme deviation (> 2.0%)**: Strong fade opportunity (counter-trend)

### 2. Structure Confirmation (SOP Alignment)
```python
# Per Shir Capital SOP: VWAP provides structure confirmation
# Long signals: Price must be above VWAP
# Short signals: Price must be below VWAP

df['structure_long'] = df['close'] > df['vwap']
df['structure_short'] = df['close'] < df['vwap']
```

### 3. Institutional Order Flow
```python
# VWAP crossovers indicate institutional positioning changes
df['vwap_cross_up'] = (df['close'] > df['vwap']) & (df['close'].shift(1) <= df['vwap'].shift(1))
df['vwap_cross_down'] = (df['close'] < df['vwap']) & (df['close'].shift(1) >= df['vwap'].shift(1))
```

### 4. Multi-Timeframe Analysis
```python
# Higher timeframe VWAP as major structure
# Lower timeframe for entry timing
htf_vwap = calculate_vwap(df_1h, session_reset=True)
ltf_vwap = calculate_vwap(df_1m, session_reset=True)

# Align and compare
# (requires TimeAligner - see Data Layer docs)
```

## Best Practices

1. **Session Reset Configuration**
   - Use `session_reset=True` for intraday trading (recommended for SOP)
   - Use `session_reset=False` for longer-term analysis

2. **Data Quality**
   - Ensure timestamps are properly parsed as datetime
   - Verify volume data is present and non-negative
   - Handle symbol filtering before VWAP calculation

3. **Performance**
   - Calculate VWAP once and store in DataFrame
   - Avoid recalculating on every iteration in loops
   - Use vectorized operations for analysis

4. **Integration with Rule Engine**
   - VWAP feeds into SOP scoring (structure confirmation)
   - Combine with DXY correlation and RSI for complete signal

---

