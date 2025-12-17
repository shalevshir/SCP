# Setup Detection & HTF Bias Fixes

**Date**: 2025-12-15  
**Issue**: November 2025 backtest produced 0 trades (4,700 rejections)  
**Root Causes Identified**:
1. Setup detector prerequisites too strict
2. HTF structure conflict detection too aggressive  
3. Missing warmup period for structure detection

---

## Problem Analysis

The November 2025 backtest showed:
- **63.1%** (2,968 signals) - "No Setup Type Detected" (all 3 detectors failed)
- **36.0%** (1,694 signals) - HTF 1H/15M Structure Conflicts
- **0.6%** (26 signals) - Sweep vs Trend Conflicts
- **0.3%** (12 signals) - Counter-Trend (opposes HTF bias)

### Root Causes

1. **HTF Structure Conflict Too Strict**: ANY cross-timeframe mismatch (e.g., 1H HL + 15M LL) was marked as conflict, but this is a normal retracement pattern.

2. **No Warmup Period**: Structure detection requires 11+ bars of 1H data. Without warmup, structure labels are `None` during the entire trading window.

3. **Setup Prerequisites**: Even with valid direction, prerequisites like BOS/CHoCH/sweeps weren't being detected.

---

## Fixes Applied

### 1. HTF Structure Conflict Detection (Fixed)

**File**: `rule_engine/htf/conflicts.py`

Previously marked ANY cross-timeframe mismatch as conflict:
- 1H bullish (HH, HL) + 15M bearish (LH, LL) = conflict ❌

Now only marks **strong momentum opposition** as conflict:
- 1H HH + 15M LL = conflict ✅ (strong bullish vs strong bearish)
- 1H LL + 15M HH = conflict ✅ (strong bearish vs strong bullish)
- 1H HL + 15M LL = **allowed** (normal bullish retracement)
- 1H LH + 15M HH = **allowed** (normal bearish retracement)

### 2. Warmup Period Added (Fixed)

**File**: `scripts/run_backtest_and_view.py`

Added `--warmup-days` parameter (default: 1 day) to load historical data before the backtest period starts. This allows structure detection to warm up before the trading window.

```bash
poetry run python scripts/run_backtest_and_view.py \
    --start 2025-11-04 --end 2025-11-10 \
    --warmup-days 1  # Load Nov 3 data for warmup
```

---

## Threshold Changes

### VWAP_RECLAIM (`rule_engine/htf/vwap/reclaim.py`)

| Parameter | Old Value | New Value | Rationale |
|-----------|-----------|-----------|-----------|
| `structure_clarity` | ≥ 0.5 | ≥ 0.4 | Allow setups with slightly lower clarity |
| `bars_since_bos` | ≤ 15 | ≤ 20 | BOS events can still be valid longer |

### DXY_CONTINUATION (`rule_engine/setup_detectors/dxy_continuation.py`)

| Parameter | Old Value | New Value | Rationale |
|-----------|-----------|-----------|-----------|
| `dxy_corr_1m` AND `dxy_corr_5m` | Both < -0.3 | At least one < -0.3 | Requiring both was too restrictive |
| `bars_since_bos` | ≤ 10 | ≤ 15 | Allow slightly older BOS events |
| `structure_clarity` | ≥ 0.5 | ≥ 0.4 | Align with VWAP_RECLAIM threshold |
| `displacement_strength` | ≥ 1.2 | ≥ 1.0 | Lower bar for displacement candles |
| `bars_since_pullback` | ≤ 5 | ≤ 8 | Allow older pullbacks |

### VWAP_FADE (`rule_engine/setup_detectors/vwap_fade.py`)

| Parameter | Old Value | New Value | Rationale |
|-----------|-----------|-----------|-----------|
| `structure_clarity` | ≥ 0.6 | ≥ 0.5 | Lower threshold for fade setups |
| `wick/body ratio` | > 2.0 | > 1.5 | Less strict rejection candle requirement |
| `trend_confidence` threshold | < 0.5 | < 0.6 | Easier to meet weakening signal requirement |
| `RSI oversold` | < 30 | < 35 | Slightly less extreme RSI required |
| `RSI overbought` | > 70 | > 65 | Slightly less extreme RSI required |
| `VWAP deviation` | > 0.5% | > 0.3% | Lower deviation threshold |

---

## Debug Logging Added

Each setup detector now logs INFO-level messages showing all prerequisite values:

```
VWAP_RECLAIM prereq check: sweep=True, clarity=0.65, bos=True, bars_since_bos=12, direction=long
DXY_CONT prereq check: corr_1m=-0.45, corr_5m=-0.72, dxy_struct=LH, dir=long, bars_since_bos=8, clarity=0.55
VWAP_FADE prereq check: dir=long, sweep=True, clarity=0.62, rsi=28.5, choch=True, trend_conf=0.4, struct_label=LH
```

---

## Bug Fix

Fixed a bug in `rule_engine/validation.py` where `validation_flags["chop_ok"]` was set **before** the DXY 5M chop check, causing the check to not be reflected in the validation flags.

---

## Testing

All 579 unit tests pass after these changes. Tests were updated to:
- Use new threshold values where applicable
- Use `chop_severity` (the field validation actually checks) instead of just `chop_detected`

---

## Expected Impact

These changes should:
1. Increase the number of signals that pass setup detection
2. Maintain SOP compliance while reducing over-filtering
3. Provide better visibility into why signals are rejected via debug logging

---

## Additional Fixes (Session 2)

### 3. 1H Candle Buffer Added

**File**: `rule_engine/htf/integration.py`

Added a 1H candle buffer (similar to existing 15M buffer) to accumulate enough 1H bars for BOS/CHoCH/FVG detection. Previously, `df_1h` was always a single-candle DataFrame which prevented structure detection.

### 4. Streaming Features Integration

**File**: `rule_engine/htf/calculator.py`

Updated `compute_htf_bias()` to use streaming feature values as **primary source**:
- `bos_detected` from `features_1h["bos_recent"]`
- `choch_detected` from `features_1h["choch_detected"]`  
- `liquidity_sweep_detected` from `features_1h["liquidity_sweep"]`
- `structure_clarity` from `features_1h["structure_clarity"]`

Falls back to df-based detection when streaming features aren't available.

### 5. Setup Detectors Updated

**Files**: 
- `rule_engine/htf/vwap/reclaim.py`
- `rule_engine/setup_detectors/dxy_continuation.py`

Setup detectors now read BOS/clarity from 1M `features` (which warm up faster) instead of relying solely on `HTFBias` fields (which need 1H warmup).

### 6. Execution Start Filter

**File**: `backtester/replay_loop.py`

Added `execution_start` parameter to skip warmup candles from signal recording. Warmup data is still processed for HTF feature computation, but signals are only recorded from the actual backtest start date.

---

## Current Status

After all fixes, November 4th backtest shows:
- **271 signals** (down from 546 with warmup included)
- **47 bullish signals** (17.3%) with valid HTF bias
- **224 neutral signals** (82.7%)
- **0 trades executed** - setup prerequisites still not met

### Remaining Issue

Setup detectors still fail because:
1. **No liquidity sweep** - sweeps are rare events (only detected in 1 out of 56 bars in sample)
2. **BOS age too high** - 1M-level BOS age is 271+ bars, exceeds 15-20 bar limit

The BOS age issue is due to using 1M-level structure tracking instead of 1H-level. The `bars_since_bos` should be counted in 1H bars (since last 1H BOS), not 1M bars.

### Next Steps

1. **BOS Age Calculation**: Use 1H-level BOS age from `HTFBias.bars_since_bos` rather than 1M-level `features["bos_age"]`
2. **Sweep Detection**: Review if liquidity sweep detection sensitivity is appropriate for the data

---

## Rollback

If needed, restore original thresholds:

```python
# VWAP_RECLAIM
CLARITY_THRESHOLD = 0.5  # Was 0.4
BOS_STALENESS_LIMIT = 15  # Was 20

# DXY_CONTINUATION
CORR_THRESHOLD = -0.3  # AND both (not OR)
BOS_STALENESS_LIMIT = 10  # Was 15
CLARITY_THRESHOLD = 0.5  # Was 0.4
DISPLACEMENT_THRESHOLD = 1.2  # Was 1.0
PULLBACK_RECENCY_LIMIT = 5  # Was 8

# VWAP_FADE
CLARITY_THRESHOLD = 0.6  # Was 0.5
WICK_BODY_RATIO = 2.0  # Was 1.5
TREND_CONF_THRESHOLD = 0.5  # Was 0.6
RSI_OVERSOLD = 30  # Was 35
RSI_OVERBOUGHT = 70  # Was 65
VWAP_DEVIATION_THRESHOLD = 0.5  # Was 0.3
```

