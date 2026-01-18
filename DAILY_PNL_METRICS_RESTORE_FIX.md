# Daily P&L Metrics Restore Fix

## Issue
After service restart, the `daily_pnl` and `daily_drawdown` metrics were not updated to reflect the restored state. While `loss_streak_current` was correctly initialized from `trade_manager._daily_tracker.state.consecutive_losses` after restore, the `daily_pnl` and `daily_drawdown` metrics remained at zero until a trade closed. This caused the Grafana dashboard to display incorrect P&L and drawdown values after a service restart, potentially showing 0 when the actual daily P&L was -500.

## Root Cause
In `services/execution/src/execution_svc/main.py`, the lifespan startup function only updated the `loss_streak_current` metric after calling `restore_active_trades()`, but did not update `daily_pnl` and `daily_drawdown` metrics. These metrics were only updated when trades closed (in `trade_manager.py`), not during the initial state restoration.

## Fix
Added metric updates for `daily_pnl` and `daily_drawdown` in the lifespan startup function, immediately after `restore_active_trades()` and the loss_streak_current update:

```python
# Update metrics based on restored state
exec_metrics.loss_streak_current.labels(
    mode=config.service_mode, service=config.service_name
).set(trade_manager._daily_tracker.state.consecutive_losses)

exec_metrics.daily_pnl.labels(
    mode=config.service_mode, service=config.service_name
).set(trade_manager._daily_tracker.state.daily_pnl)

# Calculate daily drawdown (max loss from peak)
daily_drawdown = min(0, trade_manager._daily_tracker.state.daily_pnl)
exec_metrics.daily_drawdown.labels(
    mode=config.service_mode, service=config.service_name
).set(abs(daily_drawdown))

logger.info(
    f"Restored daily state metrics: "
    f"loss_streak={trade_manager._daily_tracker.state.consecutive_losses}, "
    f"daily_pnl={trade_manager._daily_tracker.state.daily_pnl:.2f}, "
    f"daily_drawdown={abs(daily_drawdown):.2f}"
)
```

## Changes Made

### 1. `/services/execution/src/execution_svc/main.py`
- Added `daily_pnl` metric update using `trade_manager._daily_tracker.state.daily_pnl`
- Added `daily_drawdown` metric update using `abs(min(0, state.daily_pnl))`
- Updated log message to include all three restored metrics

### 2. `/services/execution/tests/unit/test_daily_state_restore.py`
- Added new test `test_metrics_updated_after_restore()` that verifies:
  - Daily state is restored correctly with -250 points P&L
  - Consecutive losses are restored correctly (2 losses)
  - Metrics are set without errors
  - Expected values match restored state

## Test Results
All tests pass:
```bash
$ poetry run pytest services/execution/tests/unit/test_daily_state_restore.py -v
================================ test session starts ================================
services/execution/tests/unit/test_daily_state_restore.py::test_daily_state_restored_on_startup PASSED
services/execution/tests/unit/test_daily_state_restore.py::test_daily_state_allows_trading_below_pdll PASSED
services/execution/tests/unit/test_daily_state_restore.py::test_daily_state_blocks_trading_at_pdll PASSED
services/execution/tests/unit/test_daily_state_restore.py::test_metrics_updated_after_restore PASSED
================================ 4 passed in 0.48s =================================
```

## Impact
- **Before**: Grafana dashboard showed 0 for `daily_pnl` and `daily_drawdown` after service restart, even if actual P&L was -500 points
- **After**: Grafana dashboard immediately displays correct values after service restart
- **Risk**: None - this is a pure metrics reporting fix, does not affect trading logic
- **Consistency**: Now all three related metrics (`loss_streak_current`, `daily_pnl`, `daily_drawdown`) are initialized consistently after restore

## Verification
To verify the fix works in production:
1. Start execution service
2. Execute some trades (e.g., 2 losses totaling -250 points)
3. Restart execution service
4. Check Grafana dashboard immediately - should show:
   - `daily_pnl{mode="paper"}` = -250
   - `daily_drawdown{mode="paper"}` = 250
   - `loss_streak_current{mode="paper"}` = 2
5. Metrics should NOT be zero

## Related Files
- `/services/execution/src/execution_svc/main.py` - Fix implementation
- `/services/execution/src/execution_svc/trade_manager.py` - Original metric update logic (on trade close)
- `/services/execution/tests/unit/test_daily_state_restore.py` - Test coverage
- `/services/execution/src/execution_svc/daily_state.py` - DailyStateTracker restore logic
- `/infra/grafana/dashboards/operations.json` - Grafana dashboard using these metrics
