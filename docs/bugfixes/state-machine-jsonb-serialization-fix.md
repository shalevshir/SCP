# Bug Fix: State Machine JSONB Serialization Issue

**Date:** December 24, 2025  
**Component:** Execution Service - StateMachineManager  
**Severity:** Critical (Data Corruption & Recovery Failure)

## Problem

The `_save_state_machine` method was pre-serializing `confirmations` and `transition_history` using `json.dumps()` before passing them to `db_pool.execute()`. However, asyncpg expects Python objects (lists/dicts) for JSONB columns, not JSON strings. Without explicit `::jsonb` casting in the SQL query, PostgreSQL stored the data as string literals rather than proper JSONB structures.

### Root Cause

**asyncpg Behavior:** When inserting into JSONB columns, asyncpg expects Python objects (lists, dicts) and handles the serialization automatically. Passing pre-serialized JSON strings causes PostgreSQL to store them as string literals unless you explicitly cast with `::jsonb` in the SQL.

**Code Issue (BEFORE):**
```python
# _save_state_machine() - Lines 269-282
# Convert confirmations to JSON string for JSONB column
confirmations_json = json.dumps(list(sm.confirmations) if sm.confirmations else [])

# Convert transition history to JSON string for JSONB column
transition_history_json = json.dumps([
    {
        "from_state": t.from_state.value,
        "to_state": t.to_state.value,
        "bar_idx": t.bar_idx,
        "reason": t.reason,
        "timestamp": t.timestamp.isoformat(),
    }
    for t in sm.transition_history
])

await self._db_pool.execute(
    query,
    signal_id,
    sm.current_state.value,
    sm.detection_bar_idx,
    db_direction,
    confirmations_json,  # JSON string, not list - WRONG!
    sm.execution_count,
    transition_history_json,  # JSON string, not list - WRONG!
)
```

### Impact on restore_from_db()

When restoring state machines, the code does:

```python
# restore_from_db() - Line 223
if row["confirmations"]:
    sm.confirmations = set(row["confirmations"])
```

**With the bug:**
- `row["confirmations"]` is stored as: `'["vwap_hold", "auto_confirm"]'` (string)
- `set(row["confirmations"])` iterates over **characters**: `{'[', '"', 'v', 'w', 'a', 'p', '_', 'h', 'o', 'l', 'd', ...}`
- Result: Corrupted confirmations set with individual characters instead of confirmation values

**Expected behavior:**
- `row["confirmations"]` should be: `['vwap_hold', 'auto_confirm']` (Python list)
- `set(row["confirmations"])` produces: `{'vwap_hold', 'auto_confirm'}` (correct)
- Result: Proper set of confirmation strings

## Impact

- **Severity:** Critical - Complete corruption of state machine data
- **Symptoms:**
  - State machines restore with corrupted confirmations (characters instead of strings)
  - `sm.confirmations` contains: `{'[', '"', 'v', 'w', 'a', 'p', ...}` instead of `{'vwap_hold', 'auto_confirm'}`
  - Confirmation checking logic breaks completely
  - Signals may incorrectly appear as confirmed or unconfirmed
  - Trade execution logic fails due to invalid state
- **Data Corruption:** All saved state machines have corrupted JSONB fields
- **Silent Failure:** No errors raised, just wrong data

## Example Scenario

```python
# Save state machine (Bar 100):
sm.confirmations = {"vwap_hold", "auto_confirm"}
await manager._save_state_machine(signal_id, sm)

# With BUG:
# Database stores: '["vwap_hold", "auto_confirm"]' (string literal)

# Service restart...

# Restore from DB (Bar 150):
await manager.restore_from_db()
sm = manager.get_state_machine(signal_id)

# With BUG:
sm.confirmations = {'[', '"', 'v', 'w', 'a', 'p', '_', 'h', 'o', 'l', 'd', ',', ...}
# Individual characters instead of confirmation strings!

# Confirmation check fails:
if "vwap_hold" in sm.confirmations:  # ❌ False! Only single chars present
    ...
```

## Solution

Remove `json.dumps()` and pass Python objects directly. asyncpg handles JSONB serialization automatically.

```python
# AFTER (Fixed) - Lines 251-280
# Convert confirmations to Python list for JSONB column
# asyncpg handles JSONB serialization automatically from Python objects
confirmations_list = list(sm.confirmations) if sm.confirmations else []

# Convert transition history to Python list of dicts for JSONB column
transition_history_list = [
    {
        "from_state": t.from_state.value,
        "to_state": t.to_state.value,
        "bar_idx": t.bar_idx,
        "reason": t.reason,
        "timestamp": t.timestamp.isoformat(),
    }
    for t in sm.transition_history
]

await self._db_pool.execute(
    query,
    signal_id,
    sm.current_state.value,
    sm.detection_bar_idx,
    db_direction,
    confirmations_list,  # Python list - asyncpg handles JSONB conversion ✓
    sm.execution_count,
    transition_history_list,  # Python list - asyncpg handles JSONB conversion ✓
)
```

This ensures:
- **Save**: asyncpg receives Python objects and properly serializes to JSONB
- **Restore**: asyncpg returns Python objects (lists/dicts), not strings
- **set() conversion**: Works correctly on list items, not string characters

## Test Coverage

Created comprehensive test suite (`test_state_machine_jsonb_fix.py`) with 6 tests:

### Test 1: Confirmations Saved as Python List
```python
async def test_confirmations_saved_as_python_list_not_json_string():
    """Verify asyncpg receives Python list, not JSON string."""
    # Asserts: isinstance(confirmations_arg, list)
    # Asserts: confirmations_arg == ["vwap_hold", "auto_confirm"]
```

### Test 2: Transition History Saved as Python List
```python
async def test_transition_history_saved_as_python_list_not_json_string():
    """Verify asyncpg receives Python list of dicts, not JSON string."""
    # Asserts: isinstance(transition_history_arg, list)
    # Asserts: all(isinstance(t, dict) for t in transition_history_arg)
```

### Test 3: Confirmations Restore Correctly
```python
async def test_confirmations_restore_as_set_not_character_iteration():
    """Verify set(row["confirmations"]) produces set of strings, not characters."""
    # Asserts: sm.confirmations == {"vwap_hold", "auto_confirm"}
    # Asserts: All confirmations are multi-character strings, not single chars
```

### Test 4: Empty Confirmations Handled
```python
async def test_empty_confirmations_handled_correctly():
    """Verify empty confirmations saved as empty list, not empty string."""
    # Asserts: confirmations_arg == []
    # Asserts: isinstance(confirmations_arg, list)
```

### Test 5: Full Roundtrip
```python
async def test_full_roundtrip_save_and_restore():
    """Test complete save → restore → verify cycle."""
    # Saves with Python objects
    # Restores and verifies data integrity
```

### Test 6: Bug Scenario Demonstration
```python
async def test_bug_scenario_json_string_breaks_set_conversion():
    """Demonstrate how JSON string would break set() conversion."""
    # Shows: set('["vwap_hold"]') = {'[', '"', 'v', 'w', 'a', ...}
    # Expected: set(['vwap_hold']) = {'vwap_hold'}
```

## Additional Fixes

### Test Data Correction

While fixing this issue, also corrected test data in `test_state_machine_uuid_key_mismatch.py`:

**Problem:** Tests were using `"reclaim_direction": "above"` (internal format) in mock DB data, but the database stores `"long"/"short"` format.

**Fix:** Changed all mock data to use correct DB format:
```python
# BEFORE (Wrong):
"reclaim_direction": "above"

# AFTER (Correct):
"reclaim_direction": "long"  # DB format: "long"/"short", not "above"/"below"
```

This aligns with the mapping logic in `restore_from_db()`:
```python
# Map DB format ("long"/"short") back to internal format ("above"/"below")
db_direction = row["reclaim_direction"]
sm.reclaim_direction = "above" if db_direction == "long" else "below"
```

## Verification

All tests pass:
```bash
# New JSONB fix tests
$ poetry run pytest services/execution/tests/unit/test_state_machine_jsonb_fix.py -v
# ✓ 6 passed

# Existing UUID key mismatch tests (with corrected mock data)
$ poetry run pytest services/execution/tests/unit/test_state_machine_uuid_key_mismatch.py -v
# ✓ 4 passed

# All state machine tests
$ poetry run pytest services/execution/tests/unit/ -k "state_machine" -v
# ✓ 17 passed
```

## Prevention

1. **Type Awareness:** Always check what asyncpg expects for PostgreSQL types:
   - JSONB → Python objects (list, dict)
   - UUID → uuid.UUID or string (converts automatically)
   - TIMESTAMP → datetime
   - Don't pre-serialize unless using explicit casting

2. **Test Restore Path:** Always test the roundtrip (save → restore → verify):
   ```python
   # Save
   await manager._save_state_machine(signal_id, sm)
   
   # Restore
   manager2 = StateMachineManager(db_pool)
   await manager2.restore_from_db()
   
   # Verify
   restored_sm = manager2.get_state_machine(signal_id)
   assert restored_sm.confirmations == original_sm.confirmations
   ```

3. **Mock DB Data Accuracy:** Use correct DB format in test mocks:
   - Match actual database constraints
   - Check comments in production code for format mappings
   - Verify DB schema before writing tests

## Related Issues

- **UUID Key Mismatch Fix:** Separate issue where UUID objects were used as dictionary keys instead of strings (fixed previously)
- **State Machine Cleanup:** Memory leak prevention for terminal state machines

## Files Modified

1. **Production Code:**
   - `services/execution/src/execution_svc/state_machine_manager.py`
     - Lines 251-280: Removed `json.dumps()`, pass Python objects

2. **Tests:**
   - `services/execution/tests/unit/test_state_machine_jsonb_fix.py` (new)
     - 6 comprehensive tests for JSONB serialization
   - `services/execution/tests/unit/test_state_machine_uuid_key_mismatch.py`
     - Fixed mock data: `"above"` → `"long"` (4 occurrences)

3. **Documentation:**
   - `docs/bugfixes/state-machine-jsonb-serialization-fix.md` (this file)

## References

- asyncpg Documentation: [Type Conversions](https://magicstack.github.io/asyncpg/current/usage.html#type-conversion)
- PostgreSQL JSONB: [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html)
- State Machine Manager: `services/execution/src/execution_svc/state_machine_manager.py`

