# DXY Availability Guardrail Fix

**Date:** December 8, 2025  
**Status:** ✅ Fixed  
**Issue Type:** Dead Code / Logic Bug  
**Severity:** High (Silent Failure)

---

## Problem Statement

The DXY availability guardrail (Guardrail 6) in `BacktestReplayLoop._check_guardrails()` was **dead code**. The guardrail was designed to block trades when DXY data is missing or invalid, but it never actually executed.

### Root Cause

The guardrail checked for `dxy_rsi` in `validation_context`:

```python
# Line 574 (before fix)
if "dxy_rsi" in validation_context:
    dxy_rsi = validation_context.get("dxy_rsi")
    if dxy_rsi is None or (isinstance(dxy_rsi, float) and pd.isna(dxy_rsi)):
        blocking_reasons.append("DXY data not available")
```

However, `BacktestProcessor._build_validation_context()` in `feature_engine/backtesting.py` (lines 433-439) **never adds `dxy_rsi`** to the validation context. It only includes:
- `session_ok`
- `session_result`
- `session_constraints`
- `guardrail_result`
- `behavior_state`

This meant the condition `if "dxy_rsi" in validation_context` was **always False**, making the guardrail completely non-functional.

### Impact

**Before Fix:**
- Trades could execute even when DXY data was unavailable (None or NaN values)
- This violates SOP requirement: "DXY availability: block signals if DXY feed missing"
- Silent failure: no error messages, just incorrect behavior
- Potential for invalid trades in production backtests

---

## Solution

### Changes Made

#### 1. Updated `_check_guardrails()` Signature

**File:** `backtester/replay_loop.py`

Added `features` parameter to access feature data directly:

```python
def _check_guardrails(
    self,
    validation_context: dict,
    current_timestamp: datetime,
    features: pd.Series | None = None,  # NEW: Added features parameter
) -> tuple[bool, list[str]]:
```

#### 2. Updated Call Site

Pass `features` to `_check_guardrails()`:

```python
# Line 371 (after fix)
guardrails_allowed, blocking_reasons = self._check_guardrails(
    validation_context, current_timestamp, features  # NEW: Pass features
)
```

#### 3. Fixed Guardrail Logic

Check `dxy_rsi` in `features` instead of `validation_context`:

```python
# Line 575 (after fix)
if features is not None and "dxy_rsi" in features.index:
    dxy_rsi = features.get("dxy_rsi")
    if dxy_rsi is None or (isinstance(dxy_rsi, float) and pd.isna(dxy_rsi)):
        blocking_reasons.append("DXY data not available")
        logger.debug(
            f"DXY availability guardrail blocked at {current_timestamp}"
        )
```

---

## Test Coverage

### New Test File

**File:** `tests/unit/test_dxy_availability_guardrail.py`

Created comprehensive test suite with 4 test cases:

1. **`test_guardrail_blocks_when_dxy_rsi_is_none`**
   - Verifies guardrail blocks when `dxy_rsi = None`
   - Expected: Entry blocked with "DXY data not available" message

2. **`test_guardrail_blocks_when_dxy_rsi_is_nan`**
   - Verifies guardrail blocks when `dxy_rsi = np.nan`
   - Expected: Entry blocked with "DXY data not available" message

3. **`test_guardrail_allows_when_dxy_rsi_is_valid`**
   - Verifies guardrail allows trades when `dxy_rsi` is valid (e.g., 55.0)
   - Expected: No DXY-related blocking message

4. **`test_backtest_with_missing_dxy_produces_no_trades`**
   - End-to-end test: backtest with all DXY data missing
   - Expected: Zero trades executed

### Test Results

```bash
$ poetry run pytest tests/unit/test_dxy_availability_guardrail.py -v
============================== 4 passed in 0.92s ===============================
```

### Regression Testing

All existing tests continue to pass:

```bash
$ poetry run pytest tests/unit/ -v
================ 1262 passed, 10 skipped, 3 warnings in 26.96s =================
```

Specifically verified:
- `tests/unit/test_replay_loop.py` (13 tests)
- `tests/unit/test_replay_loop_integration.py` (8 tests)

---

## Verification

### Before Fix

The guardrail was dead code:
- `if "dxy_rsi" in validation_context:` → Always `False`
- No blocking occurred even with missing DXY data
- Tests would have failed if they existed

### After Fix

The guardrail is now functional:
- Checks `features["dxy_rsi"]` directly
- Blocks trades when `dxy_rsi` is `None` or `NaN`
- Allows trades when `dxy_rsi` has valid numeric value
- Properly logs blocking events

---

## Design Rationale

### Why Not Add `dxy_rsi` to `validation_context`?

We chose to pass `features` directly rather than modify `validation_context` because:

1. **Separation of Concerns:**
   - `validation_context` is for session/behavior/guardrail state
   - `features` contains indicator values (RSI, VWAP, etc.)
   - Mixing them would blur the architectural boundary

2. **Minimal Change:**
   - Only affects `BacktestReplayLoop` (single module)
   - No changes needed to `BacktestProcessor` or validation layer
   - Reduces risk of breaking other components

3. **Consistency:**
   - Other feature checks (HTF bias, signal scoring) use `features` directly
   - This approach aligns with existing patterns

4. **Flexibility:**
   - Future guardrails can access any feature without modifying `validation_context`
   - Easier to add checks for other indicators (e.g., `gc_rsi`, `vwap_deviation`)

---

## SOP Compliance

This fix ensures compliance with **Guardrail 6** from the SOP:

> **DXY availability: block signals if DXY feed missing**

The guardrail now correctly:
- ✅ Detects when DXY RSI is `None` (feed missing)
- ✅ Detects when DXY RSI is `NaN` (invalid data)
- ✅ Blocks entry with clear reason: "DXY data not available"
- ✅ Logs blocking events for audit trail
- ✅ Allows trades when DXY data is valid

---

## Related Documentation

- **SOP Reference:** `docs/01-project-overview.md` (Guardrail 6)
- **Replay Loop Docs:** `docs/backtester/replay-engine.md`
- **Invalidations Docs:** `docs/backtester/invalidations.md`

---

## Commit Message

```
fix(backtester): activate DXY availability guardrail (Guardrail 6)

The DXY availability guardrail was dead code - it checked for dxy_rsi
in validation_context, but BacktestProcessor never adds it there.

Changes:
- Update _check_guardrails() to accept features parameter
- Check features["dxy_rsi"] instead of validation_context["dxy_rsi"]
- Add comprehensive test coverage for None/NaN/valid cases

The guardrail now properly blocks trades when DXY data is missing,
ensuring SOP compliance: "block signals if DXY feed missing"

Tests: 4 new tests in test_dxy_availability_guardrail.py
All existing tests pass (1262 passed, 10 skipped)
```

---

## Future Considerations

### Potential Enhancements

1. **Add GC RSI Check:**
   - Similar guardrail for `gc_rsi` availability
   - Ensures both instruments have valid data

2. **Volume Check:**
   - Block if volume is 0 or missing
   - Indicates stale/invalid market data

3. **Timestamp Validation:**
   - Ensure data is recent (not stale)
   - Add max age threshold (e.g., 5 minutes)

4. **Data Quality Metrics:**
   - Track % of candles with missing DXY
   - Alert if data quality degrades
   - Add to backtest results summary

### Monitoring

Consider adding metrics:
- `dxy_availability_blocks_count`: Number of times guardrail triggered
- `dxy_missing_percentage`: % of candles with missing DXY
- `last_dxy_block_timestamp`: Most recent blocking event

---

## Conclusion

This fix resolves a critical silent failure in the backtesting system. The DXY availability guardrail is now functional and properly enforces SOP requirements. Comprehensive test coverage ensures the fix works correctly and prevents regression.

**Status:** ✅ Complete  
**Tests:** ✅ All Passing  
**SOP Compliance:** ✅ Verified

