# VWAP Acceptance Fields Fix

## Issue Summary

The VWAP acceptance constraints (`min_vwap_acceptance` and `reclaim_timing_gate`) in `config/setups.yaml` were not functioning correctly because the required fields (`bars_near_vwap` and `bars_since_last_vwap_touch`) were missing from the features Series during signal generation.

## Root Cause

1. **Constraints defined** in `config/setups.yaml`:
   - `min_vwap_acceptance`: Requires `bars_near_vwap >= 3` to prevent "drive-by" reclaims
   - `reclaim_timing_gate`: Requires `bars_since_last_vwap_touch <= 10` to prevent delayed reclaims

2. **Fields exist** in `FeaturesMessage` schema (`services/shared/src/scp_shared/messaging/schemas.py`):
   ```python
   bars_near_vwap: int | None = Field(
       default=None,
       description="Consecutive bars within VWAP proximity band (±0.2 ATR)",
   )
   bars_since_last_vwap_touch: int | None = Field(
       default=None,
       description="Bars since last VWAP touch/interaction"
   )
   ```

3. **Fields extracted** by `build_setup_context` (`services/shared/src/scp_shared/rule_engine/scoring.py`):
   ```python
   "bars_near_vwap": features.get("bars_near_vwap"),
   "bars_since_last_vwap_touch": features.get("bars_since_last_vwap_touch"),
   ```

4. **Fields MISSING** from `features_message_to_series` (`services/bot-core/src/bot_core_svc/signal_engine.py`):
   - The conversion function did not include these fields when converting `FeaturesMessage` to pandas Series
   - Result: `features.get("bars_near_vwap")` returned `None`, causing constraints to always pass via the `is None` fallback

## Impact

- **Before Fix**: Constraints always passed (ineffective)
  - Drive-by reclaims (1-2 bars near VWAP) were accepted
  - Delayed reclaims (15+ bars since last touch) were accepted
  
- **After Fix**: Constraints properly enforce SOP rules
  - Drive-by reclaims rejected (`bars_near_vwap < 3`)
  - Delayed reclaims rejected (`bars_since_last_vwap_touch > 10`)

## Fix Applied

Added missing fields to `features_message_to_series` in `services/bot-core/src/bot_core_svc/signal_engine.py`:

```python
def features_message_to_series(msg: FeaturesMessage) -> pd.Series:
    return pd.Series(
        {
            # ... existing fields ...
            
            # VWAP acceptance fields for min_vwap_acceptance and reclaim_timing_gate constraints
            "bars_near_vwap": msg.bars_near_vwap,
            "bars_since_last_vwap_touch": msg.bars_since_last_vwap_touch,
        }
    )
```

## Test Coverage

### Unit Tests (`services/bot-core/tests/unit/test_vwap_acceptance_fields.py`)
- ✅ `test_bars_near_vwap_included_in_series` - Verifies field is present in Series
- ✅ `test_bars_since_last_vwap_touch_included_in_series` - Verifies field is present in Series
- ✅ `test_vwap_acceptance_fields_none_handling` - Verifies None values handled correctly
- ✅ `test_drive_by_reclaim_detection` - Verifies constraint can detect drive-by reclaims
- ✅ `test_delayed_reclaim_detection` - Verifies constraint can detect delayed reclaims
- ✅ `test_valid_vwap_reclaim_acceptance` - Verifies valid reclaims pass constraints

### Integration Tests (`services/bot-core/tests/unit/test_vwap_acceptance_constraints_integration.py`)
- ✅ `test_drive_by_reclaim_rejected` - End-to-end rejection of drive-by reclaims
- ✅ `test_delayed_reclaim_rejected` - End-to-end rejection of delayed reclaims
- ✅ `test_valid_vwap_reclaim_passes` - End-to-end acceptance of valid reclaims
- ✅ `test_none_values_bypass_constraints` - None values bypass constraints (ATR unavailable case)
- ✅ `test_edge_case_exactly_3_bars_passes` - Boundary case (exactly 3 bars)
- ✅ `test_edge_case_exactly_10_bars_since_touch_passes` - Boundary case (exactly 10 bars)

## Verification

All tests pass:
```bash
# Unit tests (field conversion)
poetry run pytest services/bot-core/tests/unit/test_vwap_acceptance_fields.py
# Result: 6 passed

# Integration tests (constraint enforcement)
poetry run pytest services/bot-core/tests/unit/test_vwap_acceptance_constraints_integration.py
# Result: 6 passed

# Full bot-core test suite (no regressions)
poetry run pytest services/bot-core/tests/unit/
# Result: 164 passed, 10 skipped
```

## Files Changed

1. **services/bot-core/src/bot_core_svc/signal_engine.py**
   - Added `bars_near_vwap` and `bars_since_last_vwap_touch` to `features_message_to_series`

2. **services/bot-core/tests/unit/test_vwap_acceptance_fields.py** (new file)
   - Unit tests for field conversion

3. **services/bot-core/tests/unit/test_vwap_acceptance_constraints_integration.py** (new file)
   - Integration tests for constraint enforcement

## Constraint Behavior

### `min_vwap_acceptance` (config/setups.yaml:60-62)
```yaml
min_vwap_acceptance:
  expression: "bars_near_vwap is None or bars_near_vwap >= 3"
  reject_reason: "No acceptance near VWAP - drive-by reclaim"
```
- **Purpose**: Prevent drive-by reclaims with insufficient VWAP acceptance
- **Pass**: `bars_near_vwap >= 3` or `bars_near_vwap is None` (ATR unavailable)
- **Reject**: `bars_near_vwap < 3` (1-2 bars near VWAP)

### `reclaim_timing_gate` (config/setups.yaml:64-66)
```yaml
reclaim_timing_gate:
  expression: "bars_since_last_vwap_touch is None or bars_since_last_vwap_touch <= 10"
  reject_reason: "VWAP reclaim too delayed - invalid continuation"
```
- **Purpose**: Prevent delayed reclaims that are too far from the reclaim action
- **Pass**: `bars_since_last_vwap_touch <= 10` or `bars_since_last_vwap_touch is None`
- **Reject**: `bars_since_last_vwap_touch > 10` (reclaim too old)

## Production Impact

- **Immediate**: Constraints now functional in bot-core service
- **Expected**: More aggressive rejection of low-quality VWAP_RECLAIM setups
- **Monitoring**: Track rejection rates for `min_vwap_acceptance` and `reclaim_timing_gate` in production logs

## Related Issues

- None - this is a standalone fix for a data pipeline issue
- Follow-up: Monitor if thresholds (3 bars, 10 bars) need tuning based on production data
