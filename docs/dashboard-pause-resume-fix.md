# Dashboard Pause/Resume Fix

## Problem

When the simulation auto-paused on an A+ signal, clicking the play button did not resume the simulation. The UI would appear to be paused but would not continue processing data when the play button was clicked.

## Root Cause

The issue occurred when the simulation thread stopped running (due to running out of data, an exception, or any other reason) while the simulation was in a paused state:

1. An A+ signal is detected and auto-pause is triggered (`is_paused=True`)
2. The simulation thread enters a pause loop in `_run_loop()`, sleeping and checking `is_paused` repeatedly
3. If the thread exits for any reason (e.g., `data_stream.has_more()` returns False), the thread stops but `is_paused` remains True
4. When the user clicks play, the callback checks `if self.engine.state.is_paused:` (True) and calls `resume()`
5. `resume()` only cleared the pause flags but did not restart the stopped thread
6. Result: Pause flags are cleared but nothing happens because the thread is dead

## Solution

Modified the `resume()` method in `dashboard/core/engine.py` to check if the simulation thread is still alive after clearing pause flags. If the thread has stopped, `resume()` now automatically restarts it by calling `start()`.

### Code Changes

**dashboard/core/engine.py**:

```python
def resume(self) -> None:
    """Resume simulation from pause.
    
    If the simulation thread has stopped (e.g., due to running out of data
    or an exception), this will restart it.
    """
    was_paused = self.state.is_paused
    thread_alive = self._thread and self._thread.is_alive()
    logger.info(
        f"Resume called | was_paused={was_paused} | "
        f"_running={self._running} | "
        f"thread_alive={thread_alive} | "
        f"is_simulation_running={self.state.is_simulation_running}"
    )
    
    # Clear pause flags
    self._update_state(is_paused=False, pause_reason=None, paused_at_signal=None)
    
    # If thread is not running, restart it
    if not self._running or not thread_alive:
        if was_paused:
            logger.info("Simulation was paused but thread is not running - restarting")
            self.start()
        else:
            logger.info("Resume called but simulation was not paused - starting anyway")
            self.start()
    elif was_paused:
        logger.info("Simulation resumed successfully")
```

### Enhanced Logging

Added detailed logging throughout the pause/resume flow to help diagnose issues:

1. **Dashboard callback (`dashboard/app.py`)**:
   - Logs when play button is clicked with current state
   - Logs which action is being taken (resume vs start)

2. **Engine run loop (`dashboard/core/engine.py`)**:
   - Logs when entering paused state
   - Logs when exiting paused state and resuming processing

3. **Resume method**:
   - Logs thread status (alive/dead, running/stopped)
   - Logs whether thread is being restarted

## Testing

Created comprehensive tests in `tests/unit/dashboard/test_resume_restarts_thread.py`:

1. **test_resume_restarts_thread_when_stopped**: Verifies that `resume()` restarts the thread if it has stopped
2. **test_resume_does_not_restart_if_thread_alive**: Verifies that `resume()` does not restart if thread is still alive (normal pause/resume flow)

Both tests pass, confirming the fix works correctly.

## Behavior

### Before Fix
- Pause → Thread stops → Click play → Nothing happens (pause flags cleared but thread dead)

### After Fix
- Pause → Thread stops → Click play → Resume detects dead thread → Restarts thread → Simulation continues
- Pause → Thread alive → Click play → Resume clears pause flags → Thread continues from pause loop

## Related Files

- `dashboard/core/engine.py` - Main fix in `resume()` and enhanced logging in `_run_loop()`
- `dashboard/app.py` - Enhanced logging in play button callback
- `tests/unit/dashboard/test_resume_restarts_thread.py` - Test coverage

## Notes

- The fix gracefully handles both cases: thread alive (normal pause) and thread dead (stopped while paused)
- Enhanced logging helps diagnose pause/resume issues in production
- Thread safety is maintained through existing lock mechanisms (`self._lock`)








