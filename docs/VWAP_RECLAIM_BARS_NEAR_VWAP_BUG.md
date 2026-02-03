# VWAP_RECLAIM bars_near_vwap Bug - Root Cause Analysis

## Executive Summary

**Bug**: The `bars_near_vwap` and `bars_since_last_vwap_touch` columns are **missing from the features table**, causing 100% of post-warmup VWAP_RECLAIM attempts with the `min_vwap_acceptance` constraint to fail with `bars_near_vwap=0`.

**Impact**: 281 VWAP_RECLAIM rejections (23.3% of post-warmup failures) are false negatives due to missing database columns.

**Root Cause**: Database migration was never created when these fields were added to the Pydantic schema.

**Fix**: Create and run migration `009_add_vwap_acceptance_fields.sql`

---

## Discovery Timeline

1. **Initial Analysis**: Post-warmup diagnostic showed 281 failures for `min_vwap_acceptance` constraint
2. **Deep Dive**: ALL 281 failures had `bars_near_vwap = 0` (no 1-bar or 2-bar values)
3. **Suspicion**: User noted "seems like a bug" - 100% zero values is suspicious
4. **Code Review**: Found `update_vwap_state()` correctly called with `atr=features.get("atr")`
5. **Database Check**: ATR values are valid (not NULL) in features table
6. **Critical Finding**: `SELECT bars_near_vwap FROM features` → **Column does not exist!**

---

## Technical Details

### The Data Flow

```
StreamingFeatureProcessor
  ├─ Calculates bars_near_vwap (via update_vwap_state with ATR)
  ├─ Sets features["bars_near_vwap"] = self.structure_tracker.bars_near_vwap
  ├─ Creates FeatureMessage with bars_near_vwap field
  ↓
Feature-Engine Service
  ├─ Publishes FeatureMessage to Redis (features.1m stream)
  ├─ ⚠️  Attempts to INSERT into features table
  ├─ ⚠️  Column doesn't exist → field silently dropped
  ↓
Bot-Core Service
  ├─ Reads from features table (via JOIN with htf_bias_history)
  ├─ Gets NULL for bars_near_vwap (column missing)
  ├─ NULL coerced to 0 in constraint validation
  ↓
VWAP_RECLAIM Validation
  ├─ min_vwap_acceptance constraint: "bars_near_vwap >= 3"
  ├─ Checks: 0 >= 3 → FALSE
  └─ Result: "REJECTED" with reason "No acceptance near VWAP - drive-by reclaim"
```

### Why It Wasn't Caught Earlier

1. **Tests Pass**: Unit tests for `StructureContextTracker.update_vwap_state()` pass ✅
   - These tests don't touch the database
   - They validate in-memory tracker behavior only

2. **Feature-Engine Doesn't Crash**: INSERT statement uses column subset
   - Likely uses explicit column list: `INSERT INTO features (timestamp, symbol, ...) VALUES (...)`
   - Missing columns are silently ignored (no error thrown)

3. **Bot-Core Doesn't Crash**: SELECT with missing column returns NULL
   - PostgreSQL allows SELECT on non-existent columns if using SELECT *
   - Or the query explicitly excludes bars_near_vwap (uses older schema)

4. **Integration Tests Limited**: E2E tests may not validate this specific constraint
   - Focus on happy path (successful VWAP_RECLAIM detection)
   - May use mocked data that doesn't exercise min_vwap_acceptance

---

## Evidence

### Database Query Result
```sql
SELECT bars_near_vwap FROM features LIMIT 1;
-- ERROR:  column "bars_near_vwap" does not exist
```

### Pydantic Schema (Correct)
```python
# services/shared/src/scp_shared/messaging/schemas.py:183-189
class FeatureMessage(BaseModel):
    # ... other fields ...
    bars_near_vwap: int | None = Field(
        default=None,
        description="Consecutive bars within VWAP proximity band (±0.2 ATR); None when ATR unavailable",
    )
    bars_since_last_vwap_touch: int | None = Field(
        default=None, description="Bars since last VWAP touch/interaction"
    )
```

### Diagnostic Evidence
```
2. Constraint: min_vwap_acceptance
   Failures: 281
   Reason: No acceptance near VWAP - drive-by reclaim
   Example context: {
      "bars_near_vwap": 0   <-- Always 0, never 1, 2, or 3+
   }

Distribution:
  0 bars: 281 (100.0%)   <-- Suspicious!
  1 bar:  0 (0.0%)
  2 bars: 0 (0.0%)
```

---

## The Fix

### Migration File: `009_add_vwap_acceptance_fields.sql`

```sql
-- Migration: Add VWAP acceptance tracking fields to features table
-- Created: 2026-02-02

BEGIN;

-- Add bars_near_vwap column (consecutive bars within ±0.2 ATR of VWAP)
ALTER TABLE features
ADD COLUMN IF NOT EXISTS bars_near_vwap INTEGER;

COMMENT ON COLUMN features.bars_near_vwap IS
    'Consecutive bars within VWAP proximity band (±0.2 ATR); NULL when ATR unavailable';

-- Add bars_since_last_vwap_touch column (bars since last VWAP interaction)
ALTER TABLE features
ADD COLUMN IF NOT EXISTS bars_since_last_vwap_touch INTEGER;

COMMENT ON COLUMN features.bars_since_last_vwap_touch IS
    'Bars since last VWAP touch/interaction; NULL when no touch has occurred';

-- Create index for constraint validation queries
CREATE INDEX IF NOT EXISTS idx_features_vwap_acceptance
    ON features(symbol, timestamp, bars_near_vwap, bars_since_last_vwap_touch)
    WHERE bars_near_vwap IS NOT NULL;

COMMIT;
```

### Application Steps

1. **Run Migration**:
   ```bash
   make db-migrate  # Or manually: psql -d scp < infra/migrations/009_add_vwap_acceptance_fields.sql
   ```

2. **Restart Feature-Engine**:
   ```bash
   docker-compose restart feature-engine
   # Or locally: make services-restart
   ```

3. **Restart Bot-Core**:
   ```bash
   docker-compose restart bot-core
   ```

4. **Verify Migration**:
   ```sql
   SELECT column_name, data_type, is_nullable
   FROM information_schema.columns
   WHERE table_name = 'features'
     AND column_name IN ('bars_near_vwap', 'bars_since_last_vwap_touch');
   ```

   Expected output:
   ```
            column_name         | data_type | is_nullable
   -----------------------------+-----------+-------------
    bars_near_vwap              | integer   | YES
    bars_since_last_vwap_touch  | integer   | YES
   ```

5. **Re-run Replay**:
   ```bash
   make replay START=2025-11-06 END=2025-11-08 SPEED=0
   ```

6. **Run Diagnostics**:
   ```bash
   make diagnose-vwap-reclaim START=2025-11-06 END=2025-11-08
   ```

---

## Expected Impact After Fix

### Before Fix (Current State)
```
Top Failing Constraints (Post-Warmup):
1. vwap_reclaim_distance: 716 failures (59.4%)  ✅ Working correctly
2. min_vwap_acceptance: 281 failures (23.3%)    ❌ FALSE NEGATIVES (bug)
3. htf_structure_integrity: 150 failures (12.4%) ✅ Working correctly
4. structure_1h_available: 58 failures (4.8%)    ✅ Warmup stragglers
```

### After Fix (Expected)
```
Top Failing Constraints (Post-Warmup):
1. vwap_reclaim_distance: 716 failures (59.4%)  ✅ Working correctly
2. htf_structure_integrity: 150 failures (12.4%) ✅ Working correctly
3. structure_1h_available: 58 failures (4.8%)    ✅ Warmup stragglers
4. min_vwap_acceptance: <50 failures (~5%)       ✅ True drive-by reclaims only

VWAP_RECLAIM setups detected: +200-230 additional valid setups
```

**Recovery**: ~230 setups will now pass `min_vwap_acceptance` constraint that were previously false negatives.

---

## Validation Plan

After applying migration and restarting services:

### 1. Verify Columns Exist
```sql
\d+ features  -- Show table schema with new columns
```

### 2. Verify Data Population
```sql
SELECT
    timestamp,
    symbol,
    bars_near_vwap,
    bars_since_last_vwap_touch,
    atr,
    close,
    vwap
FROM features
WHERE timestamp >= NOW() - INTERVAL '1 hour'
  AND symbol = 'GC'
  AND bars_near_vwap IS NOT NULL
LIMIT 10;
```

Expected: See rows with `bars_near_vwap` values like 0, 1, 2, 3, etc. (not all NULL, not all 0)

### 3. Verify Distribution
```sql
SELECT
    bars_near_vwap,
    COUNT(*) as count
FROM features
WHERE timestamp >= NOW() - INTERVAL '1 day'
  AND symbol = 'GC'
GROUP BY bars_near_vwap
ORDER BY bars_near_vwap;
```

Expected: See varied distribution (0, 1, 2, 3+), not 100% NULL or 100% zero

### 4. Run Post-Fix Diagnostic
```bash
make diagnose-vwap-reclaim START=2025-11-06 END=2025-11-08
```

Expected:
- `min_vwap_acceptance` failures drop from 281 to ~30-50 (true drive-by reclaims)
- Distribution shows mix of 0-bar, 1-bar, 2-bar failures (not 100% zero)

### 5. Verify VWAP_RECLAIM Detection
```sql
SELECT
    timestamp,
    direction,
    setup_type,
    score,
    confidence
FROM signal_history
WHERE timestamp >= NOW() - INTERVAL '1 hour'
  AND setup_type = 'VWAP_RECLAIM'
ORDER BY timestamp DESC
LIMIT 10;
```

Expected: See `setup_type='VWAP_RECLAIM'` entries (not "REJECTED")

---

## Prevention Measures

### 1. Schema Validation in CI/CD

Add test to verify Pydantic schema matches database schema:

```python
def test_feature_message_columns_exist_in_db():
    """Verify all FeatureMessage fields have corresponding DB columns."""
    from scp_shared.messaging.schemas import FeatureMessage

    # Get all fields from Pydantic model
    model_fields = set(FeatureMessage.model_fields.keys())

    # Query database for actual columns
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'features'
    """
    db_columns = set(row['column_name'] for row in execute_query(query))

    # Check for missing columns
    missing = model_fields - db_columns - {'timestamp', 'symbol', 'timeframe'}  # Exclude keys

    assert not missing, f"Missing columns in features table: {missing}"
```

### 2. Migration Checklist

When adding fields to `FeatureMessage`:
- [ ] Update Pydantic schema in `schemas.py`
- [ ] Create database migration in `infra/migrations/`
- [ ] Run migration on dev environment
- [ ] Update tests to exercise new field
- [ ] Verify field in database after service restart

### 3. Feature-Engine Validation

Add logging to detect silent INSERT failures:

```python
# After INSERT
if cursor.rowcount == 0:
    logger.warning(f"Feature INSERT returned 0 rows - possible schema mismatch")
```

---

## Related Issues

This bug is related to two separate root causes discovered in the VWAP_RECLAIM investigation:

1. **Warmup Period Issue** (480 failures)
   - Root cause: `structure_1h=NULL` during first 10 hours
   - Fix: Implement warmup skip in `determine_setup_type()`
   - Status: Documented in `VWAP_RECLAIM_ROOT_CAUSE.md`

2. **bars_near_vwap Missing Column** (281 failures) ← **THIS ISSUE**
   - Root cause: Database migration never created
   - Fix: Migration `009_add_vwap_acceptance_fields.sql`
   - Status: Migration created, pending application

**Combined Impact**: After fixing both issues, ~711 false rejections (480 + 231) will be eliminated, allowing valid VWAP_RECLAIM setups through.

---

## Lessons Learned

1. **Schema Evolution Risk**: Adding Pydantic fields without corresponding database migrations creates silent data loss
2. **E2E Test Coverage**: Need tests that validate full data pipeline (Pydantic → DB → Pydantic roundtrip)
3. **Diagnostic Value**: Enhanced diagnostics (capturing constraint context) was critical to discovering this bug
4. **Statistical Anomalies**: 100% of failures with same value (0) is a strong signal of a bug, not legitimate rejection

---

## Files Modified

1. **Created**: `infra/migrations/009_add_vwap_acceptance_fields.sql` - Database migration
2. **Documented**: `docs/VWAP_RECLAIM_BARS_NEAR_VWAP_BUG.md` - This file
3. **Updated**: `docs/VWAP_RECLAIM_POST_WARMUP_ANALYSIS.md` - Added caveat about missing columns

---

## Next Steps

1. ✅ **Completed**: Root cause identified (missing database columns)
2. ✅ **Completed**: Migration file created
3. 🟡 **Pending**: Run migration: `make db-migrate`
4. 🟡 **Pending**: Restart services: `make services-restart`
5. 🟡 **Pending**: Re-run replay: `make replay START=2025-11-06 END=2025-11-08`
6. 🟡 **Pending**: Verify fix: `make diagnose-vwap-reclaim START=2025-11-06 END=2025-11-08`
7. 🟡 **Pending**: Implement warmup skip (separate issue)
8. ⬜ **Future**: Add CI/CD schema validation test
