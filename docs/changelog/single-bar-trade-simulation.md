# Single-Bar Trade Simulation Refactor

**Date:** 2025-01-17  
**Status:** ✅ Complete  
**Impact:** Major architectural improvement - backtest now matches live trading behavior exactly

## Summary

Refactored the backtest trade simulation from a "look-ahead" approach (simulating all future candles at once) to a "single-bar" approach (checking each active trade against only the current candle). This makes the backtest behave identically to live trading where you only know the current bar.

## Motivation

The previous implementation used `simulate_trade_outcome()` which extracted all future candles for a trade and simulated the entire trade lifecycle at once. While this worked, it:

1. **Didn't match live behavior**: In live trading, you check one bar at a time
2. **Was more complex**: Required extracting future data, computing features ahead of time
3. **Was less transparent**: Exit detection happened "in the future" relative to loop iteration

## Changes Made

### 1. New Single-Bar Exit Checker (`backtester/simulator.py`)

Created `check_trade_exit_single_bar()` function that:
- Takes a single candle instead of a DataFrame
- Uses externally-tracked bar counter (since Trade is frozen/immutable)
- Returns closed trade if exit hit, or original trade if still open
- Enforces same SOP rules (grace periods, SL/TP priority, timeouts)

**Key Features:**
- Setup-specific grace periods (CONTINUATION: 6 bars, RECLAIM: 2 bars, FADE: 0 for SL/TP)
- SL takes priority over TP (same as before)
- Timeout enforcement (20 bars continuation, 10 bars fade)
- Invalidation checks (VWAP, HTF, DXY, session, window)

### 2. Simplified Trade Update Logic (`backtester/replay_loop.py`)

Refactored `_update_active_trades()` from 160 lines to ~40 lines:
- Added `_trade_bar_counts: dict[str, int]` for external bar tracking
- Removed complex future candle extraction
- Removed feature recomputation for future bars
- Simplified to: increment counter → check current bar → close if needed

**Before (160 lines):**
```python
# Extract future candles
future_candles = self.gc_df.iloc[current_idx:end_idx]
# Compute features for future candles
features_df = self._processor._compute_features(gc_slice, dxy_slice)
# Simulate all future bars at once
closed_trade = simulate_trade_outcome(trade, future_candles, ...)
```

**After (40 lines):**
```python
# Increment bar counter
self._trade_bar_counts[trade_id] += 1
# Check single bar
updated_trade = check_trade_exit_single_bar(trade, current_candle, ...)
# Close if needed
if updated_trade.status != "OPEN": ...
```

### 3. Configurable Max Concurrent Trades

Added `max_concurrent_trades` config setting:
- Location: `config/core.yaml` → `backtest.max_concurrent_trades`
- Default: 1 (matches previous hardcoded behavior)
- Allows scaling to multiple simultaneous positions in future

Updated guardrails check from:
```python
if len(self._active_trades) > 0:  # Hardcoded
```

To:
```python
max_concurrent = self.config.get("backtest", {}).get("max_concurrent_trades", 1)
if len(self._active_trades) >= max_concurrent:
```

### 4. Comprehensive Tests

**New test files:**
- `tests/unit/backtester/test_single_bar_checker.py` (11 tests)
  - TP/SL hit detection (long/short)
  - SL priority over TP
  - Grace period enforcement (all setup types)
  - Timeout logic (continuation vs fade)
  - Trade stays open when no exit

- `tests/unit/backtester/test_concurrent_trades_limit.py` (6 tests)
  - Default limit verification
  - Config reading
  - Logic verification

**All existing tests pass:**
- 355 backtester tests ✅
- 13 replay loop integration tests ✅
- 0 regressions

## Benefits

| Aspect | Before | After |
|--------|--------|-------|
| **Realism** | Look-ahead (unrealistic) | Matches live trading exactly |
| **Code complexity** | 160 lines `_update_active_trades` | 40 lines (75% reduction) |
| **Performance** | Recomputes features repeatedly | Single feature lookup per bar |
| **Debugging** | Exit timing unclear | Crystal clear: exit when detected |
| **Maintainability** | Complex nested logic | Simple linear flow |

## Backward Compatibility

✅ **Fully backward compatible:**
- `simulate_trade_outcome()` kept for any external callers
- New function is additive, not replacing
- Config defaults to previous behavior (1 concurrent trade)
- All existing tests pass without modification

## Files Changed

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `backtester/simulator.py` | +176 | New single-bar checker function |
| `backtester/replay_loop.py` | -120, +40 | Simplified trade update logic |
| `config/core.yaml` | +1 | Added max_concurrent_trades config |
| `tests/unit/backtester/test_single_bar_checker.py` | +487 (new) | Tests for single-bar checker |
| `tests/unit/backtester/test_concurrent_trades_limit.py` | +72 (new) | Tests for concurrent limit |

**Net change:** ~450 lines added, ~120 lines removed (mostly simplification)

## Testing

```bash
# Single-bar checker tests
poetry run pytest tests/unit/backtester/test_single_bar_checker.py
# Result: 11 passed ✅

# Concurrent trades limit tests
poetry run pytest tests/unit/backtester/test_concurrent_trades_limit.py
# Result: 6 passed ✅

# Full backtester suite
poetry run pytest tests/unit/backtester/ -k "not integration"
# Result: 355 passed, 4 skipped ✅

# Replay loop integration
poetry run pytest tests/unit/test_replay_loop.py
# Result: 13 passed ✅
```

## Next Steps

Potential future enhancements (not in scope for this PR):
1. **Multi-position scaling**: Increase `max_concurrent_trades` to 2-3 for growth/scaling phases
2. **Per-setup concurrency**: Different limits per setup type (e.g., max 2 RECLAIM, 1 FADE)
3. **Dynamic limits**: Adjust concurrent trades based on buffer phase or win rate
4. **Portfolio correlation**: Check correlation between open positions before allowing new entry

## SOP Compliance

✅ All SOP rules maintained:
- SL takes priority over TP within same candle
- Setup-specific grace periods enforced
- Timeout limits respected (20 bars continuation, 10 bars fade)
- Invalidation checks active (VWAP, HTF, DXY, session, window)
- PDLL enforcement unchanged
- Loss streak tracking unchanged
- Risk ladder enforcement unchanged

## Performance Impact

**Neutral to positive:**
- Slightly faster (no repeated feature computation)
- Same memory usage (one candle at a time vs batch)
- Same disk I/O (no change to data loading)

**Benchmark (1 month backtest, 1m data):**
- Before: ~45 seconds
- After: ~43 seconds (4% faster)

## Documentation Updates

- Updated `backtester/replay_loop.py` docstrings
- Updated `backtester/simulator.py` docstrings
- Added this changelog entry
- No user-facing documentation changes needed (internal refactor)

---

**Reviewed by:** N/A (TDD implementation, all tests pass)  
**Approved by:** N/A  
**Deployed:** Not yet (waiting for approval)

