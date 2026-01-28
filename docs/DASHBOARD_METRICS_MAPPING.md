# SCP Trader Decision Dashboard - Metrics Mapping

> Generated: 2026-01-27
> Dashboard: `infra/grafana/dashboards/trader-decision.json`
> UID: `scp-trader-decision`

## Overview

This document maps all Prometheus metrics used in the **SCP Trader A+ Decision Dashboard** to their source code locations and provides detailed calculation logic for each metric.

### Metrics Status Summary

| Status | Count | Description |
|--------|-------|-------------|
| **Available** | 33 | Metrics present in Prometheus |
| **Missing** | 1 | `scp_trading_halt_reason` (execution service not running) |

---

## Core Indicator Calculations

Before diving into individual metrics, here are the fundamental calculations that power the SCP trading system:

### VWAP (Volume-Weighted Average Price)

**Formula:**
```
VWAP = Σ(Typical Price × Volume) / Σ(Volume)
where Typical Price = (High + Low + Close) / 3
```

**How it works:**
1. For each bar, calculate the typical price (average of high, low, close)
2. Multiply typical price by volume to get "value traded"
3. Sum all value traded and divide by total volume
4. Result is the average price weighted by volume - the "fair value"

**Key behavior:**
- **Session Reset:** Resets at 08:20 AM Eastern (RTH open for Gold futures)
- **Cumulative:** Builds throughout the session, becoming more stable over time
- **Edge cases:** Zero volumes replaced with epsilon; NaN prices filled with close

**Trading interpretation:**
- VWAP represents **institutional fair value** - where large players have transacted
- Price above VWAP = market is overbought relative to fair value (potential short)
- Price below VWAP = market is oversold relative to fair value (potential long)
- The further price deviates from VWAP, the stronger the mean-reversion signal

---

### RSI (Relative Strength Index)

**Formula:**
```
RSI = 100 - (100 / (1 + RS))
where RS = Average Gain / Average Loss
```

**Wilder's Smoothing (industry standard):**
```
First Average = Simple Moving Average over period
Subsequent: new_avg = (prev_avg × (period - 1) + current_value) / period
```

**How it works:**
1. Calculate price changes between consecutive bars
2. Separate into gains (positive changes) and losses (negative changes)
3. Apply Wilder's smoothing to both gain and loss series
4. Divide smoothed average gain by smoothed average loss to get RS
5. Transform RS into 0-100 scale via the RSI formula

**Key parameters:**
- **Period:** 14 (industry standard)
- **Oversold:** < 30 (extreme selling pressure)
- **Overbought:** > 70 (extreme buying pressure)
- **Neutral zone:** 40-60 (no extreme momentum)

**Trading interpretation:**
- RSI measures **momentum and exhaustion**
- RSI < 30 signals potential buying opportunity (sellers exhausted)
- RSI > 70 signals potential selling opportunity (buyers exhausted)
- RSI 40-60 is ideal for continuation setups (room to run)
- Divergence between price and RSI can signal reversals

---

### EMA (Exponential Moving Average)

**Formula:**
```
EMA = Price × α + EMA_prev × (1 - α)
where α = 2 / (period + 1)
```

**How it works:**
1. Calculate smoothing factor α based on period
2. New EMA = current price weighted by α + previous EMA weighted by (1-α)
3. More recent prices have exponentially more weight than older prices

**Standard periods (SOP):**
- **EMA 9:** Fast - captures short-term momentum shifts
- **EMA 20:** Medium - intermediate trend reference
- **EMA 50:** Slow - longer-term trend anchor

**Trading interpretation:**
- **Bullish stack:** EMA 9 > EMA 20 > EMA 50 (all trends aligned up)
- **Bearish stack:** EMA 9 < EMA 20 < EMA 50 (all trends aligned down)
- EMAs act as **dynamic support/resistance levels**
- Full stack alignment = strongest trend confirmation
- Crossovers signal potential trend changes

---

### ATR (Average True Range)

**Formula:**
```
True Range = max(High - Low, |High - Prev_Close|, |Low - Prev_Close|)
ATR = Simple Moving Average of True Range over period
```

**How it works:**
1. Calculate True Range: the greatest of (current range, gap up, gap down)
2. This captures both intrabar and gap volatility
3. Average True Ranges over 14 periods for smooth volatility measure

**Key parameters by timeframe:**
| Timeframe | Min % | Compression Threshold |
|-----------|-------|----------------------|
| 1m | 0.08% | 0.4 |
| 5m | 0.12% | 0.35 |
| 15m | 0.20% | 0.30 |
| 1h | 0.35% | 0.25 |

**Compression detection:**
```
Compression Ratio = Current ATR / Baseline ATR (50-bar)
Compressed if: Ratio < threshold for timeframe
```

**Trading interpretation:**
- ATR measures **market volatility**
- Low ATR = compression (quiet market, potential pending expansion)
- High ATR = expansion (active market, trends in progress)
- ATR compression before setup = higher probability move
- Used to normalize VWAP deviation for cross-session comparison

---

### Structure Detection (HH/HL/LH/LL)

**Swing point identification:**
- Uses a 5-bar lookback window to identify swing highs and lows
- A swing high is a bar with higher highs than surrounding bars
- A swing low is a bar with lower lows than surrounding bars

**Structure labels:**
| Label | Definition | Trend Implication |
|-------|------------|-------------------|
| **HH** | New swing high > previous swing high | Bullish continuation |
| **HL** | New swing low > previous swing low | Bullish support holding |
| **LH** | New swing high < previous swing high | Bearish pressure |
| **LL** | New swing low < previous swing low | Bearish continuation |

**How it works:**
1. Track sequence of swing highs and swing lows
2. Compare each new swing to previous swing of same type
3. Label based on whether new swing is higher or lower
4. Bullish trend = HH + HL sequence (higher highs with higher lows)
5. Bearish trend = LL + LH sequence (lower lows with lower highs)

**Structure clarity score (0-1):**
- Measures consistency of labels over 10-bar window
- High clarity (>0.7) = clean, unambiguous swings
- Low clarity (<0.4) = mixed, conflicting signals

**Trading interpretation:**
- Structure = **institutional price action framework**
- HH/HL pattern = uptrend (buy dips)
- LL/LH pattern = downtrend (sell rallies)
- Mixed structure = choppy market, reduce position size

---

### Break of Structure (BOS)

**Detection logic:**
```
Bullish BOS: Price closes above previous swing high
Bearish BOS: Price closes below previous swing low
```

**Validity requirements:**
- Clear trend context (not choppy)
- Recent BOS (< 15 bars old)
- Good structure clarity (≥ 0.5)

**BOS age tracking:**
- Fresh (0-10 bars): Strongest signal, momentum intact
- Aging (11-20 bars): Signal weakening, caution
- Stale (>20 bars): Signal expired, setup quality degraded

**Trading interpretation:**
- BOS = **momentum confirmation**
- Bullish BOS confirms buyers broke resistance
- Bearish BOS confirms sellers broke support
- Fresh BOS + trend alignment = high-probability entry

---

### Change of Character (CHoCH)

**Detection logic:**
```
CHoCH = Counter-BOS after BOS (structure reversal)
Bullish CHoCH: Bearish BOS followed by Bullish BOS
Bearish CHoCH: Bullish BOS followed by Bearish BOS
```

**Guard reset:** When opposite trend establishes with clarity ≥ 0.5

**Trading interpretation:**
- CHoCH = **reversal confirmation**
- More significant than single BOS
- Indicates institutional sentiment shift
- Often follows liquidity sweeps

---

### Liquidity Sweep

**Detection logic:**
```
Bullish Sweep: Price breaks swing low, then reverses back above
Bearish Sweep: Price breaks swing high, then reverses back below
```

**How it works:**
1. Price briefly penetrates a swing point (stop hunt)
2. This triggers stop losses of weak hands
3. Price then reverses in opposite direction
4. Institutions accumulated at better prices

**Trading interpretation:**
- Sweep = **institutional manipulation** pattern
- Bullish sweep takes out weak longs' stops before reversing up
- Bearish sweep takes out weak shorts' stops before reversing down
- Sweep aligned with bias = high-quality entry signal

---

### DXY Correlation

**Formula:**
```
Rolling Pearson Correlation = Σ((GC - GC_mean) × (DXY - DXY_mean)) / (n × GC_std × DXY_std)
```

**Multi-window composite:**
| Window | Weight | Purpose |
|--------|--------|---------|
| 15-min | 50% | Recent correlation |
| 30-min | 30% | Medium-term |
| 60-min | 20% | Long-term stability |

**Alignment scoring:**
| Correlation | Score | Interpretation |
|-------------|-------|----------------|
| < -0.6 | Full points | Strong inverse (ideal) |
| < -0.4 | 75% | Moderate inverse |
| < -0.2 | 50% | Weak inverse |
| < 0 | 25% | Very weak |
| ≥ 0 | 0 points | No alignment |

**Trading interpretation:**
- Gold and Dollar typically move **inversely** (negative correlation)
- Strong negative correlation (< -0.6) = predictable relationship
- Bullish Gold + Bearish DXY = aligned setup (higher confidence)
- Positive correlation = unusual, reduce confidence

---

### Chop Detection

**SOP definition - ALL THREE conditions required:**

**1. Large Wicks (Indecision):**
```
Wick Ratio = (Upper Wick + Lower Wick) / Body Size
Chop threshold: Wick Ratio ≥ 1.0
```
Bars with equal or more wick than body indicate rejection and indecision.

**2. Range-Bound Price:**
```
Rolling Range = (Rolling High - Rolling Low) over lookback
Range-bound if: Rolling Range < (ATR × 1.5)
```
Price contained within narrow band, not expanding.

**3. No Directional Progress:**
```
Progress = HH/HL pattern (bullish) OR LL/LH pattern (bearish)
No progress if: <50% of comparisons show directional movement
```
Structure is mixed, no clear trend emerging.

**Trigger condition:**
```
Chop = (Large Wicks) AND (Range-Bound) AND (No Directional Progress)
Triggers when: ≥3 consecutive bars meet all conditions
```

**Trading interpretation:**
- Chop = **market indecision** at all levels
- Wicks alone = just volatile (not necessarily chop)
- Containment alone = potential consolidation (not chop)
- All three = institutional rejection of both directions
- VWAP_FADE works well in chop (counter-trend traps)
- VWAP_RECLAIM penalized in chop (needs momentum)

---

### Signal Scoring (A+ System)

**Base score calculation:**
```
Base Score = Sum of factor scores (capped at 10.0)
```

**Factor components:**

| Factor | Max Points | Calculation |
|--------|------------|-------------|
| Structure Alignment | 2.5 | Direction match, sweep, BOS age |
| VWAP Relation | 1.0 | Price vs VWAP position |
| RSI State | 1.0 | Mid-reset or extreme zones |
| EMA Stack | 1.0 | Full/partial alignment |
| DXY Correlation | 1.0 | Graduated by strength |
| HTF Bonus | 1.0 | If HTF score ≥ 8.0 |
| FVG Alignment | 1.0 | Fair Value Gap support |
| Liquidity Sweep | 1.0 | Sweep matches direction |

**Penalty system (applied after base):**

| Penalty | Points | Trigger |
|---------|--------|---------|
| Structural chop | -1.0 to -1.5 | Detected choppy structure |
| ATR compression | -0.5 | Low volatility |
| Late reclaim | -0.5 to -1.5 | BOS age 11-20+ bars |
| VWAP distance | -0.15 to -0.3 | >0.3% from VWAP |
| No expansion | -0.5 | Missing momentum signal |
| No liquidity sweep | -1.5 | Missing sweep confirmation |
| Low clarity | -0.5 to -1.5 | Structure clarity <0.6 |
| No BOS | -2.0 | Missing structure break |
| Stale BOS | -0.5 to -1.5 | BOS >15 bars old |

**Confidence classification:**
| Score | Grade | Action |
|-------|-------|--------|
| ≥ 8.0 | A+ | Execute (institutional quality) |
| 6.0-7.9 | Watch | Monitor for improvement |
| < 6.0 | Reject | Skip trade |

**Setup-specific thresholds:**
- VWAP_FADE: A+ requires ≥ 9.0 (stricter)
- VWAP_RECLAIM: A+ requires ≥ 8.0
- DXY_CONTINUATION: A+ requires ≥ 8.0

---

## ROW 0 - GLOBAL HARD GATES

These are binary gates that must ALL pass before any trade is considered.

### Session / Mode
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_session_valid{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | bot-core (port 8004) |
| **Source File** | `services/bot-core/src/bot_core_svc/metrics.py:44-46` |
| **Values** | `1` = VALID (green), `0` = INVALID (red) |

**Calculation:**
Validates current time against configured trading session windows. Gold futures RTH (Regular Trading Hours) is the primary session.

**Trading interpretation:**
- Only trade during active sessions when institutional flow is present
- Overnight sessions have different characteristics (wider spreads, less liquidity)
- Session validation prevents trading during low-liquidity periods

---

### Enforcer Tier
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_enforcer_tier{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | bot-core (port 8004) |
| **Source File** | `services/bot-core/src/bot_core_svc/metrics.py:38-41` |
| **Encoding** | `1` = Conservative, `2` = Early Mild, `3` = Mild, `4` = Offensive |

**Calculation:**
Maps config `enforcer_tier` string to numeric value. Determines risk limits and position sizing rules.

**Tier characteristics:**
| Tier | Risk Profile | Position Size | HTF Requirement |
|------|--------------|---------------|-----------------|
| Conservative | Lowest | Smallest | Strict alignment |
| Early Mild | Low | Small | Moderate alignment |
| Mild | Medium | Medium | Flexible |
| Offensive | High | Larger | Minimal |

**Trading interpretation:**
- Start conservative during drawdown or uncertainty
- Progress to higher tiers as edge is proven
- Tier affects position sizing and signal thresholds

---

### HTF Verdict
| Attribute | Value |
|-----------|-------|
| **Metric** | `clamp_max(scp_htf_conflict_detected{mode="$mode"} + scp_htf_chop_detected{mode="$mode"}, 1)` |
| **Type** | Gauge (composite) |
| **Service** | htf-bias (port 8003) |
| **Values** | `0` = PASS (green), `1` = FAIL (red) |

**Calculation:**
Combines two boolean flags using OR logic:
1. `conflict_detected` - 15M and 1H structures disagree on direction
2. `chop_detected` - Higher timeframe showing chop pattern

**Trading interpretation:**
- HTF conflict = macro uncertainty, reduce conviction
- HTF chop = no clear trend, avoid trend-following setups
- Either condition failing = degrade signal quality or stand down

---

### DXY Alignment
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_dxy_aligned{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Values** | `1` = ALIGNED (green), `0` = NOT ALIGNED (red) |

**Calculation:**
Checks if DXY (Dollar Index) movement is inversely correlated with Gold direction:
- For bullish GC bias: expects bearish DXY (negative correlation < -0.6)
- For bearish GC bias: expects bullish DXY

**Trading interpretation:**
- Gold/Dollar inverse relationship is fundamental
- Aligned = both markets confirming same macro view
- Misaligned = conflicting signals, reduce confidence

---

### Psychology Gate
| Attribute | Value |
|-----------|-------|
| **Metric** | `max by (reason) (scp_trading_halt_reason{mode="$mode"} == 1)` |
| **Type** | Gauge with label |
| **Service** | execution (port 8005) - **NOT RUNNING IN DASHBOARD MODE** |
| **Valid Reasons** | `NONE`, `PDLL`, `LOSS_STREAK`, `FATIGUE`, `UNSAFE_STATE`, `CEO_OVERRIDE`, `MAX_TRADES` |

**Reason definitions:**
| Reason | Trigger | Purpose |
|--------|---------|---------|
| NONE | Default | No halt (trading allowed) |
| PDLL | Daily loss > limit | Per-day loss limit protection |
| LOSS_STREAK | N consecutive losses | Tilt prevention |
| FATIGUE | Too many trades today | Overtrading prevention |
| UNSAFE_STATE | System issue | Kill switch, data lag |
| CEO_OVERRIDE | Manual halt | Human intervention |
| MAX_TRADES | Daily max reached | Position limit |

**Trading interpretation:**
- Psychology gates prevent emotional/mechanical trading
- PDLL stops bleeding on bad days
- Loss streak halt prevents revenge trading
- Fatigue gate prevents overtrading

---

### Seasonality
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_seasonality_adjustment{mode="$mode"}` |
| **Type** | Gauge |
| **Service** | htf-bias (port 8003) |
| **Values** | Float value (score adjustment) |

**Calculation:**
Adjusts signal scoring based on historical seasonal patterns for Gold futures. Certain months/times historically have stronger directional tendencies.

**Trading interpretation:**
- Positive adjustment = seasonality supports setup direction
- Negative adjustment = seasonality opposes setup direction
- Used as tiebreaker for borderline signals

---

## ROW 0.5 - PRICE CHARTS

### GC Price Chart (OHLC Candlesticks)
| Attribute | Value |
|-----------|-------|
| **Datasource** | PostgreSQL (TimescaleDB) |
| **Query** | `SELECT timestamp, open, high, low, close FROM candles WHERE symbol='GC' AND timeframe='1m'` |
| **Data Source** | `candles` hypertable populated by data-adapter service |

**Trading interpretation:**
- Visual representation of Gold futures price action
- Shows structure (swings, BOS, CHoCH) visually
- Essential for pattern recognition

---

### VWAP Deviation Overlay
| Attribute | Value |
|-----------|-------|
| **Datasource** | PostgreSQL (TimescaleDB) |
| **Query** | `SELECT timestamp, vwap_deviation_normalized FROM features WHERE symbol='GC' AND timeframe='1m'` |
| **Threshold Zones** | <-1.4 (green/bullish), -0.7 to 0.7 (neutral), >1.4 (red/bearish) |

**Calculation:**
```
VWAP Deviation % = ((Close - VWAP) / VWAP) × 100
Normalized Deviation = VWAP Deviation / ATR
```

**Trading interpretation:**
- Shows how far price has strayed from fair value
- Large deviations (>1.4 ATR) = extended, potential fade setup
- Near zero = at fair value, look for reclaim setups
- Normalized version accounts for volatility

---

### DXY Price Chart (OHLC Candlesticks)
| Attribute | Value |
|-----------|-------|
| **Datasource** | PostgreSQL (TimescaleDB) |
| **Query** | `SELECT timestamp, open, high, low, close FROM candles WHERE symbol='DXY' AND timeframe='1m'` |

**Trading interpretation:**
- Dollar Index movement for correlation confirmation
- Should move inversely to Gold for aligned setups
- Divergence = warning signal

---

## ROW 1 - HTF BIAS & STRUCTURE

### HTF Bias Summary

#### Bias Direction
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_bias_current{mode="$mode"}` |
| **Type** | Gauge |
| **Encoding** | `1` = BULLISH (green), `0` = NEUTRAL (yellow), `-1` = BEARISH (red) |

**Calculation:**
Derived from multi-timeframe analysis of price structure:
- Weighted blend: 40% 15M structure + 60% 1H structure
- Requires consistent HH/HL (bullish) or LL/LH (bearish) patterns
- Neutral when mixed or unclear

**Trading interpretation:**
- HTF bias = **macro direction**
- Trade with HTF bias for higher probability
- Counter-trend trades need exceptional signal quality

---

#### Bias Score
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_bias_score{mode="$mode"}` |
| **Type** | Gauge |
| **Range** | 0-10 scale |

**Calculation:**
Composite score aggregating:
- Structure alignment across timeframes
- Trend strength (consecutive directional labels)
- DXY correlation quality
- Recent BOS confirmation

**Trading interpretation:**
- Score ≥ 8 = strong HTF conviction (A+ bonus applied)
- Score 5-7 = moderate conviction (no bonus)
- Score < 5 = weak/neutral HTF (be cautious)

---

#### Bias Confidence
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_bias_confidence{mode="$mode"}` |
| **Type** | Gauge |
| **Encoding** | `4` = A+, `3` = A, `2` = B, `1` = C |

**Calculation:**
Based on alignment of multiple confirmation factors:
- A+ (4): All factors aligned, high clarity
- A (3): Most factors aligned
- B (2): Mixed signals
- C (1): Low conviction

**Trading interpretation:**
- A+ confidence = increase position size
- B/C confidence = reduce size or skip

---

### HTF Structure Matrix

#### 15M Structure
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_structure_15m{mode="$mode"}` |
| **Type** | Gauge |
| **Encoding** | `1` = HH, `2` = HL, `3` = LH, `4` = LL, `0` = NEUTRAL |

**Calculation:**
Uses swing detection on 15-minute bars:
1. Identify swing highs and lows (5-bar lookback)
2. Compare to previous swings
3. Label as HH/HL/LH/LL based on comparison

**Trading interpretation:**
- HH/HL = 15M bullish structure (uptrend)
- LL/LH = 15M bearish structure (downtrend)
- Mixed = consolidation, wait for clarity

---

#### 1H Structure
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_structure_1h{mode="$mode"}` |
| **Type** | Gauge |
| **Encoding** | Same as 15M structure |

**Calculation:**
Same swing detection logic applied to 1-hour bars.

**Trading interpretation:**
- 1H structure = dominant timeframe for trend direction
- 1H + 15M alignment = strongest confluence
- 1H bullish + 15M bearish = potential pullback (not reversal)

---

### HTF Integrity Flags

#### VWAP Trend
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_vwap_trend_confirmed{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `1` = YES, `0` = NO |

**Calculation:**
Confirms VWAP slope aligns with bias direction:
- Bullish bias + positive VWAP slope = confirmed
- Bearish bias + negative VWAP slope = confirmed

**Trading interpretation:**
- VWAP trend = institutional volume supporting direction
- Confirmation adds to conviction
- Divergence is warning signal

---

#### BOS (Break of Structure)
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_bos_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `1` = YES, `0` = NO |

**Calculation:**
Indicates price broke previous swing high/low on HTF, confirming trend:
- Bullish BOS = close above last swing high
- Bearish BOS = close below last swing low

**Trading interpretation:**
- BOS = momentum confirmation
- Fresh BOS (recent) = high-quality signal
- No BOS = setup lacks confirmation

---

#### Chop Detection
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_chop_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `1` = YES (bad), `0` = NO (good) |

**Calculation:**
Detects choppy conditions using three-factor test (see Chop Detection section above).

**Trading interpretation:**
- Chop = no clear direction, market indecision
- Avoid trend-following setups in chop
- Fade setups may work in chop (VWAP_FADE)

---

#### Liquidity Sweep
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_liquidity_sweep_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `1` = YES, `0` = NO |

**Calculation:**
Detects institutional stop-hunting pattern:
- Price briefly breaks swing point
- Then reverses in opposite direction
- Indicates smart money accumulation

**Trading interpretation:**
- Sweep + reversal = institutional entry zone
- Sweep aligned with bias = high-quality signal
- Absence of sweep = lower conviction

---

## ROW 2 - DXY & CORRELATION

### DXY Structure
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_dxy_structure{mode="$mode"}` |
| **Type** | Gauge |
| **Encoding** | `4` = HH, `3` = HL, `2` = LH, `1` = LL, `0` = N/A |

**Calculation:**
Same structure detection applied to Dollar Index:
```python
dxy_structure_map = {"HH": 4.0, "HL": 3.0, "LH": 2.0, "LL": 1.0}
```

**Trading interpretation:**
- DXY HH/HL = Dollar bullish (Gold bearish expected)
- DXY LL/LH = Dollar bearish (Gold bullish expected)
- Inverse relationship is key confirmation

---

### Correlation Strength (1m)
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_dxy_corr{mode="$mode"}` |
| **Type** | Gauge |
| **Range** | -1.0 to 1.0 |
| **Thresholds** | <-0.7 (strong inverse), -0.5 to -0.3 (weak), >-0.3 (no correlation) |

**Calculation:**
Rolling Pearson correlation over 50 periods:
```
Correlation = Σ((GC - GC_mean) × (DXY - DXY_mean)) / (n × GC_std × DXY_std)
```

**Trading interpretation:**
- < -0.6 = strong inverse (ideal for trading)
- -0.3 to -0.6 = moderate inverse (acceptable)
- > -0.3 = weak/no correlation (reduce confidence)

---

### Correlation Strength (5m)
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_dxy_5m_corr{mode="$mode"}` |
| **Type** | Gauge |
| **Range** | -1.0 to 1.0 |

**Calculation:**
Same Pearson correlation computed on 5-minute aggregated bars for smoother, less noisy signal.

**Trading interpretation:**
- 5m correlation more stable than 1m
- Use for overall trend correlation
- 1m correlation for entry timing

---

### Correlation Verdict
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_htf_dxy_aligned{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `1` = ALIGNED, `0` = NOT ALIGNED |

**Calculation:**
Final verdict combining structure and correlation:
- Aligned if: DXY structure inverse to GC bias AND correlation < -0.6

**Trading interpretation:**
- Aligned = green light for DXY confirmation factor
- Not aligned = deduct points from signal score

---

## ROW 3 - VWAP & STRUCTURE

### Setup Type
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_detected_setup_type{mode="$mode"}` |
| **Type** | Gauge |
| **Encoding** | `1` = VWAP_RECLAIM, `2` = VWAP_FADE, `3` = DXY_CONTINUATION, `0` = NONE |

**Note:** This metric shows the detected setup type regardless of A+ status. It displays what setup is being evaluated even when the signal doesn't meet A+ criteria. Use `scp_current_setup_type` to see only A+ approved setups.

**Setup definitions:**

**VWAP_RECLAIM (1):**
- Price was below VWAP, now reclaiming above (bullish) or vice versa
- Momentum setup - riding institutional flow back to fair value
- Requires: BOS, structure alignment, EMA stack
- A+ threshold: ≥ 8.0

**VWAP_FADE (2):**
- Price extended far from VWAP, fading back toward it
- Mean-reversion setup - betting on rubber band effect
- Requires: Large deviation (>0.5%), RSI extreme, rejection candle
- A+ threshold: ≥ 9.0 (stricter)

**DXY_CONTINUATION (3):**
- Gold and DXY divergence creating continuation opportunity
- Requires: Strong correlation, aligned structures, no chop
- A+ threshold: ≥ 8.0

**Trading interpretation:**
- Each setup has different characteristics and requirements
- RECLAIM = go with trend, needs momentum
- FADE = counter-trend, needs exhaustion signals
- DXY_CONT = macro divergence play

---

### VWAP State

#### VWAP Value
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_vwap{mode="$mode"}` |
| **Type** | Gauge |

**Calculation:**
```
VWAP = Σ(Typical Price × Volume) / Σ(Volume)
Resets at 08:20 AM ET (RTH open)
```

**Trading interpretation:**
- Absolute VWAP price level
- Key reference for entry/exit decisions
- Session VWAP = institutional fair value

---

#### VWAP Slope
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_vwap_slope{mode="$mode", symbol="GC"}` |
| **Type** | Gauge |

**Calculation:**
```
VWAP Slope = Current VWAP - Previous VWAP
```
Bar-to-bar change in VWAP value.

**Trading interpretation:**
- Positive slope = bullish VWAP trend (volume-weighted buying)
- Negative slope = bearish VWAP trend (volume-weighted selling)
- Slope direction should align with trade direction

---

#### VWAP Deviation
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_vwap_deviation{mode="$mode"}` |
| **Type** | Gauge |

**Calculation:**
```
VWAP Deviation % = ((Close - VWAP) / VWAP) × 100
```

**Trading interpretation:**
- Positive deviation = price above VWAP (overbought)
- Negative deviation = price below VWAP (oversold)
- >0.5% deviation = extended, potential fade opportunity
- Near 0% = at fair value, potential reclaim opportunity

---

### Structure Validity

#### BOS Recent
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_bos_recent{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `1` = YES, `0` = NO |

**Calculation:**
Boolean indicating if Break of Structure occurred within lookback window (15 bars).

**Trading interpretation:**
- Recent BOS = momentum confirmed
- No recent BOS = setup lacks momentum confirmation

---

#### BOS Age
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_bos_age{mode="$mode"}` |
| **Type** | Gauge |
| **Thresholds** | <10 (green/fresh), 10-20 (yellow), >20 (red/stale) |

**Calculation:**
Number of bars since last BOS event.

**Trading interpretation:**
- Age 0-10: Fresh BOS, high-quality signal
- Age 11-15: Aging, apply penalty (-0.5)
- Age 16-20: Stale, apply penalty (-1.0)
- Age >20: Expired, apply penalty (-1.5)

---

#### CHoCH (Change of Character)
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_choch_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `1` = YES, `0` = NO |

**Calculation:**
Indicates trend reversal signal (counter-BOS after BOS).

**Trading interpretation:**
- CHoCH = potential reversal underway
- Bullish CHoCH = bearish trend may be ending
- Bearish CHoCH = bullish trend may be ending

---

#### Structure Clarity
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_structure_clarity{mode="$mode"}` |
| **Type** | Gauge |
| **Range** | 0.0 to 1.0 |
| **Thresholds** | <0.5 (red), 0.5-0.7 (yellow), >0.7 (green) |

**Calculation:**
Confidence score based on label consistency over 10-bar window:
```
Clarity = (Consistent labels) / (Total labels in window)
```

**Trading interpretation:**
- Clarity >0.7 = clean swings, high confidence
- Clarity 0.5-0.7 = acceptable, normal conditions
- Clarity <0.5 = choppy, reduce position size

---

## ROW 4 - MOMENTUM & CONFIRMATION

### RSI
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_rsi{mode="$mode"}` |
| **Type** | Gauge |
| **Range** | 0-100 |
| **Thresholds** | <30 (oversold), 30-40 (yellow), 40-60 (neutral), 60-70 (yellow), >70 (overbought) |

**Calculation:**
See RSI section above. Uses 14-period Wilder's smoothing.

**Trading interpretation by setup:**
- VWAP_RECLAIM: Want RSI 40-60 (room to run)
- VWAP_FADE: Want RSI <30 or >70 (exhaustion)
- Extreme RSI without setup = wait for confirmation

---

### EMA Stack

#### EMA 9/20/50
| Attribute | Value |
|-----------|-------|
| **Metrics** | `scp_feature_ema_9`, `scp_feature_ema_20`, `scp_feature_ema_50` |
| **Type** | Gauge |

**Calculation:**
See EMA section above. Standard periods 9, 20, 50.

**Trading interpretation:**
- **Full bullish stack** (9>20>50): +1.0 point
- **Partial alignment**: +0.5 point
- **Full bearish stack** (9<20<50): +1.0 point (for shorts)
- **No alignment**: 0 points

---

### Expansion & Liquidity
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_feature_expansion_detected{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `1` = YES, `0` = NO |

**Calculation:**
Detects price moving away from VWAP with momentum (range expansion).

**Trading interpretation:**
- Expansion = momentum confirmed, trend likely to continue
- No expansion = potential failed move, reduce confidence
- Critical for VWAP_RECLAIM setups

---

### Second Confirmation

#### Long/Short Confirmation
| Attribute | Value |
|-----------|-------|
| **Metrics** | `scp_feature_second_confirmation_long`, `scp_feature_second_confirmation_short` |
| **Type** | Gauge |
| **Values** | `1` = YES, `0` = NO |

**Calculation:**
Secondary confirmation signals:
- Long: RSI turning up from mid-zone, bullish EMA crossover, etc.
- Short: RSI turning down from mid-zone, bearish EMA crossover, etc.

**Trading interpretation:**
- Second confirmation = additional confluence
- Increases signal score when present
- Absence doesn't necessarily reject signal

---

## ROW 5 - A+ SCORECARD & DECISION

### Signal Score
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_signal_score{mode="$mode"}` |
| **Type** | Gauge |
| **Range** | 0-10 scale |

**Calculation:**
See Signal Scoring section above. Composite of all factors minus penalties.

**Trading interpretation:**
- Score is the **single number** summarizing signal quality
- 8.0+ = A+ quality, execute
- 6.0-7.9 = watch, may improve
- <6.0 = skip, insufficient quality

---

### A+ VERDICT
| Attribute | Value |
|-----------|-------|
| **Metric** | `scp_signal_aplus_verdict{mode="$mode"}` |
| **Type** | Gauge |
| **Values** | `0` = STAND DOWN (red), `1` = EXECUTE (green) |

**Calculation:**
```
A+ Verdict = (Score ≥ threshold) AND (All hard gates pass)
where threshold = 8.0 for RECLAIM/DXY, 9.0 for FADE
```

**Trading interpretation:**
- This is the **final decision metric**
- Green = signal meets all A+ criteria, execution permitted
- Red = one or more requirements not met, stand down
- Designed for single-glance decision making

---

## Signal State Metrics

These metrics expose the complete signal state from bot-core.

### Signal Prices

| Metric | Description |
|--------|-------------|
| `scp_signal_entry_price` | Entry price (0 if no signal) |
| `scp_signal_sl_price` | Stop loss price |
| `scp_signal_tp_price` | Take profit price (TP1) |
| `scp_signal_tp2_price` | Secondary TP (0 if static mode) |

### Risk/Reward

| Metric | Description |
|--------|-------------|
| `scp_signal_rr_tp1` | R:R ratio at TP1 |
| `scp_signal_rr_potential` | Max R:R potential (continuation mode) |
| `scp_signal_risk_points` | Risk in points (entry to SL distance) |

### TP Mode

| Metric | Values | Description |
|--------|--------|-------------|
| `scp_signal_tp_mode` | 1=static, 2=continuation | TP calculation method |
| `scp_signal_be_after_tp1` | 0/1 | Move to breakeven after TP1 |

### Rejection Tracking

| Metric | Description |
|--------|-------------|
| `scp_signal_last_rejection` | Last rejection reason (0=approved) |

**Rejection reason encoding:**
| Code | Reason | Description |
|------|--------|-------------|
| 0 | approved | Signal approved |
| 1 | htf_validity | HTF conflict or chop |
| 2 | confidence_filter | Score below A+ |
| 3 | tp_validation | No structural target |
| 4 | neutral_direction | Direction unclear |
| 5 | session_filter | Outside session |
| 6 | risk_limit | PDLL/loss streak |
| 7 | cooldown | Re-entry cooldown |
| 8 | warmup | Warmup period |
| 9 | kill_switch | Kill switch active |
| 10 | invalid_context | Market context invalid |

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
| Label | HTF Encoding | DXY Encoding | Meaning |
|-------|--------------|--------------|---------|
| HH | 1 | 4 | Higher High - bullish |
| HL | 2 | 3 | Higher Low - bullish support |
| LH | 3 | 2 | Lower High - bearish pressure |
| LL | 4 | 1 | Lower Low - bearish |
| NEUTRAL | 0 | 0 | No clear structure |

### Confidence Levels
| Level | Numeric | Score Range |
|-------|---------|-------------|
| A+ | 4 | ≥ 8.0 |
| A | 3 | 7.0-7.9 |
| B | 2 | 6.0-6.9 |
| C | 1 | < 6.0 |

### Enforcer Tiers
| Tier | Numeric | Risk Profile |
|------|---------|--------------|
| Conservative | 1 | Lowest risk, smallest size |
| Early Mild | 2 | Low risk, small size |
| Mild | 3 | Medium risk, medium size |
| Offensive | 4 | Higher risk, larger size |

### Setup Types
| Type | Numeric | Description |
|------|---------|-------------|
| VWAP_RECLAIM | 1 | Momentum reclaim of VWAP |
| VWAP_FADE | 2 | Mean reversion from extended |
| DXY_CONTINUATION | 3 | Dollar divergence play |
| NONE | 0 | No active setup |

### Trading Halt Reasons
| Reason | Trigger | Description |
|--------|---------|-------------|
| NONE | Default | Trading allowed |
| PDLL | Loss > daily limit | Per-day loss limit hit |
| LOSS_STREAK | N losses in row | Consecutive loss limit |
| FATIGUE | Too many trades | Overtrading prevention |
| UNSAFE_STATE | System issue | Kill switch active |
| CEO_OVERRIDE | Manual | Human intervention |
| MAX_TRADES | Daily limit | Max trades reached |

---

## Quick Reference: What Makes an A+ Signal?

**For VWAP_RECLAIM (threshold 8.0):**
1. Clear trend structure (HH/HL or LL/LH)
2. Fresh BOS (< 15 bars)
3. Price reclaiming VWAP with momentum
4. RSI in mid-zone (40-60)
5. EMA stack aligned
6. DXY inversely correlated (< -0.6)
7. No chop detected
8. Expansion signal present

**For VWAP_FADE (threshold 9.0):**
1. Large VWAP deviation (> 0.5%)
2. RSI at extreme (< 30 or > 70)
3. Rejection candle pattern
4. Volume spike (≥ 1.5x average)
5. DXY divergence supporting fade
6. No sustained momentum against fade

**For DXY_CONTINUATION (threshold 8.0):**
1. Strong GC/DXY inverse correlation (< -0.6)
2. DXY structure aligned with GC setup
3. No HTF conflict
4. No chop on either instrument
5. Clear directional bias

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
