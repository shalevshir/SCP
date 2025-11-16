# Feature Engine Aggregator

**Purpose:** Combine all technical indicators into a unified DataFrame with modular configuration.

The Feature Engine Aggregator provides a single interface to calculate all SOP-required indicators (VWAP, RSI, EMA, DXY correlation) with flexible configuration and consistent output structure.

[← Back to Feature Engine](./README.md)

---

## Table of Contents

- [Overview](#overview)
- [API Reference](#api-reference)
- [Default Configuration](#default-configuration)
- [Usage Examples](#usage-examples)
- [Modular Configuration](#modular-configuration)
- [Timeframe Validation](#timeframe-validation)
- [SOP Integration](#sop-integration)
- [Trading Use Cases](#trading-use-cases)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Overview

The aggregator simplifies feature calculation by:

- **Unified Interface:** Single function call for all indicators
- **Modular Configuration:** Enable/disable indicators and customize parameters
- **Automatic Alignment:** Handles GC/DXY alignment for correlation
- **Index Preservation:** Maintains original DataFrame structure
- **Timeframe Validation:** Enforces SOP-approved timeframes
- **Type Safety:** All feature columns are numeric (float64)

### When to Use

✅ **Use the aggregator when:**
- You need multiple indicators simultaneously
- You want consistent configuration across your system
- You're integrating with the Rule Engine
- You need guaranteed column structure

❌ **Use individual indicators when:**
- You only need one specific indicator
- You want maximum flexibility
- You're benchmarking/testing a single indicator

---

## API Reference

### `aggregate_features()`

```python
def aggregate_features(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    indicators: dict | None = None,
) -> pd.DataFrame
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `gc_df` | `pd.DataFrame` | Gold (GC) OHLCV data. Must contain: `open`, `high`, `low`, `close`, `volume`. |
| `dxy_df` | `pd.DataFrame` | DXY (Dollar Index) price data. Must contain: `close`, `ts_event`. |
| `timeframe` | `str` | Target timeframe. Must be one of: `["1s", "1m", "15m", "1h"]`. |
| `indicators` | `dict \| None` | Optional configuration dict. If `None`, all indicators are calculated with defaults. |

#### Returns

`pd.DataFrame` - Original GC DataFrame with added feature columns:
- All original GC columns preserved
- Feature columns added based on `indicators` config:
  - `vwap`: Volume-Weighted Average Price
  - `rsi`: Relative Strength Index
  - `ema_9`, `ema_20`, `ema_50`: Exponential Moving Averages
  - `dxy_corr`: Rolling Pearson correlation with DXY

#### Raises

| Exception | Condition |
|-----------|-----------|
| `ValueError` | Invalid timeframe (not in `ALLOWED_TIMEFRAMES`) |
| `ValueError` | Missing required GC columns |
| `TypeError` | Non-DataFrame inputs |
| `DataSourceError` | GC/DXY alignment failure (from `calculate_dxy_correlation`) |

---

## Default Configuration

When `indicators=None`, the aggregator uses SOP standard parameters:

```python
DEFAULT_INDICATORS = {
    "vwap": {"session_reset": True},      # Daily session VWAP
    "rsi": {"period": 14},                # Standard RSI period
    "ema": {"periods": [9, 20, 50]},      # Fast, medium, slow EMAs
    "dxy_correlation": {"window": 50}     # SOP correlation window
}
```

---

## Usage Examples

### Basic Usage (All Indicators with Defaults)

```python
from feature_engine import aggregate_features
import pandas as pd

# Load data
gc_df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])
dxy_df = pd.read_csv('data/gc_dx_ohlcv/DX_ohlcv-1m.csv', parse_dates=['ts_event'])

# Aggregate all features (defaults)
features = aggregate_features(gc_df, dxy_df, "1m")

print(features.columns)
# Index(['ts_event', 'open', 'high', 'low', 'close', 'volume',
#        'vwap', 'rsi', 'ema_9', 'ema_20', 'ema_50', 'dxy_corr'])

print(features.dtypes['vwap'])
# dtype('float64')  ✓ All feature columns are numeric
```

### Skip Specific Indicators

```python
# Only VWAP and RSI (skip EMA and DXY)
indicators = {
    "vwap": True,
    "rsi": True,
    "ema": False,
    "dxy_correlation": None  # None or False both work
}

features = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

print("vwap" in features.columns)  # True
print("rsi" in features.columns)   # True
print("ema_9" in features.columns) # False
print("dxy_corr" in features.columns)  # False
```

### Custom Parameters

```python
# Customize indicator parameters
indicators = {
    "vwap": {"session_reset": False},    # Cumulative VWAP
    "rsi": {"period": 21},               # Longer RSI period
    "ema": {"periods": [10, 30]},        # Custom EMA periods
    "dxy_correlation": {"window": 30}    # Shorter correlation window
}

features = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

print(features.columns)
# Index(['ts_event', 'open', 'high', 'low', 'close', 'volume',
#        'vwap', 'rsi', 'ema_10', 'ema_30', 'dxy_corr'])
# Note: ema_9, ema_20, ema_50 are NOT present (only 10 and 30)
```

### Mix Defaults and Custom

```python
# Use defaults for some, customize others
indicators = {
    "vwap": True,                # Default: session_reset=True
    "rsi": {"period": 21},       # Custom
    "ema": True,                 # Default: [9, 20, 50]
    "dxy_correlation": False     # Skip
}

features = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)
```

---

## Modular Configuration

The `indicators` parameter supports three types of values:

| Value | Meaning | Example |
|-------|---------|---------|
| `True` | Use default parameters | `"vwap": True` |
| `dict` | Custom parameters | `"rsi": {"period": 21}` |
| `False` or `None` | Skip indicator | `"ema": False` |

### Configuration Examples

#### Structure-Only Analysis

```python
# Only VWAP for structure confirmation
indicators = {
    "vwap": True,
    "rsi": False,
    "ema": False,
    "dxy_correlation": False
}
```

#### Momentum-Focused Analysis

```python
# RSI and EMA for momentum/trend
indicators = {
    "vwap": False,
    "rsi": True,
    "ema": {"periods": [9, 20]},  # Fast and medium only
    "dxy_correlation": False
}
```

#### Environment-Aware Setup

```python
# Structure + Environment (VWAP + DXY)
indicators = {
    "vwap": True,
    "rsi": False,
    "ema": False,
    "dxy_correlation": True
}
```

---

## Timeframe Validation

The aggregator enforces SOP-approved timeframes for consistency:

```python
ALLOWED_TIMEFRAMES = ["1s", "1m", "15m", "1h"]
```

### Valid Timeframes

```python
# All of these pass validation
features = aggregate_features(gc_df, dxy_df, "1s")   # ✓ Tick-level analysis
features = aggregate_features(gc_df, dxy_df, "1m")   # ✓ Minute-level (most common)
features = aggregate_features(gc_df, dxy_df, "15m")  # ✓ Swing trading
features = aggregate_features(gc_df, dxy_df, "1h")   # ✓ Position trading
```

### Invalid Timeframes

```python
# These raise ValueError
features = aggregate_features(gc_df, dxy_df, "5m")   # ✗ Not in ALLOWED_TIMEFRAMES
features = aggregate_features(gc_df, dxy_df, "4h")   # ✗ Not in ALLOWED_TIMEFRAMES
features = aggregate_features(gc_df, dxy_df, "1d")   # ✗ Not in ALLOWED_TIMEFRAMES

# Error message:
# ValueError: Invalid timeframe: '5m'. Must be one of ['1s', '1m', '15m', '1h'].
```

---

## SOP Integration

The aggregator is designed to feed directly into the Rule Engine for SOP-aligned trade scoring.

### Complete SOP Feature Set

```python
from feature_engine import aggregate_features

# Calculate all SOP indicators
features = aggregate_features(gc_df, dxy_df, "1m")

# All four SOP components now available:
# 1. Structure:   features['vwap']
# 2. Momentum:    features['rsi']
# 3. Trend:       features['ema_9'], features['ema_20'], features['ema_50']
# 4. Environment: features['dxy_corr']
```

### SOP-Aligned Long Setup (8+/10 Score)

```python
features = aggregate_features(gc_df, dxy_df, "1m")

# Define SOP long setup conditions
long_setup = (
    (features['close'] > features['vwap']) &              # Structure ✓ (above VWAP)
    (features['close'] > features['ema_20']) &            # Trend ✓ (above medium EMA)
    (features['ema_9'] > features['ema_20']) &            # Trend ✓ (fast > medium)
    (features['rsi'] > 30) & (features['rsi'] < 70) &     # Momentum ✓ (healthy range)
    (features['dxy_corr'] < -0.6)                         # Environment ✓ (strong inverse)
)

# Filter for high-confidence setups
signals = features[long_setup].copy()
print(f"Found {len(signals)} high-quality long setups (8+/10)")
```

### SOP-Aligned Short Setup

```python
short_setup = (
    (features['close'] < features['vwap']) &              # Structure ✓ (below VWAP)
    (features['close'] < features['ema_20']) &            # Trend ✓ (below medium EMA)
    (features['ema_9'] < features['ema_20']) &            # Trend ✓ (fast < medium)
    (features['rsi'] > 30) & (features['rsi'] < 70) &     # Momentum ✓ (healthy range)
    (features['dxy_corr'] < -0.6)                         # Environment ✓ (strong inverse)
)
```

---

## Trading Use Cases

### 1. Multi-Timeframe Analysis

```python
# Calculate features on multiple timeframes
timeframes = ["1m", "15m", "1h"]
features_by_tf = {}

for tf in timeframes:
    # Resample data to target timeframe (not shown)
    gc_tf = resample_ohlcv(gc_df, tf)
    dxy_tf = resample_ohlcv(dxy_df, tf)
    
    features_by_tf[tf] = aggregate_features(gc_tf, dxy_tf, tf)

# Higher timeframe trend, lower timeframe entry
htf_trend = features_by_tf["1h"]["ema_20"]
ltf_entry = features_by_tf["1m"]

# Example: Long when 1h trend is bullish and 1m structure confirms
long_signal = (
    (htf_trend.iloc[-1] > features_by_tf["1h"]["close"].iloc[-10]) &  # 1h uptrend
    (ltf_entry["close"].iloc[-1] > ltf_entry["vwap"].iloc[-1])        # 1m above VWAP
)
```

### 2. Regime Detection

```python
features = aggregate_features(gc_df, dxy_df, "1m")

# Detect market regime
regime = "unknown"

if features["dxy_corr"].iloc[-1] < -0.7:
    regime = "strong_inverse"  # Gold-Dollar strongly inversely correlated
elif features["dxy_corr"].iloc[-1] > -0.3:
    regime = "decoupled"       # Gold-Dollar decoupling (risk-on?)
else:
    regime = "normal_inverse"  # Normal inverse relationship

print(f"Current market regime: {regime}")
```

### 3. Confluence Scoring

```python
features = aggregate_features(gc_df, dxy_df, "1m")

# Score each setup component (0-10)
def score_setup(row):
    score = 0
    
    # Structure (0-3 points)
    if row['close'] > row['vwap']:
        score += 3
    
    # Trend (0-3 points)
    if row['close'] > row['ema_20']:
        score += 2
    if row['ema_9'] > row['ema_20'] > row['ema_50']:
        score += 1
    
    # Momentum (0-2 points)
    if 40 <= row['rsi'] <= 60:
        score += 2
    elif 30 <= row['rsi'] <= 70:
        score += 1
    
    # Environment (0-2 points)
    if row['dxy_corr'] < -0.7:
        score += 2
    elif row['dxy_corr'] < -0.5:
        score += 1
    
    return score

features['setup_score'] = features.apply(score_setup, axis=1)

# Only trade 8+/10 setups
high_quality = features[features['setup_score'] >= 8]
print(f"High-quality setups: {len(high_quality)}")
```

---

## Best Practices

### 1. Calculate Once, Use Many Times

```python
# ✓ Good: Calculate features once
features = aggregate_features(gc_df, dxy_df, "1m")

# Use features for multiple analyses
long_signals = features[features['close'] > features['vwap']]
short_signals = features[features['close'] < features['vwap']]
ranging_signals = features[features['rsi'].between(40, 60)]
```

### 2. Skip Unused Indicators for Performance

```python
# If you only need structure, skip others
indicators = {
    "vwap": True,
    "rsi": False,
    "ema": False,
    "dxy_correlation": False
}

features = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)
# Faster execution, less memory
```

### 3. Validate Data Before Aggregating

```python
# Validate data quality before calling aggregator
assert "ts_event" in gc_df.columns, "GC data missing timestamp"
assert "ts_event" in dxy_df.columns, "DXY data missing timestamp"
assert len(gc_df) > 100, "Insufficient GC data (need >100 bars for warmup)"
assert len(dxy_df) > 100, "Insufficient DXY data (need >100 bars for warmup)"

# Now safe to aggregate
features = aggregate_features(gc_df, dxy_df, "1m")
```

### 4. Handle NaN Values Appropriately

```python
features = aggregate_features(gc_df, dxy_df, "1m")

# Drop warmup period (first 50 bars will have NaN for EMA 50 and DXY correlation)
features_clean = features.dropna()

# Or forward-fill for streaming scenarios
features_filled = features.fillna(method='ffill')

# Or use only recent data (after warmup)
features_recent = features.iloc[60:]  # Skip first 60 bars
```

---

## Troubleshooting

### Issue: ValueError - Invalid timeframe

**Error:**
```
ValueError: Invalid timeframe: '5m'. Must be one of ['1s', '1m', '15m', '1h'].
```

**Solution:**
Use only SOP-approved timeframes: `1s`, `1m`, `15m`, `1h`.

```python
# ✗ Wrong
features = aggregate_features(gc_df, dxy_df, "5m")

# ✓ Correct
features = aggregate_features(gc_df, dxy_df, "1m")
```

---

### Issue: ValueError - Missing required columns

**Error:**
```
ValueError: GC DataFrame missing required columns: ['volume']. Required columns: ['open', 'high', 'low', 'close', 'volume'].
```

**Solution:**
Ensure GC DataFrame has all OHLCV columns.

```python
# Check columns before calling aggregator
required_cols = ["open", "high", "low", "close", "volume"]
missing = [col for col in required_cols if col not in gc_df.columns]
if missing:
    print(f"Missing columns: {missing}")
    # Load correct data or rename columns
```

---

### Issue: Too many NaN values in output

**Symptom:**
Most rows have NaN for RSI, EMA, or DXY correlation.

**Cause:**
Insufficient data for indicator warmup periods:
- RSI: Needs 14+ bars (default period)
- EMA 50: Needs 50+ bars
- DXY correlation: Needs 50+ bars (default window)

**Solution:**
Provide more data (at least 60+ bars):

```python
# ✗ Too little data
gc_df = gc_df.head(20)  # Only 20 bars
features = aggregate_features(gc_df, dxy_df, "1m")
# Result: Mostly NaN

# ✓ Sufficient data
gc_df = gc_df.head(200)  # 200 bars
features = aggregate_features(gc_df, dxy_df, "1m")
# Result: Valid values after warmup period
```

---

### Issue: Different row count in output vs input

**Symptom:**
`len(features) != len(gc_df)`

**Cause:**
This should not happen with the current implementation. If it does, there may be duplicate timestamps in your data.

**Solution:**
Remove duplicate timestamps before aggregating:

```python
# Remove duplicates based on ts_event
gc_df = gc_df.drop_duplicates(subset=['ts_event'], keep='first')
dxy_df = dxy_df.drop_duplicates(subset=['ts_event'], keep='first')

features = aggregate_features(gc_df, dxy_df, "1m")
assert len(features) == len(gc_df)  # Should pass now
```

---

### Issue: DXY correlation all NaN

**Cause:**
No overlapping timestamps between GC and DXY data.

**Solution:**
Ensure GC and DXY data cover the same time period:

```python
# Check overlap
gc_start = gc_df['ts_event'].min()
gc_end = gc_df['ts_event'].max()
dxy_start = dxy_df['ts_event'].min()
dxy_end = dxy_df['ts_event'].max()

print(f"GC range: {gc_start} to {gc_end}")
print(f"DXY range: {dxy_start} to {dxy_end}")

# Ensure overlap exists
overlap_start = max(gc_start, dxy_start)
overlap_end = min(gc_end, dxy_end)

gc_df = gc_df[(gc_df['ts_event'] >= overlap_start) & (gc_df['ts_event'] <= overlap_end)]
dxy_df = dxy_df[(dxy_df['ts_event'] >= overlap_start) & (dxy_df['ts_event'] <= overlap_end)]
```

---

## Comparison: Aggregator vs. Individual Indicators

| Feature | Aggregator | Individual Indicators |
|---------|------------|----------------------|
| **API** | Single function call | Multiple function calls |
| **Configuration** | Unified dict | Multiple parameter sets |
| **Type Safety** | Guaranteed numeric | Per-indicator |
| **Timeframe Validation** | Enforced | Not enforced |
| **Performance** | Slightly slower (overhead) | Faster (direct calculation) |
| **Use Case** | Production, Rule Engine | Backtesting, research |
| **Code Complexity** | Low (one call) | Medium (multiple calls) |
| **Flexibility** | High (modular config) | Highest (direct control) |

### When to Use Each

**Use Aggregator:**
- Production trading system
- Rule Engine integration
- Multiple indicators needed
- Consistency required

**Use Individual Indicators:**
- Single indicator analysis
- Benchmarking/optimization
- Custom indicator combinations
- Maximum performance critical

---

## Related Documentation

- [VWAP Documentation](./vwap.md)
- [RSI Documentation](./rsi.md)
- [EMA Documentation](./ema.md)
- [DXY Correlation Documentation](./dxy-correlation.md)
- [Feature Engine Overview](./README.md)

---

[← Back to Feature Engine](./README.md)

