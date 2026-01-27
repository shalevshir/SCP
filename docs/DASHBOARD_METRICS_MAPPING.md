# SCP Trader Decision Dashboard - Metrics Mapping

> Generated: 2026-01-27
> Dashboard: `infra/grafana/dashboards/trader-decision.json`
> UID: `scp-trader-decision`

## Overview

This document maps all Prometheus metrics used in the **SCP Trader A+ Decision Dashboard** to their source code locations and calculation logic.

### Metrics Status Summary

| Status | Count | Description |
|--------|-------|-------------|
| **Available** | 33 | Metrics present in Prometheus |
| **Missing** | 1 | `scp_trading_halt_reason` (execution service not running) |

---

## ROW 0 - GLOBAL HARD GATES

### Session / Mode
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_session_valid{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | bot-core (port 8004) |
| **Source File** | `services/bot-core/src/bot_core_svc/metrics.py:44-46` |
| **Update Location** | `services/bot-core/src/bot_core_svc/main.py` (after session validation) |
| **Values** | `1` = VALID (green), `0` = INVALID (red) |
| **Calculation Logic** | Set by `SessionValidationService` based on trading hours (RTH for Gold futures). Validates current time against configured trading session windows. |

### Enforcer Tier
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_enforcer_tier{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | bot-core (port 8004) |
| **Source File** | `services/bot-core/src/bot_core_svc/metrics.py:38-41` |
| **Update Location** | `services/bot-core/src/bot_core_svc/main.py` (lifespan initialization) |
| **Encoding** | `1` = Conservative (blue), `2` = Early Mild (yellow), `3` = Mild (orange), `4` = Offensive (red) |
| **Calculation Logic** | Maps config `enforcer_tier` string to numeric value using `ENFORCER_TIER_MAP`. Determines risk limits and position sizing rules. |

### HTF Verdict
| Attribute | Value |
|-----------|-------|
| **Metric** | `clamp_max(scp_htf_conflict_detected{mode="$mode"} + scp_htf_chop_detected{mode="$mode"}, 1)` |
| **Type** | Gauge (composite) |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:48-56` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Values** | `0` = PASS (green), `1` = FAIL (red) |
| **Calculation Logic** | Combines two flags: `conflict_detected` (HTF timeframes disagree on direction) and `chop_detected` (price action is ranging/indecisive). Either flag triggers FAIL. |

### DXY Alignment
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_dxy_aligned{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:43-46` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Values** | `1` = ALIGNED (green), `0` = NOT ALIGNED (red) |
| **Calculation Logic** | Checks if DXY (Dollar Index) movement is inversely correlated with Gold. For bullish Gold bias, expects bearish DXY. Based on `HTFBiasMessage.dxy_aligned` boolean. |

### Psychology Gate
| Attribute | Value |
|-----------|-------|
| **Metric** | `max by (reason) (scp_trading_halt_reason{mode="$mode"} == 1)` |
| **Type** | Gauge with label |
| **Service** | execution (port 8005) - **NOT RUNNING** |
| **Source File** | `services/execution/src/execution_svc/metrics.py:84-88` |
| **Update Location** | `services/execution/src/execution_svc/trade_manager.py:334,340` and `main.py:105,111` |
| **Values** | Shows active halt reason label, or "OK" if empty |
| **Valid Reasons** | `NONE`, `PDLL`, `LOSS_STREAK`, `FATIGUE`, `UNSAFE_STATE`, `CEO_OVERRIDE`, `MAX_TRADES` |
| **Calculation Logic** | Uses `set_trading_halt_reason()` which clears all reasons then sets the active one. Tracks fatigue (too many trades), loss streaks, and PDLL (per-day loss limit) breaches. |
| **Status** | **MISSING IN PROMETHEUS** - Execution service not running |

### Seasonality
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_seasonality_adjustment{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:83-86` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Values** | Float value (score adjustment) |
| **Calculation Logic** | Retrieves `seasonality_adjustment` from `HTFBiasMessage`. Adjusts signal scoring based on historical seasonal patterns for Gold futures. |

---

## ROW 0.5 - PRICE CHART

### GC Price Chart (OHLC Candlesticks)
| Attribute | Value |
|-----------|-------|
| **Datasource** | PostgreSQL (TimescaleDB) |
| **Query** | `SELECT timestamp, open, high, low, close FROM candles WHERE symbol='GC' AND timeframe='1m'` |
| **Data Source** | `candles` hypertable populated by data-adapter service |

### VWAP Deviation
| Attribute | Value |
|-----------|-------|
| **Datasource** | PostgreSQL (TimescaleDB) |
| **Query** | `SELECT timestamp, vwap_deviation_normalized FROM features WHERE symbol='GC' AND timeframe='1m'` |
| **Threshold Zones** | <-1.4 (green/bullish), -0.7 to 0.7 (neutral), >1.4 (red/bearish) |
| **Data Source** | `features` table populated by feature-engine service |

### DXY Price Chart (OHLC Candlesticks)
| Attribute | Value |
|-----------|-------|
| **Datasource** | PostgreSQL (TimescaleDB) |
| **Query** | `SELECT timestamp, open, high, low, close FROM candles WHERE symbol='DXY' AND timeframe='1m'` |
| **Data Source** | `candles` hypertable populated by data-adapter service |

---

## ROW 1 - HTF BIAS & STRUCTURE

### HTF Bias Summary

#### Bias Direction
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_bias_current{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:9-12` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:337` via `update_bias_metrics()` |
| **Encoding** | `1` = BULLISH (green), `0` = NEUTRAL (yellow), `-1` = BEARISH (red) |
| **Calculation Logic** | Maps `current_bias` string ("bullish"/"neutral"/"bearish") to numeric. Derived from multi-timeframe analysis of price structure and trend. |

#### Bias Score
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_bias_score{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:33-36` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Range** | 0-10 scale |
| **Calculation Logic** | Composite score from `HTFBiasMessage.score`. Aggregates structure alignment, trend strength, and DXY correlation into single 0-10 value. |

#### Bias Confidence
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_bias_confidence{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:38-41` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Encoding** | `4` = A+ (green), `3` = A (yellow), `2` = B (orange), `1` = C (red) |
| **Calculation Logic** | Maps `HTFBiasMessage.confidence` string using `CONFIDENCE_ENCODING`. Based on alignment of multiple confirmation factors. |

### HTF Structure Matrix

#### 15M Structure
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_structure_15m{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:73-76` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Encoding** | `1` = HH (green), `2` = HL (light-green), `3` = LH (light-red), `4` = LL (red), `0` = NEUTRAL (yellow) |
| **Calculation Logic** | Uses `STRUCTURE_ENCODING` map on `HTFBiasMessage.structure_15m`. Identifies Higher-High, Higher-Low, Lower-High, Lower-Low patterns on 15-minute timeframe. |

#### 1H Structure
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_structure_1h{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:78-81` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Encoding** | Same as 15M structure |
| **Calculation Logic** | Same logic applied to 1-hour timeframe structure from `HTFBiasMessage.structure_1h`. |

### HTF Integrity Flags

#### VWAP Trend
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_vwap_trend_confirmed{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:58-61` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Values** | `1` = YES (green), `0` = NO (red) |
| **Calculation Logic** | Checks `getattr(bias_msg, "vwap_trend_confirmed", False)`. Confirms VWAP slope aligns with bias direction. |

#### BOS (Break of Structure)
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_bos_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:63-66` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Values** | `1` = YES (green), `0` = NO (red) |
| **Calculation Logic** | Checks `getattr(bias_msg, "bos_detected", False)`. Indicates price broke previous swing high/low confirming trend. |

#### Chop
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_chop_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:48-51` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Values** | `1` = YES (detected - bad), `0` = NO (clear - good) |
| **Calculation Logic** | `1.0 if bias_msg.chop_detected else 0.0`. Detects ranging/consolidating market conditions unsuitable for trend trading. |

#### Liquidity Sweep
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_liquidity_sweep_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Source File** | `services/htf-bias/src/htf_bias_svc/metrics.py:68-71` |
| **Update Location** | `services/htf-bias/src/htf_bias_svc/main.py:340` via `update_htf_detail_metrics()` |
| **Values** | `1` = YES (green), `0` = NO (red) |
| **Calculation Logic** | Checks `getattr(bias_msg, "liquidity_sweep_detected", False)`. Indicates price swept previous swing to grab liquidity before reversing. |

---

## ROW 2 - DXY & CORRELATION

### DXY Structure
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_dxy_structure{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:87-90` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Encoding** | `4` = HH, `3` = HL, `2` = LH, `1` = LL, `0` = N/A |
| **Calculation Logic** | ```python
dxy_structure_map = {"HH": 4.0, "HL": 3.0, "LH": 2.0, "LL": 1.0}
encoded_value = dxy_structure_map.get(features_msg.dxy_structure, 0.0)
``` |

### Correlation Strength (1m)
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_dxy_corr{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:77-80` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Range** | -1.0 to 1.0 |
| **Thresholds** | <-0.7 (green/strong inverse), -0.5 to -0.3 (yellow/weak), >-0.3 (red/no correlation) |
| **Calculation Logic** | ```python
dxy_corr = features_msg.dxy_corr if features_msg.dxy_corr is not None else features_msg.dxy_correlation
``` Rolling Pearson correlation between GC and DXY price changes. |

### Correlation Strength (5m)
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_dxy_5m_corr{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:82-85` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Range** | -1.0 to 1.0 |
| **Calculation Logic** | Same as 1m but computed on 5-minute aggregated bars for smoother signal. |

### Correlation Verdict
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_dxy_aligned{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Values** | `1` = ALIGNED (green), `0` = NOT ALIGNED (red) |
| **Calculation Logic** | Final DXY alignment verdict combining structure and correlation. See ROW 0 DXY Alignment. |

---

## ROW 3 - VWAP & STRUCTURE

### Setup Type
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_current_setup_type{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | bot-core (port 8004) |
| **Source File** | `services/bot-core/src/bot_core_svc/metrics.py:49-52` |
| **Update Location** | `services/bot-core/src/bot_core_svc/main.py` (signal generation) |
| **Encoding** | `1` = VWAP_RECLAIM (green), `2` = VWAP_FADE (blue), `3` = DXY_CONTINUATION (purple), `0` = NONE (grey) |
| **Calculation Logic** | ```python
SETUP_TYPE_ENCODING = {
    "VWAP_RECLAIM": 1.0,  # Price reclaims VWAP with trend
    "VWAP_FADE": 2.0,     # Fade extended move from VWAP
    "DXY_CONTINUATION": 3.0,  # Continue with DXY divergence
    None: 0.0,
}
``` Set from `Signal.setup_type` after evaluation. |

### VWAP State

#### VWAP Value
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_vwap{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:41-44` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Calculation Logic** | `features_msg.vwap` - Volume-Weighted Average Price. Resets at 08:20 AM ET (RTH open for Gold futures). Calculated as cumulative (price * volume) / cumulative volume. |

#### VWAP Slope
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_vwap_slope{mode="$mode", symbol="GC"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:46-48` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Calculation Logic** | `features_msg.vwap_slope` - Bar-to-bar VWAP change. Positive slope indicates bullish VWAP trend. Used for FADE setup invalidation. |

#### VWAP Deviation
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_vwap_deviation{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:50-53` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Calculation Logic** | `features_msg.vwap_deviation` - Percentage deviation from VWAP. `(close - vwap) / vwap * 100`. Used to identify extended moves. |

### Structure Validity

#### BOS Recent
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_bos_recent{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:93-96` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Values** | `1` = YES (green), `0` = NO (red) |
| **Calculation Logic** | `1.0 if features_msg.bos_recent else 0.0` - Boolean indicating if Break of Structure occurred within lookback window. |

#### BOS Age
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_bos_age{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:98-101` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Thresholds** | <10 bars (green/fresh), 10-20 (yellow), >20 (red/stale) |
| **Calculation Logic** | `features_msg.bos_age` - Number of bars since last BOS event. Fresh BOS indicates stronger setup. |

#### CHoCH (Change of Character)
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_choch_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:103-106` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Values** | `1` = YES (green), `0` = NO (red) |
| **Calculation Logic** | `1.0 if features_msg.choch_detected else 0.0` - Indicates trend reversal signal (bullish becomes bearish or vice versa). |

#### Structure Clarity
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_structure_clarity{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:108-111` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Range** | 0.0 to 1.0 (percentage) |
| **Thresholds** | <0.5 (red), 0.5-0.7 (yellow), >0.7 (green) |
| **Calculation Logic** | `features_msg.structure_clarity` - Confidence score in identified structure. Higher values indicate cleaner swing points. |

---

## ROW 4 - MOMENTUM & CONFIRMATION

### RSI Matrix
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_rsi{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:56-59` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Range** | 0-100 |
| **Thresholds** | <30 (red/oversold), 30-40 (yellow), 40-60 (green/neutral), 60-70 (yellow), >70 (red/overbought) |
| **Calculation Logic** | `features_msg.rsi` - Relative Strength Index using Wilder's smoothing. 14-period default. Calculated in `scp_shared/indicators/calculate_rsi()`. |

### EMA Stack

#### EMA 9
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_ema_9{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:61-64` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Calculation Logic** | `features_msg.ema_9` - 9-period Exponential Moving Average. Fast EMA for short-term trend. |

#### EMA 20
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_ema_20{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:66-69` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Calculation Logic** | `features_msg.ema_20` - 20-period EMA. Medium-term trend reference. |

#### EMA 50
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_ema_50{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:71-74` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Calculation Logic** | `features_msg.ema_50` - 50-period EMA. Slow EMA for longer-term trend. Bullish stack: EMA9 > EMA20 > EMA50. |

### Expansion & Liquidity
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_expansion_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:114-117` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Values** | `1` = YES (green), `0` = NO (red) |
| **Calculation Logic** | `1.0 if features_msg.expansion_detected else 0.0` - VWAP_RECLAIM expansion detection. Indicates price is moving away from VWAP with momentum. |

### Second Confirmation

#### Long Confirmation
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_second_confirmation_long{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:119-122` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Values** | `1` = YES (green), `0` = NO (red) |
| **Calculation Logic** | `1.0 if features_msg.second_confirmation_long else 0.0` - Secondary bullish confirmation (e.g., RSI turning up, EMA crossover). |

#### Short Confirmation
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_second_confirmation_short{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | feature-engine (port 8002) |
| **Source File** | `services/feature-engine/src/feature_engine_svc/metrics.py:124-127` |
| **Update Location** | `services/feature-engine/src/feature_engine_svc/main.py:517` via `update_feature_metrics()` |
| **Values** | `1` = YES (green), `0` = NO (red) |
| **Calculation Logic** | `1.0 if features_msg.second_confirmation_short else 0.0` - Secondary bearish confirmation. |

---

## ROW 5 - A+ SCORECARD & DECISION

### SOP Score Breakdown
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_signal_score{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | bot-core (port 8004) |
| **Source File** | `services/bot-core/src/bot_core_svc/metrics.py:32-35` |
| **Update Location** | `services/bot-core/src/bot_core_svc/signal_engine.py` (after each evaluation) |
| **Range** | 0-10 scale |
| **Calculation Logic** | Composite score from `Signal.score`. Evaluated by `score_signal()` in `scp_shared/rule_engine/`. Aggregates all factors including structure, VWAP, DXY, momentum. |

### A+ VERDICT
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_signal_aplus_verdict{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | bot-core (port 8004) |
| **Source File** | `services/bot-core/src/bot_core_svc/metrics.py:88-91` |
| **Update Location** | `services/bot-core/src/bot_core_svc/main.py` (via `update_signal_state_metrics()`) |
| **Values** | `0` = NOT A+ - STAND DOWN (red), `1` = A+ - EXECUTION PERMITTED (green) |
| **Calculation Logic** | Single metric combining score >= 8.0 AND hard gates passing (no HTF conflict, DXY aligned, no chop). Computed server-side in bot-core. |

---

## Signal State Metrics (New)

These metrics expose the complete signal state from bot-core, creating a single source of truth for the trader decision dashboard.

### Signal Verdict & Gates

| Metric | Type | Values | Description |
|--------|------|--------|-------------|
| `scp_signal_aplus_verdict` | Gauge | 0/1 | Final A+ verdict (1=EXECUTION PERMITTED, 0=STAND DOWN) |
| `scp_signal_hard_gates_pass` | Gauge | 0/1 | All hard gates passing (no conflict, DXY aligned, no chop) |
| `scp_signal_direction` | Gauge | 1/-1/0 | Signal direction (1=long, -1=short, 0=neutral/none) |
| `scp_signal_confidence` | Gauge | 0-4 | Confidence level (4=A+, 3=A, 2=B, 1=C, 0=none) |

### Signal Prices

| Metric | Type | Values | Description |
|--------|------|--------|-------------|
| `scp_signal_entry_price` | Gauge | float | Entry price (0 if no signal) |
| `scp_signal_sl_price` | Gauge | float | Stop loss price |
| `scp_signal_tp_price` | Gauge | float | Take profit price (TP1) |
| `scp_signal_tp2_price` | Gauge | float | Secondary TP price (0 if none/static mode) |

### Risk/Reward

| Metric | Type | Values | Description |
|--------|------|--------|-------------|
| `scp_signal_rr_tp1` | Gauge | float | R:R ratio at TP1 |
| `scp_signal_rr_potential` | Gauge | float | Max R:R potential (continuation mode) |
| `scp_signal_risk_points` | Gauge | float | Risk in points (entry to SL distance) |

### TP Mode

| Metric | Type | Values | Description |
|--------|------|--------|-------------|
| `scp_signal_tp_mode` | Gauge | 1/2 | TP mode (1=static, 2=continuation) |
| `scp_signal_be_after_tp1` | Gauge | 0/1 | Move to breakeven after TP1 (1=yes, 0=no) |

### Rejection Tracking

| Metric | Type | Values | Description |
|--------|------|--------|-------------|
| `scp_signal_last_rejection` | Gauge | 0-10 | Last rejection reason (0=approved, see encoding below) |

### Rejection Reason Encoding

| Code | Reason | Description |
|------|--------|-------------|
| 0 | approved | Signal approved (no rejection) |
| 1 | htf_validity | HTF conflict or DXY chop detected |
| 2 | confidence_filter | Below A+ threshold (score < 8) |
| 3 | tp_validation | TP validation failed (no structural target) |
| 4 | neutral_direction | Signal direction is neutral |
| 5 | session_filter | Outside trading session |
| 6 | risk_limit | PDLL or loss streak limit |
| 7 | cooldown | Re-entry cooldown active |
| 8 | warmup | Warmup period active |
| 9 | kill_switch | Kill switch active |
| 10 | active_trade | Max concurrent trades reached |

---

## Service Dependency Map

```
┌─────────────────┐     candles.1m.{gc,dxy}     ┌──────────────────┐
│  Data Adapter   │ ──────────────────────────► │  Feature Engine  │
│    (8001)       │                             │     (8002)       │
└─────────────────┘                             └────────┬─────────┘
                                                         │
                                                   features.1m/15m/1h
                                                         │
                                                         ▼
┌─────────────────┐     htf_bias.updates        ┌──────────────────┐
│    HTF Bias     │ ◄─────────────────────────  │     Bot Core     │
│    (8003)       │ ──────────────────────────► │     (8004)       │
└─────────────────┘                             └────────┬─────────┘
                                                         │
                                                   signals.pending
                                                         │
                                                         ▼
                                                ┌──────────────────┐
                                                │    Execution     │
                                                │  (8005) [DOWN]   │
                                                └──────────────────┘
```

---

## Encoding Reference Tables

### Structure Labels
| Label | HTF Encoding | DXY Encoding |
|-------|--------------|--------------|
| HH (Higher-High) | 1 | 4 |
| HL (Higher-Low) | 2 | 3 |
| LH (Lower-High) | 3 | 2 |
| LL (Lower-Low) | 4 | 1 |
| NEUTRAL / N/A | 0 | 0 |

### Confidence Levels
| Level | Numeric Value |
|-------|---------------|
| A+ | 4 |
| A | 3 |
| B | 2 |
| C | 1 |

### Enforcer Tiers
| Tier | Numeric Value |
|------|---------------|
| Conservative | 1 |
| Early Mild | 2 |
| Mild | 3 |
| Offensive | 4 |

### Setup Types
| Type | Numeric Value |
|------|---------------|
| VWAP_RECLAIM | 1 |
| VWAP_FADE | 2 |
| DXY_CONTINUATION | 3 |
| NONE | 0 |

### Trading Halt Reasons
| Reason | Description |
|--------|-------------|
| NONE | No halt (trading allowed) |
| PDLL | Per-day loss limit hit |
| LOSS_STREAK | Loss streak limit hit |
| FATIGUE | Fatigue detection |
| UNSAFE_STATE | Kill switch, data lag, etc. |
| CEO_OVERRIDE | Manual override |
| MAX_TRADES | Max trades per day reached |

---

## Action Items

1. **Start Execution Service** to enable `scp_trading_halt_reason` metric:
   ```bash
   docker-compose -f infra/docker-compose.services.yml up -d execution
   ```

2. **Verify all metrics** after execution service starts:
   ```promql
   {__name__=~"scp_.*"}
   ```
