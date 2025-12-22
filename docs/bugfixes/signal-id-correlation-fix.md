# Bug Fix: Signal-Trade Correlation in Redis Events

**Date:** December 22, 2025  
**Component:** Execution Service - TradeManager & TradeRecord  
**Severity:** High (Data Integrity)

## Problem

The `TradeManager` was publishing incorrect `signal_id` values in `trades.closed` Redis stream events. Instead of using the actual signal ID from the originating signal, it was using the trade ID, breaking signal-trade correlation for downstream analytics and monitoring services.

### Root Cause

The `TradeRecord` dataclass lacked a `signal_id` field, even though:
1. The database stores and queries `signal_id` values
2. The repository retrieves `signal_id` from the database
3. The signal-trade relationship is critical for analytics

This caused:
```python
# BEFORE (buggy)
trade_msg = TradeMessage(
    id=trade.trade_id,
    signal_id=str(trade.trade_id),  # ❌ WRONG! Using trade_id as signal_id
    direction=trade.direction,
    ...
)
```

### Impact

1. **Broken Analytics**: Downstream services cannot correlate trades back to their originating signals
2. **False Correlations**: Each trade appears to be its own signal (signal_id == trade_id)
3. **Lost Signal Tracking**: Cannot track which signals led to multiple trades (re-entries)
4. **Monitoring Gaps**: Signal performance metrics are incorrect
5. **Audit Trail Issues**: Cannot trace decisions back to originating signals

## Solution

### 1. Add `signal_id` Field to `TradeRecord`

```python
# services/shared/src/scp_shared/execution/types.py
@dataclass
class TradeRecord:
    """Minimal trade record for invalidation checking."""
    
    trade_id: str
    signal_id: str  # ✅ NEW: Source signal ID for correlation
    symbol: str
    direction: str
    # ... rest of fields
```

### 2. Populate `signal_id` from Database

```python
# services/execution/src/execution_svc/trade_repository.py

# In get_trade():
return TradeRecord(
    trade_id=str(row["id"]),
    signal_id=str(row["signal_id"]),  # ✅ Populated from DB
    symbol="GC",
    # ... rest of fields
)

# In get_open_trades():
trade = TradeRecord(
    trade_id=str(row["id"]),
    signal_id=str(row["signal_id"]),  # ✅ Populated from DB
    symbol="GC",
    # ... rest of fields
)
```

### 3. Set `signal_id` When Creating Trades

```python
# services/execution/src/execution_svc/trade_manager.py

# In _execute_trade():
trade = TradeRecord(
    trade_id=trade_id,
    signal_id=signal.id,  # ✅ Set from incoming signal
    symbol="GC",
    # ... rest of fields
)
```

### 4. Use Correct `signal_id` When Publishing

```python
# services/execution/src/execution_svc/trade_manager.py

# In _close_trade():
trade_msg = TradeMessage(
    id=trade.trade_id,
    signal_id=trade.signal_id,  # ✅ FIXED! Use actual signal_id
    direction=trade.direction,
    # ... rest of fields
)
```

## Test Coverage

Created comprehensive test suite (`test_signal_id_correlation.py`):

### Test 1: Repository Includes signal_id
```python
async def test_trade_record_includes_signal_id():
    """Verify TradeRecord loaded from DB includes signal_id."""
    trade = await repo.get_trade(trade_id)
    
    assert trade.signal_id == signal_id
    assert trade.signal_id != trade.trade_id  # Must be different!
```

### Test 2: Open Trades Include signal_id
```python
async def test_open_trades_include_signal_id():
    """Verify get_open_trades() includes signal_id."""
    trades = await repo.get_open_trades()
    
    assert trades[0].signal_id == signal_id_1
    assert trades[1].signal_id == signal_id_2
```

### Test 3: Published Events Have Correct signal_id
```python
async def test_published_trade_closed_event_has_correct_signal_id():
    """Verify trades.closed event contains correct signal_id."""
    # Create trade with signal_id
    trade = TradeRecord(trade_id=trade_id, signal_id=signal_id, ...)
    
    # Close trade
    await manager._close_trade(trade, ...)
    
    # Verify published event
    published_trade = mock_publisher.publish_closed.call_args[0][0]
    assert published_trade.signal_id == signal_id  # ✅ Correct!
    assert published_trade.signal_id != trade_id   # ✅ Not trade_id!
```

All tests pass ✅

## Before vs. After

### Before (Bug)

```python
# Database query includes signal_id
SELECT id, signal_id, direction, ... FROM trades WHERE id = $1

# But TradeRecord doesn't have signal_id field
TradeRecord(
    trade_id="trade-123",
    # signal_id missing!
    symbol="GC",
    ...
)

# Published event uses trade_id as signal_id
TradeMessage(
    id="trade-123",
    signal_id="trade-123",  # ❌ WRONG!
    ...
)

# Redis stream event
{
    "id": "trade-123",
    "signal_id": "trade-123",  # ❌ Same as trade_id!
    ...
}
```

### After (Fixed)

```python
# Database query includes signal_id
SELECT id, signal_id, direction, ... FROM trades WHERE id = $1

# TradeRecord now has signal_id field
TradeRecord(
    trade_id="trade-123",
    signal_id="signal-456",  # ✅ From database!
    symbol="GC",
    ...
)

# Published event uses actual signal_id
TradeMessage(
    id="trade-123",
    signal_id="signal-456",  # ✅ CORRECT!
    ...
)

# Redis stream event
{
    "id": "trade-123",
    "signal_id": "signal-456",  # ✅ Correct correlation!
    ...
}
```

## Files Modified

1. **services/shared/src/scp_shared/execution/types.py**
   - Added `signal_id: str` field to `TradeRecord`

2. **services/execution/src/execution_svc/trade_repository.py**
   - `get_trade()`: Populate `signal_id=str(row["signal_id"])`
   - `get_open_trades()`: Populate `signal_id=str(row["signal_id"])`

3. **services/execution/src/execution_svc/trade_manager.py**
   - `_execute_trade()`: Set `signal_id=signal.id` when creating TradeRecord
   - `_close_trade()`: Use `signal_id=trade.signal_id` (not `str(trade.trade_id)`)

4. **Test Fixtures Updated** (to include `signal_id` field):
   - `tests/unit/test_trade_repository.py`
   - `tests/unit/test_trade_manager_error_handling.py`
   - `tests/unit/test_invalidation.py`
   - `tests/unit/test_trade_persistence_on_restart.py` (3 instances)

5. **New Test Suite**:
   - `tests/unit/test_signal_id_correlation.py` (NEW)

## Downstream Impact

This fix enables:

1. **Signal Performance Tracking**: Which signals generate winning vs. losing trades
2. **Setup Analysis**: Compare VWAP_RECLAIM vs. VWAP_FADE signal success rates
3. **Re-Entry Tracking**: Multiple trades from same signal (e.g., after invalidation)
4. **HTF Bias Correlation**: Which HTF bias conditions produce best signals
5. **Time-of-Day Analysis**: Signal performance by time of day
6. **Audit Trail**: Full traceability from signal → trade → outcome

## Verification

```bash
cd services/execution

# Run new tests
poetry run pytest tests/unit/test_signal_id_correlation.py -xvs
# ✅ 3 tests passed

# Run all tests
poetry run pytest tests/unit/ -x
# ✅ 54 tests passed

# Check linters
poetry run ruff check src/
poetry run mypy src/
# ✅ No errors
```

## Migration Notes

- **Breaking Change**: `TradeRecord` now requires `signal_id` parameter
- **Existing Code**: All code creating `TradeRecord` must provide `signal_id`
- **Database Schema**: No changes needed (already stores signal_id)
- **Backwards Compatibility**: None - this is a bug fix that changes data structure

## Future Enhancements

Consider adding:
1. Foreign key constraint: `trades.signal_id → signals.id`
2. Index on `signal_id` for faster queries
3. Analytics view: `signal_performance` joining signals and trades
4. Dashboard: Signal-to-trade correlation metrics

---

**Implemented By:** AI Assistant  
**Reviewed By:** TDD (all tests pass)  
**Status:** Complete ✅

