# Sprint 4: Re-entry Protection

## Overview

Sprint 4 implements re-entry protection for VWAP_RECLAIM setups to prevent overtrading on failed reclaim ideas. After a stopped-out VWAP_RECLAIM trade, the same reclaim cannot trigger infinite re-entries. Re-entry requires fresh structural evidence (new sweep + BOS).

## Implementation Summary

### 1. Execution Count Tracking (Task 1)

**File**: `feature_engine/vwap_reclaim_state_machine.py`

Added execution count tracking to the `VWAPReclaimStateMachine`:

- **Constant**: `MAX_EXECUTIONS_PER_RECLAIM = 1`
- **Instance Variable**: `execution_count: int = 0`
- **Increment on Execution**: `on_execution()` increments `execution_count`
- **Execution Gate**: `can_execute()` checks `execution_count < MAX_EXECUTIONS_PER_RECLAIM`
- **Helper Method**: `has_execution_capacity()` returns `True` if capacity available
- **Reset on New Reclaim**: `reset()` clears `execution_count` to 0
- **Logging**: Blocked re-entry attempts are logged with reason

### 2. Stop-Out Notification (Task 2)

**File**: `backtester/replay_loop.py`

Connected the replay loop to notify the state machine when a VWAP_RECLAIM trade stops out:

- **Location**: `_update_state()` method (after trade closes)
- **Condition**: `closed_trade.setup_type == "VWAP_RECLAIM"` AND `closed_trade.exit_reason == "sl"`
- **Action**: Call `state_machine.on_stop_out(bar_idx)` to transition to `INVALIDATED`
- **State Machine Access**: Through `self._processor._streaming.structure_tracker.vwap_reclaim_sm`
- **Bar Index**: Uses `closed_trade.duration_bars` for notification
- **Logging**: Stop-out notification is logged with bar index

### 3. Execution Gate (Task 3)

**File**: `backtester/replay_loop.py`

Added execution gate to prevent re-entry on the same reclaim:

- **Location**: `_process_candle()` method (before trade creation)
- **Check**: `state_machine.can_execute()` for VWAP_RECLAIM setups
- **Action if Blocked**: Override `execution.executed = False` with rejection reason
- **Rejection Reason**: `"Max executions reached for current reclaim"`
- **Logging**: Blocked re-entry is logged with execution count and state
- **State Machine Access**: Through `self._processor._streaming.structure_tracker.vwap_reclaim_sm`

### 4. Comprehensive Unit Tests (Task 4)

**Files**:
- `tests/unit/feature_engine/test_vwap_reclaim_state_machine.py` (extended)
- `tests/unit/backtester/test_reentry_protection.py` (new)

**Test Coverage**:
- `execution_count` starts at 0
- `on_execution()` increments `execution_count`
- `can_execute()` returns `False` when `execution_count >= MAX_EXECUTIONS_PER_RECLAIM`
- `execution_count` resets on `reset()`
- `on_stop_out()` keeps `execution_count` (prevents re-entry)
- `has_execution_capacity()` helper method
- New reclaim detection resets `execution_count` (fresh structural evidence)
- `MAX_EXECUTIONS_PER_RECLAIM` constant exists and equals 1
- Blocked re-entry scenario (full flow)
- SL exit reason distinguishable from invalidation
- VWAP invalidation distinguishable from SL

## Validation Criteria

✅ **Same reclaim cannot trigger infinite re-entries**: `execution_count` enforces max of 1 execution per reclaim
✅ **Re-entry requires fresh structural evidence**: `reset()` clears `execution_count` on new reclaim detection
✅ **Overtrading in same VWAP zone is prevented**: `can_execute()` blocks re-entry after stop-out
✅ **Logs show blocked re-entry attempts**: Logging includes reason, execution count, and state
✅ **Backtest shows max 1 entry per reclaim event**: Execution gate enforces limit before trade creation

## Architecture

```
┌─────────────────┐
│   ReplayLoop    │
│                 │
│  _process_      │
│   candle()      │
└────────┬────────┘
         │ 1. Execute signal
         │ 2. Check can_execute()
         ▼
┌─────────────────┐
│ StateMachine    │
│                 │
│ execution_count │
│ = 0             │
└────────┬────────┘
         │ 3. on_execution()
         │    (count++)
         ▼
┌─────────────────┐
│ execution_count │
│ = 1             │
└────────┬────────┘
         │ 4. Trade stops out
         │ 5. on_stop_out()
         ▼
┌─────────────────┐
│ State:          │
│ INVALIDATED     │
│ count: 1        │
└────────┬────────┘
         │ 6. Attempt re-entry
         │ 7. can_execute()?
         ▼
┌─────────────────┐
│ BLOCKED         │
│ (count >= max)  │
└─────────────────┘
```

## Key Behaviors

### Re-entry Protection Flow

1. **First Execution**: State machine allows execution (`execution_count = 0`)
2. **Execution**: `execution_count` increments to 1
3. **Stop-Out**: Trade closes with `exit_reason = "sl"`, state machine transitions to `INVALIDATED`
4. **Re-entry Attempt**: `can_execute()` returns `False` because `execution_count >= MAX_EXECUTIONS_PER_RECLAIM`
5. **Trade Creation Blocked**: Execution gate overrides `executed = False` with rejection reason

### Fresh Structural Evidence

1. **New Reclaim Detection**: `on_reclaim_detected()` calls `reset()` if state is not `NONE`
2. **State Reset**: `reset()` clears `execution_count` to 0 and transitions to `NONE`
3. **New Confirmation**: New confirmation transitions to `CONFIRMED` state
4. **Re-execution Allowed**: `can_execute()` returns `True` because `execution_count = 0`

## Example Logs

### Blocked Re-entry

```
WARNING: VWAP_RECLAIM execution blocked: Max executions reached for current reclaim (execution_count=1, state=invalidated)
```

### Stop-Out Notification

```
INFO: Trade TEST_001: VWAP_RECLAIM stop-out notified to state machine (bar_idx=9)
INFO: VWAP reclaim stop-out at bar 9 (state machine invalidated)
```

### Execution Count Tracking

```
INFO: VWAP reclaim executed at bar 103 (confirmations=['vwap_hold'], execution_count=1)
DEBUG: Execution blocked: execution_count (1) >= MAX_EXECUTIONS_PER_RECLAIM (1)
```

## Testing

All tests passing:
- 577 unit tests passed
- 4 tests skipped
- 0 failures

Sprint 4 specific tests:
- 7 execution count tracking tests
- 8 re-entry protection tests

## Dependencies

- **Sprint 3**: `on_stop_out()` method (SL vs. invalidation distinction)
- **Sprint 1**: State machine foundation
- **Sprint 2**: Confirmation aggregation

## Impact

- **Overtrading Prevention**: Limits losses from repeatedly executing on failed reclaim ideas
- **Risk Management**: Ensures disciplined entry selection (one shot per reclaim)
- **Backtest Realism**: Mirrors live bot behavior (no re-entry on same setup)
- **Capital Preservation**: Prevents cascade losses from overtrading same VWAP zone

