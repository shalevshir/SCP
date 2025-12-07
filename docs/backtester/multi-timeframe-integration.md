# Multi-Timeframe Sync Layer Integration with Backtesting

## Overview

The Multi-Timeframe Sync Layer provides synchronized access to HTF (Higher Timeframe) data aligned to the execution timeframe (1m). This document explains how it integrates with the backtesting pipeline to enable efficient HTF bias computation.

## Current Backtest Architecture

### Current Flow (Without Sync Layer)

```
1. Load 1m GC/DXY data → gc_df, dxy_df
2. BacktestProcessor iterates through 1m features
3. For each 1m bar:
   - Compute HTF bias (needs 1h/15m features)
   - Currently: Load 15m/1h data separately OR compute from 1m aggregation
   - Score signal with HTF bias
   - Execute entry if A+
```

**Current Challenges:**
- HTF data must be loaded/computed separately
- Manual alignment required between 1m and HTF timestamps
- Inefficient: HTF features computed multiple times or data loaded redundantly

### New Flow (With Sync Layer)

```
1. Load multi-timeframe data using MultiTimeframeSyncLayer
   → Synchronized bars with 1m, 15m, 1h data aligned
2. BacktestProcessor iterates through 1m features
3. For each 1m bar:
   - Get synchronized bar (includes HTF candles)
   - Compute HTF features from synchronized HTF candles
   - Compute HTF bias using HTF features
   - Score signal with HTF bias
   - Execute entry if A+
```

**Benefits:**
- Single data load for all timeframes
- Automatic alignment to execution timeframe
- Efficient: HTF candles available directly from sync layer
- No redundant data loading

## Integration Points

### 1. Data Loading

**Before (Current):**
```python
from data_layer.loader import HistoricalDataLoader

loader = HistoricalDataLoader("data/gc_dx_ohlcv")
gc_df = loader.load(["GC"], "1m", start, end)["GC"]
dxy_df = loader.load(["DXY"], "1m", start, end)["DXY"]

# HTF data loaded separately (if needed)
gc_15m = loader.load(["GC"], "15m", start, end)["GC"]
gc_1h = loader.load(["GC"], "1h", start, end)["GC"]
# Manual alignment required...
```

**After (With Sync Layer):**
```python
from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
from data_layer.multi_timeframe_helpers import extract_execution_dataframes

sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
multi_tf_data = sync_layer.load(start, end)

# Extract 1m data for BacktestProcessor (helper function)
gc_df, dxy_df = extract_execution_dataframes(multi_tf_data)

# HTF data available via multi_tf_data.get_bar(timestamp)
# Or use the new pipeline functions that handle this automatically
```

### 2. HTF Bias Function

**Before (Current):**
```python
def htf_bias_func(features_1m: pd.Series, context: dict) -> HTFBias:
    """Compute HTF bias - needs to load/compute HTF features separately."""
    timestamp = features_1m["timestamp"]
    
    # Option 1: Load HTF data separately (inefficient)
    # Option 2: Aggregate from 1m data (complex, may have alignment issues)
    # Option 3: Pre-compute HTF features (memory intensive)
    
    features_1h = compute_htf_features_1h(timestamp)  # How?
    features_15m = compute_htf_features_15m(timestamp)  # How?
    
    return compute_htf_bias(features_1h, features_15m)
```

**After (With Sync Layer):**
```python
from rule_engine.htf.integration import create_htf_bias_func_with_sync_layer

# Create HTF bias function with sync layer access
htf_bias_func = create_htf_bias_func_with_sync_layer(
    multi_tf_data,
    approach="streaming",  # or "vectorized"
)

# The function is ready to use in backtest pipeline
# It automatically:
# - Retrieves synchronized HTF bars for each timestamp
# - Computes HTF features (streaming or vectorized)
# - Computes HTF bias using compute_htf_bias()
```

**Manual approach (if you need custom logic):**
```python
from rule_engine.htf.features import StreamingHTFFeatureComputer
from data_layer.multi_timeframe_helpers import build_htf_dataframe_from_candles

# Create streaming feature computer
htf_computer = StreamingHTFFeatureComputer()

def custom_htf_bias_func(features_1m: pd.Series, context: dict) -> HTFBias:
    """Custom HTF bias function with manual feature computation."""
    timestamp = features_1m["timestamp"]
    sync_bar = multi_tf_data.get_bar(timestamp)
    
    if not sync_bar:
        return HTFBias(bias="neutral", direction="neutral", score=0.0)
    
    # Update HTF features incrementally
    features_15m, features_1h = htf_computer.update_from_sync_bar(sync_bar)
    
    # Build DataFrames for structure detection
    df_15m = build_htf_dataframe_from_candles(
        [sync_bar.htf_15m[0]], "15m"
    ) if sync_bar.htf_15m else None
    df_1h = build_htf_dataframe_from_candles(
        [sync_bar.htf_1h[0]], "1h"
    ) if sync_bar.htf_1h else None
    
    return compute_htf_bias(features_1h, features_15m, df_1h=df_1h, df_15m=df_15m)
```

### 3. Complete Backtest Example (New API)

**Using the new `run_backtest_with_entries_multi_tf` function:**

```python
from datetime import datetime, timezone
from backtester.pipeline import run_backtest_with_entries_multi_tf
from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer

# Step 1: Load multi-timeframe data
sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
end = datetime(2025, 9, 30, 13, 0, 0, tzinfo=timezone.utc)

multi_tf_data = sync_layer.load(start, end)

# Step 2: Define market state
market_state = {
    "buffer_phase": "growth",
    "tier_active": "EarlyMild",
    "ceo_directive_active": True,
    "news_ok": True,
    "session_ok": True,
}

# Step 3: Run backtest with multi-timeframe sync (streaming approach)
executions, processor = run_backtest_with_entries_multi_tf(
    multi_tf_data=multi_tf_data,
    timeframe="1m",
    market_state=market_state,
    htf_approach="streaming",  # or "vectorized"
    log_signals=True,
    log_dir="logs/backtest",
)

# Analyze results
executed = [e for e in executions if e.executed]
print(f"Executed entries: {len(executed)}/{len(executions)}")
```

**Using the new `run_backtest_with_trades_multi_tf` function:**

```python
from backtester.pipeline import run_backtest_with_trades_multi_tf

risk_config = {
    "risk_per_trade": 350.0,
    "buffer_phase": "startup",
    "max_contracts": 1,
}

# Run complete backtest with trade simulation
trades = run_backtest_with_trades_multi_tf(
    multi_tf_data=multi_tf_data,
    timeframe="1m",
    market_state=market_state,
    risk_config=risk_config,
    htf_approach="vectorized",  # Pre-compute all HTF features
    log_signals=True,
    log_dir="logs/backtest",
)

# Analyze trades
winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
win_rate = len(winning_trades) / len(trades) * 100 if trades else 0
total_pnl = sum(t.pnl for t in trades if t.pnl)
print(f"Win rate: {win_rate:.1f}%")
print(f"Total PnL: {total_pnl:.2f} points")
```

## Implementation Details

### HTF Feature Computation

The HTF features are computed from HTF candles using two approaches:

**Streaming Approach (Incremental):**
```python
from rule_engine.htf.features import StreamingHTFFeatureComputer

# Maintain state for incremental HTF feature computation
htf_computer = StreamingHTFFeatureComputer()

# For each synchronized bar:
features_15m, features_1h = htf_computer.update_from_sync_bar(sync_bar)
```

**Vectorized Approach (Pre-computed):**
```python
from rule_engine.htf.features import compute_htf_features_vectorized
from data_layer.multi_timeframe_helpers import extract_htf_candles_by_timeframe

# Extract all HTF candles
gc_15m, dxy_15m = extract_htf_candles_by_timeframe(multi_tf_data, "15m")
gc_1h, dxy_1h = extract_htf_candles_by_timeframe(multi_tf_data, "1h")

# Compute all features at once
features_15m_df, features_1h_df = compute_htf_features_vectorized(
    gc_15m, dxy_15m, gc_1h, dxy_1h
)
```

**Factory Function (Recommended):**
```python
from rule_engine.htf.integration import create_htf_bias_func_with_sync_layer

# Automatically handles feature computation based on approach
htf_bias_func = create_htf_bias_func_with_sync_layer(
    multi_tf_data,
    approach="streaming",  # or "vectorized"
)
```

### Alignment Strategy

The sync layer uses **forward-fill alignment**: For each 1m execution timestamp, it provides the most recent HTF bar that closed at or before that timestamp.

**Example:**
- 1m bar at 10:05:00 → 15m bar at 10:00:00 (most recent 15m bar ≤ 10:05:00)
- 1m bar at 10:15:00 → 15m bar at 10:15:00 (15m bar just closed)
- 1m bar at 10:16:00 → 15m bar at 10:15:00 (still using previous 15m bar)

This ensures **no look-ahead bias**: HTF data is only from bars that have already closed.

## Benefits for Backtesting

1. **Efficiency**: Single data load for all timeframes
2. **Accuracy**: Automatic alignment prevents timestamp mismatches
3. **Simplicity**: HTF candles available directly, no manual alignment
4. **Consistency**: Same alignment logic for backtesting and live trading
5. **Performance**: Reduced redundant data loading and feature computation

## New API Reference

### Pipeline Functions

**`run_backtest_with_entries_multi_tf()`**
- Accepts `MultiTimeframeData` directly
- Automatically creates HTF bias function with sync layer
- Supports both streaming and vectorized HTF feature computation
- Returns `(list[EntryExecution], BacktestProcessor)`

**`run_backtest_with_trades_multi_tf()`**
- Accepts `MultiTimeframeData` directly
- Runs complete backtest with trade simulation
- Returns `list[Trade]`

### Helper Functions

**`extract_execution_dataframes(multi_tf_data)`**
- Extracts 1m GC and DXY DataFrames from `MultiTimeframeData`
- Returns `(gc_df, dxy_df)` with DatetimeIndex

**`extract_htf_candles_by_timeframe(multi_tf_data, timeframe)`**
- Extracts HTF candles for a specific timeframe
- Returns `(gc_candles, dxy_candles)`

**`candles_to_dataframe(candles, timeframe)`**
- Converts list of `Candle` objects to DataFrame
- Returns DataFrame with DatetimeIndex

### HTF Feature Computation

**`StreamingHTFFeatureComputer`**
- Maintains state for incremental HTF feature computation
- Updates features as new HTF bars arrive
- Use `update_from_sync_bar()` to update and get features

**`compute_htf_features_vectorized(...)`**
- Batch computes HTF features for all candles
- More efficient for backtesting where all data is available
- Returns `(features_15m_df, features_1h_df)`

**`create_htf_bias_func_with_sync_layer(...)`**
- Factory function to create HTF bias function
- Supports "streaming" and "vectorized" approaches
- Returns function with signature `(features_1m, context) -> HTFBias`

## Migration Path

### Phase 1: Add Sync Layer Support ✅
- ✅ Multi-Timeframe Sync Layer implemented
- ✅ DataStream integration (optional, backward compatible)
- ✅ Backtest integration (complete)

### Phase 2: Update HTF Bias Functions ✅
- ✅ Helper functions for HTF feature computation
- ✅ Factory function for HTF bias creation
- ✅ Tests updated to use sync layer

### Phase 3: Optimize Performance
- ✅ Vectorized approach for batch computation
- ✅ Streaming approach for incremental updates
- ⏳ Profile and optimize hot paths (future work)

## Testing

Integration tests should verify:
1. Sync layer provides HTF data aligned to 1m timestamps
2. HTF bias computation uses correct HTF candles
3. No look-ahead bias (HTF bars are from past/current, not future)
4. Missing HTF data handled gracefully (returns None, neutral bias)

## Example Scripts

**Complete working example:**
```bash
poetry run python scripts/backtest_with_multi_tf_sync.py \
    --data-dir data/gc_dx_ohlcv \
    --start 2025-09-30T10:00:00Z \
    --end 2025-09-30T13:00:00Z \
    --htf-approach streaming \
    --with-trades
```

**E2E test with sync layer:**
```bash
poetry run python scripts/test_rule_engine_e2e.py \
    --data-dir data/gc_dx_ohlcv \
    --start 2025-09-30T07:00:00Z \
    --end 2025-10-01T16:00:00Z \
    --use-sync-layer \
    --htf-approach vectorized
```

## Performance Comparison

**Streaming Approach:**
- ✅ Lower memory usage (incremental updates)
- ✅ Good for live trading (real-time updates)
- ⚠️ Slightly slower (updates on each bar)

**Vectorized Approach:**
- ✅ Faster (pre-computed features)
- ✅ Better for backtesting (all data available)
- ⚠️ Higher memory usage (all features in memory)

**Recommendation:**
- Use **streaming** for live trading and small backtests
- Use **vectorized** for large backtests and performance-critical scenarios

## References

- [Multi-Timeframe Sync Layer](../../data_layer/multi_timeframe_sync.py)
- [Multi-Timeframe Helpers](../../data_layer/multi_timeframe_helpers.py)
- [HTF Features Module](../../rule_engine/htf/features.py)
- [HTF Integration](../../rule_engine/htf/integration.py)
- [Backtesting Pipeline](../../backtester/pipeline.py)
- [HTF Bias Calculator](../../rule_engine/htf/calculator.py)
- [Streaming Feature Processor](../../feature_engine/streaming.py)

