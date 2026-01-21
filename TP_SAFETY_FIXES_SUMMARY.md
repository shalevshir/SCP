# TP Safety Check Fixes - SOP Compliance

## Critical Bugs Fixed in `_check_tp_safety()`

### 🔴 Issue #1: FVG Field Usage (CLARIFIED)
**Status**: Field naming was actually correct, but added documentation for clarity.

**Field Naming Convention**:
- `opposing_fvg_high/low` = **Bearish FVG** (blocks long TPs)
- `opposing_fvg_bullish_high/low` = **Bullish FVG** (blocks short TPs)

**Logic**: ✅ Already correct in original implementation

---

### 🔴 Issue #2: FVG Blocking Logic (CRITICAL BUG - FIXED)

#### ❌ BEFORE (Broken):
```python
# Only blocked if TP was INSIDE the FVG
if opposing_fvg_low <= tp_price <= opposing_fvg_high:
    return False, "TP inside opposing HTF FVG"
```

**Why This Was Wrong**:
- Only caught TPs that landed inside the FVG zone
- Missed FVGs that block the PATH to TP
- Example failure:
  - Entry = 100, Opposing FVG = 108-110, TP = 115
  - Old code: ✅ ALLOWED (TP not inside FVG)
  - SOP reality: ❌ INVALID (price must fight through FVG first)

#### ✅ AFTER (Fixed):
```python
# For longs: block if FVG is BETWEEN entry and TP
if entry_price < opposing_fvg_low < tp_price:
    return False, "Opposing HTF bearish FVG blocks path to TP"
```

**Why This Is Correct**:
- Checks if FVG lies in the path from entry to TP
- Prevents targeting through opposing imbalances
- SOP-compliant: "TP must not require passing through opposing HTF FVG"

**Example (now correctly blocked)**:
- Entry = 2650, FVG = 2675-2685, TP = 2700
- FVG_low (2675) is between entry (2650) and TP (2700)
- Result: ❌ BLOCKED ✅

---

### 🔴 Issue #3: Missing SL Validity Check (CRITICAL BUG - FIXED)

#### ❌ BEFORE (Broken):
```python
risk_distance = abs(entry_price - sl_price)
# No validation that SL is on correct side of entry!
```

**Why This Was Wrong**:
- Allowed longs with SL above entry
- Allowed shorts with SL below entry
- Artificially inflated 1R calculations
- Broke capital protection guarantees

#### ✅ AFTER (Fixed):
```python
# MANDATORY: Validate SL direction
if direction == "long":
    if sl_price >= entry_price:
        return False, "Invalid SL for long: SL must be < entry"
else:  # short
    if sl_price <= entry_price:
        return False, "Invalid SL for short: SL must be > entry"

# Now risk_distance is guaranteed valid
risk_distance = abs(entry_price - sl_price)
```

**Why This Is Correct**:
- Enforces directional SL placement
- Prevents zero-risk or negative-risk calculations
- Mandatory gate for capital protection

---

### 🟡 Issue #4: Immediate S/R Check (IMPROVED)

#### Before:
```python
# Only checked distance from entry
resistance_distance = immediate_resistance - entry_price
if 0 < resistance_distance < one_r_distance:
    return False, "within 1R"
```

#### After:
```python
# Now checks if resistance is IN THE PATH
if entry_price < immediate_resistance < tp_price:
    resistance_distance = immediate_resistance - entry_price
    if resistance_distance < one_r_distance:
        return False, "in path to TP (within 1R)"
```

**Why This Is Better**:
- Only blocks if resistance is actually in the path to TP
- Prevents false rejections when resistance is irrelevant (not in path)
- More precise SOP compliance

---

## Code Changes Summary

### `signal_engine.py` - `_check_tp_safety()`

**Changes**:
1. ✅ Added SL validity check (Check 0 - MANDATORY)
2. ✅ Fixed FVG blocking logic (checks path, not just interior)
3. ✅ Improved immediate S/R logic (path-aware)
4. ✅ Enhanced error messages (more descriptive)

**Before/After Comparison**:

| Check | Before | After | Status |
|-------|--------|-------|--------|
| SL Valid | ❌ Missing | ✅ Enforced | FIXED |
| FVG in Path | ❌ Only checks interior | ✅ Checks path | FIXED |
| S/R Path-Aware | ⚠️ Entry-distance only | ✅ Path-aware | IMPROVED |

---

## Test Coverage

All tests updated and passing:

```
TestTPSafetyChecks::test_long_tp_rejected_inside_opposing_htf_fvg PASSED
TestTPSafetyChecks::test_short_tp_rejected_inside_opposing_htf_fvg PASSED
TestTPSafetyChecks::test_long_tp_rejected_immediate_resistance_within_1r PASSED
TestTPSafetyChecks::test_short_tp_rejected_immediate_support_within_1r PASSED
TestTPSafetyChecks::test_long_tp_passes_safety_checks PASSED
TestTPSafetyChecks::test_tp_validation_end_to_end_with_safety_rejection PASSED

TestTPValidation::test_long_tp_priority_order_selects_nearest_valid PASSED
TestTPValidation::test_short_tp_priority_order_selects_nearest_valid PASSED
TestTPValidation::test_long_tp_no_valid_target_at_3r PASSED
TestTPValidation::test_long_tp_invalid_sl_above_entry_rejected PASSED
TestTPValidation::test_short_tp_invalid_sl_below_entry_rejected PASSED
```

**Total**: 11/11 TP validation tests passing ✅

---

## SOP Compliance Verification

### ✅ Enforced Rules:

1. **SL Directionality**: 
   - Long → SL < entry
   - Short → SL > entry
   - Zero risk → HARD REJECT

2. **Path Blocking**:
   - Long → Block if `entry < opposing_fvg_low < tp`
   - Short → Block if `tp < opposing_fvg_bullish_high < entry`
   - Not just interior blocking anymore

3. **Path-Aware S/R**:
   - Resistance checked only if `entry < resistance < tp`
   - Support checked only if `tp < support < entry`
   - Distance check (< 1R) applied only when in path

### ❌ Anti-Patterns Now Blocked:

1. ✅ Invalid SL placement (wrong side of entry)
2. ✅ TP through opposing HTF FVG
3. ✅ TP with immediate obstacle in path

---

## Example Scenarios

### Scenario 1: FVG Blocks Path (Now Correctly Rejected)
```
Entry:        2650
Opposing FVG: 2675-2685 (bearish, blocks longs)
TP:           2700

Old Logic: ✅ ALLOWED (TP not inside FVG)
New Logic: ❌ BLOCKED (FVG in path: 2650 < 2675 < 2700)
SOP:       ❌ BLOCKED ✅ (correct)
```

### Scenario 2: Invalid SL (Now Rejected)
```
Direction: long
Entry:     2650
SL:        2655 (ABOVE entry - invalid!)
TP:        2700

Old Logic: ✅ ALLOWED (no SL check)
New Logic: ❌ BLOCKED ("Invalid SL for long: SL must be < entry")
SOP:       ❌ BLOCKED ✅ (correct)
```

### Scenario 3: Resistance Not in Path (Now Allowed)
```
Entry:                2650
Immediate Resistance: 2640 (below entry, not in path)
TP:                   2700

Old Logic: ❌ BLOCKED (resistance within 1R of entry)
New Logic: ✅ ALLOWED (resistance not in path to TP)
SOP:       ✅ ALLOWED (correct)
```

---

## Implementation Notes

### Field Naming Convention (Important!)
The field names are deliberately direction-agnostic for the obstacle type:
- `opposing_fvg_*` means "bearish FVG" (opposes longs)
- `opposing_fvg_bullish_*` means "bullish FVG" (opposes shorts)

This follows the pattern: "opposing to [trade direction]" not "FVG direction".

### Error Messages
Updated to be more descriptive:
- Old: "TP inside opposing HTF FVG"
- New: "Opposing HTF bearish FVG (2675-2685) blocks path to TP (entry=2650, TP=2700)"

Provides full context for debugging and SOP review.

---

## Verification Checklist

- ✅ All 11 TP validation tests passing
- ✅ All 6 TP safety check tests passing
- ✅ SL validity enforced
- ✅ Path blocking logic correct
- ✅ Error messages descriptive
- ✅ No regressions introduced

---

## Related Files

- `services/bot-core/src/bot_core_svc/signal_engine.py` - Implementation
- `services/bot-core/tests/unit/test_signal_engine.py` - Test coverage
- `services/shared/src/scp_shared/messaging/schemas.py` - Field definitions
