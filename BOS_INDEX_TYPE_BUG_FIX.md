# BOS Index Type Bug Fix

## Summary

Fixed a type mismatch bug where DataFrame index labels (Timestamps) were being passed where integer positions were expected, causing `TypeError` when performing arithmetic operations or integer-based slicing.

## Bug Description

### Issue 1: BOS Index in `calculator.py`

**Location:** `services/shared/src/scp_shared/rule_engine/htf/calculator.py:931`

**Problem:**
```python
bos_index = bos_detected_bars.index[-1]  # Returns Timestamp if DatetimeIndex
```

This returns a DataFrame index label (potentially a `Timestamp` if the DataFrame has a `DatetimeIndex`), but `compute_htf_range()` expects an integer position as indicated by its type hint `bos_index: int | None`.

**Error:**
```
Addition/subtraction of integers and integer-arrays with Timestamp is no longer supported.
```

**Root Cause:**
- `bos_detected_bars.index[-1]` returns the index **label** (e.g., `pd.Timestamp("2024-01-01 15:00:00")`)
- `compute_htf_range()` expects an integer **position** (e.g., `5`)
- When passed to functions using `df.iloc[start_idx:]`, the Timestamp causes errors

### Issue 2: Range Index Arithmetic in `targets.py`

**Location:** `services/shared/src/scp_shared/rule_engine/htf/structure/targets.py:101-102, 110, 120`

**Problem:**
```python
range_high_idx = scoped_df["high"].idxmax()  # Returns index label (Timestamp)
range_low_idx = scoped_df["low"].idxmin()    # Returns index label (Timestamp)

# Later, arithmetic on Timestamp fails:
bars_after_high = scoped_df.loc[range_high_idx + 1:]  # ERROR: can't add 1 to Timestamp
```

**Root Cause:**
- `.idxmax()` and `.idxmin()` return index **labels** (Timestamps if DatetimeIndex)
- Attempting `range_high_idx + 1` fails with Timestamps
- The code then uses `.loc[]` which expects labels, but arithmetic was attempted first

## Fix

### Fix 1: Convert Index Label to Integer Position (calculator.py)

**Before:**
```python
bos_index = bos_detected_bars.index[-1]
```

**After:**
```python
# Get the integer position of the last BOS event
# Convert index label (potentially Timestamp) to integer position
bos_index_label = bos_detected_bars.index[-1]
bos_index = df_1h.index.get_loc(bos_index_label)
```

**Explanation:**
- Extract the index label first (`bos_index_label`)
- Use `df_1h.index.get_loc()` to convert the label to an integer position
- Now `bos_index` is an integer (e.g., `5`) suitable for `df.iloc[]` operations

### Fix 2: Use argmax/argmin for Integer Positions (targets.py)

**Before:**
```python
range_high_idx = scoped_df["high"].idxmax()  # Returns label
range_low_idx = scoped_df["low"].idxmin()    # Returns label

if range_high_idx < scoped_df.index[-1]:
    bars_after_high = scoped_df.loc[range_high_idx + 1:]  # ERROR
```

**After:**
```python
# Use argmax/argmin for integer positions, not idxmax/idxmin (which return labels)
range_high_pos = scoped_df["high"].argmax()  # Returns integer position
range_low_pos = scoped_df["low"].argmin()    # Returns integer position

if range_high_pos < len(scoped_df) - 1:
    bars_after_high = scoped_df.iloc[range_high_pos + 1:]  # OK
```

**Explanation:**
- Replace `.idxmax()` with `.argmax()` to get integer positions
- Replace `.idxmin()` with `.argmin()` to get integer positions
- Use `.iloc[]` for integer-based slicing (not `.loc[]`)
- Arithmetic on integer positions works correctly

## Testing

### New Test File

Created `services/shared/tests/unit/rule_engine/htf/test_calculator_bos_index_type_fix.py` with 3 tests:

1. **`test_bos_index_with_datetime_index_calls_compute_htf_range`** - Reproduces the bug with DatetimeIndex
2. **`test_bos_index_none_when_no_bos_detected`** - Verifies existing behavior when no BOS exists
3. **`test_bos_index_with_integer_index_still_works`** - Ensures backward compatibility with integer indices

### Test Results

All tests pass:
- ✅ New test file: 3/3 tests pass
- ✅ Existing targets tests: 25/25 tests pass
- ✅ Existing calculator tests: 18/18 tests pass
- ✅ All HTF tests: 418/418 tests pass

## Key Differences: Index Labels vs. Integer Positions

| Operation | Returns Index Label | Returns Integer Position |
|-----------|---------------------|--------------------------|
| `.index[-1]` | ✅ Timestamp/Label | ❌ |
| `.idxmax()` | ✅ Timestamp/Label | ❌ |
| `.idxmin()` | ✅ Timestamp/Label | ❌ |
| `.argmax()` | ❌ | ✅ Integer |
| `.argmin()` | ❌ | ✅ Integer |
| `.index.get_loc(label)` | Takes label | ✅ Returns integer |

| Usage | Works with Labels | Works with Positions |
|-------|-------------------|---------------------|
| `df.loc[idx]` | ✅ | ❌ |
| `df.iloc[idx]` | ❌ | ✅ |
| `idx + 1` (arithmetic) | ❌ | ✅ |
| `idx < len(df)` (comparison) | ❌ | ✅ |

## Impact

This bug would cause failures in production when:
1. `df_1h` has a DatetimeIndex (real-world scenario)
2. BOS is detected and HTF targets are computed
3. The Timestamp would be passed where an integer is expected

The fix ensures:
- ✅ Works correctly with DatetimeIndex (production scenario)
- ✅ Backward compatible with integer indices (existing tests)
- ✅ Type-safe: integer positions are used consistently
- ✅ No runtime errors when computing HTF structural targets

## Related Files

**Modified:**
- `services/shared/src/scp_shared/rule_engine/htf/calculator.py` (lines 920-933)
- `services/shared/src/scp_shared/rule_engine/htf/structure/targets.py` (lines 96-127)

**New:**
- `services/shared/tests/unit/rule_engine/htf/test_calculator_bos_index_type_fix.py`

## Prevention

To prevent similar issues in the future:

1. **Use `.argmax()`/`.argmin()`** when you need integer positions for:
   - Arithmetic operations (`idx + 1`, `idx - 1`)
   - Integer comparisons (`idx < len(df)`)
   - `.iloc[]` slicing

2. **Use `.idxmax()`/`.idxmin()`** when you need index labels for:
   - Direct lookups with `.loc[]`
   - No arithmetic or slicing needed

3. **Type hints** should clearly indicate:
   - `bos_index: int | None` for integer positions
   - `bos_timestamp: pd.Timestamp | None` for index labels

4. **Testing** should include scenarios with:
   - DatetimeIndex (real-world production scenario)
   - Integer index (backward compatibility)
