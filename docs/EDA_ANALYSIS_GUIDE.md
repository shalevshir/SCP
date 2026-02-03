# EDA Analysis Guide: How to Interpret Your VWAP Feature Report

This guide walks you through analyzing the EDA report step-by-step to extract actionable insights.

---

## Quick Start Checklist

Before diving deep, answer these questions by scanning the report:

1. **Data Quality**: Are there features with >20% null values? → Check "Feature Availability" table
2. **Major Bottlenecks**: Which constraint fails most often? → Check "Constraint Analysis" bar chart
3. **Threshold Tuning**: Are current thresholds too strict/loose? → Check optimization curves
4. **Anomalies**: Are there data spikes or quality issues? → Check "Anomalies" section (if enabled)

---

## Section-by-Section Analysis

### 1. Summary Statistics (Top of Report)

**What to Look For:**
- **Total Feature Records**: Should match expected data volume (1 minute bars × trading hours × days)
  - Example: 5 days × ~23 hours/day × 60 minutes = ~6,900 bars
  - Your result: 2,454 bars → Check if data is sparse or only RTH hours

- **Signal Pass Rate**: What % of signals are approved vs rejected?
  - <50%: Very strict constraints, likely missing many trades
  - 50-70%: Balanced filtering (typical for A+ threshold)
  - >70%: Constraints may be too loose, check signal quality

- **Total Rejections**: High number suggests constraints need tuning

**Example Analysis:**
```
Total Features: 2,454
Total Rejections: 2,240
Signal Pass Rate: Would be (total_evaluated - rejections) / total_evaluated

If you see 91% rejection rate → Very aggressive filtering, investigate top failing constraints
```

---

### 2. Feature Availability Table

**What to Look For:**
- **Null % < 5%**: Feature is reliable ✅
- **Null % 5-20%**: Acceptable, but monitor ⚠️
- **Null % > 20%**: Data quality issue, investigate 🚨

**Common Issues:**

| Feature | High Null % | Likely Cause | Fix |
|---------|-------------|--------------|-----|
| `max_abs_deviation_last_20` | >20% | ATR not available (warmup period) | Increase warmup bars in feature-engine |
| `bars_near_vwap` | >20% | ATR null → can't compute ±0.2 ATR band | Same as above |
| `vwap_deviation_normalized` | >20% | ATR null → can't normalize | Same as above |
| `vwap` | >5% | VWAP computation issue | Check VWAP reset logic |

**Action Items:**
1. Any feature with >20% nulls → Check `feature-engine` logs for that timeframe
2. Check if nulls cluster at start of session → Warmup period issue
3. Query database to see when nulls occur:
   ```sql
   SELECT timestamp, vwap_deviation_normalized, atr
   FROM features
   WHERE vwap_deviation_normalized IS NULL
   ORDER BY timestamp
   LIMIT 20;
   ```

---

### 3. Feature Distributions

**What to Look For:**

#### A. Histogram Shape
- **Normal (bell curve)**: Expected for most price-based features ✅
- **Skewed right**: Common for `bars_near_vwap` (most time NOT near VWAP)
- **Bimodal (two peaks)**: May indicate different market regimes
- **Extreme outliers**: Check if valid or data quality issues

#### B. Statistics Table
Focus on these metrics:

| Metric | What It Tells You | Red Flags |
|--------|-------------------|-----------|
| **Mean vs Median** | If mean >> median → right skew (outliers pulling mean up) | Large difference suggests outliers |
| **Std Dev** | Volatility of feature | Very high std → unstable feature |
| **P95** | 95% of data is below this | If P95 >> current threshold → too strict |
| **P5** | 5% of data is below this | If P5 << current threshold → too loose |

#### C. Box Plots by Direction
Compare long vs short distributions:
- **Similar distributions**: Feature is direction-agnostic (good for VWAP reclaim)
- **Clearly different**: Feature has directional bias (expected for structure features)

**Example Analysis for `bars_near_vwap`:**
```
Mean: 1.2 bars
Median: 0 bars
P95: 5 bars
Current threshold: ≥3 bars (min_vwap_acceptance constraint)

Interpretation:
- Most of the time (median=0), price is NOT near VWAP
- Only 5% of features have ≥5 bars near VWAP
- Threshold of ≥3 bars is quite strict → Consider lowering to 2 bars
```

**Example Analysis for `max_abs_deviation_last_20`:**
```
Mean: 2.8 ATR
Median: 2.1 ATR
P95: 7.5 ATR
Current threshold: ≤8.0 ATR (vwap_reclaim_distance constraint)

Interpretation:
- 95% of data is ≤7.5 ATR → Current threshold (8.0) captures most cases ✅
- Very few legitimate excursions exceed 8.0 ATR
- Threshold is well-calibrated
```

---

### 4. Constraint Analysis

This is the **MOST IMPORTANT** section for optimization.

#### A. Constraint Failure Bar Chart

**How to Read:**
- **Tallest bars = highest failure rates** → Top optimization targets
- Sort constraints by failure count (highest to lowest)

**Example Interpretation:**
```
1. min_vwap_acceptance: 800 failures (36% of signals)
2. vwap_reclaim_distance: 350 failures (16% of signals)
3. structure_label_available: 150 failures (7% of signals)
```

**Action for Top Failures:**

**Case 1: `min_vwap_acceptance` (36% failures)**
- **High failure = too strict** → Price rarely stays near VWAP for 3+ bars
- Check threshold optimization curve (see below)
- Consider reducing from 3 bars → 2 bars

**Case 2: `vwap_reclaim_distance` (16% failures)**
- **Moderate failure = working as intended** if rejecting extreme chases
- Check if failed signals would have been profitable (need backtest comparison)
- Review threshold curve to see pass rate at different values

**Case 3: `structure_label_available` (7% failures)**
- **Low failure = structural issue** → Features not computed, not a threshold problem
- Check feature-engine logs for missing structure labels
- This is NOT a threshold tuning issue

#### B. Threshold Optimization Curves

**How to Read:**
- **X-axis**: Threshold value you're testing
- **Y-axis**: Pass rate % (how many signals pass at that threshold)
- **Star marker**: Current threshold from `setups.yaml`

**Example: `min_vwap_acceptance` Curve**

```
Current threshold: 3 bars (pass rate: 64%)
Threshold 2 bars: pass rate: 82%
Threshold 4 bars: pass rate: 48%
Threshold 1 bar: pass rate: 95%
```

**Decision Framework:**

| Pass Rate | Interpretation | Action |
|-----------|----------------|--------|
| <50% | Too strict, missing many setups | Relax threshold |
| 50-70% | Balanced filtering | Keep or minor adjustment |
| 70-85% | Permissive but still selective | Consider if you want more signals |
| >85% | Too loose, minimal filtering | Tighten threshold |

**Optimization Strategy:**

1. **Identify target pass rate**: For A+ signals, aim for 60-75% pass rate per constraint
2. **Find threshold on curve**: Locate where curve crosses your target pass rate
3. **Test new threshold**: Update `setups.yaml` and run replay validation
4. **Compare results**: Check if signal quality improved (win rate, R:R)

**Example Decision:**
```yaml
# Before (in setups.yaml)
min_vwap_acceptance:
  expression: "bars_near_vwap is None or bars_near_vwap >= 3"

# After analyzing curve (pass rate too low at 64%)
min_vwap_acceptance:
  expression: "bars_near_vwap is None or bars_near_vwap >= 2"  # Now 82% pass rate
```

---

### 5. Temporal Patterns

**What to Look For:**

#### A. Time-Series Plots
- **Consistent patterns**: Feature values stable over time ✅
- **Sudden spikes**: Possible data quality issues or news events
- **Drift**: Feature values trending up/down → Market regime change
- **Session markers** (gray dashed lines at 08:20): Check if patterns differ by session

**Example Questions:**
- Does `vwap_deviation_normalized` spike at certain times? → Volatility clustering
- Are rejections more common during Asian session? → Lower liquidity
- Do features reset properly at RTH open (08:20)? → Check VWAP reset logic

#### B. Intraday Heatmaps
- **Color gradient**: Light to dark = low to high feature values
- **Vertical bands**: Identify hours with different behavior
- **Horizontal patterns**: Check if same pattern repeats each day

**Example Analysis:**
```
bars_near_vwap heatmap shows:
- Hour 8-10 (NY open): High values (bright colors) → More VWAP acceptance
- Hour 13-15 (mid-day): Low values (dark colors) → Price drifts from VWAP
- Hour 20-22 (Asian session): Medium values → Range-bound

Action: Consider time-based constraint relaxation during NY open hours
```

---

### 6. Feature Correlations

**What to Look For:**

#### A. Correlation Heatmap
- **Red cells**: Negative correlation
- **Blue cells**: Positive correlation
- **Color intensity**: Strength of correlation

**Expected Correlations:**
| Pair | Expected r | Reason |
|------|-----------|--------|
| `vwap_deviation` ↔ `vwap_deviation_normalized` | >0.8 | Both measure VWAP distance |
| `bars_near_vwap` ↔ `bars_since_last_vwap_touch` | <-0.5 | If near VWAP, recent touch |
| `max_abs_deviation_last_20` ↔ `vwap_deviation_normalized` | >0.5 | Recent excursion affects current distance |

**Red Flags:**
- **r > 0.95**: Features are nearly identical → One may be redundant
- **Unexpected correlations**: e.g., `atr` ↔ `bars_near_vwap` high correlation → Investigation needed

**Action Items:**
1. **High correlation (r > 0.8) between constraint features**: Consider removing one constraint
   ```yaml
   # If vwap_deviation and vwap_deviation_normalized are both in constraints with r=0.95
   # → Remove vwap_deviation, keep normalized version (better for cross-symbol comparison)
   ```

2. **Low correlation where expected high**: Check feature computation logic
   ```sql
   -- Verify vwap_deviation and vwap_deviation_normalized relationship
   SELECT
     vwap_deviation,
     vwap_deviation_normalized,
     atr,
     vwap_deviation / atr as computed_normalized
   FROM features
   WHERE atr > 0
   LIMIT 100;
   ```

---

### 7. Anomalies (if `--detect-anomalies` enabled)

**What to Look For:**

#### A. Anomaly Timeline
- **Isolated spikes**: Likely data quality issues or flash events
- **Clusters**: Period of extreme market conditions (news, rollover)
- **Regular patterns**: Check if anomalies occur at same time each day → Session boundary issues

#### B. Anomaly Details Table
Focus on:
- **High severity anomalies**: Z-score >5 (very extreme)
- **Same feature repeatedly**: Systematic issue with that feature
- **Specific timestamps**: Cross-reference with market events

**Example Analysis:**
```
27 anomalies detected

Feature: max_abs_deviation_last_20
Timestamp: 2025-11-06 14:32:00
Value: 15.2 ATR
Z-score: 6.8 (high severity)

Actions:
1. Check what happened at 14:32 on Nov 6:
   - Query trades table for execution
   - Check news calendar
   - Review signal_history for that timestamp

2. If data quality issue:
   - Investigate data pipeline
   - Check if rollover date (contract expiry)

3. If legitimate extreme event:
   - Verify constraint logic handles edge case
   - Check if stop loss was hit correctly
```

**Common Anomaly Patterns:**

| Pattern | Likely Cause | Action |
|---------|--------------|--------|
| Anomalies at 00:00, 08:00, 17:00 | Session transitions, VWAP reset | Expected, verify reset logic |
| Multiple features spike simultaneously | Data feed interruption | Check data-adapter logs |
| Only one feature anomalous | Feature computation bug | Review feature-engine for that feature |
| Anomalies during low volume (Asian session) | Wide spreads, thin liquidity | Consider session filters |

---

## Practical Workflow: Constraint Optimization

### Step 1: Identify Problematic Constraints (15 minutes)

```bash
# Generate report
make eda-vwap START=2025-11-05 END=2025-11-10

# Open report
open reports/vwap_eda_2025-11-05_2025-11-10.html
```

**Scan the "Constraint Analysis" section:**
1. Note the top 3 failing constraints
2. Check their pass rates in the table
3. Review reject reasons

**Example findings:**
```
Top failures:
1. min_vwap_acceptance: 800 failures (36%) - "bars_near_vwap < 3 (value=1)"
2. reclaim_timing_gate: 350 failures (16%) - "bars_since_last_vwap_touch > 10"
3. vwap_reclaim_distance: 150 failures (7%) - "max_abs_deviation_last_20 > 8.0"
```

### Step 2: Review Feature Distributions (10 minutes)

For each failing constraint, check the feature distribution:

**For `min_vwap_acceptance` (requires `bars_near_vwap >= 3`):**
```
Distribution stats:
- Median: 0 bars (50% of time, price is NOT near VWAP)
- P75: 2 bars (75% of signals have ≤2 bars)
- P95: 5 bars (95% of signals have ≤5 bars)
- Current threshold: 3 bars

Interpretation: Threshold too strict, only 25% of features meet it
```

### Step 3: Use Optimization Curves (10 minutes)

For numeric constraints, check the optimization curve:

**`min_vwap_acceptance` curve:**
```
Threshold 1 bar → 95% pass (too loose)
Threshold 2 bars → 82% pass (good balance)
Threshold 3 bars → 64% pass (current, too strict)
Threshold 4 bars → 48% pass (very strict)

Decision: Lower threshold from 3 → 2 bars
```

### Step 4: Update Configuration (5 minutes)

Edit `config/setups.yaml`:

```yaml
# Before
min_vwap_acceptance:
  expression: "bars_near_vwap is None or bars_near_vwap >= 3"
  reject_reason: "No acceptance near VWAP - drive-by reclaim"

# After
min_vwap_acceptance:
  expression: "bars_near_vwap is None or bars_near_vwap >= 2"
  reject_reason: "No acceptance near VWAP - drive-by reclaim"
```

### Step 5: Validate Changes (30 minutes)

Run replay to verify impact:

```bash
# Replay with new thresholds
make replay START=2025-11-05 END=2025-11-10 SPEED=0

# Compare signal counts
psql -d scp -c "
  SELECT
    setup_type,
    COUNT(*) as count,
    COUNT(*) FILTER (WHERE was_approved) as approved
  FROM signal_history
  WHERE timestamp >= '2025-11-05' AND timestamp < '2025-11-10'
  GROUP BY setup_type
  ORDER BY count DESC;
"
```

**Before vs After:**
```
Before (threshold = 3):
- Total signals: 2,240
- Approved: 200 (9%)
- Rejected by min_vwap_acceptance: 800

After (threshold = 2):
- Total signals: 2,240
- Approved: 600 (27%) ← More signals passed
- Rejected by min_vwap_acceptance: 400 ← Fewer rejections
```

### Step 6: Backtest Quality (Optional)

Check if additional signals are quality:

```bash
# Run backtest on new signals
# Compare win rate, avg R:R, expectancy
# Ensure added signals aren't degrading performance
```

---

## Red Flags Summary

### 🚨 Critical Issues (Fix Immediately)

1. **Feature has >50% null values**
   - Broken feature computation
   - Check feature-engine service logs

2. **Constraint fails >80% of the time**
   - Threshold impossibly strict
   - May be blocking all signals

3. **Anomalies every day at same time**
   - Systematic data pipeline issue
   - Check session boundaries, VWAP resets

### ⚠️ Warnings (Investigate)

1. **Feature null % increased over time**
   - Compare EDA reports from different periods
   - Data quality degradation

2. **Constraint failure rate varies significantly by day**
   - Check if market regime changed
   - May need dynamic thresholds

3. **Strong unexpected correlations (|r| > 0.8)**
   - Features may be redundant
   - Review constraint logic

### ✅ Healthy Signals

1. **All features <10% null**
2. **Constraint failure rates 20-40%** (balanced filtering)
3. **Feature distributions stable across days**
4. **Expected correlations present** (e.g., deviation metrics correlated)

---

## Quick Reference: SQL Queries for Follow-Up

### Check Null Patterns
```sql
SELECT
  DATE(timestamp) as date,
  COUNT(*) as total,
  COUNT(bars_near_vwap) as non_null_bars_near_vwap,
  (COUNT(*) - COUNT(bars_near_vwap))::float / COUNT(*) * 100 as null_pct
FROM features
WHERE symbol = 'GC' AND timeframe = '1m'
  AND timestamp >= '2025-11-05' AND timestamp < '2025-11-10'
GROUP BY DATE(timestamp)
ORDER BY date;
```

### Check Constraint Failure by Hour
```sql
SELECT
  EXTRACT(hour FROM timestamp) as hour,
  diagnostics->'vwap_reclaim_validation'->>'failed_constraint' as constraint,
  COUNT(*) as failures
FROM signal_history
WHERE setup_type = 'REJECTED'
  AND diagnostics ? 'vwap_reclaim_validation'
  AND timestamp >= '2025-11-05' AND timestamp < '2025-11-10'
GROUP BY hour, constraint
ORDER BY hour, failures DESC;
```

### Verify Feature Correlation
```sql
SELECT
  CORR(vwap_deviation, vwap_deviation_normalized) as correlation,
  COUNT(*) as sample_size
FROM features
WHERE vwap_deviation IS NOT NULL
  AND vwap_deviation_normalized IS NOT NULL
  AND timestamp >= '2025-11-05' AND timestamp < '2025-11-10';
```

---

## Next Steps After Analysis

1. **Document Findings**: Create summary of insights in `docs/EDA_FINDINGS_YYYY-MM-DD.md`
2. **Propose Changes**: List constraint threshold adjustments in `config/setups.yaml`
3. **Validate Changes**: Run replay validation with new thresholds
4. **Compare Results**: Generate new EDA report and compare metrics
5. **Iterate**: Repeat process for next constraint bottleneck

---

## Advanced: Multi-Period Comparison

To detect drift or validate stability:

```bash
# Week 1
make eda-vwap START=2025-11-01 END=2025-11-08

# Week 2
make eda-vwap START=2025-11-08 END=2025-11-15

# Compare:
# - Are feature distributions similar?
# - Are constraint failure rates stable?
# - Any new anomalies patterns?
```

Create comparison table:

| Metric | Week 1 | Week 2 | Change | Status |
|--------|--------|--------|--------|--------|
| bars_near_vwap median | 0 | 0 | 0% | ✅ Stable |
| min_vwap_acceptance failures | 36% | 38% | +2% | ⚠️ Monitor |
| max_abs_deviation_last_20 P95 | 7.5 ATR | 8.2 ATR | +9% | ⚠️ Higher volatility |

---

## Resources

- **EDA Script Source**: `scripts/eda/eda_vwap_features.py`
- **Constraint Definitions**: `config/setups.yaml` (lines 16-78)
- **Feature Schemas**: `services/shared/src/scp_shared/messaging/schemas.py`
- **Database Schema**: `infra/migrations/` (001, 006, 009, 010)
- **Diagnostic Tools**: `scripts/diagnose_vwap_reclaim.py`

For additional help, see:
- [EDA Usage Documentation](EDA.md)
- [VWAP Reclaim Root Cause Analysis](VWAP_RECLAIM_ROOT_CAUSE.md)
- [Historical Replay Guide](HISTORICAL_REPLAY_BACKTEST.md)
