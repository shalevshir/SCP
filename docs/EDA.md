# EDA: Exploratory Data Analysis

This document describes the EDA (Exploratory Data Analysis) tools available for analyzing trading bot features, constraints, and signal quality.

## Overview

The EDA toolkit provides interactive HTML reports for analyzing:
- Feature distributions and statistical properties
- Constraint failure patterns and pass rates
- Threshold optimization recommendations
- Temporal patterns (intraday and multi-day)
- Feature correlations
- Anomaly detection

## VWAP Feature EDA

### Purpose

Analyze VWAP_RECLAIM features and constraint validation to:
1. Understand feature distributions and identify data quality issues
2. Identify which constraints reject signals most frequently
3. Optimize constraint thresholds based on actual data
4. Detect anomalies and edge cases
5. Understand temporal patterns (session-based, intraday)

### Usage

#### Basic Usage

```bash
# Generate report for a date range
make eda-vwap START=2025-11-05 END=2025-11-10

# Or use the script directly
poetry run python scripts/eda/eda_vwap_features.py \
    --start 2025-11-05 \
    --end 2025-11-10
```

#### Advanced Usage

```bash
# Custom output path
poetry run python scripts/eda/eda_vwap_features.py \
    --start 2025-11-05 \
    --end 2025-11-10 \
    --output reports/custom_name.html

# With anomaly detection
poetry run python scripts/eda/eda_vwap_features.py \
    --start 2025-11-05 \
    --end 2025-11-10 \
    --detect-anomalies \
    --anomaly-method zscore

# Analyze DXY instead of GC
poetry run python scripts/eda/eda_vwap_features.py \
    --start 2025-11-05 \
    --end 2025-11-10 \
    --symbol DXY

# Custom database URL
poetry run python scripts/eda/eda_vwap_features.py \
    --start 2025-11-05 \
    --end 2025-11-10 \
    --db-url postgresql://user:pass@host:5432/db
```

#### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--start` | Start date (YYYY-MM-DD) | **Required** |
| `--end` | End date (YYYY-MM-DD) | **Required** |
| `--output` | Output HTML path | `reports/vwap_eda_{start}_{end}.html` |
| `--symbol` | Symbol to analyze (GC, DXY) | `GC` |
| `--detect-anomalies` | Enable anomaly detection | `false` |
| `--anomaly-method` | Method: `zscore` or `iqr` | `zscore` |
| `--db-url` | PostgreSQL connection URL | `$DATABASE_URL` |

### Output Report

The generated HTML report contains the following sections:

#### 1. Summary Statistics
- Total feature records analyzed
- Days covered in analysis
- Signal pass rate
- Total rejections

#### 2. Feature Availability
Table showing:
- Count of non-null values
- Null percentage
- Mean, median, std deviation for each feature

#### 3. Feature Distributions
For each VWAP feature:
- **Histogram with KDE overlay**: Shows distribution shape, skewness
- **Box plot by direction**: Compare long vs short distributions
- **Statistics table**: Percentiles (5th, 25th, 50th, 75th, 95th), skewness, kurtosis

**Features analyzed**:
- `vwap_deviation` - Raw VWAP deviation percentage
- `vwap_deviation_normalized` - ATR-normalized deviation
- `max_abs_deviation_last_20` - Maximum excursion in last 20 bars
- `min_abs_deviation_last_20` - Minimum excursion in last 20 bars
- `bars_near_vwap` - Consecutive bars within ±0.2 ATR of VWAP
- `bars_since_last_vwap_touch` - Bars elapsed since last VWAP touch
- `atr` - Average True Range (14-period)
- `vwap_slope` - Rate of VWAP change

#### 4. Constraint Analysis
- **Failure counts bar chart**: Constraints sorted by failure frequency
- **Pass/fail rates table**: Shows which constraints reject most signals
- **Threshold optimization curves**: For numeric constraints, shows pass rate vs threshold value
  - `vwap_reclaim_distance`: Test upper bounds from 0.5 to 12.0 ATR
  - `vwap_reclaim_current_distance`: Test upper bounds from 0.5 to 5.0 ATR
  - `min_vwap_acceptance`: Test lower bounds from 1 to 10 bars
  - `reclaim_timing_gate`: Test upper bounds from 5 to 20 bars

**Constraints tracked** (from `config/setups.yaml`):
- `structure_1h_available` - HTF 1H structure exists
- `htf_structure_integrity` - HTF structure aligns with direction
- `structure_label_available` - Micro structure label exists
- `vwap_reclaim_distance` - Prior excursion 0.5-8.0 ATR from VWAP
- `vwap_reclaim_current_distance` - Currently within 2.0 ATR of VWAP
- `no_late_reclaim` - BOS age >= 20 bars if BOS recent
- `bos_reclaim_gate` - BOS direction aligns with trade direction
- `direction_bos_alignment` - BOS/CHoCH alignment with direction
- `no_structure_conflict` - No HTF structure conflict
- `min_vwap_acceptance` - At least 3 bars near VWAP
- `reclaim_timing_gate` - VWAP touch within last 10 bars
- `structure_label_direction_long` - Micro structure supports long
- `structure_label_direction_short` - Micro structure supports short

#### 5. Temporal Patterns
- **Time-series plots**: Feature values over time with session markers (RTH open at 08:20 ET)
- **Intraday heatmaps**: Hour of day vs feature value (color = mean value)
- Analyze session-based patterns (Asian, London, NY sessions)

#### 6. Feature Correlations
- **Correlation heatmap**: Pearson correlation matrix (color scale: red = negative, blue = positive)
- **Strong correlations list**: Pairs with |r| > 0.6

**Expected correlations**:
- `vwap_deviation` ↔ `vwap_deviation_normalized`: Strong positive (both measure VWAP distance)
- `max_abs_deviation_last_20` ↔ `vwap_deviation_normalized`: Moderate positive (recent excursion influences current distance)
- `bars_near_vwap` ↔ `bars_since_last_vwap_touch`: Negative (if near VWAP, recent touch)

#### 7. Anomalies (if `--detect-anomalies` enabled)
- **Anomaly timeline**: Scatter plot showing timestamps with extreme feature values
- **Anomaly details table**: List of detected anomalies with severity
- **Detection methods**:
  - `zscore`: Flag points where |z-score| > 3 (default)
  - `iqr`: Flag points outside Q1 - 1.5*IQR or Q3 + 1.5*IQR

#### 8. Recommendations
Automatically generated insights:
- Constraints with >30% failure rate → Suggests relaxing threshold
- Features with >20% null values → Suggests checking feature computation
- High correlation pairs (|r| > 0.8) → Potential redundancy

### Interpreting Results

#### High Constraint Failure Rate
If a constraint fails >30% of the time:
1. Check if threshold is too strict for current market conditions
2. Review threshold optimization curve to find better value
3. Consider if constraint logic needs adjustment

**Example**: If `vwap_reclaim_distance` (max_abs_deviation_last_20 <= 8.0 ATR) fails 40% of the time, check the optimization curve. If 95th percentile is 10.0 ATR, consider raising threshold to 10.0.

#### High Null Percentage
If a feature has >20% null values:
1. Check feature computation logic in `feature-engine` service
2. Verify ATR is available (required for normalized metrics)
3. Review warmup period (some features need historical data)

**Example**: If `max_abs_deviation_last_20` has 30% nulls, check if ATR is computed correctly and if sufficient historical bars are available.

#### Strong Unexpected Correlations
If two features have |r| > 0.8:
1. Consider if one feature is redundant
2. Check for data pipeline issues (e.g., feature A incorrectly computed from feature B)
3. Evaluate if both features are needed in constraints

#### Anomalies
Detected anomalies indicate:
- **Data quality issues**: Spikes due to bad data, missing values backfilled incorrectly
- **Extreme market conditions**: Flash crashes, news events, session transitions
- **Edge cases**: Test constraint logic on these timestamps to ensure robustness

### Example Workflow

#### 1. Initial Analysis
```bash
# Generate baseline report for last week
make eda-vwap START=2025-11-05 END=2025-11-10

# Open report
open reports/vwap_eda_2025-11-05_2025-11-10.html
```

**Review**:
- Are all features populated? (check null %)
- Which constraints fail most? (check constraint analysis)
- Are distributions reasonable? (check for outliers)

#### 2. Threshold Optimization
If `min_vwap_acceptance` fails 50% of the time:
1. Check threshold optimization curve in report
2. Note current threshold (3 bars) and pass rate
3. Find threshold where pass rate = 80% (e.g., 2 bars)
4. Update `config/setups.yaml`:
   ```yaml
   min_vwap_acceptance:
     expression: "bars_near_vwap is None or bars_near_vwap >= 2"
   ```
5. Re-run replay to validate change

#### 3. Anomaly Investigation
If anomalies detected:
```bash
# Generate report with anomaly detection
poetry run python scripts/eda/eda_vwap_features.py \
    --start 2025-11-05 \
    --end 2025-11-10 \
    --detect-anomalies \
    --output reports/vwap_eda_with_anomalies.html
```

**Review anomaly table**:
- Note timestamps with extreme values
- Query `features` table for those timestamps
- Check if signal was generated/rejected at those times
- Verify constraint logic handles edge cases correctly

#### 4. Multi-Period Comparison
Compare different time periods to check for drift:
```bash
# Early November
make eda-vwap START=2025-11-01 END=2025-11-05

# Late November
make eda-vwap START=2025-11-20 END=2025-11-25

# Compare:
# - Are feature distributions stable?
# - Are constraint pass rates consistent?
# - Have correlations changed?
```

### Database Schema Reference

The EDA script queries the following tables:

#### `features` table
Columns used:
- `timestamp`, `symbol`, `timeframe`
- `close`, `vwap`, `atr`, `rsi`
- `vwap_deviation`, `vwap_deviation_normalized`, `vwap_slope`
- `max_abs_deviation_last_20`, `min_abs_deviation_last_20`
- `bars_near_vwap`, `bars_since_last_vwap_touch`
- `structure_label`, `ema_9`, `ema_20`, `ema_50`

#### `signal_history` table
Columns used:
- `timestamp`, `id`, `symbol`, `direction`, `setup_type`
- `score`, `confidence`, `was_approved`, `rejection_stage`
- `diagnostics->'vwap_reclaim_validation'` (JSONB):
  - `failed_constraint`: Name of first failed constraint
  - `reject_reason`: Human-readable rejection reason
  - `context_snapshot`: Feature values at rejection time

### Performance Notes

- **Data volume**: Script handles 10K+ feature records efficiently
- **Query optimization**: Uses TimescaleDB hypertable indexing
- **Memory usage**: ~100MB for 5-day analysis
- **Report size**: ~2-5MB HTML file (embedded Plotly charts)

### Troubleshooting

#### "No data available"
- Check that features exist for the date range:
  ```sql
  SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
  FROM features WHERE symbol = 'GC' AND timeframe = '1m';
  ```
- Verify `DATABASE_URL` env var is set correctly
- Ensure `infra-up` has been run (PostgreSQL container)

#### "No constraint failures found"
- Check that signal_history has rejection records:
  ```sql
  SELECT COUNT(*) FROM signal_history
  WHERE setup_type = 'REJECTED'
    AND diagnostics ? 'vwap_reclaim_validation';
  ```
- Verify bot-core service has been running and generating signals
- Check date range overlaps with trading sessions

#### Charts not rendering
- Open browser console (F12) for JavaScript errors
- Verify Plotly CDN is accessible (requires internet)
- Try different browser (Chrome, Firefox, Safari)

### Future Enhancements

Planned features:
1. **Multi-setup EDA**: Extend to VWAP_FADE and DXY_CONTINUATION
2. **Comparative analysis**: Side-by-side comparison of different periods
3. **Live dashboard**: Real-time EDA service (FastAPI + WebSocket)
4. **Export to CSV**: Download filtered data for external analysis
5. **Jupyter notebook integration**: Load EDA data into notebooks

### Related Documentation

- [VWAP Reclaim Root Cause Analysis](VWAP_RECLAIM_ROOT_CAUSE.md) - Constraint debugging
- [Historical Replay & Backtest](HISTORICAL_REPLAY_BACKTEST.md) - Validation workflow
- [Feature Engine Service](../services/feature-engine/README.md) - Feature computation
- [Bot Core Service](../services/bot-core/README.md) - Signal generation and scoring

### Support

For issues or questions:
1. Check [GitHub Issues](https://github.com/shalevshir/SCP/issues)
2. Review constraint definitions in `config/setups.yaml`
3. Inspect diagnostics in `signal_history` table
4. Enable verbose logging in bot-core service
