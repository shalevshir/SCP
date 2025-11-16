# Feature Engine Documentation

The Feature Engine module provides technical indicators and feature calculations for market analysis. All indicators are designed to work with OHLCV DataFrame structures and follow consistent API patterns.

## Overview

The Feature Engine calculates technical indicators required by the Rule Engine for trade signal generation. Each indicator:
- Accepts pandas DataFrames with standardized OHLCV columns
- Returns pandas Series with the same index as input
- Handles edge cases (NaN, zero volume, missing data)
- Supports session-based calculations where applicable
- Is thoroughly tested with ≥99% correlation to industry benchmarks

## Implemented Indicators

### ✅ [VWAP (Volume-Weighted Average Price)](./vwap.md)
**Purpose:** Identify fair value and institutional order flow

**Key Features:**
- Daily session resets (configurable)
- Cumulative mode for multi-day analysis
- 100% correlation with manual calculation
- Handles zero volume and NaN gracefully

**Usage:**
```python
from feature_engine import calculate_vwap
df['vwap'] = calculate_vwap(df, session_reset=True)
```

[📖 Full VWAP Documentation](./vwap.md)

---

### ✅ [RSI (Relative Strength Index)](./rsi.md)
**Purpose:** Measure momentum and identify overbought/oversold conditions

**Key Features:**
- Wilder's smoothing method (industry standard)
- ±0.1 precision vs TA-Lib
- Configurable periods (default 14)
- Handles all gains/losses edge cases

**Usage:**
```python
from feature_engine import calculate_rsi
df['rsi'] = calculate_rsi(df, period=14)
```

[📖 Full RSI Documentation](./rsi.md)

---

### ✅ [EMA (Exponential Moving Average)](./ema.md)
**Purpose:** Identify trends and generate trading signals

**Key Features:**
- Gives more weight to recent prices
- SOP periods: 9 (fast), 20 (medium), 50 (slow)
- ±0.01 precision vs TA-Lib
- Fully vectorized (pandas .ewm())
- Multiple EMA helper function

**Usage:**
```python
from feature_engine import calculate_ema, calculate_ema_multiple
df['ema_20'] = calculate_ema(df, period=20)
emas = calculate_ema_multiple(df, periods=[9, 20, 50])
```

[📖 Full EMA Documentation](./ema.md)

---

### ✅ [DXY Correlation](./dxy-correlation.md)
**Purpose:** Measure relationship between Gold and Dollar Index for market environment analysis

**Key Features:**
- Rolling Pearson correlation (default window 50)
- Inner join alignment (handles mismatches safely)
- Negative correlation validation (< -0.6 on inverse segments)
- Tested on 1m and 15m timeframes
- Fully vectorized implementation

**Usage:**
```python
from feature_engine import calculate_dxy_correlation
correlation = calculate_dxy_correlation(gc_df, dxy_df, window=50)
```

[📖 Full DXY Correlation Documentation](./dxy-correlation.md)

---

## Planned Indicators (Phase 2)

The following indicators are under development:

- **ATR (Average True Range)** - Volatility measurement for position sizing

Each new indicator will follow the same patterns established by VWAP and RSI:
- Standardized DataFrame input/Series output
- Comprehensive edge case handling
- ≥99% correlation validation
- Full test coverage

## Quick Start

### Installation

```bash
# Install dependencies
uv sync  # or poetry install

# Verify installation
python -c "from feature_engine import calculate_vwap, calculate_rsi; print('OK')"
```

### Basic Example

```python
import pandas as pd
from feature_engine import calculate_vwap, calculate_rsi

# Load your data
df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])

# Calculate indicators
df['vwap'] = calculate_vwap(df, session_reset=True)
df['rsi'] = calculate_rsi(df, period=14)

# Identify trading conditions
df['above_vwap'] = df['close'] > df['vwap']
df['overbought'] = df['rsi'] > 70
df['oversold'] = df['rsi'] < 30

# SOP-aligned signal: Price above VWAP, RSI not overbought
df['long_setup'] = (df['close'] > df['vwap']) & (df['rsi'] < 70)
```

## Architecture

### Module Structure

```
feature_engine/
├── __init__.py       # Exports all indicators
├── vwap.py          # VWAP calculation
├── rsi.py           # RSI calculation
└── (future indicators...)
```

### Design Principles

1. **Consistent API**
   - All indicators accept DataFrames and return Series
   - Same index preservation across all indicators
   - Predictable parameter naming

2. **Edge Case Handling**
   - No NaN propagation beyond expected windows
   - Graceful handling of insufficient data
   - Clear error messages with actionable guidance

3. **Performance**
   - Vectorized operations where possible
   - O(n) time complexity for most indicators
   - Suitable for real-time streaming data

4. **Testing**
   - ≥99% correlation with industry benchmarks
   - Comprehensive edge case coverage
   - Real market data validation

## Integration with Trading System

### SOP (Standard Operating Procedure) Alignment

The Feature Engine is designed to support Shir Capital's SOP scoring system:

```python
# Example SOP-aligned logic
df['vwap'] = calculate_vwap(df, session_reset=True)
df['rsi'] = calculate_rsi(df, period=14)

# Structure confirmation (VWAP)
df['structure_long'] = df['close'] > df['vwap']
df['structure_short'] = df['close'] < df['vwap']

# Momentum confirmation (RSI)
df['momentum_healthy'] = (df['rsi'] > 30) & (df['rsi'] < 70)

# Combined signal (8+/10 scoring)
df['signal_quality'] = (
    df['structure_long'].astype(int) * 4 +    # Structure = 4 points
    df['momentum_healthy'].astype(int) * 2 +  # Momentum = 2 points
    # ... additional factors (DXY, volume, etc.)
)

df['trade_signal'] = df['signal_quality'] >= 8
```

### Rule Engine Integration

Feature Engine outputs feed directly into the Rule Engine:

1. **VWAP** → Structure confirmation score
2. **RSI** → Momentum score  
3. **EMA** (future) → Trend direction score
4. **DXY Correlation** (future) → Market environment score

## Best Practices

### 1. Calculate Once, Use Many Times

```python
# Good: Calculate indicators once
df['vwap'] = calculate_vwap(df, session_reset=True)
df['rsi'] = calculate_rsi(df, period=14)

# Use for multiple analyses
long_signals = df[df['close'] > df['vwap']]
overbought = df[df['rsi'] > 70]
```

### 2. Validate Data Before Calculation

```python
# Check for required columns
required = {'close', 'high', 'low', 'volume'}
assert required.issubset(df.columns), f"Missing columns: {required - set(df.columns)}"

# Ensure proper data types
df['ts_event'] = pd.to_datetime(df['ts_event'])
```

### 3. Handle Multiple Timeframes

```python
# Calculate on different timeframes
for timeframe in ['1m', '15m', '1h']:
    df_tf = load_data(timeframe)
    df_tf['vwap'] = calculate_vwap(df_tf)
    df_tf['rsi'] = calculate_rsi(df_tf)
    analyze(df_tf)
```

### 4. Never Trade on Single Indicator

```python
# Bad: Single indicator signal
if df['rsi'].iloc[-1] < 30:
    enter_long()  # Too simplistic!

# Good: Multiple confirmations
if (df['rsi'].iloc[-1] < 30 and           # Oversold
    df['close'].iloc[-1] > df['vwap'].iloc[-1] and  # Above VWAP
    df['volume'].iloc[-1] > df['volume'].mean()):    # Volume confirmation
    enter_long()  # Multi-factor signal
```

## Troubleshooting

### Common Issues

**Issue:** `ModuleNotFoundError: No module named 'feature_engine'`
```bash
# Solution: Install package
cd /path/to/SCP
uv pip install -e .
```

**Issue:** `ValueError: Missing required columns`
```python
# Solution: Verify DataFrame structure
print(df.columns.tolist())
print(df.dtypes)
```

**Issue:** All NaN values in indicator output
```python
# Solution: Check data length vs period
print(f"Data length: {len(df)}, RSI period: 14")
# Need at least period+1 rows for valid output
```

**Issue:** VWAP not resetting at session boundaries
```python
# Solution: Ensure timestamp column is datetime type
df['ts_event'] = pd.to_datetime(df['ts_event'])
```

## Contributing

When adding new indicators:

1. **Follow TDD**: Write failing tests first
2. **Validate Accuracy**: ≥99% correlation with benchmarks
3. **Handle Edge Cases**: Test all error conditions
4. **Document Thoroughly**: Create `docs/feature-engine/[indicator].md`
5. **Update README**: Add to indicators list above
6. **Export Function**: Update `feature_engine/__init__.py`

See [Development Workflow](../05-development-workflow.md) for full TDD guidelines.

## Testing

Run all feature engine tests:
```bash
pytest tests/unit/test_vwap.py tests/unit/test_rsi.py -v
```

Run specific indicator tests:
```bash
pytest tests/unit/test_vwap.py -v  # VWAP only
pytest tests/unit/test_rsi.py -v   # RSI only
```

With coverage:
```bash
pytest tests/unit/ --cov=feature_engine --cov-report=html
```

## Further Reading

- [VWAP Full Documentation](./vwap.md) - Complete VWAP guide with examples
- [RSI Full Documentation](./rsi.md) - Complete RSI guide with examples
- [Data Layer Guide](../10-data-layer.md) - OHLCV data structures
- [Testing Guide](../06-testing.md) - Test framework and TDD practices
- [Development Workflow](../05-development-workflow.md) - Coding standards

---

**Related Documentation:**
- [Project Overview](../01-project-overview.md)
- [Development Workflow](../05-development-workflow.md)
- [Testing Guide](../06-testing.md)

