# Fix: Feature-Based Invalidations During Trade Simulation

**Date**: 2025-11-26  
**Branch**: feature/validation-replay-layer  
**Type**: Bug Fix (Critical)  
**Status**: ✅ Fixed and Verified

---

## Problem

### Issue Description

The recent refactoring of `backtester/pipeline.py` removed the computation of `future_features` that were previously passed to `simulate_trade_outcome()`. This caused all feature-based invalidation checks to be silently skipped during trade simulation.

### Affected Components

The following invalidation checks in `InvalidationChecker` were disabled:

1. **VWAP Invalidation** (`check_vwap_invalidation`)
   - Long VWAP_RECLAIM: Exit when close < VWAP
   - Short VWAP_RECLAIM: Exit when close > VWAP
   - Long VWAP_FADE: Exit when close > VWAP (reclaim)
   - Short VWAP_FADE: Exit when close < VWAP (reclaim)

2. **HTF Structure Invalidation** (`check_htf_structure_invalidation`)
   - Long: Exit on LH/LL structure (bearish break)
   - Short: Exit on HH/HL structure (bullish break)

3. **DXY Flip** (`check_dxy_flip`)
   - Exit when DXY correlation/structure breaks against trade direction

### Root Cause

All three invalidation methods return `(False, None)` immediately when `features is None`:

```python
def check_vwap_invalidation(self, trade, candle, features=None):
    if features is None:
        return False, None  # ⚠️ Silently skips check
```

Without `future_features`, these critical SOP rules were not enforced during backtesting.

### Impact

- **Backtest Accuracy**: Trades held longer than SOP allows
- **Risk Exposure**: Invalidated trades not exited early
- **Performance Metrics**: Win rates and R-multiples inflated
- **SOP Compliance**: VWAP, HTF structure, and DXY rules not enforced

---

## Solution

### Changes Made

**File**: `backtester/pipeline.py`  
**Function**: `run_backtest_with_trades()`

Added computation of `future_features` before calling `simulate_trade_outcome()`:

```python
# Compute features for future candles (required for invalidation checks)
# Without features, VWAP/HTF/DXY invalidations will be silently skipped
future_features = None
if not future_candles.empty:
    try:
        # Find entry index in gc_df
        entry_idx = gc_df.index.get_loc(entry.entry_timestamp)
        
        # Get data slice from start up to end of future candles
        end_idx = min(entry_idx + 1 + len(future_candles), len(gc_df))
        gc_slice = gc_df.iloc[:end_idx]
        dxy_slice = dxy_df.iloc[:end_idx] if len(dxy_df) >= end_idx else dxy_df
        
        # Compute features for the entire slice using processor
        features_df = processor._compute_features(gc_slice, dxy_slice)
        
        # Extract only features for future candles (after entry)
        if len(features_df) > entry_idx + 1:
            future_features_df = features_df.iloc[entry_idx + 1 :].copy()
            
            # Set timestamp index and align with future_candles
            # ... (index alignment logic) ...
            
            future_features = future_features_df.reindex(
                future_candles.index, method=None
            )
    except Exception as e:
        logger.warning(
            f"Failed to compute features for future candles: {e}. "
            "Feature-based invalidations (VWAP/HTF/DXY) will be skipped."
        )
        future_features = None

# Pass future_features to simulator
closed_trade = simulate_trade_outcome(
    trade=trade,
    future_candles=future_candles,
    invalidation_checker=invalidation_checker,
    config=config,
    future_features=future_features,  # ✅ Now passed
)
```

### Key Design Decisions

1. **Reuse Existing Processor**: Use the `processor` instance already created for state persistence
2. **No State Pollution**: `_compute_features()` is stateless for feature computation
3. **Graceful Degradation**: If feature computation fails, log warning but continue (degraded mode)
4. **Index Alignment**: Ensure features align with future_candles timestamps for accurate per-candle checks

---

## Verification

### Tests Added

**File**: `tests/unit/backtester/test_feature_passing_bug.py`

1. **`test_simulate_trade_outcome_receives_future_features()`**
   - Verifies `future_features` parameter is passed to `simulate_trade_outcome`
   - Confirms features have correct shape and are not None
   - Uses mocking to track actual function calls

2. **`test_invalidation_checker_returns_early_without_features()`**
   - Documents the behavior: InvalidationChecker returns early when features=None
   - Verifies all three methods (VWAP, HTF, DXY) return `(False, None)`
   - Shows why the fix is critical

### Test Results

```bash
# All backtester tests pass
$ uv run pytest tests/unit/backtester/ -v
190 passed, 1 skipped in 4.15s

# Full test suite passes
$ uv run pytest tests/unit/ -v
1154 passed, 4 skipped, 3 warnings in 6.89s

# New verification tests pass
$ uv run pytest tests/unit/backtester/test_feature_passing_bug.py -v
✓ simulate_trade_outcome called 1 times
  ✓ Call 1: future_features provided (shape: (20, 14))
2 passed in 1.27s

# VWAP invalidation tests pass
$ uv run pytest tests/unit/backtester/test_invalidations.py -v -k "vwap"
9 passed in 0.33s
```

---

## Before vs After

### Before Fix

```python
# ❌ No future_features passed
closed_trade = simulate_trade_outcome(
    trade=trade,
    future_candles=future_candles,
    invalidation_checker=invalidation_checker,
    config=config,
    # Missing: future_features parameter
)

# Result: All feature-based invalidations silently skipped
# - VWAP invalidations not checked
# - HTF structure breaks not detected
# - DXY flips not caught
```

### After Fix

```python
# ✅ future_features computed and passed
future_features = compute_future_features(...)  # Restored computation

closed_trade = simulate_trade_outcome(
    trade=trade,
    future_candles=future_candles,
    invalidation_checker=invalidation_checker,
    config=config,
    future_features=future_features,  # ✅ Now provided
)

# Result: All SOP invalidations properly enforced
# ✓ VWAP invalidations detected
# ✓ HTF structure breaks exit trades
# ✓ DXY flips trigger exits
```

---

## Impact Assessment

### SOP Compliance

- ✅ **VWAP Rules**: Now enforced correctly
- ✅ **HTF Structure**: Breaks detected and trades exited
- ✅ **DXY Alignment**: Flips trigger invalidations
- ✅ **Risk Management**: Trades exit earlier on invalidations

### Backtest Accuracy

- **More Realistic Results**: Invalidations now match live trading
- **Lower Win Rates** (expected): Some trades exit earlier at losses
- **Better Risk Management**: Trades don't overstay invalidated conditions
- **True SOP Performance**: Metrics now reflect actual rule enforcement

### Performance Impact

- **Computation Cost**: Minimal (features computed once per trade)
- **Memory**: Negligible (only future window features, max 20 bars)
- **Speed**: No measurable slowdown in tests

---

## Related Documentation

- [Invalidation Rules](../backtester/invalidations.md)
- [Trade Simulator](../backtester/simulator.md)
- [Pipeline Integration](../backtester/pipeline-integration.md)
- [Replay Engine](../backtester/replay-engine.md)

---

## Lessons Learned

1. **Critical Dependencies**: Feature-based invalidations have hard dependencies on feature data
2. **Silent Failures**: Early returns without logging can hide critical bugs
3. **Test Coverage**: Need tests that verify parameters are passed, not just behavior
4. **Documentation**: Inline comments about "Required for X" should be enforced by tests

---

## Status

- ✅ Bug identified and root cause analyzed
- ✅ Fix implemented in `backtester/pipeline.py`
- ✅ Tests added to verify fix
- ✅ All existing tests pass (no regressions)
- ✅ Documentation updated

**Ready for merge** into `feature/validation-replay-layer` branch.

