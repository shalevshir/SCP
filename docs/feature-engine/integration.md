# Feature Engine Integration Layer

[← Back to Feature Engine](./README.md)

**Purpose:** Complete integration layer that processes aligned GC and DXY datasets through the full FeatureEngine pipeline, computes all required features, applies validation rules, and produces feature DataFrames ready for Rule Engine scoring.

---

## Table of Contents

- [Overview](#overview)
- [API Reference](#api-reference)
- [Structure Labels](#structure-labels)
- [VWAP Deviation](#vwap-deviation)
- [Format Conversion](#format-conversion)
- [Data Alignment](#data-alignment)
- [Validation Integration](#validation-integration)
- [Usage Examples](#usage-examples)
- [Data Quality Guarantees](#data-quality-guarantees)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Integration Layer provides a complete end-to-end solution for processing market data from the HistoricalDataLoader through the FeatureEngine to produce ready-to-score feature DataFrames. It handles:

1. **Format Conversion**: Converts between timestamp index (loader output) and ts_event column (aggregator input)
2. **Data Alignment**: Aligns GC and DXY DataFrames by timestamp for correlation calculation
3. **Feature Computation**: Runs all indicators (RSI, VWAP, EMA, DXY correlation)
4. **Structure Analysis**: Adds structure labels (HH/HL/LH/LL) for swing point detection
5. **Fade Detection**: Calculates VWAP deviation for counter-trend setup identification
6. **Validation**: Applies session and trade validation rules
7. **Data Quality**: Ensures no NaNs past initialization window

### When to Use

✅ **Use the integration layer when:**
- Processing data from HistoricalDataLoader
- Need complete feature set for Rule Engine scoring
- Want automatic format conversion and alignment
- Need validation rules applied before scoring

❌ **Use individual functions when:**
- Working with pre-formatted DataFrames
- Only need specific indicators
- Custom processing pipeline required

---

## API Reference

### `process_features()`

Main integration function that processes aligned datasets through the full pipeline.

```python
def process_features(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    context: dict | None = None,
    validation_engine: ValidationEngine | None = None,
    session_validator: SessionValidator | None = None,
) -> pd.DataFrame
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `gc_df` | `pd.DataFrame` | GC DataFrame from HistoricalDataLoader (timestamp index, OHLCV columns) |
| `dxy_df` | `pd.DataFrame` | DXY DataFrame from HistoricalDataLoader (timestamp index, OHLCV columns) |
| `timeframe` | `str` | Timeframe string (e.g., "1m", "15m", "1h"). Must be in ALLOWED_TIMEFRAMES |
| `context` | `dict \| None` | Optional validation context dict with keys: session_ok, tier_active, htf_bias, etc. |
| `validation_engine` | `ValidationEngine \| None` | Optional ValidationEngine instance for trade validation |
| `session_validator` | `SessionValidator \| None` | Optional SessionValidator instance for session validation |

#### Returns

Complete feature DataFrame with:
- All original GC columns (open, high, low, close, volume, symbol)
- Indicator columns: vwap, rsi, ema_9, ema_20, ema_50, dxy_corr
- Structure column: structure_label (HH/HL/LH/LL)
- Deviation column: vwap_deviation (percentage)
- Validation column: validation_status (if validators provided)
- Timestamp column: ts_event

#### Raises

- `TypeError`: If inputs are not DataFrames
- `ValueError`: If required columns are missing or alignment fails

---

### `prepare_for_aggregation()`

Converts DataFrame from timestamp index format to ts_event column format.

```python
def prepare_for_aggregation(df: pd.DataFrame) -> pd.DataFrame
```

**Example:**
```python
# Input: DataFrame with timestamp index
df_indexed = pd.DataFrame(
    {"open": [100.0], "close": [101.0]},
    index=pd.DatetimeIndex(["2025-01-01 09:00"], tz=UTC)
)

# Output: DataFrame with ts_event column
df_converted = prepare_for_aggregation(df_indexed)
# Result has ts_event column and RangeIndex
```

---

### `align_dataframes()`

Aligns GC and DXY DataFrames by timestamp for correlation calculation.

```python
def align_dataframes(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]
```

**Example:**
```python
gc_aligned, dxy_aligned = align_dataframes(gc_df, dxy_df)
# Both DataFrames now have matching timestamps and ts_event columns
```

---

## Structure Labels

Structure labels identify swing points in price action and classify them based on their relationship to previous swing points.

### Labels

- **HH (Higher High)**: Swing high above previous swing high (bullish structure)
- **HL (Higher Low)**: Swing low above previous swing low (bullish structure)
- **LH (Lower High)**: Swing high below previous swing high (bearish structure)
- **LL (Lower Low)**: Swing low below previous swing low (bearish structure)

### Algorithm

1. Identifies swing highs using rolling window (local maxima)
2. Identifies swing lows using rolling window (local minima)
3. Compares each swing point to previous swing point of same type
4. Labels based on relative position (higher/lower)

### Usage

```python
from feature_engine import calculate_structure_labels

df['structure_label'] = calculate_structure_labels(df, swing_window=5)
```

### Parameters

- `swing_window` (int, default=5): Number of periods to look back/forward to identify swing points
- `high_column` (str, default="high"): Name of high price column
- `low_column` (str, default="low"): Name of low price column

---

## VWAP Deviation

VWAP deviation measures how far price has moved from fair value (VWAP), which is useful for identifying fade opportunities.

### Formula

```
vwap_deviation = abs((close - vwap) / vwap * 100)
```

### Usage

```python
from feature_engine import calculate_vwap_deviation

df['vwap_deviation'] = calculate_vwap_deviation(df)
```

### Interpretation

- **Low deviation (< 0.5%)**: Price near VWAP, continuation setups more likely
- **High deviation (> 1.0%)**: Price far from VWAP, fade setups more likely
- **Extreme deviation (> 2.0%)**: Strong fade opportunity (counter-trend)

---

## Format Conversion

The integration layer handles conversion between two DataFrame formats:

1. **Loader Format**: Timestamp index, OHLCV columns (HistoricalDataLoader output)
2. **Aggregator Format**: RangeIndex, ts_event column, OHLCV columns (aggregate_features input)

### Conversion Flow

```
Loader Output (timestamp index)
    ↓ prepare_for_aggregation()
Aggregator Input (ts_event column)
    ↓ aggregate_features()
Feature Output (ts_event column)
```

---

## Data Alignment

GC and DXY DataFrames must be aligned by timestamp for correlation calculation. The integration layer:

1. Converts both DataFrames to common format (ts_event column)
2. Finds overlapping timestamps
3. Filters to common timestamps only
4. Sorts by timestamp for consistent ordering

### Alignment Requirements

- Both DataFrames must have either timestamp index or ts_event column
- At least one overlapping timestamp required
- Timestamps must be timezone-aware (UTC)

---

## Validation Integration

The integration layer can apply validation rules before returning features:

### Session Validation

Validates that timestamps are within permitted trading hours:

```python
from validation.session_validator import SessionValidator, SessionConfig

session_validator = SessionValidator(config)
features = process_features(
    gc_df, dxy_df, "1m",
    session_validator=session_validator
)
# Adds validation_status column: "session_ok" or "session_blocked"
```

### Trade Validation

Full trade validation requires trade direction (determined during scoring), so the integration layer marks rows as ready for validation:

```python
from validation.engine import ValidationEngine

validation_engine = ValidationEngine()
features = process_features(
    gc_df, dxy_df, "1m",
    validation_engine=validation_engine
)
# Adds validation_ready column: True
```

---

## Usage Examples

### Basic Usage

```python
from data_layer import HistoricalDataLoader
from feature_engine import process_features
from datetime import datetime, timezone

# Load data
loader = HistoricalDataLoader("data/gc_dx_ohlcv")
start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=timezone.utc)
end = datetime(2025, 9, 30, 5, 0, 0, tzinfo=timezone.utc)
data = loader.load(["GC", "DXY"], "1m", start, end)

# Process features
features = process_features(
    data["GC"],
    data["DXY"],
    "1m"
)

# Features now contain all indicators, structure labels, and VWAP deviation
print(features.columns)
# Index(['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol',
#        'vwap', 'rsi', 'ema_9', 'ema_20', 'ema_50', 'dxy_corr',
#        'structure_label', 'vwap_deviation'])
```

### With Validation

```python
from validation.session_validator import SessionValidator, SessionConfig, SeasonRule
from datetime import time

# Create session validator
default_rule = SeasonRule(
    name="Default",
    months=frozenset(range(1, 13)),
    window_start=time(10, 0),
    window_end=time(13, 0),
    allowed_tiers=frozenset({"Conservative", "EarlyMild", "Mild", "Offensive"}),
    allowed_setups=frozenset({"continuation"}),
    min_score=8.0,
    max_losses=2,
    dxy_correlation_max=-0.6,
)

config = SessionConfig(
    timezone="Asia/Jerusalem",
    default_rule=default_rule,
)

session_validator = SessionValidator(config)

# Process with validation
features = process_features(
    data["GC"],
    data["DXY"],
    "1m",
    session_validator=session_validator
)

# Filter to valid sessions only
valid_features = features[features["validation_status"] == "session_ok"]
```

### Identifying Fade Setups

```python
# Find fade opportunities (high VWAP deviation + extreme RSI)
fade_setups = features[
    (features["vwap_deviation"] > 1.0) &  # Significant deviation
    ((features["rsi"] < 30) | (features["rsi"] > 70))  # Extreme RSI
]

print(f"Found {len(fade_setups)} fade setup opportunities")
```

### Structure Analysis

```python
# Identify bullish structure (HH/HL pattern)
bullish_structure = features[
    features["structure_label"].isin(["HH", "HL"])
]

# Identify bearish structure (LH/LL pattern)
bearish_structure = features[
    features["structure_label"].isin(["LH", "LL"])
]
```

---

## Data Quality Guarantees

The integration layer ensures:

1. **No NaNs Past Initialization**: After the initialization window (50 periods), all feature columns are populated
2. **Proper Alignment**: GC and DXY timestamps match exactly
3. **Consistent Types**: All numeric columns are float64, structure_label is object
4. **Sorted Timestamps**: Data is sorted chronologically
5. **Complete Feature Set**: All required features are computed

### Initialization Windows

- **RSI**: 14 periods (first 14 values are NaN)
- **EMA**: 50 periods (first 50 values are NaN for ema_50)
- **DXY Correlation**: 50 periods (first 50 values are NaN)
- **Structure Labels**: 2 * swing_window + 1 periods (first values may be NaN)

---

## Troubleshooting

### Issue: "No overlapping timestamps found"

**Cause**: GC and DXY DataFrames have no common timestamps.

**Solution**: Ensure both DataFrames cover the same time period and have matching timezone.

```python
# Check timestamps
print(f"GC range: {gc_df.index.min()} to {gc_df.index.max()}")
print(f"DXY range: {dxy_df.index.min()} to {dxy_df.index.max()}")
```

### Issue: "Missing required columns"

**Cause**: GC DataFrame missing OHLCV columns.

**Solution**: Verify DataFrame structure from HistoricalDataLoader.

```python
# Check columns
required = ["open", "high", "low", "close", "volume"]
missing = [col for col in required if col not in gc_df.columns]
print(f"Missing columns: {missing}")
```

### Issue: NaNs past initialization window

**Cause**: Insufficient data or calculation error.

**Solution**: Check data length and indicator calculations.

```python
# Check for NaNs
max_init = 50
if len(features) > max_init:
    for col in ["vwap", "rsi", "ema_9", "ema_20", "ema_50"]:
        nan_count = features[col].iloc[max_init:].isna().sum()
        if nan_count > 0:
            print(f"Warning: {nan_count} NaNs in {col} past initialization")
```

### Issue: Structure labels all NaN

**Cause**: Insufficient data for swing detection.

**Solution**: Ensure at least `2 * swing_window + 1` rows of data.

```python
# Check data length
min_rows = 2 * swing_window + 1
if len(df) < min_rows:
    print(f"Need at least {min_rows} rows, got {len(df)}")
```

---

## Related Documentation

- [Feature Engine Overview](./README.md)
- [VWAP Documentation](./vwap.md)
- [RSI Documentation](./rsi.md)
- [EMA Documentation](./ema.md)
- [DXY Correlation Documentation](./dxy-correlation.md)
- [Aggregator Documentation](./aggregator.md)
- [Data Layer Guide](../10-data-layer.md)
- [Validation Layer Guide](../11-validation-layer.md)

