# VWAP_RECLAIM Diagnostic Guide

## Problem

VWAP_RECLAIM setups are being rejected during setup detection, causing signals to be saved with `setup_type="REJECTED"` instead of `setup_type="VWAP_RECLAIM"`.

## Solution Overview

Enhanced the scoring system to capture detailed constraint validation failures for VWAP_RECLAIM setups. This allows us to:

1. Identify which specific constraint(s) are causing rejections
2. See example context values that caused failures
3. Make data-driven decisions about constraint adjustments

## Implementation

### Code Changes

**File**: `services/shared/src/scp_shared/rule_engine/scoring.py`

1. **Modified `determine_setup_type()`** to accept optional `diagnostics` parameter
2. **Added `_extract_relevant_context()`** helper to capture constraint-specific context values
3. **Enhanced logging** to output constraint failures with context at INFO level

When VWAP_RECLAIM validation fails, the system now:
- Logs: `"VWAP_RECLAIM constraint 'X' failed: <reason> | Context: {...}"`
- Saves to `signal.diagnostics["vwap_reclaim_validation"]`:
  ```json
  {
    "failed_constraint": "vwap_reclaim_distance",
    "reject_reason": "VWAP deviation outside acceptable range (0.5-3.0 ATR)",
    "evaluated_constraints": ["structure_1h_available", "htf_structure_integrity", ...],
    "context_snapshot": {
      "vwap_deviation_normalized": 0.45,
      "direction": "long",
      "close": 2650.5,
      "vwap": 2649.0
    }
  }
  ```

### Diagnostic Tool

**File**: `services/bot-core/src/bot_core_svc/diagnostics/vwap_reclaim_analyzer.py`

CLI tool to query and analyze constraint failures from `signal_history` table.

## Usage

### Step 1: Deploy Code Changes

```bash
# Rebuild shared library
make shared-install

# Restart bot-core service to use updated code
docker-compose restart bot-core
# OR if running locally:
# make services-restart
```

### Step 2: Run Bot-Core to Collect Data

Wait for bot-core to process live or replay data. The enhanced diagnostics will be captured automatically when VWAP_RECLAIM constraints fail.

### Step 3: Run Diagnostic Analyzer

```bash
# Analyze last 7 days (default)
python -m bot_core_svc.diagnostics.vwap_reclaim_analyzer

# Analyze specific date range
python -m bot_core_svc.diagnostics.vwap_reclaim_analyzer \
    --start "2025-01-15" \
    --end "2025-01-20"

# Analyze last 30 days
python -m bot_core_svc.diagnostics.vwap_reclaim_analyzer --days 30

# Custom database connection
python -m bot_core_svc.diagnostics.vwap_reclaim_analyzer \
    --db-host localhost \
    --db-port 5432 \
    --db-name scp_trading \
    --db-user scp_user
```

### Step 4: Review Report

Example output:

```
================================================================================
VWAP_RECLAIM Constraint Failure Analysis
================================================================================
Period: 2025-01-15 00:00 to 2025-01-20 00:00

Total REJECTED signals: 1,234
  - With VWAP_RECLAIM diagnostics: 856
  - Without diagnostics: 378

Top Failing Constraints:
--------------------------------------------------------------------------------

1. Constraint: vwap_reclaim_distance
   Failures: 523
   Reason: VWAP deviation outside acceptable range (0.5-3.0 ATR)
   Example context: {
      "vwap_deviation_normalized": 0.42,
      "direction": "long",
      "close": 2650.5,
      "vwap": 2649.8
   }

2. Constraint: min_vwap_acceptance
   Failures: 187
   Reason: Drive-by reclaim without acceptance (bars_near_vwap < 3)
   Example context: {
      "bars_near_vwap": 2
   }

3. Constraint: structure_1h_available
   Failures: 146
   Reason: HTF 1H structure missing - cannot validate HTF alignment
   Example context: {
      "structure_1h": null
   }

================================================================================

Next Steps:
  1. Review top failing constraint(s)
  2. Check if constraint threshold is too strict
  3. Verify feature values are calculated correctly
  4. Adjust constraint in config/setups.yaml or fix data pipeline
  5. Re-run analysis after changes to verify improvement
```

The report is also saved to `diagnostics_reports/vwap_reclaim_analysis_<timestamp>.txt`

### Step 5: Fix Constraints

Based on the diagnostic results, implement fixes:

#### Option A: Adjust Constraint Thresholds

**File**: `config/setups.yaml`

Example: Relax `vwap_reclaim_distance` from 0.5-3.0 to 0.3-3.5 ATR

```yaml
VWAP_RECLAIM:
  enabled: true
  constraints:
    vwap_reclaim_distance:
      expression: >
        direction == 'neutral' or
        (vwap_deviation_normalized >= 0.3 and vwap_deviation_normalized <= 3.5)
      reject_reason: "VWAP deviation outside acceptable range (0.3-3.5 ATR)"
```

Example: Lower `min_vwap_acceptance` from 3 to 2 bars

```yaml
    min_vwap_acceptance:
      expression: >
        bars_near_vwap is None or bars_near_vwap >= 2
      reject_reason: "Drive-by reclaim without acceptance (bars_near_vwap < 2)"
```

#### Option B: Fix Data Pipeline Issues

If `structure_1h_available` is failing:
- Check htf-bias service logs for errors
- Verify 1H candle aggregation is working
- Ensure structure detection runs on 1H timeframe

#### Option C: Temporarily Disable Constraint

For debugging, temporarily make constraint always pass:

```yaml
    vwap_reclaim_distance:
      expression: "True"  # Always pass
      reject_reason: "DISABLED FOR TESTING"
```

### Step 6: Validate Fixes

After making changes:

```bash
# 1. Validate YAML syntax
make lint

# 2. Run tests
make test

# 3. Restart bot-core to reload config
docker-compose restart bot-core

# 4. Monitor logs for "Setup detected: VWAP_RECLAIM"
docker logs -f bot-core | grep "VWAP_RECLAIM"

# 5. Query signal_history for successful detections
psql -d scp_trading -c "
  SELECT timestamp, direction, setup_type, score, confidence
  FROM signal_history
  WHERE setup_type = 'VWAP_RECLAIM'
  ORDER BY timestamp DESC
  LIMIT 10;
"

# 6. Re-run diagnostic analyzer to verify improvement
python -m bot_core_svc.diagnostics.vwap_reclaim_analyzer --days 1
```

## Verification Checklist

- [ ] Code changes deployed (shared library rebuilt, bot-core restarted)
- [ ] Logs show detailed constraint failures: `grep "VWAP_RECLAIM constraint" bot-core.log`
- [ ] Diagnostic analyzer runs without errors
- [ ] Report shows `with_vwap_diagnostics > 0`
- [ ] Top failing constraint identified
- [ ] Constraint fix implemented in `config/setups.yaml`
- [ ] Tests pass: `make test`
- [ ] After fix, `signal_history` contains records with `setup_type='VWAP_RECLAIM'`
- [ ] A+ signals generated (score >= 8.0)
- [ ] Signals reach execution service

## Manual SQL Queries

If you prefer to query the database directly:

### Check if diagnostics are being captured

```sql
SELECT
  diagnostics->'vwap_reclaim_validation'
FROM signal_history
WHERE setup_type = 'REJECTED'
  AND diagnostics ? 'vwap_reclaim_validation'
LIMIT 1;
```

### Count rejections by constraint

```sql
SELECT
  diagnostics->'vwap_reclaim_validation'->>'failed_constraint' as constraint,
  COUNT(*) as failures
FROM signal_history
WHERE setup_type = 'REJECTED'
  AND diagnostics ? 'vwap_reclaim_validation'
  AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY constraint
ORDER BY failures DESC;
```

### View example context for a specific constraint

```sql
SELECT
  timestamp,
  diagnostics->'vwap_reclaim_validation'->>'failed_constraint' as constraint,
  diagnostics->'vwap_reclaim_validation'->>'reject_reason' as reason,
  diagnostics->'vwap_reclaim_validation'->'context_snapshot' as context
FROM signal_history
WHERE setup_type = 'REJECTED'
  AND diagnostics->'vwap_reclaim_validation'->>'failed_constraint' = 'vwap_reclaim_distance'
LIMIT 5;
```

## VWAP_RECLAIM Constraints Reference

All 14 constraints that must pass for VWAP_RECLAIM detection:

1. **structure_1h_available**: HTF 1H structure must exist
2. **htf_structure_integrity**: Direction must match structure_1h (HH/HL for long, LL/LH for short)
3. **structure_label_available**: Structure label must exist
4. **vwap_reclaim_distance**: Deviation between 0.5-3.0 ATR normalized
5. **no_late_reclaim**: BOS not recent OR BOS age >= 20
6. **bos_reclaim_gate**: BOS direction None, matches direction, or >= 20 bars old
7. **direction_bos_alignment**: No recent conflicting BOS
8. **no_structure_conflict**: No HTF structure conflict
9. **min_vwap_acceptance**: bars_near_vwap >= 3 (or None)
10. **reclaim_timing_gate**: bars_since_last_vwap_touch <= 10
11. **structure_label_direction_long**: For longs, structure_label not in ('LH', 'LL')
12. **structure_label_direction_short**: For shorts, structure_label not in ('HH', 'HL')

See `config/setups.yaml` lines 16-98 for full constraint definitions.

## Troubleshooting

### No diagnostics in report ("with_vwap_diagnostics: 0")

**Cause**: Code changes not deployed yet OR no VWAP_RECLAIM attempts in period

**Solution**:
1. Verify code changes deployed: `grep "_extract_relevant_context" services/shared/src/scp_shared/rule_engine/scoring.py`
2. Check logs for constraint failures: `grep "VWAP_RECLAIM constraint" bot-core.log`
3. Extend date range: `--days 30`

### All constraints failing for same reason

**Cause**: Data pipeline issue (e.g., all features are None/missing)

**Solution**:
1. Check feature-engine service health
2. Verify Redis streams have data: `redis-cli XREAD COUNT 1 STREAMS features.1m 0`
3. Check htf-bias service for 1H structure: `redis-cli XREAD COUNT 1 STREAMS htf_bias 0`

### Constraint fixes don't help (cascading failures)

**Cause**: Fixing one constraint reveals next constraint always fails

**Solution**:
- Iterative approach: fix top constraint → re-run diagnostics → fix next constraint
- Consider if constraints are fundamentally mismatched with market conditions
- Review backtest results to see if VWAP_RECLAIM worked historically

## Next Steps

After identifying and fixing the root cause constraint(s):

1. **Monitor live trading**: Watch for VWAP_RECLAIM signals reaching execution
2. **Backtest validation**: Run backtester with updated constraints, compare results
3. **Win rate analysis**: Track performance of relaxed constraints over 30+ trades
4. **Iterate**: If constraint was over-relaxed, tighten gradually while monitoring

## Related Files

- Code changes: `services/shared/src/scp_shared/rule_engine/scoring.py`
- Analyzer tool: `services/bot-core/src/bot_core_svc/diagnostics/vwap_reclaim_analyzer.py`
- Constraints config: `config/setups.yaml` (lines 16-98)
- Signal history schema: `infra/migrations/` (signal_history table)
- Setup validator: `services/shared/src/scp_shared/rule_engine/setup_validator.py`
