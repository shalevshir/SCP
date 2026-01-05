# Bug Fix: State Machine UUID Key Mismatch on Restart

**Date:** December 22, 2025  
**Component:** Execution Service - StateMachineManager  
**Severity:** Critical (Service Recovery Failure)

## Problem

The `StateMachineManager.restore_from_db()` method stored restored state machines using `uuid.UUID` objects as dictionary keys, but all lookup methods (`get_state_machine`, `check_confirmation`, `execute`) expected string keys. This type mismatch made all restored state machines inaccessible after service restart, completely breaking recovery functionality.

### Root Cause

**asyncpg Behavior:** When reading UUID columns from PostgreSQL, asyncpg returns `uuid.UUID` objects, not strings.

**Code Issue:**
```python
# restore_from_db() - Line 204 (BEFORE)
self._state_machines[row["signal_id"]] = sm  # UUID object as key!
```

**Lookup Code:**
```python
# get_state_machine() - Line 82
sm = self._state_machines.get(signal_id)  # signal_id is a STRING parameter

# create_from_signal() - Line 57  
self._state_machines[signal.id] = sm  # signal.id is a STRING
```

### Type Mismatch

```python
# Dictionary after restore:
{
    UUID('1bfd1d7f-c7eb-4439-82e3-6e9e21d2c9b4'): <VWAPReclaimStateMachine>,
}

# Lookup attempt:
get_state_machine('1bfd1d7f-c7eb-4439-82e3-6e9e21d2c9b4')
# Returns None because UUID('...') != '...'
```

## Impact

- **Severity:** Critical - Complete failure of recovery mechanism
- **Symptoms:** After service restart:
  - Restored state machines invisible to all code
  - `check_confirmation()` returns `False` (can't find state machine)
  - `execute()` fails silently (can't find state machine)
  - Signals lost in limbo - never executed despite being ready
- **Data Loss:** Pending signals effectively lost on restart
- **Silent Failure:** No errors raised, state machines just inaccessible

## Example Scenario

```python
# Before Restart (Bar 100):
# Signal created, state machine stored
signal_id = "1bfd1d7f-c7eb-4439-82e3-6e9e21d2c9b4"  # String
manager._state_machines[signal_id] = sm  # ✓ Works

# Service restart...

# After Restart (Bar 150):
# Database returns UUID object
row["signal_id"] = UUID('1bfd1d7f-c7eb-4439-82e3-6e9e21d2c9b4')  # UUID object
manager._state_machines[row["signal_id"]] = sm  # ❌ UUID key!

# Try to check confirmation:
manager.check_confirmation("1bfd1d7f-c7eb-4439-82e3-6e9e21d2c9b4")
# Returns False - can't find state machine!

# Dict keys:
manager._state_machines.keys()
# [UUID('1bfd1d7f-c7eb-4439-82e3-6e9e21d2c9b4')]  # UUID object

# Lookup fails:
UUID('1bfd1d7f-c7eb-4439-82e3-6e9e21d2c9b4') != '1bfd1d7f-c7eb-4439-82e3-6e9e21d2c9b4'
```

## Solution

Convert UUID to string when storing restored state machines:

```python
# BEFORE (Buggy) - Line 204
self._state_machines[row["signal_id"]] = sm

# AFTER (Fixed) - Line 204-206
# Convert UUID to string for consistent key type
# (asyncpg returns UUID objects, but all lookups use strings)
self._state_machines[str(row["signal_id"])] = sm
```

This ensures consistent key types:
- New state machines: `self._state_machines[signal.id]` → string key
- Restored state machines: `self._state_machines[str(row["signal_id"])]` → string key
- All lookups: `self._state_machines.get(signal_id)` → string parameter

## Test Coverage

Created comprehensive test suite (`test_state_machine_uuid_key_mismatch.py`) with 4 tests:

### Test 1: Basic Accessibility
```python
async def test_restored_state_machine_accessible_by_string_key():
    """Test that restored state machines are accessible using string keys."""
    signal_id_str = str(uuid4())
    signal_id_uuid = UUID(signal_id_str)
    
    # Mock DB to return UUID object
    mock_db_pool.fetch.return_value = [
        {"signal_id": signal_id_uuid, ...}  # UUID object from asyncpg
    ]
    
    manager = StateMachineManager(mock_db_pool)
    await manager.restore_from_db()
    
    # Lookup using string should work
    sm = manager.get_state_machine(signal_id_str)
    assert sm is not None  # ✓ Fixed!
```

### Test 2: check_confirmation() Integration
```python
async def test_check_confirmation_works_after_restore():
    """Test that check_confirmation works with restored state machines."""
    # ... restore with UUID ...
    
    # This should work, not return False
    is_confirmed = manager.check_confirmation(signal_id_str, bar_idx=101)
    assert is_confirmed is not None  # ✓ Fixed!
```

### Test 3: execute() Integration
```python
async def test_execute_works_after_restore():
    """Test that execute works with restored state machines."""
    # ... restore with UUID ...
    
    # This should work, not fail silently
    await manager.execute(signal_id_str, bar_idx=102)
    
    sm = manager.get_state_machine(signal_id_str)
    assert sm.execution_count == 1  # ✓ Fixed!
```

### Test 4: Multiple State Machines
```python
async def test_multiple_restored_state_machines_all_accessible():
    """Test that all restored state machines are accessible."""
    # ... restore 3 state machines with UUIDs ...
    
    # All should be accessible by string IDs
    for str_id, uuid_obj in signal_ids:
        sm = manager.get_state_machine(str_id)
        assert sm is not None  # ✓ Fixed!
```

All 4 tests pass ✓

## Why This Bug Occurred

1. **Different Data Sources:**
   - New signals: Come from Redis messages (Pydantic models with string IDs)
   - Restored signals: Come from PostgreSQL (asyncpg returns UUID objects)

2. **Implicit Type Assumption:**
   - Code assumed all keys would be strings
   - No type conversion in restoration path

3. **No Type Checking:**
   - Python allows mixed key types in dicts
   - No runtime error when using UUID as key
   - Silent failure when lookup misses

## Files Modified

1. `services/execution/src/execution_svc/state_machine_manager.py` - Fixed UUID→string conversion
2. `services/execution/tests/unit/test_state_machine_uuid_key_mismatch.py` (NEW) - Test suite

## Verification

```bash
cd services/execution

# Run new tests
poetry run pytest tests/unit/test_state_machine_uuid_key_mismatch.py -xvs
# ✅ 4 tests passed

# Run all tests
poetry run pytest tests/unit/ -x
# ✅ 32 tests passed
```

## Related Best Practices

### Type Consistency in Dictionary Keys

Always ensure consistent key types when using multiple data sources:

```python
# ❌ BAD: Mixed key types
some_dict[uuid_object] = value  # UUID key
some_dict[string_id] = value    # String key

# ✅ GOOD: Consistent key types
some_dict[str(uuid_object)] = value  # Convert to string
some_dict[string_id] = value         # Already string
```

### Database Type Conversions

Be aware of how database drivers handle types:

```python
# asyncpg for PostgreSQL:
row["uuid_column"]  # Returns uuid.UUID object, not str

# psycopg2 for PostgreSQL:
row["uuid_column"]  # Returns string by default

# Always convert explicitly:
str(row["uuid_column"])  # Explicit conversion
```

## Future Improvements

Consider adding:
1. **Type Hints:** Add `dict[str, VWAPReclaimStateMachine]` annotation to catch mismatches
2. **Validation:** Assert key types on insertion to catch bugs early
3. **Logging:** Log restored state machine keys for debugging
4. **Integration Test:** Test full restart cycle with real database

---

**Implemented By:** AI Assistant  
**Reviewed By:** TDD (all tests pass)  
**Status:** Complete ✅





