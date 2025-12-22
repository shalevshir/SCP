# Short VWAP_RECLAIM DXY Threshold Asymmetry Fix

**Date:** 2025-12-20  
**Status:** ✅ Fixed and Tested  
**Component:** `backtester/invalidations.py`

## Problem

The DXY invalidation logic for VWAP_RECLAIM trades had an asymmetric threshold between long and short trades that violated the documented fix intent.

### Original Code (Lines 547-551)

```python
if trade.direction == "long":
    # Long: exit only if correlation flips to >= 0.0 (hard flip)
    condition_met = dxy_corr >= 0.0
else:  # short
    # Short: exit only if correlation becomes strongly inverse
    condition_met = dxy_corr < -0.6
```

### Issue

The comment on lines 536-538 claimed "require stronger threshold AND 3-bar persistence", but:

1. **Long trades:** Threshold was correctly hardened from VWAP_FADE's `> -0.3` to `>= 0.0` (sign flip detection)
2. **Short trades:** Threshold was **NOT hardened** - remained at `< -0.6` (same as VWAP_FADE)

This created two problems:

| Trade | Expected Correlation | Wrong Threshold | Issue |
|-------|---------------------|-----------------|-------|
| Long  | negative (DXY ↓, GC ↑) | `>= 0.0` ✅ | Correct sign flip |
| Short | positive (DXY ↑, GC ↓) | `< -0.6` ❌ | Detects extreme inverse, not sign flip |

The short threshold `< -0.6` is conceptually wrong because:
- It does NOT detect when positive correlation flips to non-positive
- It only triggers on extreme inverse correlation (which is actually BULLISH for GC)
- Short VWAP_RECLAIM only got 3-bar persistence benefit, not the "stronger threshold"

## Root Cause

The fix author applied **magnitude symmetry** (`+0.3` shift for both) instead of **sign flip symmetry** (crossing zero against trade direction).

## Solution

Changed short VWAP_RECLAIM to use sign flip detection (`<= 0.0`), matching the conceptual symmetry with long trades:

### Fixed Code (Lines 549-551)

```python
else:  # short
    # Short: exit only if correlation loses positive alignment (<= 0.0)
    condition_met = dxy_corr <= 0.0
```

### Correct Symmetry

| Direction | Expected Correlation | Exit When (Sign Flip) | Persistence |
|-----------|---------------------|----------------------|-------------|
| Long      | negative            | `>= 0.0` (no longer negative) | 3 bars |
| Short     | positive            | `<= 0.0` (no longer positive) | 3 bars |

Both directions now detect when correlation **crosses zero** against the trade direction, with 3-bar persistence to prevent noise.

## Changes Made

### 1. Code Fix (`backtester/invalidations.py`)

**Line 536-540:** Updated comment to reflect sign flip logic

```python
# FIX: For VWAP_RECLAIM, require sign flip detection AND 3-bar persistence
# DXY is a pre-entry gate (SOP), not an aggressive intra-trade kill switch
# Exit when correlation flips against trade direction (sign flip), persisting 3+ bars
# Long: exit when corr >= 0.0 (no longer negative)
# Short: exit when corr <= 0.0 (no longer positive)
```

**Line 549-551:** Changed short threshold from `< -0.6` to `<= 0.0`

```python
else:  # short
    # Short: exit only if correlation loses positive alignment (<= 0.0)
    condition_met = dxy_corr <= 0.0
```

### 2. Test Coverage (`tests/unit/backtester/test_dxy_invalidation.py`)

Added comprehensive test `test_vwap_reclaim_short_sign_flip_detection` that verifies:

1. **Positive correlation (0.3):** Does NOT trigger invalidation ✅
2. **Zero correlation (0.0) for 3 bars:** Triggers invalidation (sign flip at boundary) ✅
3. **Negative correlation (-0.5) for 3 bars:** Triggers invalidation (sign flip to negative) ✅

## Verification

### Test Results

```bash
$ poetry run pytest tests/unit/backtester/test_dxy_invalidation.py -v
======================== 11 passed in 0.33s =========================

$ poetry run pytest tests/unit/backtester/ -v
======================== 425 passed, 4 skipped in 2.45s =========================
```

All tests pass, confirming:
- ✅ Short VWAP_RECLAIM now uses sign flip detection
- ✅ No regressions in other backtester logic
- ✅ 3-bar persistence still enforced

### Comparison Table

| Scenario | Old Behavior | New Behavior |
|----------|-------------|--------------|
| Short, dxy_corr = 0.3 | No exit | No exit ✅ |
| Short, dxy_corr = 0.0 (3 bars) | No exit ❌ | Exit ✅ (sign flip) |
| Short, dxy_corr = -0.5 (3 bars) | No exit ❌ | Exit ✅ (sign flip) |
| Short, dxy_corr = -0.7 (3 bars) | Exit ⚠️ | Exit ✅ (sign flip) |

The new behavior correctly exits when correlation loses positive alignment, not just when it becomes extremely negative.

## Impact

### Before Fix
- Short VWAP_RECLAIM trades would remain open even when DXY correlation flipped from positive to negative
- Only exited on extreme inverse correlation (`< -0.6`), which is rare and indicates GC bullishness
- Asymmetric treatment meant shorts were exposed to correlation regime changes longer than intended

### After Fix
- Short VWAP_RECLAIM exits when correlation crosses zero (loses positive alignment)
- Symmetric sign flip logic for both long and short trades
- Consistent with SOP intent: DXY is a pre-entry gate, exit on regime change

## Related Files

- `backtester/invalidations.py` - Core invalidation logic
- `tests/unit/backtester/test_dxy_invalidation.py` - Test coverage
- `backtester/simulator.py` - Exit reason mapping (unchanged)
- `backtester/trade.py` - Exit reason validation (unchanged)

## Follow-up

None required. Fix is complete and verified.

---

**Issue Reporter:** User  
**Fix Implemented By:** Assistant  
**Reviewed By:** TDD (all tests pass)


