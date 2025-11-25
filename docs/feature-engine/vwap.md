# VWAP (Volume-Weighted Average Price)

[← Back to Feature Engine](./README.md)

**Purpose:** Calculate the volume-weighted average price, a key indicator for identifying fair value and institutional order flow.

**Session Reset:** VWAP resets at **08:20 AM Eastern Time** (Regular Trading Hours open for Gold futures), which is the institutional standard used by most hedge funds and commodity traders.

**Formula:**
```
VWAP = Σ(Typical Price × Volume) / Σ(Volume)
where Typical Price = (High + Low + Close) / 3
```

## Session Reset Behavior

### 08:20 ET Reset Time

VWAP sessions reset at **08:20 AM ET** to align with institutional standards for Gold futures trading:

- **Sessions run:** 08:20 ET → 08:19:59 ET next day
- **Bars before 08:20 ET** belong to the **previous** session
- **Bars at/after 08:20 ET** start a **new** session

**Why 08:20 ET?**
- Regular Trading Hours (RTH) open for Gold futures
- Where most institutional volume occurs
- Industry standard for intraday VWAP calculation
- Used by hedge funds and commodity trading desks

### DST Handling

DST transitions are handled automatically using the `America/New_York` timezone:
- **EST (Winter):** UTC-5 → 08:20 EST = 13:20 UTC
- **EDT (Summer):** UTC-4 → 08:20 EDT = 12:20 UTC
- Transitions occur automatically on DST boundaries

### Examples

**Session Grouping:**
```python
from datetime import datetime
from zoneinfo import ZoneInfo

# Example 1: Before reset (belongs to previous session)
# 08:00 ET on Jan 15 → Jan 14 session
ts1 = datetime(2025, 1, 15, 13, 0, tzinfo=ZoneInfo("UTC"))  # 08:00 ET
# VWAP cumulative from Jan 14 session

# Example 2: At reset (starts new session)
# 08:20 ET on Jan 15 → Jan 15 session
ts2 = datetime(2025, 1, 15, 13, 20, tzinfo=ZoneInfo("UTC"))  # 08:20 ET
# VWAP resets, first bar of Jan 15 session

# Example 3: After reset (continues new session)
# 10:00 ET on Jan 15 → Jan 15 session
ts3 = datetime(2025, 1, 15, 15, 0, tzinfo=ZoneInfo("UTC"))  # 10:00 ET
# VWAP cumulative within Jan 15 session
```

#### Basic Usage

```python
from feature_engine import calculate_vwap
import pandas as pd

# Load your OHLCV data (with timezone-aware timestamps)
df = pd.DataFrame({
    'ts_event': pd.date_range('2025-01-01 09:00', periods=100, freq='1min', tz='UTC'),
    'high': [...],
    'low': [...],
    'close': [...],
    'volume': [...]
})

# Calculate VWAP with 08:20 ET session resets (default)
vwap = calculate_vwap(df, session_reset=True)

# Calculate cumulative VWAP (no resets)
vwap_cumulative = calculate_vwap(df, session_reset=False)

# Add VWAP to DataFrame
df['vwap'] = vwap
```

**Note:** Timezone-naive timestamps are assumed to be UTC. For best results, use timezone-aware timestamps.

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
  - `True`: Reset VWAP at **08:20 AM ET** session boundaries
  - `False`: Calculate cumulative VWAP across entire dataset
  - Sessions run from 08:20 ET to 08:19:59 ET next day

- `session_column` (str, default="ts_event"): 
  - Name of the timestamp column used for session boundary detection
  - Must be datetime or parseable as datetime when `session_reset=True`
  - **Timezone-naive timestamps are assumed to be UTC**

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

# Load real GC (Gold) data with timezone parsing
df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])

# Ensure timestamps are timezone-aware (assume UTC if not specified)
if df['ts_event'].dt.tz is None:
    df['ts_event'] = df['ts_event'].dt.tz_localize('UTC')

# Filter to specific symbol
gc_data = df[df['symbol'] == 'GCZ5'].copy()

# Calculate intraday VWAP (resets at 08:20 ET)
gc_data['vwap'] = calculate_vwap(gc_data, session_reset=True)

# Identify price vs VWAP relationship
gc_data['above_vwap'] = gc_data['close'] > gc_data['vwap']
gc_data['distance_from_vwap'] = gc_data['close'] - gc_data['vwap']
```

**Session Reset Visualization:**

```python
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

# Create data around the 08:20 ET reset boundary
timestamps = pd.date_range(
    start='2025-01-15 13:00',  # 08:00 ET
    end='2025-01-15 14:00',    # 09:00 ET
    freq='1min',
    tz='UTC'
)

# Sample OHLCV data
df = pd.DataFrame({
    'ts_event': timestamps,
    'high': [2650.0] * len(timestamps),
    'low': [2640.0] * len(timestamps),
    'close': [2645.0] * len(timestamps),
    'volume': [1000.0] * len(timestamps)
})

# Calculate VWAP
df['vwap'] = calculate_vwap(df, session_reset=True)

# VWAP will reset at index where ts_event == 13:20 UTC (08:20 ET)
reset_idx = df[df['ts_event'] == '2025-01-15 13:20:00+00:00'].index[0]
print(f"VWAP resets at index {reset_idx}")
print(f"Before reset: {df.loc[reset_idx-1, 'vwap']:.2f}")
print(f"After reset: {df.loc[reset_idx, 'vwap']:.2f} (equal to typical price)")
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
4. **Session Boundaries:** Correctly resets at 08:20 ET, handles DST transitions automatically
5. **Timezone-Naive Data:** Assumes UTC if no timezone specified
6. **Index Preservation:** Maintains original DataFrame index in returned Series

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
   - Sessions reset at 08:20 ET (Regular Trading Hours open)
   - Use `session_reset=False` for longer-term analysis

2. **Timezone Awareness**
   - **Always use timezone-aware timestamps** for accurate session detection
   - Timezone-naive timestamps are assumed to be UTC
   - DST transitions are handled automatically (EST ↔ EDT)
   - Verify your data timezone matches expectations

3. **Data Quality**
   - Ensure timestamps are properly parsed as datetime
   - Verify volume data is present and non-negative
   - Handle symbol filtering before VWAP calculation
   - Check for gaps around 08:20 ET reset time

4. **Performance**
   - Calculate VWAP once and store in DataFrame
   - Avoid recalculating on every iteration in loops
   - Use vectorized operations for analysis

5. **Integration with Rule Engine**
   - VWAP feeds into SOP scoring (structure confirmation)
   - Combine with DXY correlation and RSI for complete signal
   - Session reset aligns with institutional standards

## Implementation Notes

### Institutional Standard

The 08:20 ET reset aligns with institutional VWAP standards for Gold futures:
- **RTH (Regular Trading Hours):** 08:20 ET - 13:30 ET
- **Most institutional volume** occurs during RTH
- **Industry standard** for hedge funds and commodity desks
- **Prevents arbitrary midnight resets** that don't reflect actual trading sessions

### Why Not Midnight?

Gold trades nearly 24 hours on Globex (18:00 ET → 17:00 ET). A midnight reset would be arbitrary and not aligned with actual institutional trading patterns. The 08:20 ET reset reflects where real trading activity and liquidity begin.

---

