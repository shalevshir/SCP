# HTF Bias Consistency Fix

**Date**: November 24, 2025  
**Status**: ✅ Fixed  
**Priority**: High

## Issue

The `vwap_trend_confirmed` and `dxy_alignment` flags in `HTFBias` were calculated using the neutralized `bias` variable (after DXY chop or conflict detection), while `fvg_alignment_score` correctly used `original_bias`. This created inconsistent behavior where:

- When bias was neutralized to "neutral" due to DXY chop or conflicts, these flags would always be `False`
- Even when the underlying market structure showed clear directional alignment
- This caused incorrect signal scoring and validation

## Root Cause

In `rule_engine/htf/calculator.py`, the `compute_htf_bias()` function:

1. Computed base bias: `bias, direction, score = compute_htf_bias_multi_timeframe()`
2. Stored original: `original_bias = bias`
3. Neutralized bias when DXY chop or conflicts detected: `bias = "neutral"`
4. **Bug**: Used neutralized `bias` instead of `original_bias` for:
   - `vwap_trend_confirmed` (lines 415-418)
   - `dxy_alignment` (line 442)
5. **Correct**: Used `original_bias` for:
   - `fvg_alignment_score` (line 430)

## Solution

Changed the calculation logic to consistently use `original_bias` for all structure-based flags:

### Before (Incorrect)
```python
# Line 415-418: Used neutralized bias
if bias == "bullish" and vwap_distance_1h is not None and vwap_distance_1h > 0:
    vwap_trend_confirmed = True
elif bias == "bearish" and vwap_distance_1h is not None and vwap_distance_1h < 0:
    vwap_trend_confirmed = True

# Line 442: Used neutralized bias
if bias != "neutral":
    if (dxy_corr_1h < -0.6 and dxy_corr_15m < -0.6):
        dxy_alignment = True
```

### After (Correct)
```python
# Line 416-419: Use original_bias
if original_bias == "bullish" and vwap_distance_1h is not None and vwap_distance_1h > 0:
    vwap_trend_confirmed = True
elif original_bias == "bearish" and vwap_distance_1h is not None and vwap_distance_1h < 0:
    vwap_trend_confirmed = True

# Line 445: Use original_bias
if original_bias != "neutral":
    if (dxy_corr_1h < -0.6 and dxy_corr_15m < -0.6):
        dxy_alignment = True
```

## Impact

### Positive Changes
- **Consistency**: All structure-based flags now use the same bias reference (`original_bias`)
- **Accuracy**: Flags correctly reflect underlying market structure even when bias is neutralized
- **Scoring**: HTF score adjustments in `adjust_score_with_htf()` now work correctly
- **Validation**: Signal validation can properly use these flags for decision-making

### Example Scenario
**Before Fix**:
- Market: Strong bullish structure (HH, price > VWAP, DXY correlation -0.75)
- DXY: In chop mode
- Result: `bias="neutral"`, `vwap_trend_confirmed=False`, `dxy_alignment=False` ❌
- Problem: Loses valuable market structure information

**After Fix**:
- Market: Strong bullish structure (HH, price > VWAP, DXY correlation -0.75)
- DXY: In chop mode
- Result: `bias="neutral"`, `vwap_trend_confirmed=True`, `dxy_alignment=True` ✅
- Benefit: Preserves market structure information while signaling caution via neutral bias

## Testing

Added comprehensive tests in `tests/unit/rule_engine/htf/test_htf_calculator.py`:

1. **`test_vwap_and_dxy_alignment_use_original_bias_when_neutralized()`**
   - Tests DXY chop neutralization scenario
   - Verifies flags reflect original bullish structure

2. **`test_vwap_and_dxy_alignment_use_original_bias_on_conflict()`**
   - Tests structure conflict neutralization scenario
   - Verifies flags reflect original bearish structure

### Test Results
- ✅ All 17 HTF calculator tests pass
- ✅ All 356 rule_engine tests pass
- ✅ All 32 scoring/validation tests pass
- ✅ All 11 integration tests pass
- ✅ Total: 533 relevant tests pass

## Files Changed

1. **`rule_engine/htf/calculator.py`**
   - Line 416: Changed `bias` to `original_bias` in VWAP trend check
   - Line 418: Changed `bias` to `original_bias` in VWAP trend check
   - Line 445: Changed `bias` to `original_bias` in DXY alignment check
   - Added explanatory comments

2. **`tests/unit/rule_engine/htf/test_htf_calculator.py`**
   - Added `TestHTFCalculatorBiasConsistency` class
   - Added two comprehensive tests for both neutralization scenarios

## Backwards Compatibility

✅ **Fully backwards compatible**
- No changes to HTFBias structure or API
- No changes to function signatures
- Only changes internal calculation logic
- All existing tests pass without modification

## Related Components

This fix improves consistency with:
- `rule_engine.htf.integration.adjust_score_with_htf()` - Uses these flags for scoring
- `rule_engine.htf.integration.validate_signal_with_htf()` - Uses these flags for validation
- `rule_engine.scoring.score_signal()` - Receives adjusted scores
- `rule_engine.validation.validate_signal()` - Validates with HTF context

## Conclusion

This fix ensures that HTFBias fields consistently reflect the underlying market structure while still allowing the bias to be neutralized for trade execution decisions. This separation of concerns is critical for:
- Accurate signal scoring
- Proper risk management
- Transparent decision-making
- Auditability of trade decisions








