# Trader A+ Decision Dashboard Metrics Guide

This document explains each metric displayed in the **SCP Trader A+ Decision Dashboard**, including how it's calculated, what it represents, and how to interpret its values.

## Overview

The Trader Decision Dashboard provides real-time visibility into all factors that determine whether a trade setup qualifies as "A+" (high confidence, execution permitted). The dashboard is organized into seven logical sections:

1. **Global Hard Gates** — Binary pass/fail conditions that must all pass
2. **Price Chart** — Live GC and DXY candle visualization
3. **HTF Bias & Structure** — Higher timeframe directional context
4. **DXY & Correlation** — Dollar index relationship tracking
5. **VWAP & Structure** — Price-to-VWAP relationship and structure validity
6. **Momentum & Confirmation** — RSI, EMAs, and entry confirmations
7. **A+ Scorecard & Decision** — Final composite score and verdict

---

## Dashboard Variables

| Variable | Options | Description |
|----------|---------|-------------|
| **Mode** | `dev`, `test`, `replay`, `paper`, `live` | Filters metrics by trading mode |
| **Symbol** | `GC` | Target instrument (Gold Futures) |

---

## ROW 0 — GLOBAL HARD GATES

These are binary "gate" conditions that must all pass before any trade can be considered. If any gate fails, trading is blocked regardless of signal score.

---

## ROW 0.5 — PRICE CHART

### GC Price Chart (OHLC Candlesticks)
**Data Source:** TimescaleDB (PostgreSQL) - `candles` table

**SQL Query:**
```sql
SELECT
  timestamp AS "time",
  open AS "Open",
  high AS "High",
  low AS "Low",
  close AS "Close"
FROM candles
WHERE
  symbol = 'GC'
  AND timeframe = '1m'
  AND timestamp BETWEEN [time_range]
ORDER BY timestamp ASC
```

**Visualization Type:** Candlestick chart
- **Green candles**: Close > Open (bullish)
- **Red candles**: Close < Open (bearish)
- **Wicks**: Show high and low of each 1-minute period
- **Precision**: 2 decimal places (e.g., 2650.75)

**What it displays:** Professional OHLC (Open-High-Low-Close) candlestick chart showing Gold price movement bar-by-bar with precise historical pricing from the database.

**Why it matters:** Shows market structure, momentum, and price action in the traditional candlestick format that traders use. Helps identify support/resistance, reversals, and trend strength. Queries directly from TimescaleDB to show accurate historical candles during replay.

---

### DXY Price Chart (OHLC Candlesticks)
**Data Source:** TimescaleDB (PostgreSQL) - `candles` table

**SQL Query:**
```sql
SELECT
  timestamp AS "time",
  open AS "Open",
  high AS "High",
  low AS "Low",
  close AS "Close"
FROM candles
WHERE
  symbol = 'DXY'
  AND timeframe = '1m'
  AND timestamp BETWEEN [time_range]
ORDER BY timestamp ASC
```

**Visualization Type:** Candlestick chart
- **Green candles**: Close > Open (DXY strengthening)
- **Red candles**: Close < Open (DXY weakening)
- **Wicks**: Show high and low of each 1-minute period
- **Precision**: 3 decimal places (e.g., 107.258)

**What it displays:** Professional OHLC candlestick chart showing Dollar Index price movement bar-by-bar with precise historical pricing from the database.

**Why it matters:** DXY movement provides crucial context for Gold trades due to their inverse correlation. Seeing DXY structure helps validate trade direction and anticipate Gold reversals. Queries directly from TimescaleDB to show accurate historical candles during replay.

---

**Technical Note:** These charts query TimescaleDB directly instead of Prometheus metrics. This ensures proper time-series data with historical accuracy, especially important during replay mode where we need to display candles from past dates. Prometheus gauge metrics only store the current value, which would cause all historical candles to appear identical.

---

### Session / Mode
**Metric:** `scp_session_valid{mode="$mode"}`

| Value | Display | Color |
|-------|---------|-------|
| 1 | VALID | Green |
| 0 | INVALID | Red |

**What it measures:** Whether the current time falls within allowed trading hours for the selected mode.

**Calculation:** The Bot Core service evaluates the current timestamp against session configuration (trading windows defined per mode). Returns `1` if within trading hours, `0` otherwise.

**Why it matters:** Prevents trading during low-liquidity periods (overnight, weekends) or outside designated paper/live windows.

---

### Enforcer Tier
**Metric:** `scp_enforcer_tier{mode="$mode"}`

| Value | Display | Color | Meaning |
|-------|---------|-------|---------|
| 1 | Conservative | Blue | Strictest filters, fewest trades |
| 2 | Early Mild | Yellow | Slightly relaxed |
| 3 | Mild | Orange | Balanced risk/opportunity |
| 4 | Offensive | Red | Most permissive |

**What it measures:** The currently active risk management tier that adjusts scoring thresholds and trade frequency.

**Calculation:** Set by configuration based on mode, account state, or time of day. Maps string values to numeric: `"Conservative" → 1`, `"Early Mild" → 2`, `"Mild" → 3`, `"Offensive" → 4`.

**Why it matters:** Different tiers have different A+ score thresholds, max position sizes, and filtering strictness.

---

### HTF Verdict
**Metric:** `clamp_max(scp_htf_conflict_detected{mode="$mode"} + scp_htf_chop_detected{mode="$mode"}, 1)`

| Value | Display | Color |
|-------|---------|-------|
| 0 | PASS | Green |
| 1 | FAIL | Red |

**What it measures:** Combined check for two HTF (Higher Time Frame) blocking conditions:
- **Conflict Detected:** 15m and 1h structure are pointing in opposite directions
- **Chop Detected:** Market is ranging without clear directional structure

**Calculation:** If either `scp_htf_conflict_detected` OR `scp_htf_chop_detected` equals 1, the verdict is FAIL. The `clamp_max(..., 1)` ensures the combined value doesn't exceed 1.

**Why it matters:** Trading against conflicting HTF structure or in choppy conditions leads to whipsaws and losses. This is a hard gate.

---

### DXY Alignment
**Metric:** `scp_htf_dxy_aligned{mode="$mode"}`

| Value | Display | Color |
|-------|---------|-------|
| 1 | ALIGNED | Green |
| 0 | NOT ALIGNED | Red |

**What it measures:** Whether the Dollar Index (DXY) movement supports the current trade direction.

**Calculation:** Gold (GC) typically has an inverse correlation with DXY. The system checks if DXY structure/movement aligns with expected direction for the signal:
- For **long GC**: DXY should be bearish or weakening
- For **short GC**: DXY should be bullish or strengthening

**Why it matters:** Trades against DXY direction have lower win rates. This intermarket confirmation is a key edge.

---

### Psychology Gate
**Metric:** `max by (reason) (scp_trading_halt_reason{mode="$mode"} == 1)`

| Value | Display | Color |
|-------|---------|-------|
| (empty) | OK | Green |
| `LOSS_STREAK` | LOSS_STREAK | Red |
| `FATIGUE` | FATIGUE | Red |
| `PDLL` | PDLL | Red |
| `MAX_TRADES` | MAX_TRADES | Red |
| `COOL_DOWN` | COOL_DOWN | Red |

**What it measures:** Whether trading is halted due to psychological or risk management triggers.

**Calculation:** The Execution service tracks multiple halt conditions:
- **LOSS_STREAK:** Consecutive losing trades exceeded threshold
- **FATIGUE:** Too many trades in short period
- **PDLL:** Previous Day's Low Limit hit (daily loss limit)
- **MAX_TRADES:** Maximum daily trade count reached
- **COOL_DOWN:** Forced waiting period after certain events

**Why it matters:** Prevents revenge trading and enforces discipline when the trader/system is in a losing streak.

---

### Seasonality
**Metric:** `scp_htf_seasonality_adjustment{mode="$mode"}`

| Value | Color | Meaning |
|-------|-------|---------|
| > 0 | Blue | Positive seasonal bias (favorable period) |
| 0 | Blue | No seasonal adjustment |
| < 0 | Blue | Negative seasonal bias (unfavorable period) |

**What it measures:** Score adjustment based on historical seasonal patterns for gold.

**Calculation:** Looks up current date against historical seasonal patterns (e.g., `november_december` period). Returns a float value that modifies the base signal score.

**Why it matters:** Certain times of year historically favor gold's direction (e.g., year-end demand).

---

## ROW 1 — HTF BIAS & STRUCTURE

These panels show the higher timeframe directional context that determines which direction (long/short) is valid.

### HTF Bias Summary
**Metrics:**
- `scp_htf_bias_current{mode="$mode"}` — Current bias direction
- `scp_htf_bias_score{mode="$mode"}` — Bias strength score (0-10)
- `scp_htf_bias_confidence{mode="$mode"}` — Confidence level

**Bias Encoding:**
| Value | Display | Color |
|-------|---------|-------|
| 1 | BULLISH | Green |
| 0 | NEUTRAL | Yellow |
| -1 | BEARISH | Red |

**Confidence Encoding:**
| Value | Display | Color |
|-------|---------|-------|
| 4 | A+ | Green |
| 3 | A | Yellow |
| 2 | B | Orange |
| 1 | C | Red |

**What it measures:** The overall higher timeframe bias calculated from 15m and 1h structure, VWAP trends, and DXY alignment.

**Calculation:** The HTF Bias service aggregates 1m candles into 15m/1h bars, calculates structure (swing highs/lows), and determines:
- **Bias:** Direction based on structure alignment
- **Score:** 0-10 based on structure clarity, confirmation strength
- **Confidence:** Grade based on score thresholds (8+ = A+, 6+ = A, etc.)

**Why it matters:** Only take trades aligned with HTF bias. Contra-trend trades have poor risk/reward.

---

### HTF Structure Matrix
**Metrics:**
- `scp_htf_structure_15m{mode="$mode"}` — 15-minute structure label
- `scp_htf_structure_1h{mode="$mode"}` — 1-hour structure label

**Structure Encoding:**
| Value | Display | Color | Meaning |
|-------|---------|-------|---------|
| 1 | HH | Green | Higher High (bullish) |
| 2 | HL | Light Green | Higher Low (bullish continuation) |
| 3 | LH | Light Red | Lower High (bearish) |
| 4 | LL | Red | Lower Low (bearish continuation) |
| 0 | NEUTRAL | Yellow | No clear structure |

**What it measures:** The most recent swing structure on each timeframe.

**Calculation (Swing Detection with 5-bar window):**
1. **Swing High Detection:** A bar is a swing high if its high is greater than the highs of the 5 bars before AND after it
2. **Swing Low Detection:** A bar is a swing low if its low is less than the lows of the 5 bars before AND after it
3. **Label Assignment:**
   - If new swing high > previous swing high → **HH** (Higher High)
   - If new swing low > previous swing low → **HL** (Higher Low)
   - If new swing high < previous swing high → **LH** (Lower High)
   - If new swing low < previous swing low → **LL** (Lower Low)

**HTF Aggregation:**
- 1m candles are aggregated into 15m and 1h candles in Feature Engine
- Each timeframe maintains its own swing tracker
- Labels update at timeframe boundaries (e.g., every 15 minutes for 15m)

**Why it matters:** Structure alignment between 15m and 1h increases confidence. Conflicting structure (e.g., 15m=HH, 1h=LL) triggers the HTF Verdict FAIL gate.

---

### HTF Integrity Flags
**Metrics:**
- `scp_htf_vwap_trend_confirmed{mode="$mode"}` — VWAP trend confirmation
- `scp_htf_bos_detected{mode="$mode"}` — Break of Structure
- `scp_htf_chop_detected{mode="$mode"}` — Chop detection
- `scp_htf_liquidity_sweep_detected{mode="$mode"}` — Liquidity sweep

| Value | Display | Color |
|-------|---------|-------|
| 1 | YES | Green |
| 0 | NO | Red |

**What each measures and calculation:**

**VWAP Trend Confirmed:**
- **Definition:** Whether price action confirms VWAP slope direction
- **Calculation:** True when:
  - Bullish bias AND close > VWAP AND vwap_slope > 0
  - Bearish bias AND close < VWAP AND vwap_slope < 0
- **Uses:** Original bias direction (before neutralization from DXY/conflicts)

**BOS Detected:**
- **Definition:** Break of Structure on HTF timeframes
- **Calculation:** Same as 1m BOS but on aggregated 15m/1h candles
- **Trigger:** Close breaks beyond previous swing high (bullish) or swing low (bearish)

**Chop Detected (Structural Chop):**
- **Definition:** Market exhibiting structural disorder, avoid trading
- **Calculation:** True when ANY of these conditions are met:
  1. **Overlapping swings:** Recent swing high < previous swing low OR recent swing low > previous swing high (price oscillating within swings)
  2. **Poor structure + No BOS:** Structure clarity < 0.3 AND no BOS in last 15 bars AND some swings exist
  3. **Wick dominance:** Bodies consistently small relative to wicks (indecision)
- **Note:** Different from simple `is_chop` which detects rapid H→L→H or L→H→L alternations

**Liquidity Sweep:**
- **Definition:** Stop hunt detected where price briefly breaks a level then reverses
- **Calculation:** True when:
  1. Price breaks beyond a previous swing high/low (potential stop hunt)
  2. Closes back inside the range (reversal)
  3. Volume spike confirms institutional activity
- **Sweep direction:** "bullish" = swept lows (potential long), "bearish" = swept highs (potential short)

**Why it matters:** These are secondary confirmations that refine entry timing and filter low-probability setups. Chop = stay out. Sweep = potential reversal opportunity.

---

## ROW 2 — DXY & CORRELATION

Dollar Index relationship is critical for gold trading due to the inverse correlation.

### DXY Structure
**Metric:** `scp_feature_dxy_structure{mode="$mode"}`

**Encoding:**
| Value | Display |
|-------|---------|
| 4 | HH (Higher High) |
| 3 | HL (Higher Low) |
| 2 | LH (Lower High) |
| 1 | LL (Lower Low) |
| 0 | N/A (No structure) |

**What it measures:** The current structure label on DXY based on swing highs and lows.

**Calculation:** The Feature Engine service computes DXY structure using the same `StructureContextTracker` algorithm as GC (applied to DXY price data). The metric is encoded as a numeric value for Prometheus, then decoded in the dashboard using value mappings.

**Why it matters:** DXY structure provides directional context for GC trades:
- **HH/HL (bullish DXY)** → Supports short GC setups (inverse correlation)
- **LL/LH (bearish DXY)** → Supports long GC setups (inverse correlation)
- DXY structure should be opposite to desired GC direction for high-confidence trades.

---

### Correlation Strength
**Metrics:**
- `scp_feature_dxy_corr{mode="$mode"}` — 1-minute rolling correlation
- `scp_feature_dxy_5m_corr{mode="$mode"}` — 5-minute rolling correlation

**Range:** -1.0 to +1.0

**Thresholds:**
| Value | Color | Meaning |
|-------|-------|---------|
| -0.7 to -1.0 | Green | Strong inverse (ideal for GC trading) |
| -0.5 to -0.7 | Orange | Moderate inverse |
| -0.3 to -0.5 | Yellow | Weak correlation |
| > -0.3 | Red | Correlation breakdown |

**What it measures:** Rolling Pearson correlation between GC and DXY price movements.

**Calculation:**
1. **Align timestamps:** Inner join GC and DXY candles by timestamp
2. **Calculate returns:** For each aligned pair, compute close-to-close returns
3. **Rolling correlation:** Apply Pearson correlation over rolling window

```
Pearson r = Σ((GC_return - mean_GC) × (DXY_return - mean_DXY)) / 
            (std_GC × std_DXY × n)
```

**Window sizes:**
- `dxy_corr` (1m): 50-bar rolling window on 1-minute candles
- `dxy_5m_corr`: Uses 5-minute equivalent (15-bar, 30-bar, 60-bar windows weighted)

**Multi-window weighted score (for advanced analysis):**
```
weighted_score = 0.5 × corr_15min + 0.3 × corr_30min + 0.2 × corr_60min
```

**Edge cases:**
- Missing DXY data → Returns NaN
- No overlapping timestamps → Returns empty
- NaN values propagated through calculation

**Why it matters:** Gold (GC) has a historically inverse correlation with DXY. When correlation breaks down (moves toward 0 or positive), the intermarket signal is unreliable. Strong negative correlation (-0.7 or stronger) increases signal confidence.

---

### Correlation Verdict
**Metric:** `scp_htf_dxy_aligned{mode="$mode"}`

| Value | Display | Color |
|-------|---------|-------|
| 1 | ALIGNED | Green |
| 0 | NOT ALIGNED | Red |

**What it measures:** Final determination of whether DXY supports the trade direction.

**Calculation:** Combines correlation strength with DXY structure direction. Must have:
- Strong enough negative correlation (threshold configurable)
- DXY moving opposite to intended GC direction

---

## ROW 3 — VWAP & STRUCTURE

VWAP (Volume Weighted Average Price) is a core reference for the trading system.

### Setup Type
**Metric:** `scp_current_setup_type{mode="$mode"}`

| Value | Display | Color | Description |
|-------|---------|-------|-------------|
| 0 | NONE | Grey | No active setup |
| 1 | VWAP_RECLAIM | Green | Price reclaiming VWAP after deviation |
| 2 | VWAP_FADE | Blue | Price fading away from VWAP |
| 3 | DXY_CONTINUATION | Purple | DXY-driven continuation trade |

**What it measures:** The currently detected trading setup pattern.

**Calculation:** Bot Core evaluates features against setup detection rules:
- **VWAP_RECLAIM:** Price was below VWAP, now crossing back above (for longs)
- **VWAP_FADE:** Price extended from VWAP, fading back toward it
- **DXY_CONTINUATION:** Strong DXY signal driving the setup

**Why it matters:** Different setups have different invalidation rules and risk profiles.

---

### VWAP State (Time Series Chart)
**Metrics:**
- `scp_feature_vwap{mode="$mode"}` — Current VWAP value
- `scp_feature_vwap_slope{mode="$mode"}` — VWAP slope (rate of change)
- `scp_feature_vwap_deviation{mode="$mode"}` — Price deviation from VWAP (%)

**What each measures and calculation:**

**VWAP (Volume-Weighted Average Price):**
- **Definition:** Fair value price weighted by volume since session open
- **Calculation:**
  ```
  Typical Price = (High + Low + Close) / 3
  VWAP = Σ(Typical Price × Volume) / Σ(Volume)
  ```
- **Session Reset:** Resets at 08:20 AM Eastern Time (Gold futures RTH open)
- **Cumulative:** Accumulates price × volume from session start

**VWAP Slope:**
- **Definition:** Rate of change of VWAP, indicates directional momentum
- **Calculation:** `vwap_slope = vwap[current] - vwap[previous]`
- **Interpretation:**
  - Positive slope → VWAP rising → bullish bias
  - Negative slope → VWAP falling → bearish bias
  - Near zero → VWAP flat → no directional bias
- **Used for:** VWAP_FADE invalidation (requires slope confirmation in trade direction)

**VWAP Deviation:**
- **Definition:** Percentage distance of price from VWAP
- **Calculation:** `deviation = abs((close - vwap) / vwap) × 100`
- **Interpretation:**
  - High deviation (>0.5%) → Price extended from fair value → fade opportunity
  - Low deviation (<0.2%) → Price near fair value → neutral
- **Used for:** VWAP_FADE setup detection (requires significant deviation)

**Why it matters:** 
- Slope confirms directional bias for trade validation
- Deviation identifies mean reversion opportunities (VWAP_FADE)
- VWAP serves as dynamic support/resistance for entry/exit decisions

---

### Structure Validity
**Metrics:**
- `scp_feature_bos_recent{mode="$mode"}` — Recent Break of Structure
- `scp_feature_bos_age{mode="$mode"}` — Bars since last BOS
- `scp_feature_choch_detected{mode="$mode"}` — Change of Character
- `scp_feature_structure_clarity{mode="$mode"}` — Structure clarity score

**BOS Recent / CHoCH:**
| Value | Display | Color |
|-------|---------|-------|
| 1 | YES | Green |
| 0 | NO | Red |

**BOS Age Thresholds:**
| Value | Color | Meaning |
|-------|-------|---------|
| 0-9 | Green | Fresh BOS, high relevance |
| 10-19 | Yellow | BOS aging, moderate relevance |
| 20+ | Red | Stale BOS, low relevance |

**Clarity Thresholds:**
| Value | Color | Meaning |
|-------|-------|---------|
| 0.7+ | Green | Clear structure |
| 0.5-0.7 | Yellow | Moderate clarity |
| < 0.5 | Red | Unclear/choppy |

**What each measures and how calculated:**

**BOS Recent (Break of Structure):**
- **Definition:** True when price closes beyond a previous swing high (bullish BOS) or swing low (bearish BOS)
- **Calculation:** `bos_recent = True if bos_age <= 15 else False`
- **Detection:** When close price breaks above the highest swing high → bullish BOS; breaks below lowest swing low → bearish BOS
- **Threshold:** 15 bars (configurable)

**BOS Age:**
- **Definition:** Number of bars since the last Break of Structure event
- **Calculation:** `bos_age = current_bar_count - last_bos_bar_index`
- **Value:** Integer starting from 0 (BOS on current bar) to N

**CHoCH (Change of Character):**
- **Definition:** A trend reversal signal when BOS occurs opposite to the prevailing trend
- **Calculation:** CHoCH is detected when ALL of these conditions are met:
  1. Previous trend exists (not neutral)
  2. BOS detected on current bar
  3. BOS direction is OPPOSITE to trend direction (e.g., bullish trend + bearish BOS = bearish CHoCH)
  4. Structure clarity >= 0.5 (sufficient clarity to trust the reversal)
  5. No recent CHoCH in same direction (prevents duplicate triggers)
- **Guard reset:** CHoCH guard resets when sustained opposite trend establishes (clarity >= 0.5, 10+ bars elapsed)

**Structure Clarity:**
- **Definition:** Measures how "clean" the recent swing sequence is (trending vs choppy)
- **Calculation:** Analyzes the last 10 swing labels (HH/HL/LH/LL) and counts:
  - **Continuations:** Same type follows same type (HH→HH, HL→HL, LH→LH, LL→LL)
  - **Alternations:** Different type follows different type (HH→LL, HL→LH, etc.)
  - **Formula:** `clarity = continuations / (continuations + alternations)`
- **Range:** 0.0 (all alternations = choppy) to 1.0 (all continuations = trending)
- **Example:** Sequence [HH, HH, HL, HH, HL] has 3 continuations, 1 alternation → clarity = 0.75

**Why it matters:** Fresh BOS with high clarity = strong entry signal. Stale BOS or low clarity = avoid entry.

---

## ROW 4 — MOMENTUM & CONFIRMATION

Momentum indicators and entry confirmation signals.

### RSI Matrix (Gauge)
**Metric:** `scp_feature_rsi{mode="$mode"}`

**Range:** 0-100

**Thresholds:**

| Value | Color | Meaning |
|-------|-------|---------|
| 0-30 | Red | Oversold (potential long opportunity) |
| 30-40 | Yellow | Approaching oversold |
| 40-60 | Green | Neutral/balanced |
| 60-70 | Yellow | Approaching overbought |
| 70-100 | Red | Overbought (potential short opportunity) |

**What it measures:** Relative Strength Index using Wilder's smoothing method (industry standard).

**Calculation (14-period default):**
```
1. Calculate price changes: delta = close - close[prev]
2. Separate gains and losses:
   - gains = max(delta, 0)  
   - losses = abs(min(delta, 0))
3. First average (SMA for initial period):
   - first_avg_gain = mean(gains[1:15])
   - first_avg_loss = mean(losses[1:15])
4. Subsequent averages (Wilder's smoothing):
   - avg_gain = (prev_avg_gain × 13 + current_gain) / 14
   - avg_loss = (prev_avg_loss × 13 + current_loss) / 14
5. Calculate RSI:
   - RS = avg_gain / avg_loss
   - RSI = 100 - (100 / (1 + RS))
   - Edge cases: if avg_loss = 0, RSI = 100 (if gains) or 50 (if no gains)
```

#### **Warmup:** First 14 bars return NaN (insufficient data).

**Why it matters:** RSI confirms momentum direction and identifies overextended conditions for mean reversion setups (VWAP_FADE).

---

### EMA Stack (Time Series Chart)
**Metrics:**
- `scp_feature_ema_9{mode="$mode"}` — 9-period EMA (fast)
- `scp_feature_ema_20{mode="$mode"}` — 20-period EMA (medium)
- `scp_feature_ema_50{mode="$mode"}` — 50-period EMA (slow)

**What it measures:** Exponential Moving Averages at different periods showing trend alignment.

**Calculation:**
```
EMA = Close × k + EMA[prev] × (1 - k)
k = 2 / (period + 1)
```

**Why it matters:**
- **Stacked EMAs (9 > 20 > 50):** Strong bullish trend
- **Inverse stack (9 < 20 < 50):** Strong bearish trend
- **Crossed/tangled:** Ranging/indecision

---

### Expansion & Liquidity
**Metric:** `scp_feature_expansion_detected{mode="$mode"}`

| Value | Display | Color |
|-------|---------|-------|
| 1 | YES | Green |
| 0 | NO | Red |

**What it measures:** Whether market is expanding out of compression (resolving from a tight range).

**Calculation:** Returns True if ANY of these four signals are detected:

1. **Recent BOS** (within 10 bars):
   - `bos_age <= 10` (configurable threshold)
   - Reason tag: `"recent_bos"`

2. **Range Expansion**:
   - Current bar range (high - low) > 1.5× median range of last 10 bars
   - Formula: `current_range > median(last_10_ranges) * 1.5`
   - Reason tag: `"range_expansion"`

3. **ATR Expansion**:
   - ATR compression ratio > 0.7 (rising from compressed state)
   - Formula: `atr_compression_ratio > 0.7`
   - Reason tag: `"atr_expansion"`

4. **Displacement Candle**:
   - Current bar body > 2× average body of last 10 bars, OR
   - Current bar range > 2× average range of last 10 bars
   - Formula: `current_body > avg_body * 2.0 OR current_range > avg_range * 2.0`
   - Reason tag: `"displacement_candle"`

**Why it matters:** VWAP_RECLAIM setups require expansion detection for valid entries. Expansion indicates price resolving from compression with momentum, increasing probability of follow-through.

---

### Second Confirmation
**Metrics:**
- `scp_feature_second_confirmation_long{mode="$mode"}` — Long entry confirmation
- `scp_feature_second_confirmation_short{mode="$mode"}` — Short entry confirmation

| Value | Display | Color |
|-------|---------|-------|
| 1 | YES | Green |
| 0 | NO | Red |

**What it measures:** Whether secondary confirmation criteria are satisfied after a VWAP reclaim is detected. Prevents premature entries.

**Calculation:** Returns True if ANY of these confirmation signals are detected (for long direction, short is inverse):

1. **VWAP Hold** (`vwap_hold`):
   - Price holding above VWAP for 2+ consecutive bars post-reclaim
   - Formula: `all(close[i] > vwap[i] for i in last_2_bars)`
   - Requires: 2+ bars since reclaim

2. **Volume Expansion** (`volume_expansion`):
   - Current bar volume > 1.5× average of 4 pre-reclaim bars
   - Formula: `current_volume > avg(pre_reclaim_volumes) * 1.5`
   - Baseline: Uses 4 bars BEFORE reclaim as reference

3. **Micro Higher Low** (`micro_hl` for longs, `micro_lh` for shorts):
   - Higher low formed above VWAP (for longs)
   - Formula: `lows[-1] > lows[-2] AND lows[-1] > vwap`
   - Lookback: Up to 3 bars post-reclaim

4. **Expansion Signals** (`expansion_*`):
   - Any expansion signal (from detect_expansion) that aligns with reclaim direction
   - Includes: `expansion_recent_bos`, `expansion_range_expansion`, etc.

**Expiration:** If no confirmation within MAX_RECLAIM_AGE bars (configurable), the reclaim setup expires and returns `confirmed=False`.

**State Tracking:** Uses VWAP reclaim state machine with states:
- `PENDING_ACCEPTANCE`: Waiting for confirmation
- `CONFIRMED`: Confirmation achieved (persists until executed)
- `EXPIRED`: No confirmation within window
- `INVALIDATED`: Structural break invalidated the setup

**Why it matters:** Second confirmation prevents entering VWAP reclaim trades too early before the move is validated, reducing whipsaw losses.

---

## ROW 5 — A+ SCORECARD & DECISION

The final scoring and decision output.

### SOP Score Breakdown (Table)
**Metric:** `scp_signal_score{mode="$mode"}`

**Range:** 0.0 to 10.0

**What it measures:** The composite signal quality score based on all factors.

**Calculation:** Weighted sum of individual component scores:
```
Score = Base Score 
      + HTF Bias Score
      + Structure Score
      + DXY Correlation Score
      + Momentum Score
      + Confirmation Bonus
      + Seasonality Adjustment
```

Each component has defined weights in the scoring configuration.

**Why it matters:** The score quantifies setup quality. Higher scores indicate more confluence factors aligning.

---

### A+ VERDICT (Primary Decision Panel)
**Metric:** `scp_signal_score{mode="$mode"} * (scp_htf_conflict_detected{mode="$mode"} == 0) * (scp_htf_dxy_aligned{mode="$mode"} == 1)`

**Thresholds:**
| Score | Display | Color |
|-------|---------|-------|
| 8.0 - 10.0 | A+ — EXECUTION PERMITTED | Green |
| 0.0 - 7.99 | NOT A+ — STAND DOWN | Red |

**What it measures:** The final binary decision: execute or stand down.

**Calculation:** 
1. Takes the signal score (0-10)
2. Multiplies by hard gate results (0 or 1):
   - HTF Conflict NOT detected (must be 0)
   - DXY Aligned (must be 1)
3. If score ≥ 8.0 AND all hard gates pass → A+ EXECUTION PERMITTED
4. Otherwise → STAND DOWN

**Why it matters:** This is THE decision. Green = take the trade. Red = wait for better setup.

---

## Metric Sources by Service

| Service | Port | Metrics Provided |
|---------|------|------------------|
| **Feature Engine** | 8002 | `scp_feature_*` (VWAP, RSI, EMA, DXY correlation, structure) |
| **HTF Bias** | 8003 | `scp_htf_*` (bias, structure 15m/1h, conflict, chop, integrity flags) |
| **Bot Core** | 8004 | `scp_signal_score`, `scp_session_valid`, `scp_enforcer_tier`, `scp_current_setup_type` |
| **Execution** | 8005 | `scp_trading_halt_reason` |

---

## Common Troubleshooting

### A+ Verdict is Red despite high score
**Check:**
1. HTF Verdict — Is there a conflict or chop detected?
2. DXY Alignment — Is DXY aligned with trade direction?
3. Psychology Gate — Is trading halted due to loss streak/limits?

### Score stuck at 0
**Check:**
1. Session Valid — Are we in trading hours?
2. Feature Engine health — Are features being computed?
3. HTF Bias health — Is bias being calculated?

### DXY showing NOT ALIGNED
**Check:**
1. DXY data flow — Is DXY data reaching Feature Engine?
2. Correlation value — Has correlation broken down (near 0)?
3. DXY structure — Does DXY structure conflict with desired GC direction?

---

## Related Documentation

- [Microservices Architecture](./microservices_architecture.md) — Service design details
- [SL/TP Rules](../.cursor/rules/sl_tp_rules.mdc) — Stop loss and take profit configuration
- [Scoring Configuration](../config/scoring_config.yaml) — Score weights and thresholds
