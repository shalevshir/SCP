# Vectorized Backtesting Processor

[← Back to Feature Engine](./README.md)

**Purpose:** Provide fast, vectorized feature calculation for backtesting while preventing look-ahead bias through strict time slicing.

---

## Overview

The `BacktestProcessor` class provides a vectorized feature calculation mode optimized for backtesting large datasets. It computes all indicators once using pandas vectorization for speed, then carefully yields features one timestamp at a time to ensure no look-ahead bias.

### Key Features

- **Fast**: Uses vectorized pandas operations (10x+ faster than incremental mode on large datasets)
- **Safe**: Guarantees no look-ahead bias through strict time slicing and future data masking
- **Compatible**: Produces outputs matching incremental FeatureState within tolerance
- **Configurable**: Supports session resets, custom warmup periods, and all indicator configurations

### Use Cases

- **Backtesting**: Primary use case - process historical data quickly for strategy validation
- **Batch Analysis**: Analyze large datasets of historical trades
- **Performance Testing**: Compare strategy performance across different time periods

---

## Architecture

### Comparison with Other Modes

| Mode | Speed | Look-Ahead Safety | Use Case |
|------|-------|-------------------|----------|
| Incremental (FeatureState) | Slow (Python loops) | Guaranteed by design | Live trading, realistic backtesting |
| Vectorized (process_features) | Fast | Requires discipline | Batch analysis with careful time slicing |
| **Backtesting (BacktestProcessor)** | **Fast** | **Guaranteed** | **Backtesting at scale** |

### How It Prevents Look-Ahead

The processor uses two key strategies to prevent look-ahead bias:

1. **Vectorized Computation**: Most indicators (VWAP, RSI, EMA, DXY correlation) use rolling windows or exponential smoothing that naturally avoid look-ahead when computed vectorized. These are computed once for the entire dataset.

2. **Delayed Structure Labels**: Structure labels are delayed by `swing_window` bars in `calculate_structure_labels()`, ensuring labels only use past data. When a swing point is detected at position `i`, its label appears at position `i + swing_window`. The last `swing_window` bars naturally have `None` labels since there isn't enough future data to confirm swings. This matches the incremental StructureState behavior and guarantees zero lookahead bias.

---

## API Reference

### BacktestProcessor

```python
class BacktestProcessor:
    def __init__(
        self,
        timeframe: str,
        session_reset: bool = True,
        rsi_period: int = 14,
        ema_periods: list[int] | None = None,
        dxy_window: int = 50,
        swing_window: int = 5,
        warmup_period: int | None = None,
    ):
        """Initialize BacktestProcessor with configuration."""
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeframe` | `str` | required | Timeframe string (e.g., "1m", "15m", "1h") |
| `session_reset` | `bool` | `True` | Whether to reset VWAP at session boundaries (day changes) |
| `rsi_period` | `int` | `14` | RSI calculation period |
| `ema_periods` | `list[int]` | `[9, 20, 50]` | List of EMA periods to calculate |
| `dxy_window` | `int` | `50` | DXY correlation rolling window size |
| `swing_window` | `int` | `5` | Structure label swing detection window |
| `warmup_period` | `int` | auto | Number of periods to skip before yielding features. If None, uses `max(dxy_window, swing_window * 2 + 1, rsi_period)` |

---

### iterate_with_context()

```python
def iterate_with_context(
    self,
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
) -> Iterator[tuple[pd.Series, dict]]:
    """Yield features and validation context without look-ahead bias."""
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `gc_df` | `pd.DataFrame` | GC DataFrame with DatetimeIndex and OHLCV columns |
| `dxy_df` | `pd.DataFrame` | DXY DataFrame with DatetimeIndex and OHLCV columns |

#### Returns

Iterator that yields **tuples of `(features, validation_context)`** for each timestamp after warmup period.

**Tuple Contents**:
1. **features (pd.Series)**: Feature series with all indicators
2. **validation_context (dict)**: Validation context with:
   - `dxy_corr`: DXY correlation for this timestamp
   - `session_constraints`: SessionConstraints (if session validator configured)
   - Additional validation-related context

**Features Series Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `datetime` | Current candle timestamp |
| `symbol` | `str` | "GC" |
| `timeframe` | `str` | Configured timeframe |
| `open` | `float` | Open price |
| `high` | `float` | High price |
| `low` | `float` | Low price |
| `close` | `float` | Close price |
| `volume` | `float` | Volume |
| `vwap` | `float` | Volume-Weighted Average Price |
| `rsi` | `float \| None` | Relative Strength Index (0-100) |
| `ema_9` | `float` | 9-period EMA |
| `ema_20` | `float` | 20-period EMA |
| `ema_50` | `float` | 50-period EMA |
| `dxy_corr` | `float \| None` | GC-DXY correlation (-1 to 1) |
| `structure_label` | `str \| None` | "HH", "HL", "LH", "LL", or None |
| `vwap_deviation` | `float \| None` | Percentage deviation from VWAP |

---

## Usage Examples

### Basic Usage

```python
from datetime import datetime, timezone
from feature_engine import BacktestProcessor
from data_layer import HistoricalDataLoader

# Load data
loader = HistoricalDataLoader("data/gc_dx_ohlcv")
start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
end = datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc)
data = loader.load(["GC", "DXY"], "1m", start, end)

# Create processor
processor = BacktestProcessor(timeframe="1m")

# Iterate through features (note: returns tuples!)
for features, validation_context in processor.iterate_with_context(data["GC"], data["DXY"]):
    # Process each timestamp
    print(f"Timestamp: {features['timestamp']}")
    print(f"VWAP: {features['vwap']:.2f}")
    print(f"RSI: {features['rsi']:.1f}")
    print(f"DXY Correlation: {validation_context.get('dxy_corr')}")
    
    # Make trading decision
    if features['rsi'] < 30 and features['close'] < features['vwap']:
        print("  → Potential LONG setup")
```

### Integration with Rule Engine

```python
from feature_engine import BacktestProcessor
from rule_engine import score_signal

# Setup
processor = BacktestProcessor(timeframe="1m")

# Backtest loop
signals = []
for features, validation_context in processor.iterate_with_context(gc_df, dxy_df):
    # Build scoring context
    scoring_context = {
        "session_ok": True,
        "htf_bias": "bullish",
        "htf_direction": "long",
        "enforcer_tier": "Conservative",
    }
    
    # Score the signal
    signal = score_signal(features, scoring_context)
    
    if signal.score >= 8.0:
        signals.append(signal)
        print(f"Signal: {signal.setup_type} @ {features['timestamp']}, Score: {signal.score}")

print(f"\nTotal signals: {len(signals)}")
```

### Custom Configuration

```python
# Configure for faster warmup and custom indicators
processor = BacktestProcessor(
    timeframe="15m",
    session_reset=True,
    rsi_period=21,
    ema_periods=[12, 26, 50],
    dxy_window=30,
    swing_window=3,
    warmup_period=30,  # Custom warmup
)

for features, validation_context in processor.iterate_with_context(gc_df, dxy_df):
    # Process features
    pass
```

### Collecting Features for Analysis

```python
# Collect all features into a DataFrame (unpack tuples)
processor = BacktestProcessor(timeframe="1m")

# Extract just features from tuples
features_list = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]

# Convert to DataFrame
features_df = pd.DataFrame(features_list)
features_df.set_index("timestamp", inplace=True)

# Analyze
print(f"Average VWAP: {features_df['vwap'].mean():.2f}")
print(f"RSI > 70 count: {(features_df['rsi'] > 70).sum()}")
print(f"Bullish structure: {(features_df['structure_label'].isin(['HH', 'HL'])).sum()}")
```

---

## Performance Characteristics

### Speed Comparison

On a dataset of 10,000 candles:

| Mode | Time | Speedup |
|------|------|---------|
| Incremental (FeatureState) | ~5.0s | 1x |
| Vectorized (BacktestProcessor) | ~0.5s | 10x |

Performance improves with dataset size. On 100 candles, both modes take similar time due to setup overhead.

### Memory Usage

- **Incremental**: O(window_size) - only maintains rolling buffers
- **Vectorized**: O(n) - stores all features in memory

For datasets larger than 100K rows, consider processing in batches.

---

## Validation & Testing

### Parity with Incremental Mode

The BacktestProcessor is validated against FeatureState to ensure outputs match within tolerance:

| Indicator | Tolerance | Notes |
|-----------|-----------|-------|
| VWAP | Exact match | Cumulative calculation |
| RSI | ±0.5 | Wilder's smoothing |
| EMA | ±0.01 | Exponential smoothing |
| DXY Correlation | ±0.05 | Pearson correlation |
| VWAP Deviation | ±0.01 | Percentage calculation |

See `tests/unit/test_feature_parity.py` for comprehensive parity tests.

### No Look-Ahead Verification

Tests verify that:
1. Features don't change when future data is modified
2. **Structure labels are delayed** by `swing_window` bars, ensuring no future data is used (see `test_structure_labels_delayed_to_prevent_lookahead_bias`)
3. All indicators use only historical data in their calculations
4. Vectorized structure labels match incremental StructureState within tolerance

---

## Edge Cases

### Zero Volume

VWAP handles zero volume by using epsilon (smallest float value) to prevent division by zero.

### Session Boundaries

When `session_reset=True`, VWAP automatically detects day changes and resets cumulative values.

### Missing Data

The processor requires aligned timestamps between GC and DXY. Missing data will be handled by the data loader.

### Structure Labels Near End

The last `swing_window` bars naturally have `None` for `structure_label` and `structure_type` because there isn't enough future data to confirm swings that would be delayed beyond the end of the dataset. This is a natural consequence of the delayed labeling approach and ensures zero lookahead bias. The delayed labeling matches the incremental StructureState behavior, where labels appear `swing_window` bars after swing detection.

---

## Limitations

1. **Memory**: Stores all features in memory. For very large datasets (>1M rows), process in batches.
2. **Structure Labels**: The last `swing_window` bars have `None` labels due to delayed labeling (not enough future data to confirm swings). This matches incremental mode behavior and ensures zero lookahead bias.
3. **Single Iteration**: Each call to `iterate_with_context()` recomputes features. Cache results if iterating multiple times.

---

## Best Practices

1. **Use for Backtesting**: This is the recommended mode for backtesting at scale.
2. **Cache Results**: If you need to iterate over the same data multiple times, collect features into a DataFrame first.
3. **Validate Outputs**: Compare against incremental mode on a sample dataset to ensure correctness.
4. **Monitor Memory**: For very large datasets, process in chunks or use streaming.

---

## Related Documentation

- [Feature Engine Overview](./README.md)
- [Incremental FeatureState](./state.md)
- [Integration Layer](./integration.md)
- [VWAP](./vwap.md)
- [RSI](./rsi.md)
- [EMA](./ema.md)
- [DXY Correlation](./dxy-correlation.md)
- [Structure Labels](./structure.md)

