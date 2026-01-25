# Type Consistency Fix: bars_near_vwap

**Date:** 2026-01-22  
**Issue:** Type mismatch causing dead code in constraint  
**Status:** ✅ **FIXED**

---

## Problem

The `min_vwap_acceptance` constraint had a `is None` bypass that never executed:

```yaml
min_vwap_acceptance:
  expression: "bars_near_vwap is None or bars_near_vwap >= 3"
```

**Root cause:**
- `bars_near_vwap` was typed as `int` (not `int | None`) with default `0`
- When ATR unavailable, code set `bars_near_vwap = 0` (not `None`)
- The `is None` check was **dead code** - never True
- Constraint evaluated `0 >= 3` → **False**, incorrectly rejecting valid signals

**Contrast with correct implementation:**
- `bars_since_last_vwap_touch` correctly used `int | None` type
- Its `is None` bypass worked as intended

---

## Impact

**Before fix:**
- Signals rejected when ATR unavailable during warmup
- `is None` bypass in constraint was dead code
- Inconsistent with `bars_since_last_vwap_touch` handling

**After fix:**
- Signals pass when ATR unavailable (tracking not possible)
- Three distinct states properly handled:
  - `None` = tracking unavailable (ATR missing)
  - `0` = tracking available, price not near VWAP
  - `1+` = tracking available, price near VWAP

---

## Solution

Changed `bars_near_vwap` from `int` to `int | None` throughout the codebase:

### 1. StructureContext Dataclass

```python
# BEFORE
bars_near_vwap: int = 0

# AFTER
bars_near_vwap: int | None = None  # None when ATR unavailable
```

### 2. StructureContextTracker State

```python
# BEFORE
self.bars_near_vwap: int = 0

# AFTER
self.bars_near_vwap: int | None = None  # None when ATR unavailable
```

### 3. update_vwap_state() Logic

```python
# BEFORE
if atr is not None and atr > 0:
    if is_near_vwap:
        self.bars_near_vwap += 1  # ❌ Crashes if None
    else:
        self.bars_near_vwap = 0
else:
    self.bars_near_vwap = 0  # ❌ Should be None

# AFTER
if atr is not None and atr > 0:
    if is_near_vwap:
        self.bars_near_vwap = 1 if self.bars_near_vwap is None else self.bars_near_vwap + 1
    else:
        self.bars_near_vwap = 0  # Tracking available, not near
else:
    pass  # Keep as None (tracking unavailable)
```

### 4. FeaturesMessage Schema

```python
# BEFORE
bars_near_vwap: int = Field(
    default=0,
    description="Consecutive bars within VWAP proximity band (±0.2 ATR)"
)

# AFTER
bars_near_vwap: int | None = Field(
    default=None,
    description="Consecutive bars within VWAP proximity band (±0.2 ATR); None when ATR unavailable"
)
```

---

## State Semantics

### `bars_near_vwap`

| Value | Meaning | Constraint Behavior |
|-------|---------|---------------------|
| `None` | ATR unavailable, tracking not possible | **PASS** (bypass) |
| `0` | ATR available, price currently away from VWAP | **FAIL** (drive-by) |
| `1` | Near VWAP for 1 bar | **FAIL** (need ≥3) |
| `2` | Near VWAP for 2 bars | **FAIL** (need ≥3) |
| `3+` | Near VWAP for 3+ bars | **PASS** (meets threshold) |

### `bars_since_last_vwap_touch` (already correct)

| Value | Meaning | Constraint Behavior |
|-------|---------|---------------------|
| `None` | No VWAP touch detected yet | **PASS** (bypass) |
| `0` | Currently touching VWAP | **PASS** |
| `1-10` | Recently touched (within window) | **PASS** |
| `11+` | Too long since touch | **FAIL** (delayed) |

---

## Validation Results

All test scenarios passing:

```
✅ Initial state: None
✅ No ATR provided: None
✅ Touch VWAP with ATR: 1
✅ Stay near: 2
✅ Move away: 0 (not None)
✅ Constraint with None: PASS (bypass works)
✅ Constraint with 0: REJECTED (drive-by)
✅ Constraint with 3: PASS (threshold met)
```

---

## Files Modified

| File | Change |
|------|--------|
| `services/shared/src/scp_shared/indicators/structure.py` | `bars_near_vwap: int | None = None` in dataclass and tracker |
| `services/shared/src/scp_shared/indicators/structure.py` | Updated `update_vwap_state()` logic to handle None |
| `services/shared/src/scp_shared/messaging/schemas.py` | `bars_near_vwap: int | None = Field(default=None, ...)` |
| `services/shared/tests/unit/indicators/test_vwap_acceptance_tracking.py` | Updated tests to expect None initially |
| `services/shared/tests/unit/rule_engine/test_vwap_reclaim_sop_constraints.py` | Added test for 0 vs None distinction |

---

## Design Rationale

### Why Three States?

1. **`None` (tracking unavailable):**
   - ATR not computed yet (warmup period)
   - Should not reject signals - feature not available
   - Bypass constraint check gracefully

2. **`0` (tracking available, not near):**
   - ATR computed, price tracked, currently away from VWAP
   - Valid measurement: "price is far from VWAP"
   - Should reject if < 3 (drive-by reclaim)

3. **`1+` (tracking available, near VWAP):**
   - ATR computed, price within proximity band
   - Valid measurement: "price has been near VWAP for N bars"
   - Should pass if >= 3 (sufficient acceptance)

### Consistency with bars_since_last_vwap_touch

Both fields now follow the same pattern:
- `int | None` type
- `None` means "tracking not available" (not an error, gracefully bypass)
- `0` or positive integer means "tracking available with specific value"

---

## Backward Compatibility

**Risk:** Low
- Change only affects warmup period (when ATR not available)
- Production systems with warmed-up ATR unaffected
- Tests updated to match new semantics

**Migration:** None required
- State automatically initializes to None
- First bar with ATR starts tracking correctly

---

**Fix verified:** All tests passing ✅  
**Type consistency:** Now matches `bars_since_last_vwap_touch` ✅  
**Constraint bypass:** `is None` check now works correctly ✅
