# Feature Engine Guide

The Feature Engine module provides technical indicators and feature calculations for market analysis. All indicators are designed to work with OHLCV DataFrame structures and follow consistent API patterns.

## Overview

The Feature Engine calculates technical indicators required by the Rule Engine for trade signal generation. Each indicator:
- Accepts pandas DataFrames with standardized OHLCV columns
- Returns pandas Series with the same index as input
- Handles edge cases (NaN, zero volume, missing data)
- Supports session-based calculations where applicable
- Is thoroughly tested with ≥99% correlation to industry benchmarks

## Available Indicators

### VWAP (Volume-Weighted Average Price)

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
# Identify when price deviates significantly from VWAP
df['vwap_deviation_pct'] = ((df['close'] - df['vwap']) / df['vwap']) * 100

# Filter for significant deviations (>0.5%)
significant_moves = df[abs(df['vwap_deviation_pct']) > 0.5]
```

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

## Future Indicators

The following indicators are planned for Phase 2:

- **RSI (Relative Strength Index)** - Momentum and overbought/oversold conditions
- **EMA (Exponential Moving Average)** - Trend identification (9, 20, 50 periods)
- **DXY Correlation** - Dollar index relationship analysis
- **ATR (Average True Range)** - Volatility measurement for position sizing

Each indicator will follow the same patterns established by VWAP:
- Standardized DataFrame input/Series output
- Comprehensive edge case handling
- ≥99% correlation validation
- Full test coverage

## Troubleshooting

**Issue:** `ValueError: Missing required columns`
```python
# Solution: Verify DataFrame has all required columns
required = {'high', 'low', 'close', 'volume'}
missing = required - set(df.columns)
print(f"Missing columns: {missing}")
```

**Issue:** VWAP not resetting at session boundaries
```python
# Solution: Check timestamp column is datetime type
print(df['ts_event'].dtype)  # Should be datetime64[ns]
df['ts_event'] = pd.to_datetime(df['ts_event'])
```

**Issue:** NaN values in VWAP output
```python
# Solution: Check for all-zero volume or all-NaN prices
print(f"Zero volume rows: {(df['volume'] == 0).sum()}")
print(f"NaN prices: {df[['high', 'low', 'close']].isna().sum()}")
```

## Contributing

When adding new indicators to the Feature Engine:

1. Follow TDD: Write failing tests first
2. Validate against industry benchmarks (≥99% correlation)
3. Handle all edge cases (NaN, zero, single row, etc.)
4. Document API with examples
5. Add to this documentation
6. Update `feature_engine/__init__.py` exports

See [Development Workflow](./05-development-workflow.md) for full TDD guidelines.

---

**Related Documentation:**
- [Data Layer Guide](./10-data-layer.md) - OHLCV data structure
- [Testing Guide](./06-testing.md) - Test framework and practices
- [Development Workflow](./05-development-workflow.md) - TDD methodology

