# Partial Profit Implementation Bugs - Critical Analysis

**Date:** 2026-02-10
**Severity:** High (all three bugs)
**Phase:** 7 (DXY_CONTINUATION partial profit + runner management)
**Status:** In Progress

## Overview

Three interconnected bugs in the DXY_CONTINUATION partial profit implementation corrupt trade analytics, P&L calculations, and state management. These bugs affect **all** DXY_CONTINUATION trades that reach +1R, regardless of whether they're single-contract or multi-contract positions.

---

## Bug #1: `update_breakeven` Overwrites Original SL Price

### Problem

`TradeRepository.update_breakeven()` **overwrites the `sl_price` column** with the breakeven price (entry ± 0.1R buffer). When the trade closes, `close_trade()` reads this corrupted `sl_price` to compute `risk_amount`, resulting in:

- **Negative risk_amount** for longs (BE > entry, so entry - BE < 0)
- **Negative risk_amount** for shorts (BE < entry, so BE - entry < 0)
- **R_multiple stored as 0.0** in database (due to corrupted risk calculation)

### Code Location

**File:** `services/execution/src/execution_svc/trade_repository.py`
**Lines:** 337-352

```python
async def update_breakeven(self, trade_id: str, be_price: float) -> None:
    """Update breakeven SL price for a trade."""
    query = """
        UPDATE trades
        SET sl_price = $1  # ❌ BUG: Overwrites original SL!
        WHERE id = $2
    """
    await self._db_pool.execute(query, be_price, UUID(trade_id))
```

**File:** `services/execution/src/execution_svc/trade_repository.py`
**Lines:** 159-221 (`close_trade` method)

```python
async def close_trade(self, trade_id: str, exit_price: float, ...):
    # Read trade from DB
    query = "SELECT ... sl_price ... FROM trades WHERE id = $1"
    row = await self._db_pool.fetchrow(query, UUID(trade_id))

    # ❌ BUG: sl_price is now BE price, not original SL!
    sl_price = row["sl_price"]  # Returns BE price (2650 + 1.0 = 2651.0)

    # Calculate risk (WRONG for longs with BE set)
    if row["direction"] == "long":
        risk_amount = entry_price - sl_price  # 2650 - 2651 = -1.0 ❌

    # R-multiple calculation
    if risk_amount != 0:
        r_multiple = pnl_points / risk_amount  # ANY_PNL / -1.0 = negative
    else:
        r_multiple = 0.0  # ❌ Stored as 0.0 in database
```

### Impact

- **All DXY_CONTINUATION trades** that reach +1R (including single-contract trades that can't execute partial close) have `r_multiple = 0.0` in the database
- **Analytics corrupted** - can't measure actual R performance
- **Trade journal unusable** - R-multiples don't reflect actual risk/reward

### Example

Long trade:
- Entry: 2650.0
- Original SL: 2640.0 (risk = 10.0 points)
- TP: 2680.0
- Reaches +1R → BE set to 2651.0 (entry + 0.1R)
- `update_breakeven` overwrites `sl_price` column: 2640.0 → 2651.0
- Trade exits at 2675.0 (pnl = +25 points)
- `close_trade` reads sl_price = 2651.0
- risk_amount = 2650 - 2651 = **-1.0**
- r_multiple = 25 / -1.0 = **-25.0** (stored as 0.0 due to validation)

---

## Bug #2: Trade Quantity Not Updated After Partial Close

### Problem

After `reduce_position()` succeeds, `trade.quantity` is **never decremented** on the `TradeRecord`, and **no database update** is made for the reduced quantity.

The broker's internal position tracking is updated correctly, but:
1. The in-memory `TradeRecord` retains the original quantity
2. The database `trades.quantity` column retains the original quantity
3. When the remaining position closes, `close_trade()` multiplies `pnl_points * quantity` using the **stale original quantity**, producing incorrect dollar P&L

### Code Location

**File:** `services/execution/src/execution_svc/trade_manager.py`
**Lines:** 546-585

```python
# Calculate 40% of position
partial_qty = int(trade.quantity * 0.4)  # e.g., 5 contracts → 2 contracts

try:
    if partial_qty >= 1:
        await self._broker.reduce_position(
            trade.symbol, partial_qty, candle.close
        )
        logger.info(f"Partial profit executed successfully...")
        # ❌ BUG: trade.quantity is NEVER updated!
        # Should be: trade.quantity -= partial_qty
except Exception as e:
    logger.error(f"Failed to execute partial profit...")

# Update trade state (unconditional - see Bug #3)
trade.partial_taken = True
trade.current_sl_price = be_price
# ❌ Still missing: trade.quantity update and DB persistence
```

**No `update_quantity` method exists** in `TradeRepository`.

### Impact

- **Dollar P&L corrupted** for all multi-contract DXY_CONTINUATION trades
- Example: 5-contract trade closes 2 contracts (40%), then closes remaining 3 contracts
  - Partial close P&L: 2 contracts × 100 points × $100/point = **$20,000** (correct)
  - Final close reads `quantity = 5` from DB (stale)
  - Final close P&L: 5 contracts × 50 points × $100/point = **$25,000** (should be 3 × 50 × $100 = **$15,000**)
  - **Total P&L overstated by $10,000**

### Cascade Effects

1. Daily P&L tracking (`DailyStateTracker`) receives incorrect P&L
2. PDLL (Per-Day Loss Limit) calculations are wrong
3. Trade count appears higher than actual (database shows 5 contracts, actually 3 remaining)
4. Analytics/reporting show inflated profits

---

## Bug #3: Partial Profit State Persists on Broker Failure

### Problem

When `reduce_position()` raises an exception, the `except` block only logs the error. Execution **falls through** to unconditionally set:
- `trade.partial_taken = True`
- `trade.breakeven_set = True`
- `trade.be_set = True`
- Persist BE to database

This means:
1. A **failed broker call** permanently marks the trade as having taken partial profit
2. The trade is **prevented from retrying** partial profit (check: `if action == "partial_profit" and not trade.partial_taken`)
3. The stop loss is **moved to breakeven** even though the position was **never actually reduced**

### Code Location

**File:** `services/execution/src/execution_svc/trade_manager.py`
**Lines:** 567-585

```python
try:
    if partial_qty >= 1:
        await self._broker.reduce_position(...)
        logger.info(f"Partial profit executed successfully...")
    else:
        logger.warning(f"Partial profit NOT executed...")
except Exception as e:
    logger.error(f"Failed to execute partial profit...")
    # ❌ BUG: Exception caught but execution continues!

# ❌ BUG: These updates happen UNCONDITIONALLY
trade.partial_taken = True  # FALSE POSITIVE - broker call may have failed!
trade.breakeven_set = True
trade.current_sl_price = be_price
trade.be_set = True
trade.be_price = be_price
trade.be_set_bar_idx = self._sm_manager._bar_counter
trade.tp1_hit_bar_idx = self._sm_manager._bar_counter

# ❌ BUG: BE persisted to DB even if reduce_position failed
await self._repo.update_breakeven(trade.trade_id, be_price)
```

### Impact

- **Broker failures silently corrupt trade state**
- **Position still at full size** but system thinks 40% was closed
- **SL moved to breakeven** exposing full position to smaller stop
- **Partial profit can never retry** (blocked by `not trade.partial_taken` check)
- **Runner unlock logic fails** (requires `partial_taken = True` which is now a lie)

### Failure Scenarios

1. **Network timeout** during broker API call
2. **Insufficient margin** (broker rejects reduce order)
3. **Order rejection** (price slippage, market closed, etc.)
4. **Broker API error** (rate limit, server error, etc.)

All of these leave the trade in an **inconsistent state** where the system believes partial profit was taken but the broker position remains unchanged.

---

## Root Cause Analysis

### Design Flaw: Database Schema

The `trades` table has **one `sl_price` column** that serves two purposes:
1. **Original risk calculation** (for R-multiple)
2. **Current stop loss** (for trade management)

These are **not the same** after breakeven is set:
- Original SL: Entry ± 1R (e.g., 2640.0 for long at 2650.0)
- Current SL (BE): Entry ± 0.1R (e.g., 2651.0 for long at 2650.0)

**Overwriting `sl_price` destroys the original risk data.**

### Design Flaw: Missing Atomicity

The partial profit operation has **three state changes** that must succeed **atomically**:
1. Broker position reduction
2. In-memory trade state update
3. Database persistence

Currently, these are **not atomic** - failure at any step leaves inconsistent state.

### Design Flaw: Missing Rollback

There's **no rollback logic** if broker call fails:
- State updates happen unconditionally
- Database updates happen even on failure
- No way to recover from failed partial profit attempt

---

## Proposed Solution

### 1. Add `original_sl_price` Column

**Migration:** `013_add_original_sl_price.sql`

```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'trades' AND column_name = 'original_sl_price'
    ) THEN
        ALTER TABLE trades ADD COLUMN original_sl_price NUMERIC(12,4);

        -- Backfill existing trades: copy sl_price to original_sl_price
        UPDATE trades
        SET original_sl_price = sl_price
        WHERE original_sl_price IS NULL;

        -- Make it NOT NULL after backfill
        ALTER TABLE trades ALTER COLUMN original_sl_price SET NOT NULL;

        COMMENT ON COLUMN trades.original_sl_price IS
            'Original SL price (never changes) - used for R-multiple calculation';
        COMMENT ON COLUMN trades.sl_price IS
            'Current SL price (may change to BE) - used for trade management';
    END IF;
END $$;
```

### 2. Update `insert_trade` to Set Both Columns

```python
async def insert_trade(self, ...):
    query = """
        INSERT INTO trades (
            ..., sl_price, original_sl_price, ...
        ) VALUES (
            ..., $5, $5, ...  -- Both set to original SL
        )
        RETURNING id
    """
```

### 3. Update `close_trade` to Use `original_sl_price`

```python
async def close_trade(self, trade_id: str, exit_price: float, ...):
    query = """
        SELECT ..., original_sl_price, sl_price, ...
        FROM trades WHERE id = $1
    """
    row = await self._db_pool.fetchrow(query, UUID(trade_id))

    # Use original_sl_price for R-multiple calculation
    original_sl = row["original_sl_price"]

    if row["direction"] == "long":
        risk_amount = entry_price - original_sl  # ✅ Always correct

    r_multiple = pnl_points / risk_amount if risk_amount != 0 else 0.0
```

### 4. Add `update_quantity` Method

```python
async def update_quantity(self, trade_id: str, new_quantity: int) -> None:
    """Update trade quantity after partial close.

    Args:
        trade_id: Trade ID
        new_quantity: New quantity after reduction
    """
    query = """
        UPDATE trades
        SET quantity = $1
        WHERE id = $2
    """
    await self._db_pool.execute(query, new_quantity, UUID(trade_id))
    logger.info(f"Updated trade {trade_id} quantity to {new_quantity}")
```

### 5. Make State Updates Conditional on Broker Success

```python
# Execute partial profit: close 40% of position at TP1
partial_qty = int(trade.quantity * 0.4)
broker_success = False  # Track broker operation success

try:
    if partial_qty >= 1:
        await self._broker.reduce_position(
            trade.symbol, partial_qty, candle.close
        )
        broker_success = True  # ✅ Mark success
        logger.info(f"Partial profit executed successfully...")
    else:
        # Single contract: can't execute partial but can move to BE
        broker_success = True  # ✅ No broker call needed
        logger.warning(f"Partial profit NOT executed - quantity={trade.quantity}...")
except Exception as e:
    broker_success = False  # ❌ Mark failure
    logger.error(f"Failed to execute partial profit: {e}", exc_info=True)
    # ❌ DO NOT update state - return early
    return  # Or continue without state updates

# ✅ ONLY update state if broker succeeded
if broker_success:
    # Update in-memory trade state
    trade.partial_taken = True
    trade.breakeven_set = True
    trade.current_sl_price = be_price
    trade.be_set = True
    trade.be_price = be_price
    trade.be_set_bar_idx = self._sm_manager._bar_counter
    trade.tp1_hit_bar_idx = self._sm_manager._bar_counter

    # Update quantity if partial was actually executed
    if partial_qty >= 1:
        new_quantity = trade.quantity - partial_qty
        trade.quantity = new_quantity
        await self._repo.update_quantity(trade.trade_id, new_quantity)

    # Persist BE state to database
    await self._repo.update_breakeven(trade.trade_id, be_price)
```

### 6. Update `update_breakeven` Documentation

```python
async def update_breakeven(self, trade_id: str, be_price: float) -> None:
    """Update current SL price to breakeven.

    NOTE: This updates sl_price (current stop), NOT original_sl_price.
    The original_sl_price is preserved for R-multiple calculation.

    Args:
        trade_id: Trade ID
        be_price: Breakeven stop loss price (entry ± 0.1R buffer)
    """
```

---

## Testing Strategy

### Unit Tests

1. **Test original_sl_price preservation**
   - Insert trade with SL = 2640.0
   - Update BE to 2651.0
   - Close trade at 2675.0
   - Verify: `original_sl_price = 2640.0`, `sl_price = 2651.0`, `r_multiple = 2.5`

2. **Test quantity update after partial close**
   - Insert 5-contract trade
   - Execute partial profit (close 2 contracts)
   - Verify: `quantity = 3`, trade.quantity = 3
   - Close remaining 3 contracts
   - Verify: P&L uses quantity = 3

3. **Test broker failure rollback**
   - Mock `reduce_position` to raise exception
   - Trigger partial profit
   - Verify: `partial_taken = False`, `sl_price` unchanged, `quantity` unchanged

4. **Test single-contract behavior**
   - Insert 1-contract trade
   - Trigger partial profit (should log warning, NOT execute broker call)
   - Verify: `partial_taken = True`, `sl_price` moved to BE, `quantity = 1` (unchanged)

### Integration Tests

1. Full partial profit flow with 5-contract position
2. Partial profit with broker API timeout
3. Backfill migration test (existing trades get `original_sl_price = sl_price`)

---

## Deployment Plan

1. **Create migration** `013_add_original_sl_price.sql`
2. **Run migration** on dev/test environments
3. **Update TradeRepository**:
   - `insert_trade()` - set both columns
   - `close_trade()` - use `original_sl_price`
   - `update_quantity()` - new method
4. **Update TradeManager**:
   - Conditional state updates
   - Quantity tracking
5. **Run full test suite**
6. **Deploy to staging**
7. **Backtest verification** (ensure R-multiples are correct)
8. **Deploy to production**

---

## Severity Assessment

| Bug | Severity | Impact | Affected Trades |
|-----|----------|--------|----------------|
| #1: SL overwrite | **HIGH** | Corrupted R-multiples in DB | All DXY_CONTINUATION trades that reach +1R |
| #2: Quantity not updated | **HIGH** | Inflated P&L | All multi-contract DXY_CONTINUATION trades |
| #3: State persistence on failure | **HIGH** | Trade corruption | Any DXY_CONTINUATION trade with broker failure |

**Overall Severity: CRITICAL** - All three bugs must be fixed together to ensure data integrity.
