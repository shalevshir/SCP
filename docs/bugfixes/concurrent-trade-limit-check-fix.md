# Concurrent Trade Limit Check Bug Fix

**Date:** 2025-12-22  
**Component:** Execution Service - TradeManager  
**Severity:** High (Risk Management Issue)  
**Status:** ✅ Fixed

---

## Summary

The `execute_pending_signals` method in `TradeManager` did not check the concurrent trade limit (`max_active_trades`) when executing buffered signals. This created a risk of exceeding the configured concurrent trade limit, potentially bypassing a critical risk management control.

---

## Bug Description

### Root Cause

In `execute_pending_signals`, the method checked daily limits (`_daily_tracker.can_trade()`) but did not verify the concurrent trade limit before calling `execute_entry()` for each buffered signal.

### Scenario

1. **Setup:** `max_active_trades = 1` (only 1 concurrent trade allowed)
2. **Buffering:** Multiple signals arrive within the same bar
3. **Buffering Check:** `on_signal()` checks concurrent limit and accepts signals if below capacity
4. **Execution:** All buffered signals are stored in `_pending_signals`
5. **Bug:** `execute_pending_signals()` attempts to execute ALL buffered signals without re-checking concurrent limit
6. **Result:** Multiple `execute_entry()` calls attempted even though limit is 1

### Masking Factor

The bug was partially masked by the `PaperBroker` implementation, which only allows one position per symbol. When the second trade attempted execution, the broker raised a `ValueError`:

```python
if symbol in self._positions:
    raise ValueError(
        f"Position already exists for {symbol}. "
        "Close existing position before opening new one."
    )
```

However, **this is not reliable protection**:
- Real brokers may allow multiple positions per symbol
- The error happened **after** attempting execution (inefficient, logs errors)
- Violates the principle of explicit limit checking at the appropriate layer

---

## Code Changes

### File: `services/execution/src/execution_svc/trade_manager.py`

**Location:** `execute_pending_signals` method (line 160-184)

**Before:**
```python
async def execute_pending_signals(self, next_bar_open: float) -> None:
    """Execute buffered signals at next bar open price."""
    if not self._pending_signals:
        return
    
    logger.info(
        f"Executing {len(self._pending_signals)} pending signals "
        f"at open={next_bar_open:.2f}"
    )
    
    for signal in self._pending_signals:
        # Check daily limits before executing
        can_trade, reason = self._daily_tracker.can_trade()
        if not can_trade:
            logger.info(f"Signal {signal.id} blocked by daily limits: {reason}")
            continue
        
        await self.execute_entry(signal, next_bar_open)
    
    # Clear pending signals after execution
    self._pending_signals.clear()
```

**After (Fixed):**
```python
async def execute_pending_signals(self, next_bar_open: float) -> None:
    """Execute buffered signals at next bar open price."""
    if not self._pending_signals:
        return
    
    logger.info(
        f"Executing {len(self._pending_signals)} pending signals "
        f"at open={next_bar_open:.2f}"
    )
    
    for signal in self._pending_signals:
        # Check concurrent trade limit FIRST
        # (prevents attempting execution when already at capacity)
        if len(self._active_trades) >= self._max_active_trades:
            logger.info(
                f"Signal {signal.id} blocked: max active trades reached "
                f"({len(self._active_trades)}/{self._max_active_trades})"
            )
            continue
        
        # Check daily limits before executing
        can_trade, reason = self._daily_tracker.can_trade()
        if not can_trade:
            logger.info(f"Signal {signal.id} blocked by daily limits: {reason}")
            continue
        
        await self.execute_entry(signal, next_bar_open)
    
    # Clear pending signals after execution
    self._pending_signals.clear()
```

### Key Changes

1. **Added concurrent limit check:** Before attempting `execute_entry()`, verify that `len(self._active_trades) < self._max_active_trades`
2. **Positioned check first:** Concurrent limit is checked BEFORE daily limits for efficiency
3. **Explicit logging:** Log when signals are blocked due to concurrent limit
4. **Early continue:** Skip to next signal when at capacity

---

## Test Coverage

### New Test File

**File:** `services/execution/tests/unit/test_trade_manager_concurrent_limit.py`

Created comprehensive test suite covering:

1. **`test_concurrent_trade_limit_with_buffered_signals`**
   - **Purpose:** Demonstrates the bug and verifies the fix
   - **Scenario:** Buffer 2 signals when `max_active_trades=1`
   - **Assertion:** Only 1 `execute_entry()` call should occur
   - **Result:** ✅ Passes after fix (was failing before)

2. **`test_concurrent_limit_with_daily_limit_interaction`**
   - **Purpose:** Verify concurrent limit checked BEFORE daily limits
   - **Scenario:** Buffer 3 signals, max_active_trades=1, high daily limit
   - **Assertion:** Only 1 trade executes (concurrent limit), not all 3
   - **Result:** ✅ Passes

3. **`test_sequential_execution_respects_concurrent_limit`**
   - **Purpose:** Verify limit works across multiple execution cycles
   - **Scenario:** Execute 1 trade, close it, execute another
   - **Assertion:** Sequential execution works correctly
   - **Result:** ✅ Passes

### Test Results

```bash
$ poetry run pytest tests/unit/test_trade_manager_concurrent_limit.py -v
# 3 passed, 0 failed ✅

$ poetry run pytest tests/unit/ -q
# 58 passed, 0 failed ✅
```

All existing tests continue to pass, confirming no regressions.

---

## Impact Assessment

### Before Fix

- **Risk:** Multiple trades could execute in same bar, exceeding `max_active_trades`
- **Probability:** Low (masked by broker protection, but not guaranteed)
- **Impact:** High (violates core risk management rule)
- **Detection:** Would only appear in logs as broker errors

### After Fix

- **Protection:** Explicit concurrent limit check at correct layer
- **Efficiency:** Prevents unnecessary `execute_entry()` attempts
- **Clarity:** Clear log messages when signals blocked by concurrent limit
- **Reliability:** Does not rely on broker to enforce application-level limits

---

## Related Components

### Checked Limits (in order)

1. **Concurrent Trade Limit** (`_max_active_trades`)
   - Checked in: `on_signal()` (buffering phase) ✅
   - Checked in: `execute_pending_signals()` (execution phase) ✅ **[FIXED]**

2. **Daily Limits** (`_daily_tracker`)
   - PDLL (Per Day Loss Limit)
   - Max trades per day
   - Checked in: `execute_pending_signals()` ✅

3. **Re-entry Protection** (`VWAPReclaimStateMachine.can_execute()`)
   - Max executions per reclaim context
   - Checked in: `execute_entry()` ✅

4. **Broker Limits** (e.g., single position per symbol)
   - Paper broker: 1 position per symbol
   - Real broker: varies by configuration
   - **Should NOT be primary protection for app-level limits**

---

## Configuration

No configuration changes required. The fix uses existing configuration:

```python
class ExecutionConfig(BaseServiceConfig):
    max_active_trades: int = Field(
        default=1,
        description="Maximum concurrent trades",
    )
```

---

## Verification

To verify the fix works correctly:

```bash
# Run the specific test demonstrating the bug
cd services/execution
poetry run pytest tests/unit/test_trade_manager_concurrent_limit.py::test_concurrent_trade_limit_with_buffered_signals -v -s

# Expected output:
# execute_entry was called 1 times  ✅ (was 2 before fix)
# PASSED
```

---

## Lessons Learned

1. **Layer Separation:** Don't rely on downstream components (broker) to enforce application-level limits
2. **Check at Execution:** Limits must be re-checked at execution time, not just buffering time
3. **Test Masking:** Paper broker's built-in protections masked the bug; integration tests with real broker config would have caught it earlier
4. **Explicit Checks:** Always make limit checks explicit and log when they trigger

---

## Follow-Up Actions

- [x] Implement fix in `execute_pending_signals`
- [x] Add comprehensive test coverage
- [x] Verify all existing tests pass
- [ ] Consider adding metrics for blocked signals (concurrent vs daily vs re-entry)
- [ ] Review other limit checks across services for similar patterns

---

## Approval

**Reviewed by:** AI (Cursor Agent)  
**Tested by:** Automated test suite (58 tests)  
**Deployed to:** Pending user approval

---

## References

- **PR:** TBD
- **Issue:** User-reported via code review
- **Related Docs:**
  - `docs/vwap-reclaim-execution-lifecycle.md`
  - `services/execution/README.md`
  - `.cursor/rules/project_overview.mdc`



