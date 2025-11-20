

# Incremental FeatureState Engine

The FeatureState engine provides stateful, incremental feature calculation for real-time trading and realistic backtesting without look-ahead bias.

## Overview

The incremental engine processes candles one at a time, maintaining all indicator state (VWAP, RSI, EMA, DXY correlation, structure labels) without referencing future data. This ensures:

- **No look-ahead bias**: Only uses data available up to the current timestamp
- **Live trading compatibility**: Matches exactly how features would be calculated in production
- **Realistic backtesting**: Simulates live data flow accurately
- **Asynchronous instrument support**: Handles GC and DXY candles arriving independently

## Architecture

### State Classes

Each indicator has its own state class that maintains calculation state:

#### VWAPState
- Tracks cumulative price × volume and cumulative volume
- Detects session boundaries (day changes) and resets automatically
- Handles zero volume gracefully

#### RSIState
- Implements Wilder's smoothing method (industry standard)
- Maintains rolling average gain and average loss
- Requires 14-period warmup

#### EMAState
- Calculates multiple EMAs simultaneously (9, 20, 50 periods)
- Uses first price as seed value (no warmup needed)
- Formula: EMA = price × α + EMA_prev × (1 - α), where α = 2/(period+1)

#### DXYCorrelationState
- Maintains rolling buffers of GC and DXY prices (50-period window)
- Calculates Pearson correlation coefficient
- Requires 50-period warmup

#### StructureState
- Identifies swing highs and lows without look-ahead
- Labels as HH (Higher High), HL (Higher Low), LH (Lower High), LL (Lower Low)
- Uses only past data from buffer (swing_window * 2 + 1 periods)

### Main FeatureState Class

The `FeatureState` class coordinates all indicator states and handles:

- GC + DXY synchronization
- Warmup period tracking
- Out-of-order candle detection
- Missing candle handling
- Feature aggregation

## Usage

### Basic Usage

```python
from datetime import datetime, timezone
from common.types import Candle
from feature_engine import FeatureState

# Initialize state
state = FeatureState(
    timeframe="1m",
    session_reset=True,  # Reset VWAP at session boundaries
    rsi_period=14,
    ema_periods=[9, 20, 50],
    dxy_window=50,
    swing_window=5,
)

# Process candles one at a time
for gc_candle, dxy_candle in candle_stream:
    features = state.update(gc_candle=gc_candle, dxy_candle=dxy_candle)
    
    if features is not None and state.is_ready():
        # Features are ready (past warmup period)
        print(f"VWAP: {features['vwap']:.2f}")
        print(f"RSI: {features['rsi']:.1f}")
        print(f"DXY Corr: {features['dxy_corr']:.3f}")
```

### Handling Missing Candles

```python
# GC-only update (DXY lagging)
features = state.update(gc_candle=gc_candle)

# DXY-only update (GC lagging)
features = state.update(dxy_candle=dxy_candle)

# Synchronized update (both arrive together)
features = state.update(gc_candle=gc_candle, dxy_candle=dxy_candle)
```

### Warmup Period Management

```python
state = FeatureState(timeframe="1m")

print(f"Warmup remaining: {state.warmup_remaining()}")  # 50 (max of all indicators)

# Process candles
for i, candle in enumerate(candles):
    features = state.update(gc_candle=candle)
    
    if state.is_ready():
        print(f"Ready after {i+1} candles")
        break
```

### Session Boundary Handling

```python
# VWAP resets at session boundaries (day changes)
state = FeatureState(timeframe="1m", session_reset=True)

# Day 1
day1_candle = Candle(
    timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
    ...
)
features1 = state.update(gc_candle=day1_candle)

# Day 2 - VWAP automatically resets
day2_candle = Candle(
    timestamp=datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc),
    ...
)
features2 = state.update(gc_candle=day2_candle)
```

## Warmup Periods

Different indicators have different warmup requirements:

| Indicator | Warmup Period | Reason |
|-----------|--------------|--------|
| VWAP | 0 | Cumulative from first candle |
| EMA | 0 | Uses first price as seed |
| RSI | 14 | Needs 14 periods for initial average |
| DXY Correlation | 50 | Needs full rolling window |
| Structure Labels | 11 | Needs swing_window * 2 + 1 periods |

**Maximum warmup**: 50 periods (DXY correlation)

After warmup, `is_ready()` returns `True` and all indicators produce valid values.

## Output Format

The `update()` method returns a pandas Series with the following columns:

```python
{
    "timestamp": datetime,      # Current candle timestamp
    "symbol": str,              # "GC"
    "timeframe": str,           # e.g., "1m"
    "open": float,              # OHLCV data
    "high": float,
    "low": float,
    "close": float,
    "volume": float,
    "vwap": float,              # Volume-Weighted Average Price
    "rsi": float | None,        # Relative Strength Index (0-100)
    "ema_9": float,             # 9-period EMA
    "ema_20": float,            # 20-period EMA
    "ema_50": float,            # 50-period EMA
    "dxy_corr": float | None,   # GC-DXY correlation (-1 to 1)
    "structure_label": str | None,  # "HH", "HL", "LH", "LL", or None
    "vwap_deviation": float | None, # Percentage deviation from VWAP
}
```

Values may be `None` during warmup period or when insufficient data is available.

## Comparison with Vectorized Mode

### Vectorized (Batch) Mode

```python
from feature_engine import process_features

# Load all data at once
gc_df = loader.load(["GC"], "1m", start, end)["GC"]
dxy_df = loader.load(["DXY"], "1m", start, end)["DXY"]

# Calculate all features at once (fast)
features_df = process_features(gc_df, dxy_df, "1m")

# Iterate through time for backtesting
for i in range(len(features_df)):
    current_features = features_df.iloc[i]
    # Make trading decision (only use data up to i)
```

**Pros**: Fast (vectorized operations), simple
**Cons**: Requires discipline to avoid look-ahead, memory intensive

### Incremental (Stateful) Mode

```python
from feature_engine import FeatureState

state = FeatureState(timeframe="1m")

# Process one candle at a time
for candle in candle_stream:
    features = state.update(gc_candle=candle)
    # Make trading decision (no look-ahead possible)
```

**Pros**: No look-ahead possible, matches live trading exactly, memory efficient
**Cons**: Slower (Python loops), more complex state management

### Recommendation

- **Backtesting**: Use vectorized mode with strict time slicing for speed
- **Live Trading**: Use incremental mode (required)
- **Validation**: Compare both to ensure correctness

## Validation

The incremental engine has been validated against the vectorized implementation:

- **VWAP**: Exact match (cumulative calculation)
- **RSI**: Within ±0.1 (Wilder's smoothing)
- **EMA**: Within ±0.0001 (floating point precision)
- **DXY Correlation**: Within ±0.01 (Pearson correlation)
- **VWAP Deviation**: Within ±0.01 (percentage calculation)

See `tests/unit/test_feature_parity.py` for comprehensive parity tests.

## Edge Cases

### Zero Volume

VWAP handles zero volume by using epsilon (smallest float value) to prevent division by zero.

### All Gains / All Losses

RSI handles edge cases:
- All gains → RSI = 100
- All losses → RSI = 0
- No movement → RSI = 50

### Missing Timestamps

The engine handles timestamp gaps gracefully. Missing candles don't break the calculation.

### Out-of-Order Candles

Out-of-order candles are logged as warnings but processed. The state uses the latest candle provided.

### Session Boundaries

VWAP automatically detects day changes and resets cumulative values when `session_reset=True`.

## Performance

Incremental calculation is slower than vectorized due to Python loops, but performance is acceptable for live trading:

- **Throughput**: ~1000 candles/second on modern hardware
- **Latency**: <1ms per candle update
- **Memory**: O(window_size) for rolling buffers

For backtesting large datasets, use vectorized mode for speed.

## Implementation Notes

### No Look-Ahead Guarantee

The structure label calculation has been specifically designed to avoid look-ahead:

```python
# WRONG (look-ahead bias):
window = data[i - swing_window : i + swing_window + 1]  # Includes future data!

# CORRECT (no look-ahead):
# Only identify swing point at buffer center when we have enough past data
center_idx = swing_window
is_swing = all(center_value >= buffer[j] for j in range(len(buffer)) if j != center_idx)
```

### Wilder's Smoothing

RSI uses Wilder's smoothing (not simple EMA):

```python
# First period: Simple moving average
avg_gain = sum(gains[:period]) / period

# Subsequent periods: Wilder's formula
avg_gain = (avg_gain * (period - 1) + current_gain) / period
```

This matches industry-standard RSI implementations (TA-Lib, TradingView).

### EMA Alpha

EMA uses alpha = 2/(period+1), matching pandas `.ewm(span=period, adjust=False)`:

```python
alpha = 2.0 / (period + 1)
ema = price * alpha + ema_prev * (1 - alpha)
```

## API Reference

### FeatureState

```python
class FeatureState:
    def __init__(
        self,
        timeframe: str,
        session_reset: bool = True,
        rsi_period: int = 14,
        ema_periods: list[int] | None = None,
        dxy_window: int = 50,
        swing_window: int = 5,
    ):
        """Initialize FeatureState with configuration."""
    
    def update(
        self,
        gc_candle: Candle | None = None,
        dxy_candle: Candle | None = None,
    ) -> pd.Series | None:
        """Update state with new candle(s) and return features."""
    
    def is_ready(self) -> bool:
        """Check if past warmup period."""
    
    def warmup_remaining(self) -> int:
        """Return number of candles needed to complete warmup."""
    
    def get_features(self) -> pd.Series:
        """Get current feature values (may contain NaN if not ready)."""
```

### Individual State Classes

```python
class VWAPState:
    def update(self, candle: Candle) -> float:
        """Update VWAP state and return current VWAP."""

class RSIState:
    def update(self, price: float) -> float | None:
        """Update RSI state and return current RSI (or None if not ready)."""

class EMAState:
    def update(self, price: float) -> dict[str, float]:
        """Update EMA state and return dict of current EMAs."""

class DXYCorrelationState:
    def update(
        self, gc_price: float | None, dxy_price: float | None, timestamp: datetime
    ) -> float | None:
        """Update correlation state and return current correlation."""

class StructureState:
    def update(self, high: float, low: float) -> str | None:
        """Update structure state and return label if swing point detected."""
```

## Testing

Run unit tests:

```bash
uv run pytest tests/unit/test_feature_state.py -v
```

Run parity tests (incremental vs vectorized):

```bash
uv run pytest tests/unit/test_feature_parity.py -v
```

Run all feature engine tests:

```bash
uv run pytest tests/unit/test_feature*.py -v
```

## See Also

- [Feature Engine Overview](./README.md)
- [VWAP Documentation](./vwap.md)
- [RSI Documentation](./rsi.md)
- [EMA Documentation](./ema.md)
- [DXY Correlation Documentation](./dxy-correlation.md)
- [Structure Labels Documentation](./structure.md)
- [Integration Layer Documentation](./integration.md)

