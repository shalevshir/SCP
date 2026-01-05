# DXY FADE Message Threshold Fix

**Date**: 2024-12-29  
**Issue**: Inconsistency between actual DXY threshold and error message for VWAP_FADE invalidation  
**Severity**: Medium (misleading error messages make debugging difficult)

## Problem

For **VWAP_FADE long trades**, the DXY flip invalidation logic had a mismatch between:
- **Code threshold**: `-0.3` (invalidates when `dxy_corr > -0.3`)
- **Error message**: `"expected < -0.6"`

This created confusion during debugging, as the error message suggested a different threshold than what was actually being enforced.

### Example Error Message (BEFORE fix)
```
DXY flip: correlation -0.290 indicates DXY structure breaking against long trade (expected < -0.6)
```

The trade was invalidated at `-0.29` (which is `> -0.3`), but the message said it expected `< -0.6`.

## Root Cause

The issue existed in **both** implementations:
1. **Legacy backtester**: `backtester/invalidations.py:657-661`
2. **Microservices**: `services/shared/src/scp_shared/execution/invalidation.py:582-586`

The code correctly checked:
```python
if dxy_corr > -0.3:  # Invalidate if correlation becomes too weak/positive
```

But the message incorrectly stated:
```python
f"breaking against long trade (expected < -0.6)"
```

This was likely a copy-paste error where the `-0.6` threshold from the short side was incorrectly used in the long side's message.

## Logic Verification

### VWAP_FADE Long Trade DXY Logic
- **Entry expectation**: Negative DXY correlation (DXY down = GC up)
- **Invalidation**: When correlation becomes too weak (approaching zero or positive)
- **Threshold**: `-0.3` is the boundary
  - `dxy_corr = -0.5` → Strong negative → Trade valid
  - `dxy_corr = -0.3` → At boundary → Trade valid (need `>` not `>=`)
  - `dxy_corr = -0.29` → Weak negative → Trade **INVALIDATED**
  - `dxy_corr = 0.0` → No correlation → Trade **INVALIDATED**
  - `dxy_corr = 0.3` → Positive → Trade **INVALIDATED**

### VWAP_FADE Short Trade DXY Logic
- **Entry expectation**: Positive or weakly negative DXY correlation
- **Invalidation**: When correlation becomes too negative (strong inverse)
- **Threshold**: `-0.6` is the boundary
  - `dxy_corr = 0.3` → Positive → Trade valid
  - `dxy_corr = -0.3` → Weak negative → Trade valid
  - `dxy_corr = -0.6` → At boundary → Trade valid (need `<` not `<=`)
  - `dxy_corr = -0.61` → Strong negative → Trade **INVALIDATED**

## Solution

Updated error messages to match actual thresholds:

### Microservices (`services/shared/src/scp_shared/execution/invalidation.py`)
```python
# BEFORE
f"breaking against long trade (expected < -0.6)"

# AFTER
f"breaking against long trade (expected < -0.3)"
```

### Legacy Backtester (`backtester/invalidations.py`)
```python
# BEFORE
f"breaking against long trade (expected < -0.6)"

# AFTER
f"breaking against long trade (expected < -0.3)"
```

## Example Error Message (AFTER fix)
```
DXY flip: correlation -0.290 indicates DXY structure breaking against long trade (expected < -0.3)
```

Now the message correctly states that correlation should be `< -0.3` to remain valid, which matches the code logic.

## Testing

### New Test Suite
Created comprehensive test suite: `services/shared/tests/unit/execution/test_dxy_fade_message_accuracy.py`

Tests verify:
1. **Message accuracy**: Error message references correct threshold
2. **Boundary conditions**: Exact threshold behavior (`-0.3` and `-0.6`)
3. **Threshold logic**: Correct invalidation at various correlation levels
4. **Symmetry**: Long and short logic are appropriately inverse

### Test Results
```bash
# Microservices (7 new tests)
cd services/shared && poetry run pytest tests/unit/execution/test_dxy_fade_message_accuracy.py
# Result: 7 passed

# Existing tests still pass
cd services/shared && poetry run pytest tests/unit/execution/test_invalidation.py
# Result: 35 passed

# Legacy backtester tests still pass
cd SCP && poetry run pytest tests/unit/test_invalidation_symmetry.py
# Result: 12 passed
```

## Impact

### Positive
- **Debugging clarity**: Error messages now accurately reflect what threshold was violated
- **Developer confidence**: No confusion about which threshold is actually enforced
- **Audit trail**: Trade invalidation logs now provide accurate information

### Risk
- **None**: Code logic unchanged, only message text updated
- **Backward compatibility**: Error message format unchanged, only threshold value corrected
- **No behavioral change**: Trades are invalidated at the exact same thresholds as before

## Files Modified

1. `services/shared/src/scp_shared/execution/invalidation.py` (line 585)
2. `backtester/invalidations.py` (line 660)
3. `services/shared/tests/unit/execution/test_dxy_fade_message_accuracy.py` (new file, 207 lines)
4. `docs/bugfixes/dxy-fade-message-threshold-fix.md` (this file)

## Related Documentation

- **VWAP_FADE setup**: Not documented (no entry requirement for DXY correlation)
- **Invalidation logic**: `docs/vwap-reclaim-execution-lifecycle.md`
- **DXY correlation**: Used for trade direction confirmation, not a hard requirement for VWAP_FADE entry

## Recommendations

1. **Document DXY thresholds**: Add clear comments explaining why `-0.3` and `-0.6` were chosen
2. **Configuration**: Consider making these thresholds configurable rather than hard-coded
3. **Monitoring**: Track DXY flip invalidations to verify thresholds are appropriate
4. **Review**: Periodically review if threshold values align with actual market behavior

## Verification Checklist

- [x] Identified issue in both microservices and legacy code
- [x] Analyzed threshold logic and confirmed correct values
- [x] Created comprehensive test suite (TDD)
- [x] Fixed microservices error message
- [x] Fixed legacy backtester error message
- [x] Verified all existing tests still pass
- [x] Verified new tests pass
- [x] Documented fix with examples
- [x] No lint errors introduced



