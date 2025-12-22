# Bug Fix: Trade Publisher Zero P&L Logging

**Date:** December 22, 2025  
**Component:** Execution Service - TradePublisher  
**Severity:** Low (Cosmetic/Logging)

## Problem

The `TradePublisher.publish_closed()` method incorrectly logged "N/A" for trades that closed exactly at entry price (P&L = 0.0), making it impossible to distinguish between missing P&L data and true zero P&L.

### Root Cause

The condition `if trade.pnl_points` is falsy for `0.0`, causing the code to treat zero P&L the same as `None`:

```python
# BEFORE (buggy)
pnl_str = f"{trade.pnl_points:.2f} points" if trade.pnl_points else "N/A"
```

### Issue

In Python, `0.0` evaluates to `False` in boolean context:
```python
>>> bool(0.0)
False
>>> bool(None)
False
```

This caused trades exiting at entry price to log incorrectly:
```
✗ Published trade closed: long exit @ 2650.00 (pnl=N/A, reason=MANUAL_EXIT, trade_id=test-1)
                                                        ^^^^
                                                Should be "0.00 points"
```

## Impact

- **Cosmetic Only**: Only affects log messages, not trade state or P&L calculation
- **Ambiguity**: Cannot distinguish between:
  - Trades with missing P&L data (`pnl_points=None`)
  - Trades that broke even (`pnl_points=0.0`)
- **Debugging Confusion**: Makes analyzing break-even trades harder

## Solution

Changed the condition to explicitly check for `None`:

```python
# AFTER (fixed)
pnl_str = f"{trade.pnl_points:.2f} points" if trade.pnl_points is not None else "N/A"
```

This correctly handles all cases:
- `pnl_points=0.0` → `"0.00 points"` ✓
- `pnl_points=10.0` → `"10.00 points"` ✓
- `pnl_points=-5.0` → `"-5.00 points"` ✓
- `pnl_points=None` → `"N/A"` ✓

## Test Coverage

Created comprehensive test suite (`test_trade_publisher_zero_pnl.py`):

### Test 1: Zero P&L
```python
async def test_publish_closed_with_zero_pnl():
    """Test that trades with 0.0 P&L show '0.00 points' not 'N/A'."""
    trade = TradeMessage(
        ...,
        entry_price=2650.0,
        exit_price=2650.0,  # Break-even
        pnl_points=0.0,
    )
    
    await publisher.publish_closed(trade)
    
    # Verify log shows "pnl=0.00 points"
    assert "pnl=0.00 points" in log_message
```

### Test 2: Positive P&L
```python
async def test_publish_closed_with_positive_pnl():
    """Test that positive P&L is correctly formatted."""
    trade = TradeMessage(..., pnl_points=10.0)
    
    await publisher.publish_closed(trade)
    
    assert "pnl=10.00 points" in log_message
```

### Test 3: Negative P&L
```python
async def test_publish_closed_with_negative_pnl():
    """Test that negative P&L is correctly formatted."""
    trade = TradeMessage(..., pnl_points=-5.0)
    
    await publisher.publish_closed(trade)
    
    assert "pnl=-5.00 points" in log_message
```

### Test 4: None P&L
```python
async def test_publish_closed_with_none_pnl():
    """Test that None P&L is correctly formatted as 'N/A'."""
    trade = TradeMessage(..., pnl_points=None)
    
    await publisher.publish_closed(trade)
    
    assert "pnl=N/A" in log_message
```

All 4 tests pass ✅

## Before vs. After

### Before (Bug)
```
# Zero P&L
Published trade closed: long exit @ 2650.00 (pnl=N/A, ...)
                                                   ^^^^ Wrong!

# None P&L
Published trade closed: long exit @ 2650.00 (pnl=N/A, ...)
                                                   ^^^^ Correct
```

### After (Fixed)
```
# Zero P&L
Published trade closed: long exit @ 2650.00 (pnl=0.00 points, ...)
                                                   ^^^^^^^^^^^^ Correct!

# None P&L
Published trade closed: long exit @ 2650.00 (pnl=N/A, ...)
                                                   ^^^^ Still correct
```

## Files Modified

1. `services/execution/src/execution_svc/trade_publisher.py` - Fixed condition
2. `services/execution/tests/unit/test_trade_publisher_zero_pnl.py` (NEW) - Test suite

## Why This Matters

While cosmetic, this fix improves:
1. **Log Clarity**: Distinguish between missing data and break-even trades
2. **Debugging**: Easier to identify trades that exited at entry price
3. **Code Correctness**: Explicit `is not None` check is Pythonic best practice
4. **Future-Proofing**: Prevents confusion if zero P&L becomes meaningful

## Verification

```bash
cd services/execution

# Run new tests
poetry run pytest tests/unit/test_trade_publisher_zero_pnl.py -xvs
# ✅ 4 tests passed

# Run all tests
poetry run pytest tests/unit/ -x
# ✅ 28 tests passed
```

## Related Best Practices

This bug demonstrates a common Python pitfall. Always use explicit `is not None` checks for numeric values that can legitimately be zero:

```python
# ❌ BAD: Treats 0.0 as falsy
if value:
    ...

# ✅ GOOD: Explicitly checks for None
if value is not None:
    ...

# ✅ ALSO GOOD: For strict zero checks
if value != 0:
    ...
```

---

**Implemented By:** AI Assistant  
**Reviewed By:** TDD (all tests pass)  
**Status:** Complete ✅

