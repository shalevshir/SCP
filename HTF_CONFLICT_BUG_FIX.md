# HTF Conflict Detection Bug Fix

**Date:** 2026-02-10
**Severity:** High
**Status:** Fixed

## Problem

The `on_htf_bias()` method in `TradeManager` was building a dictionary from `HTFBiasMessage` but omitted the critical `conflict_detected` and `conflict_reason` fields.

This caused the `check_runner_hard_invalidation()` method's check for HTF conflicts to always return `False` since the key was never present in the dictionary, silently disabling this critical safety check.

**Impact:** DXY_CONTINUATION runner trades that should exit immediately when an HTF conflict is detected (e.g., 15m/1h structure mismatch) would remain open instead, potentially resulting in significant losses.

## Root Cause

In `services/execution/src/execution_svc/trade_manager.py`, the `on_htf_bias()` method at line 330-338:

```python
self._latest_htf_bias = {
    "timestamp": htf_bias_msg.timestamp,
    "bias": htf_bias_msg.bias,
    "score": htf_bias_msg.score,
    "confidence": htf_bias_msg.confidence,
    "structure_15m": htf_bias_msg.structure_15m,
    "structure_1h": htf_bias_msg.structure_1h,
    "dxy_aligned": htf_bias_msg.dxy_aligned,
    "chop_detected": htf_bias_msg.chop_detected,
    # MISSING: conflict_detected and conflict_reason
}
```

This incomplete dict is then passed to `InvalidationChecker.check_runner_hard_invalidation()` which checks:

```python
if htf_bias.get("conflict_detected", False):  # Always returns False!
    conflict_reason = htf_bias.get("conflict_reason", "unknown")
    reason = f"htf_conflict_detected: {conflict_reason}"
    return "exit_runner", reason
```

## Solution

**File:** `services/execution/src/execution_svc/trade_manager.py`
**Lines:** 330-341

Added the missing fields to the HTF bias dictionary:

```python
self._latest_htf_bias = {
    "timestamp": htf_bias_msg.timestamp,
    "bias": htf_bias_msg.bias,
    "score": htf_bias_msg.score,
    "confidence": htf_bias_msg.confidence,
    "structure_15m": htf_bias_msg.structure_15m,
    "structure_1h": htf_bias_msg.structure_1h,
    "dxy_aligned": htf_bias_msg.dxy_aligned,
    "chop_detected": htf_bias_msg.chop_detected,
    # FIX: Include conflict fields for hard invalidation checks
    "conflict_detected": htf_bias_msg.conflict_detected,
    "conflict_reason": htf_bias_msg.conflict_reason,
}
```

Also updated the debug logging to include conflict status:

```python
logger.debug(
    f"HTF bias updated: {htf_bias_msg.bias} (score={htf_bias_msg.score:.1f}, "
    f"confidence={htf_bias_msg.confidence}, dxy_aligned={htf_bias_msg.dxy_aligned}, "
    f"chop={htf_bias_msg.chop_detected}, conflict={htf_bias_msg.conflict_detected})"
)
```

## Testing

**New Test File:** `services/execution/tests/unit/test_htf_conflict_detection.py`

Created comprehensive unit tests covering:

1. ✅ `test_on_htf_bias_includes_conflict_fields` - Verifies fields are included
2. ✅ `test_on_htf_bias_no_conflict` - Verifies no-conflict case works
3. ✅ `test_runner_exits_on_htf_conflict` - Verifies trade exits when conflict detected
4. ✅ `test_runner_continues_without_htf_conflict` - Verifies trade continues normally
5. ✅ `test_htf_conflict_takes_priority_over_unlock` - Verifies hard invalidation happens BEFORE unlock attempts (per spec Section 4)

All tests pass successfully.

## Verification

Before fix:
```
❌ BUG CONFIRMED: Check returns False, trade continues despite conflict!

Original message has conflict_detected=True
Dict has conflict_detected=MISSING KEY
Dict has conflict_reason=MISSING KEY
```

After fix:
```
✅ CORRECT: HTF conflict detected, trade would exit
   Reason: 15m/1h structure mismatch

Original message has conflict_detected=True
Dict has conflict_detected=True
Dict has conflict_reason=15m/1h structure mismatch
```

## Related Code

- **Schema:** `services/shared/src/scp_shared/messaging/schemas.py` - `HTFBiasMessage` (lines 269-274)
- **Invalidation:** `services/shared/src/scp_shared/execution/invalidation.py` - `check_runner_hard_invalidation()` (lines 391-478)
- **Runner Unlock:** `services/shared/src/scp_shared/execution/invalidation.py` - `check_runner_unlock()` (lines 277-389)

## Phase Impact

This bug affects **Phase 7** (Runner unlock logic) where DXY_CONTINUATION trades transition from partial profit (40% close at +1R) to runner management (60% remainder targeting TP2).

The hard invalidation check is critical to exit runners immediately when the continuation thesis breaks, preventing catastrophic losses.

## Deployment Priority

**CRITICAL** - Should be deployed immediately as this is a high-severity safety bug that could result in significant financial losses if HTF conflicts occur during active runner positions.
