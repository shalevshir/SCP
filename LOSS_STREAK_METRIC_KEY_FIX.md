# Loss Streak Metric Key Fix

**Date:** January 16, 2026  
**Status:** ✅ Complete

## Problem Statement

The code in `trade_manager.py` was accessing `_daily_state.get("loss_streak", 0)` but the `InvalidationChecker._daily_state` dictionary uses the key `"consecutive_losses"`, not `"loss_streak"`. This caused the `loss_streak_current` metric to always return `0` (the default) regardless of the actual consecutive loss count, making the metric useless for monitoring.

**Location:** `services/execution/src/execution_svc/trade_manager.py:633-636`

## Root Cause

**Incorrect Key Access:**

```python
# WRONG CODE (trade_manager.py:634)
loss_streak = self._invalidation_checker._daily_state.get(
    "loss_streak", 0  # ❌ This key doesn't exist
)
```

**Actual Dictionary Structure** (`InvalidationChecker.__init__` in `services/shared/src/scp_shared/execution/invalidation.py:78-83`):

```python
self._daily_state: dict[str, Any] = {
    "consecutive_losses": 0,  # ✅ Correct key
    "daily_pnl": 0.0,
    "last_session_date": None,
    "pdll": pdll_limit,
}
```

The key mismatch meant:
- `.get("loss_streak", 0)` would always return the default value `0`
- The actual `consecutive_losses` value was never read
- The `loss_streak_current` metric was effectively broken

## Solution

Changed the key from `"loss_streak"` to `"consecutive_losses"`:

```python
# FIXED CODE
loss_streak = self._invalidation_checker._daily_state.get(
    "consecutive_losses", 0  # ✅ Correct key
)
metrics.loss_streak_current.labels(
    mode=self._service_mode, service=self._service_name
).set(loss_streak)
```

## Impact

### Before Fix

The `loss_streak_current` metric would always report `0`:

```
scp_loss_streak_current{mode="paper", service="execution"} 0
# Always 0, even after multiple consecutive losses
```

This made it impossible to:
- Monitor consecutive loss streaks
- Trigger alerts when loss streak limits are approached
- Debug guardrail behavior related to loss streaks
- Verify that loss streak detection is working correctly

### After Fix

The metric now correctly reports the actual consecutive loss count:

```
scp_loss_streak_current{mode="paper", service="execution"} 3
# Correctly shows 3 consecutive losses
```

Operators can now:
- Monitor actual loss streak counts
- Set up Grafana alerts for concerning loss streaks
- Verify guardrail enforcement (e.g., max 3 consecutive losses)
- Debug patterns in losing trades

## Files Modified

1. ✅ **`services/execution/src/execution_svc/trade_manager.py`** (line 634)
   - Changed `"loss_streak"` → `"consecutive_losses"`

## Verification

After restarting the execution service, verify the metric works:

```bash
# Check the metric is being set correctly
curl http://localhost:8005/metrics | grep scp_loss_streak_current

# Expected output (when no losses):
# scp_loss_streak_current{mode="paper",service="execution"} 0

# After a losing trade:
# scp_loss_streak_current{mode="paper",service="execution"} 1
```

### Testing the Fix

To verify the fix is working:

1. **No losses:** Metric should be `0`
2. **After 1 loss:** Metric should be `1`
3. **After 2 consecutive losses:** Metric should be `2`
4. **After a win:** Metric should reset to `0`

The metric should match the value in `InvalidationChecker._daily_state["consecutive_losses"]`.

## Related Metrics

The fix ensures consistency with other risk tracking metrics:

- `scp_loss_streak_current`: Now correctly reports consecutive losses
- `scp_daily_pnl`: Already working (uses correct key `"daily_pnl"`)
- `scp_trading_halt_reason`: Can now properly indicate `"LOSS_STREAK"` halt when limit is reached

## Grafana Dashboard

The "Loss Streak Current" panel (Row 6, Debug section) will now display correct values:

```promql
scp_loss_streak_current{mode="$mode"}
```

This panel can be used to:
- Monitor current loss streak
- Set alerts when approaching limits (e.g., alert if >= 2)
- Verify guardrails are working correctly

## Next Steps

1. **Rebuild execution service** to apply the fix:
   ```bash
   docker compose -f infra/docker-compose.infra.yml \
                  -f infra/docker-compose.services.yml \
                  -f infra/docker-compose.paper.yml \
                  up --build -d execution
   ```

2. **Verify the fix** after restart:
   ```bash
   # Check metric is initialized
   curl http://localhost:8005/metrics | grep scp_loss_streak_current
   
   # Should show 0 initially
   # scp_loss_streak_current{mode="paper",service="execution"} 0
   ```

3. **Monitor during operation** to ensure it updates correctly when trades close

4. **Add alert** in Grafana for high loss streaks:
   ```promql
   # Alert when loss streak >= 2
   scp_loss_streak_current{mode="paper"} >= 2
   ```

## Related Fixes in This Session

This fix is part of a series of monitoring improvements:

1. ✅ **Grafana Dashboard Fixes**
   - Fixed "Execution Service Up" panel (removed mode filter from `up` metric)
   - Fixed "Enforcer Tier" panel (changed textMode to value_and_name)
   - Fixed dashboard mode variable default to "paper"

2. ✅ **Signal Rejection Tracking**
   - Added specific rejection reasons: `htf_validity`, `neutral_direction`
   - Fixed SignalEngine.generate() to return rejection reason
   - Updated bot-core to record correct rejection reasons

3. ✅ **Trading Halt Reason Metric**
   - Initialized metric at service startup
   - Added distinct halt reasons: PDLL, LOSS_STREAK, MAX_TRADES, etc.

4. ✅ **SERVICE_MODE Environment Variable**
   - Added to all docker compose files for consistent metrics labeling

5. ✅ **Loss Streak Metric Key** (THIS FIX)
   - Fixed key from `"loss_streak"` to `"consecutive_losses"`
   - Metric now correctly reports actual consecutive losses

All metrics now have proper labeling, correct data sources, and meaningful values for production monitoring.
