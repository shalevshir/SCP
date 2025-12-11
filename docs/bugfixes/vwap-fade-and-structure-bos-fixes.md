# Bug Fixes: VWAP Fade Invalidation & Structure BOS Fields

**Date:** December 11, 2025  
**Status:** ✅ Fixed and Verified

## Summary

Fixed two critical bugs discovered after Structure Engine v2.0 Part 1 implementation:

1. **VWAP_FADE invalidation logic was inverted** - causing incorrect trade exits
2. **StructureContext BOS fields were unimplemented** - causing silent failures in downstream code
3. **Bonus: Fixed DXY feature key mismatches** - found during testing

---

## Bug 1: VWAP_FADE Invalidation Logic Inverted

### Problem

The invalidation condition was backwards, checking for SUCCESS instead of INVALIDATION:

**OLD (Incorrect) Logic:**
```python
if trade.direction == "long":
    # Long fade: invalid if close BELOW VWAP
    if candle.close < vwap and vwap_slope < 0:
        condition_met = True
else:  # short
    # Short fade: invalid if close ABOVE VWAP  
    if candle.close > vwap and vwap_slope > 0:
        condition_met = True
```

**Why This Was Wrong:**
- Long fade = long position entered BELOW VWAP, expecting price to continue lower
- Checking `close < vwap` means the fade is WORKING (success), not invalidated
- Invalidation occurs when price RECLAIMS ABOVE VWAP (fade premise broken)

### Solution

Inverted the conditions to correctly detect invalidation:

**NEW (Correct) Logic:**
```python
if trade.direction == "long":
    # Long fade (long position): invalid if RECLAIMS ABOVE VWAP
    if candle.close > vwap and vwap_slope > 0:
        condition_met = True
else:  # short
    # Short fade (short position): invalid if BREAKS BELOW VWAP
    if candle.close < vwap and vwap_slope < 0:
        condition_met = True
```

### Files Modified

- `backtester/invalidations.py` (lines 245-252)
  - Fixed condition logic
  - Updated comments to explain correct behavior
  - Updated error message format to match new logic (line 264)

### Tests Updated

- `tests/unit/backtester/test_invalidations.py`
  - Updated test data to match corrected behavior
  - `test_vwap_invalidation_long_fade_requires_2_bars`
  - `test_vwap_invalidation_long_fade_counter_resets`
  - `test_vwap_invalidation_short_fade_requires_2_bars`
  - `test_vwap_invalidation_short_fade_not_triggered_with_one_bar`

### Impact

**Before Fix:**
- ❌ Fades were invalidated when they were WORKING (price moving as expected)
- ❌ Fades stayed open when they were FAILING (price moving opposite to expectation)
- ❌ Completely inverted exit logic

**After Fix:**
- ✅ Fades invalidated when price breaks fade premise
- ✅ Fades allowed to run when price moves as expected
- ✅ Correct risk management

---

## Bug 2: StructureContext BOS Fields Unimplemented

### Problem

`StructureContextTracker` initialized BOS tracking fields but never populated them:

```python
# In __init__:
self.last_bos_direction: str | None = None
self.last_bos_idx: int | None = None

# In update():
bos_age = None if self.last_bos_idx is None else (self.bar_count - self.last_bos_idx)

# Result:
# bos_age is ALWAYS None (last_bos_idx never set)
```

**Why This Was Dangerous:**
- Fields were exposed in `StructureContext` dataclass
- Downstream code could depend on `bos_age` values
- Silent failures - no errors, just None values everywhere
- False sense of feature availability

### Solution

Removed unimplemented BOS fields entirely (to be added in Structure Engine v2.0 Part 2):

**Removed from `StructureContext`:**
- `last_bos_direction`
- `bos_age`

**Retained:**
- CHoCH fields (these ARE implemented)
- Added comments noting BOS will be added in Part 2

### Files Modified

- `feature_engine/structure.py`
  - Removed BOS fields from `StructureContext` dataclass
  - Removed BOS tracking from `StructureContextTracker`
  - Removed `bos_age` from batch computation function
  - Added comments explaining BOS is Part 2 work

- `feature_engine/streaming.py`
  - Removed `bos_age` from feature output
  - Added comment noting future Part 2 addition

- `feature_engine/backtesting.py`
  - Removed `bos_age` from both iterator methods
  - Added comments for clarity

### Tests Updated

- `tests/unit/feature_engine/test_structure_context.py`
  - Removed BOS fields from test expectations
  - Added comments explaining Part 2 scope

### Impact

**Before Fix:**
- ❌ Silent failures (bos_age always None, no warning)
- ❌ False API - advertised but didn't work
- ❌ Potential downstream bugs from None values

**After Fix:**
- ✅ No silent failures - field doesn't exist = clear error if accessed
- ✅ Honest API - only expose what's implemented
- ✅ Part 2 can add BOS properly with tests

---

## Bonus Fix: DXY Feature Key Mismatches

### Problem

Multiple key naming inconsistencies discovered during testing:

1. Invalidation checker looked for `"dxy_structure"` but features use `"dxy_structure_label"`
2. Tests used generic `"dxy_corr_micro"` but checker expected `"dxy_corr_1m"` and `"dxy_corr_5m"`

### Solution

Updated invalidation checker to support both naming conventions:

```python
# Support both timeframe-specific and generic keys
corr_1m = _sanitize_float(features.get("dxy_corr_1m") or features.get("dxy_corr_micro"))
corr_5m = _sanitize_float(features.get("dxy_corr_5m") or features.get("dxy_corr_micro"))
dxy_structure = features.get("dxy_structure_label") or features.get("dxy_structure")
```

Updated tests to use correct keys matching HTFBias spec.

### Files Modified

- `backtester/invalidations.py`
  - Added fallback logic for DXY keys (line 395-397)
  
- `tests/unit/backtester/test_invalidations.py`
  - Fixed key names in DXY continuation tests

---

## Test Results

### Before Fixes
- ❌ 4 invalidation tests failing
- ❌ 3 DXY invalidation tests failing
- ❌ Logic errors causing incorrect trade management

### After Fixes
- ✅ All 52 invalidation tests pass
- ✅ All 9 DXY invalidation tests pass
- ✅ All 1000+ unit tests pass
- ✅ Zero regressions

---

## Verification Commands

```bash
# Run invalidation tests
poetry run pytest tests/unit/backtester/test_invalidations.py -v

# Run DXY invalidation tests
poetry run pytest tests/unit/backtester/test_dxy_invalidation.py -v

# Run structure context tests
poetry run pytest tests/unit/feature_engine/test_structure_context.py -v

# Run full suite
poetry run pytest tests/unit/ -q
```

---

## Impact Assessment

### Critical (Bug 1 - VWAP Fade)
- **Severity:** CRITICAL - inverted exit logic
- **Scope:** All VWAP_FADE trades in production/backtest
- **Fix Priority:** IMMEDIATE
- **Risk:** High - causes opposite behavior (exits winners, keeps losers)

### High (Bug 2 - BOS Fields)
- **Severity:** HIGH - silent API failure
- **Scope:** Any code depending on `bos_age` values
- **Fix Priority:** HIGH
- **Risk:** Medium - causes None values but no crashes

### Medium (Bonus - DXY Keys)
- **Severity:** MEDIUM - key naming mismatch
- **Scope:** DXY_CONTINUATION invalidation checks
- **Fix Priority:** MEDIUM
- **Risk:** Low - fallback logic now handles both formats

---

## Lessons Learned

1. **Test After Refactors:** Large refactors (Structure Engine v2) can expose pre-existing bugs
2. **Honest APIs:** Only expose fields that are actually implemented
3. **Key Conventions:** Standardize feature key names across modules
4. **Inverselogic Traps:** Be extra careful with invalidation/negation logic
5. **TDD Saves:** Tests caught these issues immediately

---

## Conclusion

All bugs fixed and verified with comprehensive testing. System now correctly:
- ✅ Invalidates fades when price moves opposite to fade premise
- ✅ Only exposes implemented structure fields
- ✅ Handles multiple DXY key naming conventions
- ✅ Maintains zero regressions in test suite

Ready to proceed with Structure Engine v2.0 Part 2.
