# Multi-Window DXY Correlation

## Overview

Multi-window DXY correlation provides enhanced correlation analysis between Gold (GC) and Dollar Index (DXY) by analyzing the relationship across three timeframes simultaneously:
- **15-minute window**: Captures short-term correlation (recent price relationship)
- **30-minute window**: Captures medium-term correlation
- **60-minute window**: Captures long-term correlation (macro trend)

This approach provides a more robust and smoother correlation signal compared to single-window analysis, reducing noise while maintaining sensitivity to regime changes.

## Why Multi-Window?

### Problems with Single-Window Correlation
1. **Noise sensitivity**: Short windows are noisy and produce false signals
2. **Lag**: Long windows lag behind regime changes
3. **Fixed perspective**: Single timeframe misses multi-scale dynamics

### Multi-Window Benefits
1. **Noise reduction**: Weighted average smooths out short-term noise
2. **Regime sensitivity**: Shorter windows detect changes quickly
3. **Stability**: Longer windows provide stable baseline
4. **Flexible weighting**: Prioritize timeframes based on trading style

## Function Signature

```python
from feature_engine import calculate_multiwindow_dxy_correlation

result = calculate_multiwindow_dxy_correlation(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    weights: dict[str, float] | None = None,
    gc_price_column: str = "close",
    dxy_price_column: str = "close",
    timestamp_column: str = "ts_event",
) -> pd.DataFrame
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `gc_df` | `pd.DataFrame` | Required | Gold (GC) price data with timestamps |
| `dxy_df` | `pd.DataFrame` | Required | Dollar Index (DXY) price data with timestamps |
| `weights` | `dict[str, float]` | `{'15min': 0.5, '30min': 0.3, '60min': 0.2}` | Weights for each window (must sum to 1.0) |
| `gc_price_column` | `str` | `"close"` | Column name for GC prices |
| `dxy_price_column` | `str` | `"close"` | Column name for DXY prices |
| `timestamp_column` | `str` | `"ts_event"` | Column name for timestamps |

## Returns

A `pd.DataFrame` with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `corr_15min` | `float` | 15-minute rolling correlation |
| `corr_30min` | `float` | 30-minute rolling correlation |
| `corr_60min` | `float` | 60-minute rolling correlation |
| `weighted_score` | `float` | Weighted average of all three windows |

Index is timestamps from aligned data. Values are `NaN` until sufficient data is available for each window.

## Default Weights

The default weights favor shorter timeframes, suitable for intraday trading:

```yaml
15min: 0.5  # 50% weight - most recent correlation
30min: 0.3  # 30% weight - medium-term trend
60min: 0.2  # 20% weight - longer-term baseline
```

This weighting prioritizes recent correlation changes while maintaining awareness of longer-term relationships.

## Usage Examples

### Basic Usage (Default Weights)

```python
import pandas as pd
from feature_engine import calculate_multiwindow_dxy_correlation

# Load data
gc_df = pd.read_csv("GC_ohlcv-1m.csv", parse_dates=["ts_event"])
dxy_df = pd.read_csv("DX_ohlcv-1m.csv", parse_dates=["ts_event"])

# Calculate multi-window correlation
result = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)

# Check weighted score
print(result["weighted_score"].tail())

# Identify strong inverse correlation
strong_inverse = result[result["weighted_score"] < -0.6]
print(f"Found {len(strong_inverse)} periods with strong inverse correlation")
```

### Custom Weights (Conservative Approach)

For a more stable signal, increase weight on longer timeframes:

```python
# Conservative weights: favor longer-term stability
custom_weights = {
    "15min": 0.2,  # Less weight on noisy short-term
    "30min": 0.3,
    "60min": 0.5,  # More weight on stable long-term
}

result = calculate_multiwindow_dxy_correlation(
    gc_df, 
    dxy_df, 
    weights=custom_weights
)
```

### Custom Weights (Aggressive Approach)

For faster reaction to regime changes:

```python
# Aggressive weights: favor recent correlation
aggressive_weights = {
    "15min": 0.7,  # High weight on recent changes
    "30min": 0.2,
    "60min": 0.1,
}

result = calculate_multiwindow_dxy_correlation(
    gc_df, 
    dxy_df, 
    weights=aggressive_weights
)
```

### Integration with Rule Engine

```python
from feature_engine import calculate_multiwindow_dxy_correlation
from rule_engine import score_setup

# Calculate correlation
dxy_corr = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)

# Use weighted score for setup scoring
current_corr = dxy_corr["weighted_score"].iloc[-1]

# Check if inverse correlation is strong enough
if current_corr < -0.6:
    print("✓ Strong inverse correlation - DXY alignment confirmed")
    dxy_score = 2  # Award full points
else:
    print("✗ Weak correlation - DXY alignment not confirmed")
    dxy_score = 0
```

### Analyzing Correlation Breakdown

Compare individual windows to understand correlation dynamics:

```python
result = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)

# Get latest values
latest = result.iloc[-1]

print(f"15min correlation: {latest['corr_15min']:.3f}")
print(f"30min correlation: {latest['corr_30min']:.3f}")
print(f"60min correlation: {latest['corr_60min']:.3f}")
print(f"Weighted score:    {latest['weighted_score']:.3f}")

# Detect regime change
if latest['corr_15min'] > -0.3 and latest['corr_60min'] < -0.7:
    print("⚠️ Regime change detected: short-term correlation weakening")
```

## Interpretation Guide

### Weighted Score Ranges

| Score Range | Interpretation | Trading Implication |
|-------------|----------------|---------------------|
| < -0.8 | Very strong inverse correlation | High confidence in GC-DXY inverse relationship |
| -0.8 to -0.6 | Strong inverse correlation | Normal inverse relationship (✓ tradeable) |
| -0.6 to -0.3 | Moderate inverse correlation | Weakening relationship (⚠️ caution) |
| -0.3 to +0.3 | No correlation | Decoupled / ranging (✗ avoid DXY-based setups) |
| > +0.3 | Positive correlation | Abnormal relationship (✗✗ high risk) |

### Window Divergence Signals

#### Strong Agreement (All Windows Negative)
```
15min: -0.75
30min: -0.72
60min: -0.68
Weighted: -0.73
```
**Interpretation**: Stable inverse correlation across all timeframes → High confidence

#### Short-Term Breakdown
```
15min: -0.25  ⚠️ Weak
30min: -0.65
60min: -0.70
Weighted: -0.46
```
**Interpretation**: Recent correlation weakening → Possible regime change or temporary noise

#### Long-Term Shift
```
15min: -0.70
30min: -0.55
60min: -0.30  ⚠️ Weak
Weighted: -0.60
```
**Interpretation**: Longer-term correlation changing → Macro regime shift underway

## Technical Details

### Window Calculation

Each window uses Pearson correlation over the specified number of 1-minute periods:
- **15min window**: 15 periods (15 1-minute bars)
- **30min window**: 30 periods (30 1-minute bars)
- **60min window**: 60 periods (60 1-minute bars)

### Weighted Score Formula

```python
weighted_score = (
    corr_15min * weight_15min +
    corr_30min * weight_30min +
    corr_60min * weight_60min
)
```

With default weights:
```python
weighted_score = (
    corr_15min * 0.5 +
    corr_30min * 0.3 +
    corr_60min * 0.2
)
```

### Data Requirements

- **Minimum data**: 60 periods (1 hour) for all windows to be valid
- **Partial results**: 15min and 30min available before 60min
- **Alignment**: Timestamps must match between GC and DXY (inner join)

### NaN Handling

- First 14 periods: `corr_15min` is `NaN`
- First 29 periods: `corr_30min` is `NaN`
- First 59 periods: `corr_60min` is `NaN`
- First 59 periods: `weighted_score` is `NaN` (requires all windows)

## Performance Considerations

### Computational Cost
- **Low**: Reuses existing single-window correlation function
- **Vectorized**: Efficient pandas operations
- **Scalable**: O(n) complexity per window

### Memory Usage
- Returns 4 columns (3 correlations + weighted score)
- Similar memory footprint to single-window correlation

### Optimization Tips
```python
# For backtesting, calculate once and reuse
dxy_corr = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)

# Then access specific timeframes as needed
latest_weighted = dxy_corr["weighted_score"].iloc[-1]

# Or get time series for plotting
correlation_history = dxy_corr["weighted_score"].dropna()
```

## Configuration

Multi-window weights are configured in `config/scoring_config.yaml`:

```yaml
validation:
  dxy_multiwindow_weights:
    15min: 0.5   # Short-term correlation
    30min: 0.3   # Medium-term correlation
    60min: 0.2   # Long-term correlation
```

Load configuration in your code:

```python
import yaml
from pathlib import Path

config_path = Path("config/scoring_config.yaml")
with open(config_path) as f:
    config = yaml.safe_load(f)

weights = config["validation"]["dxy_multiwindow_weights"]
result = calculate_multiwindow_dxy_correlation(gc_df, dxy_df, weights=weights)
```

## Testing

Comprehensive tests are available in `tests/unit/test_dxy_correlation_multiwindow.py`:

```bash
# Run multi-window correlation tests
uv run pytest tests/unit/test_dxy_correlation_multiwindow.py -v

# Run with coverage
uv run pytest tests/unit/test_dxy_correlation_multiwindow.py --cov=feature_engine.dxy_correlation
```

## Related Documentation

- [DXY Correlation Feature](dxy-correlation.md) - Single-window correlation
- [Feature Engine Integration](integration.md) - Feature pipeline integration
- [Rule Engine DXY Module](../rule-engine/dxy-module.md) - DXY scoring logic

## Changelog

### v1.0.0 (2025-11-24)
- Initial implementation of multi-window DXY correlation
- Default weights: 15min (0.5), 30min (0.3), 60min (0.2)
- Comprehensive test suite (20 tests)
- Configuration support in scoring_config.yaml
- DoD: ✓ Implement rolling 15/30/60 min inverse correlation
- DoD: ✓ Weighted scoring implemented

---

**Related Story**: Add DXY Chop Detection, Correlation & Inversion Logic  
**Task**: Enhance DXY correlation windowing  
**Status**: ✅ Complete

