# Bug Fix: Streaming Structure Label Extraction

**Date**: 2025-12-09  
**Status**: ✅ Fixed  
**Severity**: High  
**Affected Modules**: `feature_engine/streaming.py`, HTF streaming calculator

---

## Problem

HTF structure labels (`structure_1h`, `structure_15m`) were consistently empty/None in the HTF calculator (`rule_engine/htf/calculator.py:55`) when using the streaming HTF approach, even when clear structure patterns existed in the data.

### Root Cause

The `StreamingFeatureProcessor` was using a **fixed position** to extract structure labels from the sparse labels series:

```python
# OLD (BUGGY) CODE
label_idx = len(labels_series) - self.swing_window - 1
current_label = labels_series.iloc[label_idx]
```

**Why this failed:**
- Structure labels are **sparse** - they only exist at actual swing points (HH/HL/LH/LL)
- Most bars have `None` or `pd.NA` for structure_label
- Using a fixed index `len - swing_window - 1` would often land on a non-swing bar
- Result: `current_label` would be `None`, and `last_structure_label` wouldn't get updated

### Example Scenario (Original Bug)

With a 30-bar buffer and swing_window=3:
- Fixed index would be `30 - 3 - 1 = 26`
- If bar 26 is not a swing point → `labels_series.iloc[26] = pd.NA`
- Label never updates, stays `None`

### Follow-Up Issue: Buffer Size Too Small for 1H

Even after fixing the extraction logic, the condition `if len(valid_labels) > 0:` was **never passing for 1H timeframe**.

**Root Cause**: 
- 30-bar buffer for 1H = only 30 hours of data
- Market doesn't form enough clear swing points in 30 hours
- `labels_series.dropna()` returned empty series
- No structure labels were detected

**Additional Fix**: Made buffer size timeframe-aware:
- **1H**: 100 bars (~4 days of data)
- **15M**: 50 bars (~12.5 hours)
- **1M**: 30 bars (30 minutes)

---

## Solution

Changed the extraction logic to find the **most recent valid swing point** instead of using a fixed position:

```python
# NEW (FIXED) CODE
valid_labels = labels_series.dropna()

if len(valid_labels) > 0:
    # Latest real swing point (HH/HL/LH/LL)
    current_label = valid_labels.iloc[-1]
    self.last_structure_label = current_label
```

**Why this works:**
- `dropna()` filters out all non-swing bars
- `.iloc[-1]` gets the most recent confirmed swing
- Labels now correctly persist between swing points
- Works regardless of buffer size or swing sparsity

---

## Changes Made

### 1. Updated `feature_engine/streaming.py` (multiple sections)

#### A. Timeframe-Aware Buffer Sizing (lines 53-75)

**Problem**: 30-bar buffer was too small for 1H timeframe (only 30 hours), causing no swings to be detected.

**Added**:
```python
@staticmethod
def _get_buffer_size_for_timeframe(timeframe: str) -> int:
    if "h" in tf_lower:  # 1h, 2h, 4h
        return 100  # ~4 days for 1h
    elif "15m" in tf_lower:
        return 50  # ~12.5 hours
    elif "5m" in tf_lower:
        return 40  # ~3.3 hours
    else:  # 1m
        return 30
```

**Impact**: 
- 1H now has 100-bar buffer (~4 days of data)
- 15M has 50-bar buffer (~12.5 hours)
- Better swing detection on higher timeframes

#### B. Fixed Label Extraction Logic (lines 285-305)

**Before:**
- Fixed index calculation: `label_idx = len(labels_series) - self.swing_window - 1`
- Only updated `last_structure_label` if that specific position had a valid label
- Often resulted in no label updates

**After:**
- Find all valid (non-NA) labels: `valid_labels = labels_series.dropna()`
- Get the most recent: `current_label = valid_labels.iloc[-1]`
- Initialize `current_label = self.last_structure_label` before buffer check
- Labels always have a value (persisted or new)
- Added debug logging when no swings detected

#### C. Improved Debugging (lines 294-299)

**Added**:
```python
else:
    # No swings detected in buffer
    if self.last_structure_label is None:
        logger.debug(
            f"[{self.timeframe}] No swings detected in {len(self.structure_buffer)}-bar buffer "
            f"(swing_window={self.swing_window}). Consider increasing buffer size or swing_window."
        )
```

This helps diagnose when buffer size is still insufficient.

### 2. Added Integration Tests (test_streaming_structure_fix.py)

Created `tests/unit/feature_engine/test_streaming_structure_fix.py` with 4 tests:
1. **test_structure_labels_populated_with_clear_trend**: Verifies labels are detected in a clear uptrend
2. **test_structure_label_persists_between_swings**: Verifies labels persist correctly between swing points
3. **test_empty_structure_when_insufficient_data**: Verifies graceful handling when buffer is too small
4. **test_buffer_size_scales_with_timeframe**: Verifies 1H > 15M > 1M buffer sizes

---

## Testing

### Unit Tests

```bash
poetry run pytest tests/unit/feature_engine/test_streaming_structure_fix.py -v
# ✅ 4 passed (including new buffer size test)

poetry run pytest tests/unit/feature_engine/ -v
# ✅ 12 passed

poetry run pytest tests/unit/rule_engine/htf/ -v
# ✅ 381 passed

# Combined streaming + HTF
poetry run pytest tests/unit/ -k "streaming or htf" -q
# ✅ 393 passed
```

### Integration Verification

The fix ensures that:
- ✅ Structure labels are now populated in `features_1h["structure_label"]`
- ✅ Structure labels are now populated in `features_15m["structure_label"]`
- ✅ HTF calculator receives valid structure data at `rule_engine/htf/calculator.py:55`
- ✅ Labels persist correctly between swing points (no flickering)
- ✅ Labels update when new swings are detected

---

## Impact

### Before Fix
- HTF bias calculation had no structure information
- `structure_1h` and `structure_15m` were always `None`
- Structure-based scoring was ineffective
- Affected all backtests using `--htf-approach streaming`

### After Fix
- HTF structure labels work correctly in streaming mode
- Structure-based bias detection is now functional
- Backtests with streaming HTF now have full structure context
- Improves overall HTF bias quality

---

## Usage Notes

### For Backtesting (Recommended)

Use **vectorized HTF** for best structure detection:

```bash
poetry run python scripts/run_backtest_and_view.py \
    --start 2025-07-01T10:00:00Z \
    --end 2025-07-31T13:00:00Z \
    --htf-approach vectorized  # Recommended for backtesting
```

Vectorized processes the entire dataset at once, giving more reliable swing detection.

### For Live Trading

Use **streaming HTF** (now fixed):

```bash
# Streaming HTF now correctly extracts structure labels
htf_bias_func = create_htf_bias_func_with_sync_layer(
    multi_tf_data, 
    approach="streaming"  # Works correctly now
)
```

---

## Related Files

- **Fixed**: `feature_engine/streaming.py` (lines 248-282)
- **Tests**: `tests/unit/feature_engine/test_streaming_structure_fix.py`
- **Affected**: `rule_engine/htf/calculator.py`, `rule_engine/htf/features.py`
- **Integration**: `backtester/replay_loop.py`, `rule_engine/htf/streaming.py`

---

## Technical Details

### Structure Label Sparsity

Structure labels are delayed by `swing_window` bars to prevent look-ahead bias:
- Calculated in `feature_engine/structure.py::calculate_structure_labels()`
- First `swing_window * 2` positions are `pd.NA` (warmup)
- Last `swing_window` positions are `pd.NA` (no future confirmation)
- Only actual swing points have labels (HH/HL/LH/LL)

### Buffer Requirements

For structure detection to work, the streaming buffer needs:
- Minimum bars: `3 * swing_window + 1`
- With swing_window=3: need at least 10 bars
- Buffer size (maxlen=30) provides plenty of data

### Persistence Strategy

- Labels persist between swing points (intentional design)
- When a new swing is detected, label updates immediately
- If no swings in buffer, last known label persists
- This matches expected trading behavior (structure stays until it breaks)

---

## Verification Checklist

- [x] Bug identified and root cause understood
- [x] Fix implemented in `feature_engine/streaming.py`
- [x] Unit tests added covering the fix
- [x] All existing tests still pass
- [x] HTF structure labels now populate correctly
- [x] Documentation created
- [x] No regressions in vectorized mode

---

**End of Changelog**

