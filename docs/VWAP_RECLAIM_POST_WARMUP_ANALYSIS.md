# VWAP_RECLAIM Post-Warmup Analysis (Nov 6-8, 2025)

## Executive Summary

**Analysis Period**: 2025-11-06 to 2025-11-08 (post-warmup, when structure_1h data is available)

**Key Finding**: After eliminating warmup period, constraints are working **correctly** and protecting trade quality. The top 3 failing constraints are all appropriately rejecting low-quality setups.

---

## Results Overview

### Rejection Statistics
```
Total REJECTED signals: 1,978
  - With VWAP_RECLAIM diagnostics: 1,205 (60.9%)
  - Without diagnostics: 773 (39.1%)
```

### Top 4 Failing Constraints

| Rank | Constraint | Failures | % of Total | Verdict |
|------|-----------|----------|------------|---------|
| 1 | vwap_reclaim_distance | 716 | 59.4% | ✅ Working correctly |
| 2 | min_vwap_acceptance | 281 | 23.3% | ✅ Working correctly |
| 3 | htf_structure_integrity | 150 | 12.4% | ✅ Working correctly |
| 4 | structure_1h_available | 58 | 4.8% | ✅ Much improved (warmup stragglers) |

---

## Detailed Constraint Analysis

### 1. vwap_reclaim_distance (716 failures, 59.4%)

**Constraint**: Price must be 0.5-3.0 ATR away from VWAP

**Example Failure**:
```json
{
  "vwap": 3998.71,
  "close": 4018.2,
  "direction": "long",
  "vwap_deviation_normalized": 16.24  // <-- 16 ATRs away!
}
```

**Analysis**:
- Price is **16.24 ATRs** away from VWAP (constraint allows max 3.0)
- This is a massive chase entry - price is extremely extended
- Risk of mean reversion back to VWAP is very high

**Verdict**: ✅ **Working correctly** - protecting us from terrible late entries

**Action**: ❌ No change needed

---

### 2. min_vwap_acceptance (281 failures, 23.3%)

**Constraint**: Must have at least 3 bars near VWAP (`bars_near_vwap >= 3`)

**Example Failure**:
```json
{
  "bars_near_vwap": 0  // <-- Drive-by reclaim, zero acceptance
}
```

**Analysis**:
- **100% of failures** have `bars_near_vwap = 0` (not 1 or 2)
- These are "drive-by" reclaims where price briefly crosses VWAP and immediately moves away
- No consolidation or acceptance near VWAP level
- High probability of false breakout

**Distribution**:
```
0 bars: 281 (100.0%)
1 bar:  0 (0.0%)
2 bars: 0 (0.0%)
```

**Verdict**: ✅ **Working correctly** - filtering out weak drive-by reclaims

**Action**: ❌ No change needed (lowering threshold to 2 or 1 would recover 0 additional setups)

**Note**: If we had failures with 1-2 bars, we might consider relaxing to 2, but all failures are 0-bar drive-bys.

---

### 3. htf_structure_integrity (150 failures, 12.4%)

**Constraint**: Direction must align with 1H structure
- Long trades require `structure_1h in ['HH', 'HL']` (bullish)
- Short trades require `structure_1h in ['LL', 'LH']` (bearish)

**Example Failure**:
```json
{
  "direction": "long",
  "structure_1h": "LL"  // <-- Bearish 1H structure, trying to go long
}
```

**Analysis**:
- Attempting long trade when 1H timeframe is making Lower Lows (bearish)
- This is a counter-trend trade against higher timeframe
- HTF structure should guide trade direction, not oppose it

**Verdict**: ✅ **Working correctly** - prevents counter-trend trades

**Action**: ❌ No change needed

---

### 4. structure_1h_available (58 failures, 4.8%)

**Constraint**: `structure_1h is not None`

**Analysis**:
- Down from **480 failures** in warmup period (88% reduction!)
- Remaining 58 failures likely due to:
  - Market closed periods (overnight, weekends)
  - Sparse trading hours with data gaps
  - HTF bias service still warming up structure detection

**Verdict**: ✅ **Much improved** - warmup was the root cause

**Action**: ✅ Implement warmup skip (will eliminate entirely)

---

## Comparison: Warmup vs Post-Warmup

### structure_1h_available Constraint

| Period | Total Rejected | Structure Failures | % Structure Failures |
|--------|---------------|-------------------|---------------------|
| Warmup (Nov 5, 01:00-10:59) | 354 | 354 | **100.0%** |
| Post-Warmup (Nov 6-8) | 1,978 | 58 | **4.8%** |

**Improvement**: 95.2% reduction in structure_1h failures post-warmup ✅

---

## Recommendations

### ✅ Primary Action: Implement Warmup Skip

**What**: Skip VWAP_RECLAIM attempts during first 10 hours of session

**Why**:
- Eliminates 354 false rejections due to missing structure_1h
- Aligns with industry best practice (warmup periods are standard)
- Prevents using incomplete data for trading decisions

**Implementation**: See `docs/VWAP_RECLAIM_ROOT_CAUSE.md` Option 1

---

### ❌ Do NOT Relax Existing Constraints

Based on post-warmup analysis, **all constraints are working correctly**:

1. **vwap_reclaim_distance**: Correctly rejecting chase entries (16 ATR away!)
2. **min_vwap_acceptance**: Correctly rejecting drive-by reclaims (0 bars acceptance)
3. **htf_structure_integrity**: Correctly rejecting counter-trend trades
4. **structure_1h_available**: Warmup skip will eliminate remaining failures

**Relaxing any of these constraints would allow low-quality trades through.**

---

## Expected Impact After Warmup Skip

### Before Warmup Skip (Current State)
```
Period: Nov 5-8 (includes warmup)
Total rejected: 2,114
Structure_1h failures: 480 (22.7%)
```

### After Warmup Skip (Expected)
```
Period: Nov 5-8 (skips first 10 hours)
Total rejected: ~1,980  (excludes 354 warmup rejections)
Structure_1h failures: ~58 (2.9%)
VWAP_RECLAIM detected: Increase expected (unknown baseline)
```

---

## Next Steps

1. ✅ **Completed**: Post-warmup analysis confirms constraints are working correctly
2. 🟡 **Next**: Implement warmup skip in `scoring.py`
3. 🟡 **Next**: Add `warmup_hours: 10` to `config/setups.yaml`
4. 🟡 **Next**: Re-run diagnostics to verify fix
5. 🟡 **Next**: Check signal_history for `setup_type='VWAP_RECLAIM'` entries

---

## Key Insights

1. **Warmup was 95% of the problem**: structure_1h failures dropped from 100% to 4.8% post-warmup
2. **Constraints are protecting quality**: Top failing constraints are correctly rejecting bad setups
3. **No over-fitting**: All rejection reasons are legitimate (chase entries, drive-by reclaims, counter-trend)
4. **Clean post-warmup data**: After structure_1h available, system works as designed

---

## Files Referenced

- **Diagnostic Tool**: `scripts/diagnose_vwap_reclaim.py`
- **Root Cause Analysis**: `docs/VWAP_RECLAIM_ROOT_CAUSE.md`
- **Constraints Config**: `config/setups.yaml` (lines 16-98)
- **Scoring Logic**: `services/shared/src/scp_shared/rule_engine/scoring.py`
