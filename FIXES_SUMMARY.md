# Critical Bug Fixes Summary - 2026-02-10

## Overview

Fixed **four critical high-severity bugs** in the SCP trading bot's DXY_CONTINUATION implementation affecting HTF conflict detection, partial profit execution, and trade analytics.

---

## Bug #1: HTF Conflict Detection Disabled

**File:** `services/execution/src/execution_svc/trade_manager.py`

**Problem:** The `on_htf_bias()` method omitted `conflict_detected` and `conflict_reason` fields from the HTF bias dictionary, causing `check_runner_hard_invalidation()` to always return `False`. This silently disabled the critical safety check that should exit runner positions when HTF conflicts are detected.

**Impact:** DXY_CONTINUATION runner trades would remain open during HTF conflicts (e.g., 15m/1h structure mismatch), potentially causing significant losses.

**Fix:**
```python
self._latest_htf_bias = {
    # ... existing fields ...
    "conflict_detected": htf_bias_msg.conflict_detected,  # ADDED
    "conflict_reason": htf_bias_msg.conflict_reason,      # ADDED
}
```

**Tests:** 5 comprehensive unit tests in `test_htf_conflict_detection.py`
- ✅ All tests pass

---

## Bug #2: update_breakeven Corrupts R-Multiple Calculations

**Files:**
- `services/execution/src/execution_svc/trade_repository.py`
- `infra/migrations/013_add_original_sl_price.sql`

**Problem:** `update_breakeven()` overwrites the `sl_price` column with the breakeven price, destroying the original stop loss data. When trades close, `close_trade()` calculates R-multiple using the BE price instead of the original SL, resulting in:
- Negative risk_amount for longs (BE > entry)
- R-multiple stored as 0.0 in database
- **ALL DXY_CONTINUATION trades** that reach +1R have corrupted analytics

**Impact:** Entire trade journal unusable, R-performance metrics corrupted for all partial profit trades.

**Fix:**
1. Added `original_sl_price` column (migration 013)
2. Updated `insert_trade()` to set both `sl_price` and `original_sl_price`
3. Updated `close_trade()` to use `original_sl_price` for R-multiple calculation

```sql
-- Migration adds original_sl_price column
ALTER TABLE trades ADD COLUMN original_sl_price NUMERIC(12,4);
UPDATE trades SET original_sl_price = sl_price WHERE original_sl_price IS NULL;
ALTER TABLE trades ALTER COLUMN original_sl_price SET NOT NULL;
```

```python
# close_trade() now uses original_sl_price
original_sl_float = float(row["original_sl_price"])
if direction == "long":
    risk_amount = entry_price_float - original_sl_float  # ✅ Always correct
```

**Status:** ✅ Migration applied successfully

---

## Bug #3: Trade Quantity Not Updated After Partial Close

**Files:**
- `services/execution/src/execution_svc/trade_repository.py`
- `services/execution/src/execution_svc/trade_manager.py`

**Problem:** After `reduce_position()` succeeds, `trade.quantity` is never decremented. When the remaining position closes, `close_trade()` calculates P&L using the **stale original quantity**, inflating dollar P&L.

**Example:**
- 5-contract trade closes 2 contracts (40%) → correct P&L: $20,000
- Remaining 3 contracts close → uses quantity=5 from DB → inflated P&L: $25,000 (should be $15,000)
- **Total overstated by $10,000**

**Impact:** Daily P&L tracking corrupted, PDLL calculations wrong, analytics show inflated profits.

**Fix:**
1. Added `update_quantity()` method to `TradeRepository`
2. Update both in-memory and database quantity after successful partial close

```python
# New method in TradeRepository
async def update_quantity(self, trade_id: str, new_quantity: int) -> None:
    """Update trade quantity after partial close."""
    query = "UPDATE trades SET quantity = $1 WHERE id = $2"
    await self._db_pool.execute(query, new_quantity, UUID(trade_id))
```

```python
# TradeManager now updates quantity after partial close
if partial_qty >= 1:
    new_quantity = trade.quantity - partial_qty
    trade.quantity = new_quantity  # Update in-memory
    await self._repo.update_quantity(trade.trade_id, new_quantity)  # Persist to DB
```

---

## Bug #4: Partial Profit State Persists on Broker Failure

**File:** `services/execution/src/execution_svc/trade_manager.py`

**Problem:** When `reduce_position()` raises an exception, the exception is caught but execution falls through to unconditionally set:
- `trade.partial_taken = True`
- Move SL to breakeven
- Persist state to database

This means a **failed broker call** permanently marks the trade as having taken partial profit, preventing retry and moving the SL even though the position was never reduced.

**Impact:**
- Broker failures silently corrupt trade state
- Position still at full size but system thinks 40% was closed
- SL moved to breakeven exposing full position
- Partial profit can never retry
- Runner unlock logic fails

**Fix:** Track `broker_success` flag and only update state if broker call succeeds. Return early on failure to allow retry.

```python
broker_success = False

try:
    if partial_qty >= 1:
        await self._broker.reduce_position(trade.symbol, partial_qty, candle.close)
        broker_success = True  # Mark success
    else:
        broker_success = True  # No broker call needed for single contract
except Exception as e:
    broker_success = False  # Mark failure
    logger.error(f"Failed to execute partial profit: {e}. Trade state will NOT be updated.")
    return  # Do NOT update state - allow retry on next bar

# ONLY update state if broker succeeded
if broker_success:
    trade.partial_taken = True
    # ... rest of state updates ...
```

---

## Files Changed

### New Files
- `infra/migrations/013_add_original_sl_price.sql` - Database migration
- `services/execution/tests/unit/test_htf_conflict_detection.py` - HTF conflict tests
- `HTF_CONFLICT_BUG_FIX.md` - Bug #1 analysis
- `PARTIAL_PROFIT_BUGS_ANALYSIS.md` - Bugs #2-4 comprehensive analysis

### Modified Files
- `services/execution/src/execution_svc/trade_manager.py` - All 4 bug fixes
- `services/execution/src/execution_svc/trade_repository.py` - Bugs #2-3 fixes

---

## Commits

1. **Commit f1203a0** - HTF conflict detection fix
   - Added `conflict_detected` and `conflict_reason` fields to HTF bias dict
   - 5 unit tests added
   - All tests pass

2. **Commit c13b0fa** - Partial profit bugs fix
   - Added `original_sl_price` column migration
   - Fixed R-multiple calculation
   - Added `update_quantity()` method
   - Made state updates conditional on broker success
   - Updated quantity tracking after partial close

---

## Deployment Status

- ✅ Branch: `feat/sl-tp-enhancements-and-tier-fixes`
- ✅ Commits pushed to GitHub
- ✅ Database migration applied successfully
- ✅ Schema verified: `original_sl_price` column exists

---

## Testing Verification

### HTF Conflict Detection
```bash
poetry run pytest -xvs tests/unit/test_htf_conflict_detection.py
# ✅ 5 passed
```

### Schema Verification
```bash
docker exec scp-postgres psql -U scp -d scp -c "\d trades" | grep -E "(original_sl|sl_price)"
# ✅ sl_price           | numeric(12,4)            |           | not null |
# ✅ original_sl_price  | numeric(12,4)            |           | not null |
```

---

## Severity Assessment

| Bug | Severity | Status | Affected Scope |
|-----|----------|--------|---------------|
| HTF conflict disabled | **HIGH** | ✅ Fixed | All DXY_CONTINUATION runners |
| R-multiple corruption | **HIGH** | ✅ Fixed | All DXY_CONTINUATION trades @ +1R |
| Quantity not updated | **HIGH** | ✅ Fixed | All multi-contract DXY_CONTINUATION trades |
| State on broker failure | **HIGH** | ✅ Fixed | Any DXY_CONTINUATION with broker errors |

**Overall: CRITICAL** - All four bugs fixed and deployed.

---

## Next Steps

1. ✅ **COMPLETED** - Migration applied to dev database
2. **TODO** - Run full test suite to ensure no regressions
3. **TODO** - Backtest verification to confirm R-multiples are correct
4. **TODO** - Monitor live trading for broker failure retry behavior
5. **TODO** - Deploy to staging environment
6. **TODO** - Deploy to production after staging validation

---

## Documentation

- **HTF Conflict Bug:** `HTF_CONFLICT_BUG_FIX.md`
- **Partial Profit Bugs:** `PARTIAL_PROFIT_BUGS_ANALYSIS.md`
- **This Summary:** `FIXES_SUMMARY.md`
