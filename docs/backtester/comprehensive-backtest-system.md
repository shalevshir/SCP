# Shir Capital Backtest System - Complete Technical Documentation

**Version:** 2.0  
**Last Updated:** December 2025  
**Author:** Shir Capital Development Team

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture & Data Flow](#2-architecture--data-flow)
3. [Candle Processing](#3-candle-processing)
4. [Higher Timeframe (HTF) Bias Calculation](#4-higher-timeframe-htf-bias-calculation)
5. [Guardrails & Validation](#5-guardrails--validation)
6. [Signal Scoring & Confluence](#6-signal-scoring--confluence)
7. [Risk Management](#7-risk-management)
8. [Trade Simulation & Exits](#8-trade-simulation--exits)
9. [State Management](#9-state-management)
10. [Performance Metrics](#10-performance-metrics)

---

## 1. System Overview

### Purpose

The Shir Capital Backtest System is a comprehensive, TDD-driven trading simulation engine that:
- **Processes historical market data candle-by-candle** (no lookahead bias)
- **Enforces all Shir Capital SOP rules** (structure, VWAP, DXY, seasonality)
- **Generates A+ confidence signals** via multi-factor confluence scoring
- **Simulates realistic trade execution** with structure-based SL/TP
- **Tracks complete trade lifecycle** from entry to exit with full auditability

### Key Design Principles

1. **Zero Lookahead Bias**: Features computed incrementally, only using data up to current candle
2. **SOP Compliance**: All guardrails enforced (PDLL, loss streaks, session times, seasonality)
3. **Deterministic Results**: Same input → same output, reproducible across runs
4. **Realistic Execution**: Next bar open entries, intra-candle exit priority (SL before TP)
5. **Complete Auditability**: Every decision logged with reasoning

### Core Components

| Component | Responsibility | Module |
|-----------|---------------|--------|
| **BacktestReplayLoop** | Main orchestrator, processes data candle-by-candle | `backtester/replay_loop.py` |
| **BacktestProcessor** | Incremental feature computation (VWAP, RSI, EMA, DXY) | `feature_engine/backtesting.py` |
| **HTF Bias Calculator** | Multi-timeframe analysis (1H + 15M structure, FVGs, sweeps) | `rule_engine/htf/` |
| **ValidationEngine** | SOP validation (session, CEO directives, HTF alignment) | `validation/engine.py` |
| **BehaviorGuardrails** | Loss streak, fatigue, session extension checks | `validation/guardrails.py` |
| **RuleEngine** | Signal scoring with weighted confluence factors | `rule_engine/scoring.py` |
| **EntryModel** | Entry execution at next bar open | `backtester/entry_model.py` |
| **Trade** | Complete trade lifecycle (SL/TP, PnL, exit tracking) | `backtester/trade.py` |
| **Simulator** | Trade outcome simulation (TP/SL/invalidations/timeout) | `backtester/simulator.py` |
| **InvalidationChecker** | Trade-level invalidations (VWAP/HTF/DXY/session) | `backtester/invalidations.py` |

---

## 2. Architecture & Data Flow

### High-Level Pipeline

```
[Historical Data]
       ↓
[Multi-Timeframe Sync Layer]
       ↓
[BacktestReplayLoop] ← Main Orchestrator
       ↓
┌──────────────────────────────┐
│ For Each Candle:             │
│  1. Update Active Trades     │ ← Check exits on current candle
│  2. Check Guardrails         │ ← PDLL, loss streak, session, DXY
│  3. Compute HTF Bias         │ ← 1H + 15M structure analysis
│  4. Generate Signal          │ ← Confluence scoring
│  5. Execute Entry            │ ← Next bar open if A+ confidence
│  6. Create Trade             │ ← Calculate SL/TP, track state
│  7. Update State             │ ← PnL, loss streak, daily counters
└──────────────────────────────┘
       ↓
[BacktestResults]
```

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   Multi-Timeframe Data                       │
│  GC: [1m, 15m, 1h] + DXY: [1m, 15m, 1h]                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              BacktestProcessor (Incremental)                 │
│  • Compute features bar-by-bar (VWAP, RSI, EMA)            │
│  • Track behavior state (loss streak, fatigue)              │
│  • Build validation context                                 │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  HTF Bias Calculator                         │
│  • 1H: Structure (BOS/CHoCH), FVGs, liquidity sweeps       │
│  • 15M: Swing highs/lows, VWAP trend, DXY correlation     │
│  • Output: HTFBias (bullish/bearish/neutral, 0-10 score)  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   Validation Engine                          │
│  • Session time (10:00-13:00 ILT)                          │
│  • HTF bias alignment                                       │
│  • DXY structure (continuation setups only)                │
│  • Fatigue, risk budget, news events                       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   Behavior Guardrails                        │
│  • Loss streak limits (1 in Sept, 2 otherwise)             │
│  • PDLL enforcement ($600 default)                         │
│  • Max trades per day (2 default)                          │
│  • Fatigue flag, session extension                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                     RuleEngine (Scoring)                     │
│  • Weighted factors: structure, VWAP, RSI, EMA, DXY, FVG  │
│  • HTF bonus (+1.5 if aligned)                             │
│  • Setup-specific weights (RECLAIM, FADE, CONTINUATION)    │
│  • Output: Signal (0-10 score, A+/A/B+/B/C confidence)    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    Entry Execution                           │
│  • A+ confidence required (score ≥ 8.0)                    │
│  • Execute at next bar open (realistic slippage)           │
│  • Calculate structure-based SL/TP                          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  Trade Simulation                            │
│  • Process future candles bar-by-bar                        │
│  • Exit priority: SL → TP → Invalidations → Timeout       │
│  • Track: PnL (points + dollars), R achieved, duration     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   BacktestResults                            │
│  • All trades (closed with outcomes)                        │
│  • Metrics: Win rate, average R, total PnL, PDLL hits     │
│  • Auditability: Every decision logged with reasoning      │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Candle Processing

### BacktestProcessor: Incremental Feature Computation

**Location:** `feature_engine/backtesting.py`

The `BacktestProcessor` is responsible for **incremental, lookahead-free** feature computation. It processes historical data bar-by-bar, maintaining internal state to simulate live trading conditions.

#### Key Features

1. **Zero Lookahead Bias**: Only uses data up to current candle
2. **Incremental Computation**: Maintains rolling windows for VWAP, EMA, RSI
3. **Validation Context**: Builds session constraints, guardrail state for each candle
4. **Behavior Tracking**: Tracks loss streaks, fatigue flags, session resets

#### Feature Set

| Feature | Description | Calculation |
|---------|-------------|-------------|
| **vwap** | Volume-weighted average price | `Σ(price × volume) / Σ(volume)` (daily reset) |
| **rsi** | Relative strength index (14-period) | `100 - (100 / (1 + RS))` where `RS = avg_gain / avg_loss` |
| **ema_9** | 9-period exponential moving average | `EMA = (close × α) + (prev_EMA × (1 - α))` where `α = 2/(9+1)` |
| **ema_20** | 20-period exponential moving average | Same as above, `α = 2/(20+1)` |
| **ema_50** | 50-period exponential moving average | Same as above, `α = 2/(50+1)` |
| **dxy_corr** | GC-DXY correlation (50-bar window) | Rolling Pearson correlation between GC and DXY returns |
| **structure_label** | Microstructure classification | "HH", "HL", "LH", "LL", "NONE" |

#### Validation Context

For each candle, the processor builds a **ValidationContext** containing:

```python
{
    "timestamp": current_timestamp,
    "session_ok": bool,  # 10:00-13:00 ILT
    "session_constraints": SessionConstraints,  # Max losses, tier rules
    "guardrail_result": GuardrailResult,  # Loss streak, fatigue checks
    "behavior_state": BehaviorState,  # Current loss streak, fatigue flag
    "dxy_available": bool,  # Whether DXY feed is valid
}
```

#### Iteration Pattern

```python
processor = BacktestProcessor(timeframe="1m")

for features, validation_context, next_candle in processor.iterate_with_entry_context(gc_df, dxy_df):
    # features: pd.Series with all computed features
    # validation_context: dict with session/guardrail state
    # next_candle: Candle | None for entry execution (None at end of data)
    
    # Process this candle (guardrails, HTF bias, signal generation, entry execution)
    ...
```

---

## 4. Higher Timeframe (HTF) Bias Calculation

### Overview

The HTF Bias Calculator analyzes **1H and 15M timeframes** to determine the dominant market structure. This is the **primary filter** for signal generation—only signals aligned with HTF bias are allowed.

**Location:** `rule_engine/htf/`

### Two Approaches

#### 1. Streaming (Incremental)

**Location:** `rule_engine/htf/streaming.py`

- **Use Case**: Mimics live trading, bar-by-bar updates
- **Memory**: O(1), maintains small state buffers
- **Performance**: Fast, processes bars as they close
- **How It Works**:
  - Maintains separate `StreamingFeatureProcessor` for 1H and 15M
  - Detects bar boundaries (15M closes every 15 bars, 1H closes every 60 bars)
  - Calls `compute_htf_bias()` when boundaries reached

```python
calculator = StreamingHTFBiasCalculator()

for gc_bar, dxy_bar in zip(gc_1m_data, dxy_1m_data):
    htf_bias = calculator.update(gc_bar, dxy_bar)
    if htf_bias:
        # New HTF bias available (1H or 15M bar closed)
        print(f"HTF Bias: {htf_bias.bias}, Score: {htf_bias.score}")
```

#### 2. Vectorized (Pre-computed)

**Location:** `rule_engine/htf/calculator.py`

- **Use Case**: Batch processing, backtesting entire datasets
- **Memory**: O(n), pre-computes all HTF features upfront
- **Performance**: Faster for large datasets, one-time computation
- **How It Works**:
  - Pre-resamples 1M data to 1H and 15M
  - Computes all HTF features (structure, FVGs, sweeps) in batch
  - Lookups are instant during backtest

```python
htf_bias = compute_htf_bias_multi_timeframe(
    df_1m=gc_1m_data,
    dxy_1m=dxy_1m_data,
    timestamp=current_timestamp,
)
```

### HTF Bias Components

#### 1H Timeframe Analysis

| Component | Description | Detection Method |
|-----------|-------------|------------------|
| **Structure (BOS/CHoCH)** | Break of Structure or Change of Character | Swing high/low breaks with price confirmation |
| **FVGs (Fair Value Gaps)** | Imbalances left by strong directional moves | 3-candle pattern: `candle[i-1].low > candle[i+1].high` |
| **Liquidity Sweeps** | Stop hunts above swing highs/below swing lows | Price wicks above/below swings, then reverses |
| **VWAP Trend** | Relative position to VWAP | `close > vwap` (bullish) or `close < vwap` (bearish) |
| **DXY Correlation** | Gold-Dollar inverse relationship | Rolling 50-bar correlation, strong inverse expected |

#### 15M Timeframe Analysis

| Component | Description | Purpose |
|-----------|-------------|---------|
| **Swing Highs/Lows** | Recent pivot points | Confirmation, structure validation |
| **Microstructure** | HH, HL, LH, LL patterns | Trend confirmation within 1H bias |
| **VWAP Reclaims** | Price crossing VWAP with volume | Entry trigger confirmation |

### HTF Bias Output: HTFBias Object

```python
@dataclass
class HTFBias:
    bias: str  # "bullish", "bearish", "neutral"
    direction: str  # "long", "short", None
    score: float  # 0-10 (8+ required for A+ confidence)
    confidence: str  # "high", "medium", "low"
    
    # Structure context
    bos_candle: Candle | None  # Break of structure candle (for SL calculation)
    confirmation_candle: Candle | None  # Confirmation candle (for SL calculation)
    choch_detected: bool  # Change of character
    
    # Alignment flags
    dxy_alignment: bool  # DXY correlation aligned
    vwap_alignment: bool  # VWAP trend aligned
    
    # Confluence breakdown
    structure_score: float  # 0-3 (BOS/CHoCH/swing breaks)
    fvg_score: float  # 0-2 (Fair value gaps aligned)
    sweep_score: float  # 0-2 (Liquidity sweeps detected)
    vwap_score: float  # 0-1.5 (VWAP trend alignment)
    dxy_score: float  # 0-1.5 (DXY correlation strength)
    
    rationale: str  # Human-readable explanation
```

### HTF Scoring Logic

**Total HTF Score = Structure + FVG + Sweep + VWAP + DXY (max 10.0)**

| Factor | Weight | Criteria |
|--------|--------|----------|
| **Structure** | 0-3.0 | BOS (3.0), CHoCH (2.0), Swing break (1.5) |
| **FVG** | 0-2.0 | Bullish FVG (2.0), Neutral FVG (1.0) |
| **Sweep** | 0-2.0 | Liquidity sweep aligned (2.0) |
| **VWAP** | 0-1.5 | Close > VWAP (bullish, 1.5) or < VWAP (bearish, 1.5) |
| **DXY** | 0-1.5 | Strong inverse correlation < -0.6 (1.5) |

**Confidence Classification:**
- **High**: HTF Score ≥ 7.5
- **Medium**: 5.0 ≤ HTF Score < 7.5
- **Low**: HTF Score < 5.0

---

## 5. Guardrails & Validation

### Three-Layer Guardrail System

#### Layer 1: Pre-Signal Guardrails (Before Scoring)

**Location:** `backtester/replay_loop.py` → `_check_guardrails()`

These guardrails **block signal generation entirely** if not met:

| Guardrail | Rule | Blocking Reason |
|-----------|------|-----------------|
| **PDLL Hit** | Daily loss ≤ -$600 (default) | "PDLL hit - no further trading today" |
| **PDLL Check** | Current daily PnL ≤ -$600 | "PDLL limit reached: daily_pnl={pnl}" |
| **Daily Trade Limit** | Max 2 trades per day (default) | "Daily trade limit reached: {count}/{max}" |
| **Session Time** | 10:00-13:00 ILT (default) | "Outside trading session hours" |
| **DXY Availability** | DXY correlation not None/NaN | "DXY data not available" |
| **Risk Ladder** | Max contracts > 0 for current phase | "Risk ladder constraint: max_contracts=0" |

**Code Flow:**

```python
def _check_guardrails(validation_context, current_timestamp, features):
    blocking_reasons = []
    
    # Check PDLL
    if self._pdll_hit:
        blocking_reasons.append("PDLL hit - no further trading today")
    
    # Check daily loss
    if self._daily_pnl <= -pdll_limit:
        blocking_reasons.append(f"PDLL limit reached: {self._daily_pnl:.2f}")
    
    # Check trade count
    if self._trades_today >= max_trades_per_day:
        blocking_reasons.append(f"Daily trade limit reached")
    
    # Check session time
    if not session_ok:
        blocking_reasons.append("Outside trading session hours")
    
    # Check DXY availability
    if dxy_corr is None or pd.isna(dxy_corr):
        blocking_reasons.append("DXY data not available")
    
    # Check risk ladder
    if max_contracts <= 0:
        blocking_reasons.append("Risk ladder constraint")
    
    return len(blocking_reasons) == 0, blocking_reasons
```

#### Layer 2: Behavior Guardrails (Before Entry)

**Location:** `validation/guardrails.py`

These guardrails **evaluate behavioral state** (loss streaks, fatigue) before allowing new entries:

| Guardrail | Rule | Implementation |
|-----------|------|----------------|
| **Loss Streak** | Max 2 consecutive losses (1 in September) | `consecutive_losses >= max_losses` |
| **Fatigue Flag** | Manual operator halt | `fatigue_flag == True` |
| **Session Extension** | Trading beyond allowed window | `session_extended == True` |

**BehaviorState Tracking:**

```python
@dataclass(frozen=True)
class BehaviorState:
    consecutive_losses: int = 0
    fatigue_flag: bool = False
    session_extended: bool = False
    last_reset: datetime | None = None
```

**Loss Streak Logic:**

```python
def record_trade_outcome(won: bool | None):
    if won is True:
        # Win: reset streak
        consecutive_losses = 0
    elif won is False:
        # Loss: increment streak
        consecutive_losses += 1
    # won is None (breakeven): streak unchanged
```

#### Layer 3: Validation Engine (Signal-Level)

**Location:** `validation/engine.py`

The `ValidationEngine` evaluates **signal-level SOP compliance**:

| Check | Rule | Error Message |
|-------|------|---------------|
| **Session Active** | 10:00-13:00 ILT | "Trading session not active" |
| **HTF Alignment** | Signal direction matches HTF bias | "HTF bias mismatch: {bias} vs {direction}" |
| **DXY Trending** | DXY structure clean (continuation only) | "DXY structure not clean" |
| **Risk Budget** | Daily risk allowance not exhausted | "Risk budget exhausted" |
| **News Events** | No high-impact news active | "High-impact news event active" |

**Validation Flow:**

```python
def validate(context, direction, setup_type):
    errors = []
    
    # Behavior guardrails
    if guardrail_result and not guardrail_result.allowed:
        errors.extend(guardrail_result.reasons)
    
    # Session time
    if not context.session_ok:
        errors.append("Trading session not active")
    
    # HTF bias alignment
    if context.htf_bias == "bullish" and direction == "short":
        errors.append("HTF bias mismatch")
    
    # DXY structure (continuation only)
    if setup_type in ("DXY_CONTINUATION",) and not context.dxy_trending_clean:
        errors.append("DXY structure not clean")
    
    return ValidationResult(valid=len(errors) == 0, errors=errors)
```

---

## 6. Signal Scoring & Confluence

### Confluence Scoring System

**Location:** `rule_engine/scoring.py`

The RuleEngine uses a **weighted multi-factor confluence model** to score signals from 0-10. Only signals scoring **≥8.0** ("A+" confidence) are executed.

### Weighted Factors

| Factor | Weight Range | Criteria | Setup Specificity |
|--------|--------------|----------|-------------------|
| **Structure Alignment** | 0-2.5 | HH/HL (bullish) or LH/LL (bearish) | All setups |
| **VWAP Relation** | 0-2.0 | Close > VWAP (bullish) or < VWAP (bearish) | VWAP_RECLAIM, VWAP_FADE |
| **RSI State** | 0-1.5 | Oversold (<30) or overbought (>70) | VWAP_FADE heavily weighted |
| **EMA Stack** | 0-1.5 | EMA 9 > 20 > 50 (bullish) or reverse (bearish) | All setups |
| **DXY Correlation** | 0-1.5 | Strong inverse correlation (< -0.6) | DXY_CONTINUATION heavily weighted |
| **FVG Alignment** | 0-1.0 | Fair value gap in signal direction | VWAP_RECLAIM, DXY_CONTINUATION |
| **Liquidity Sweep** | 0-1.0 | Sweep detected before signal | VWAP_FADE, VWAP_RECLAIM |
| **HTF Bonus** | 0-1.5 | HTF bias aligned with signal | All setups |

### Setup-Specific Weight Profiles

#### VWAP_RECLAIM (Continuation)

**When**: Price reclaims VWAP with volume, continuation setup

**Factor Weights:**
```yaml
structure_alignment: 2.5  # Strongest weight (HH/HL required)
vwap_relation: 2.0        # VWAP reclaim is core trigger
ema_stack: 1.5            # Trend confirmation
dxy_corr: 1.0             # Moderate DXY weight
rsi_state: 1.0            # Moderate RSI weight
fvg_alignment: 1.0        # FVG alignment bonus
liquidity_sweep: 0.5      # Minor weight
```

**Max Base Score**: 9.5 (before HTF bonus)

#### VWAP_FADE (Mean Reversion)

**When**: Price extends far from VWAP with extreme RSI, fade setup

**Factor Weights:**
```yaml
rsi_state: 2.5            # Strongest weight (RSI < 30 or > 70 required)
vwap_relation: 2.0        # VWAP deviation is key
structure_alignment: 1.5  # Structure less critical (counter-trend)
liquidity_sweep: 1.5      # Sweep detection highly valued
ema_stack: 1.0            # Moderate EMA weight
dxy_corr: 0.5             # Minor DXY weight
fvg_alignment: 0.5        # Minor FVG weight
```

**Max Base Score**: 9.5 (before HTF bonus)

#### DXY_CONTINUATION (Correlation Play)

**When**: Strong inverse DXY correlation drives GC movement

**Factor Weights:**
```yaml
dxy_corr: 3.0             # Dominant factor (correlation < -0.8 required)
structure_alignment: 2.0  # Structure confirmation
ema_stack: 1.5            # Trend confirmation
vwap_relation: 1.5        # VWAP trend
fvg_alignment: 1.0        # FVG bonus
rsi_state: 0.5            # Minor RSI weight
liquidity_sweep: 0.0      # Not applicable
```

**Max Base Score**: 9.5 (before HTF bonus)

### HTF Score Adjustment

After calculating base score, **HTF bias alignment** applies bonuses:

| HTF Alignment | Bonus | Logic |
|---------------|-------|-------|
| **Aligned + High Confidence** | +1.5 | HTF score ≥ 7.5, signal direction matches HTF direction |
| **Aligned + Medium Confidence** | +1.0 | 5.0 ≤ HTF score < 7.5, direction matches |
| **Neutral or Misaligned** | +0.0 | No bonus |

**Final Score Capping:**
- Final Score = min(Base Score + HTF Bonus, 10.0)
- A+ Confidence requires Final Score ≥ 8.0

### Confidence Classification

| Score Range | Confidence | Action |
|-------------|------------|--------|
| 8.0 - 10.0 | **A+** | **EXECUTE** entry at next bar open |
| 7.0 - 7.9 | **A** | Log signal, no entry (score too low) |
| 6.0 - 6.9 | **B+** | Log signal, no entry |
| 5.0 - 5.9 | **B** | Log signal, no entry |
| 0.0 - 4.9 | **C or Reject** | Rejected signal |

### Signal Object

```python
@dataclass
class Signal:
    timestamp: datetime
    symbol: str  # "GC"
    timeframe: str  # "1m"
    direction: str  # "long" or "short"
    setup_type: str  # "VWAP_RECLAIM", "VWAP_FADE", "DXY_CONTINUATION"
    htf_bias: str  # "bullish", "bearish", "neutral"
    
    score: float  # 0-10 (final score after HTF bonus)
    confidence: str  # "A+", "A", "B+", "B", "C", "Reject"
    
    factors: dict[str, float]  # Factor breakdown (structure, vwap, rsi, etc.)
    rationale: str  # Human-readable explanation
    validation_flags: dict[str, bool]  # session_ok, htf_valid, dxy_alignment_ok
    enforcer_tier: str  # "Conservative", "Early Mild", "Mild", "Offensive"
```

---

## 7. Risk Management

### Structure-Based Stop Loss (SL)

**Location:** `backtester/trade.py` → `calculate_stop_loss()`

**SOP Rule**: SL must be **structure-based**, never inside liquidity zones (FVG, sweep wick, VWAP reclaim wick).

#### Continuation Setups (VWAP_RECLAIM, DXY_CONTINUATION)

**Long**:
```
SL = min(confirmation_candle.low, bos_candle.low if provided)
```

**Short**:
```
SL = max(confirmation_candle.high, bos_candle.high if provided)
```

**Rationale**:
- Long: SL below the lower of confirmation/BOS (protects against structure break)
- Short: SL above the higher of confirmation/BOS (protects against structure break)

#### Fade Setup (VWAP_FADE)

**Long**:
```
SL = sweep_candle.low
```

**Short**:
```
SL = sweep_candle.high
```

**Rationale**:
- Fade setups use sweep candle extreme (wick low/high) as SL
- Sweep must take **only one side** (not both), otherwise invalid

### R-Multiple Based Take Profit (TP)

**Location:** `backtester/trade.py` → `calculate_take_profit()`

**SOP Rule**: TP based on **R:R ratio** (2R or 3R) with seasonality adjustments.

#### Calculation

```python
risk_distance = abs(entry_price - stop_loss)

if direction == "long":
    TP = entry_price + (risk_distance × R_multiple)
else:  # short
    TP = entry_price - (risk_distance × R_multiple)
```

#### R-Multiple Rules

| Setup Type | Default R | Seasonality Adjustment |
|------------|-----------|------------------------|
| **VWAP_RECLAIM** | 3R | September: 2R (defensive) |
| **DXY_CONTINUATION** | 3R | September: 2R (defensive) |
| **VWAP_FADE** | 2R | Nov-Dec + HTF + DXY aligned: Upgrade to 3R |

**Upgrade Logic (VWAP_FADE):**
```python
if setup_type == "VWAP_FADE":
    if month in [11, 12] and htf_aligned and dxy_aligned:
        r_multiple = 3.0  # Upgraded
    else:
        r_multiple = 2.0  # Default
```

### Phase-Aware Risk Ladder

**Location:** `risk_config` passed to `create_trade_from_entry()`

| Phase | Buffer | Risk/Trade | Max Loss/Day | Max Contracts |
|-------|--------|------------|--------------|---------------|
| **Startup** | $0-5K | $350 | $600 | 1 |
| **Growth** | $5-15K | $450-600 | $900-1K | 1-2 |
| **Scaling** | $15-40K | $700-1K | $1.5-2K | 2-3 |
| **Institutional** | $40K+ | $1.2K+ | $2.5K+ | 3-4 |

**Risk Config Example:**
```python
risk_config = {
    "risk_per_trade": 600.0,  # Dollar risk per trade
    "buffer_phase": "growth",
    "max_contracts": 1,
}
```

**Contracts Determination:**
```python
contracts = risk_config.get("max_contracts", 1)
```

### Dollar-Based PnL Calculation

**Location:** `backtester/pnl_calculator.py`

**Components:**
1. **Gross PnL**: Point movement × tick value × contracts
2. **Slippage Cost**: Simulated market impact (0.5 ticks default)
3. **Commission Cost**: Broker fees ($5 per contract per side default)
4. **Net PnL**: Gross PnL - Slippage - Commission

**Formula:**
```python
# Gross PnL
price_change_points = exit_price - entry_price  # (long)
gross_pnl = price_change_points × (tick_value / tick_size) × contracts

# Slippage (applied on both entry and exit)
slippage_cost = -abs(slippage_ticks × tick_value × contracts)

# Commission (entry + exit)
commission_cost = -(commission_per_contract × 2 × contracts)

# Net PnL
net_pnl = gross_pnl + slippage_cost + commission_cost
```

**Example (GC):**
```
Entry: 2650.0, Exit: 2665.0 (long, +15 points)
Contracts: 1
Tick value: $10
Tick size: 0.1
Slippage: 0.5 ticks ($5)
Commission: $5 per contract per side ($10 total)

Gross PnL = 15 × ($10 / 0.1) × 1 = $1,500
Slippage = -$5
Commission = -$10
Net PnL = $1,500 - $5 - $10 = $1,485
```

---

## 8. Trade Simulation & Exits

### Trade Lifecycle

**Location:** `backtester/simulator.py` → `simulate_trade_outcome()`

#### Entry Execution

**Location:** `backtester/entry_model.py` → `execute_entry_at_next_open()`

- **When**: Signal with A+ confidence (score ≥ 8.0) generated
- **Execution**: Next bar open (realistic slippage, no lookahead)
- **Rejection**: If next candle not available (end of data)

```python
def execute_entry_at_next_open(signal: Signal, next_candle: Candle | None):
    if next_candle is None:
        # End of data, cannot execute
        return EntryExecution(
            executed=False,
            rejection_reason="no_next_candle",
            ...
        )
    
    if signal.confidence != "A+":
        # Score too low
        return EntryExecution(
            executed=False,
            rejection_reason="confidence_too_low",
            ...
        )
    
    # Execute at next bar open
    return EntryExecution(
        executed=True,
        entry_timestamp=next_candle.timestamp,
        entry_price=next_candle.open,
        signal=signal,
        ...
    )
```

#### Exit Priority (SOP Compliant)

**Within each candle, exits are checked in strict priority order:**

1. **Stop Loss** → Exit at SL price (highest priority per SOP)
2. **Take Profit** → Exit at TP price
3. **VWAP Invalidation** → Exit at candle open
4. **HTF Invalidation** → Exit at candle open
5. **DXY Flip** → Exit at candle open
6. **Session End** → Exit at candle open (13:00 ILT default)
7. **Setup Window Expiration** → Exit at candle open
8. **Timeout** → Exit at candle close (20 bars continuation, 10 bars fade)
9. **End of Data** → Exit at last candle close

**Code Flow:**

```python
for candle in future_candles:
    bars_elapsed += 1
    
    # 1. Stop Loss (highest priority)
    if check_sl_hit(trade, candle):
        return close_trade(trade, candle, "sl", config)
    
    # 2. Take Profit
    if check_tp_hit(trade, candle):
        return close_trade(trade, candle, "tp", config)
    
    # 3-7. Invalidations
    if invalidation_checker:
        is_invalid, reason = invalidation_checker.check_all(trade, candle, bars_elapsed)
        if is_invalid:
            return close_trade(trade, candle, map_reason(reason), config)
    
    # 8. Timeout
    if check_timeout(bars_elapsed, trade.setup_type):
        return close_trade(trade, candle, "timeout", config)

# 9. End of data
return close_trade(trade, last_candle, "end_of_data", config)
```

### Invalidation Checks

**Location:** `backtester/invalidations.py`

#### +1R Time Limit

**SOP Rule**: Trade must reach +1R within time limits, else exit.

| Setup Type | Time Limit |
|------------|------------|
| VWAP_RECLAIM | 20 bars |
| DXY_CONTINUATION | 20 bars |
| VWAP_FADE | 10 bars |

**Logic:**
```python
def check_no_1r_reached(trade, bars_elapsed):
    time_limit = R1_TIME_LIMITS.get(trade.setup_type, 20)
    
    if bars_elapsed < time_limit:
        return False, None  # Not at time limit yet
    
    if not state["reached_1r"]:
        return True, f"+1R not reached within {time_limit} bars"
    
    return False, None
```

#### VWAP Invalidation

**SOP Rule**: Exit if VWAP structure breaks against trade direction.

**Continuation (VWAP_RECLAIM):**
- Long: Invalid if `close < VWAP` (price falls below VWAP)
- Short: Invalid if `close > VWAP` (price rises above VWAP)

**Fade (VWAP_FADE):**
- Long: Invalid if `close > VWAP` (VWAP reclaimed from below)
- Short: Invalid if `close < VWAP` (VWAP reclaimed from above)

#### HTF Structure Invalidation

**SOP Rule**: Exit if HTF structure breaks opposite to trade direction.

**Logic:**
- Long: Invalid if structure shows LH or LL (bearish structure)
- Short: Invalid if structure shows HH or HL (bullish structure)

```python
def check_htf_structure_invalidation(trade, candle, features):
    structure_label = features.get("structure_label")
    
    if trade.direction == "long":
        if structure_label in ("LH", "LL"):
            return True, f"HTF invalidation: {structure_label} (bearish)"
    else:  # short
        if structure_label in ("HH", "HL"):
            return True, f"HTF invalidation: {structure_label} (bullish)"
    
    return False, None
```

#### DXY Flip

**SOP Rule**: Exit immediately when DXY breaks alignment.

**Heuristic:**
- Long: DXY correlation should be negative (<-0.3). If correlation > -0.3, DXY flipped.
- Short: DXY correlation can be less negative. If correlation < -0.6, DXY flipped.

#### Session End

**SOP Rule**: Force exit at session end (13:00 ILT default).

```python
def check_session_end(trade, candle, session_end_time=time(13, 0)):
    israel_tz = ZoneInfo("Asia/Jerusalem")
    local_dt = candle.timestamp.astimezone(israel_tz)
    
    if local_dt.time() >= session_end_time:
        return True, f"Session end: {local_dt.time()} >= {session_end_time}"
    
    return False, None
```

#### Daily Risk Stop

**SOP Rule**: Exit if consecutive loss limit reached or PDLL breached.

**Logic:**
- September: Max 1 loss
- Other months: Max 2 losses
- PDLL: Default $600 per day

```python
def check_daily_risk_breach(trade, candle, daily_pnl_state):
    consecutive_losses = daily_pnl_state.get("consecutive_losses", 0)
    month = candle.timestamp.month
    
    max_losses = 1 if month == 9 else 2
    
    if consecutive_losses >= max_losses:
        return True, f"Daily risk stop: {consecutive_losses} consecutive losses"
    
    pdll = daily_pnl_state.get("pdll")
    daily_pnl = daily_pnl_state.get("daily_pnl", 0.0)
    
    if pdll and daily_pnl <= -abs(pdll):
        return True, f"PDLL breached: {daily_pnl:.2f}"
    
    return False, None
```

---

## 9. State Management

### Session-Level State

**Location:** `backtester/replay_loop.py`

The `BacktestReplayLoop` maintains **mutable state** across the entire backtest session:

```python
class BacktestReplayLoop:
    def __init__(self, ...):
        # Active trades (max 1 at a time per SOP)
        self._active_trades: dict[str, Trade] = {}
        
        # Daily state (resets at session boundary)
        self._daily_pnl: float = 0.0
        self._session_date: datetime | None = None
        self._trades_today: int = 0
        self._pdll_hit: bool = False
        
        # Lifetime metrics
        self._max_consecutive_losses: int = 0
        self._pdll_hit_count: int = 0
        self._session_reset_count: int = 0
        
        # Results tracking
        self._all_trades: list[Trade] = []
        self._all_executions: list[EntryExecution] = []
```

### State Updates

#### Session Reset (Daily Boundary)

**When**: New trading day detected

**Resets:**
- Daily PnL → 0.0
- PDLL hit flag → False
- Trades today counter → 0
- Loss streak → 0 (BehaviorTracker)
- InvalidationChecker daily state

```python
def _reset_session(current_timestamp):
    current_date = current_timestamp.date()
    
    if self._session_date and current_date == self._session_date:
        return  # Same session, no reset
    
    # Reset daily state
    self._daily_pnl = 0.0
    self._pdll_hit = False
    self._trades_today = 0
    self._session_date = current_date
    
    # Reset behavior tracker
    self._processor._behavior_tracker.reset_for_session(current_timestamp)
    
    # Reset invalidation checker
    self._invalidation_checker._daily_state = {
        "consecutive_losses": 0,
        "daily_pnl": 0.0,
        "last_session_date": current_date,
    }
```

#### Trade Outcome Recording

**When**: Trade closes with PnL

**Updates:**
- Daily PnL (accumulated)
- Loss streak (win resets, loss increments, breakeven no change)
- InvalidationChecker daily state (for PDLL checks)
- BehaviorTracker (for loss streak guardrails)

```python
def _update_state(closed_trade):
    # Update daily PnL
    self._daily_pnl += closed_trade.pnl
    
    # Determine outcome
    if closed_trade.pnl > 0:
        won = True
    elif closed_trade.pnl < 0:
        won = False
    else:
        won = None  # Breakeven
    
    # Update behavior tracker
    self._processor.record_trade_outcome(won)
    
    # Update invalidation checker
    self._invalidation_checker.record_trade_outcome(closed_trade, won)
    
    # Track max consecutive losses
    current_state = self._processor._behavior_tracker.state
    self._max_consecutive_losses = max(
        self._max_consecutive_losses,
        current_state.consecutive_losses
    )
```

### Trade-Level State

**Location:** `backtester/invalidations.py`

The `InvalidationChecker` maintains **per-trade state** to track progress:

```python
class InvalidationChecker:
    def __init__(self):
        self._trade_states: dict[str, dict] = {}
        self._daily_state: dict = {
            "consecutive_losses": 0,
            "daily_pnl": 0.0,
            "last_session_date": None,
        }
    
    def _get_trade_state(self, trade_id):
        if trade_id not in self._trade_states:
            self._trade_states[trade_id] = {
                "reached_1r": False,
                "vwap_reclaimed": False,
                "window_active": True,
            }
        return self._trade_states[trade_id]
```

**State Tracking:**
- **reached_1r**: Whether trade reached +1R profit
- **vwap_reclaimed**: Whether VWAP was reclaimed (fade setups)
- **window_active**: Whether setup window is still active

---

## 10. Performance Metrics

### BacktestResults Object

**Location:** `backtester/replay_loop.py` → `BacktestResults`

```python
@dataclass
class BacktestResults:
    trades: list[Trade]  # All closed trades
    executions: list[EntryExecution]  # All entry attempts (including rejected)
    
    # PnL metrics
    total_pnl: float  # Total PnL in points
    total_pnl_dollars: float | None  # Total PnL in dollars (if config provided)
    
    # Win rate
    win_rate: float  # Percentage (0-100)
    total_trades: int
    winning_trades: int
    losing_trades: int
    
    # R-multiple
    average_r: float  # Average R achieved per trade
    
    # Guardrail hits
    max_consecutive_losses: int
    pdll_hits: int  # Number of times PDLL was hit
    session_resets: int  # Number of session resets
```

### Metric Calculation

#### Win Rate

```python
win_rate = (winning_trades / total_trades × 100) if total_trades > 0 else 0.0
```

#### Average R

```python
r_values = [t.r_realized for t in trades if t.r_realized is not None]
average_r = sum(r_values) / len(r_values) if r_values else 0.0
```

#### Total PnL (Points)

```python
total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
```

#### Total PnL (Dollars)

```python
total_pnl_dollars = sum(t.pnl_net for t in trades if t.pnl_net is not None)
```

### Per-Trade Metrics

Each `Trade` object contains:

```python
@dataclass
class Trade:
    # PnL metrics
    pnl: float | None  # Realized PnL in points
    pnl_percent: float | None  # PnL as % of risk
    r_realized: float | None  # Actual R achieved (e.g., 2.5R)
    
    # Dollar-based PnL
    pnl_dollars: float | None  # Gross PnL in dollars
    pnl_net: float | None  # Net PnL after slippage + commission
    slippage_cost: float | None  # Slippage cost in dollars
    commission_cost: float | None  # Commission cost in dollars
    
    # Trade metadata
    duration_bars: int | None  # Trade duration in candles
    invalidation_triggered: bool  # Whether closed due to invalidation
    status: str  # "OPEN", "CLOSED_WIN", "CLOSED_LOSS", "STOPPED_OUT"
```

### Logging & Auditability

**Key Log Messages:**

1. **Backtest Start:**
   ```
   Starting Backtest Replay Loop
   Dataset: {candle_count} candles
   Timeframe: {timeframe}
   Buffer phase: {buffer_phase}
   Tier active: {tier_active}
   ```

2. **Guardrail Block:**
   ```
   Guardrails blocked entry at {timestamp}: {blocking_reasons}
   ```

3. **Signal Generated:**
   ```
   Confluence breakdown: structure=2.50, vwap=2.00, rsi=1.50, ema=1.50, 
   dxy=1.50, fvg=1.00, sweep=0.50, htf_bonus=1.50 | base=9.00, final=10.00
   ```

4. **Trade Opened:**
   ```
   Trade opened: {trade_id} {direction} {symbol} @ {entry_price} 
   (SL={stop_loss}, TP={take_profit}, R={r_multiple})
   ```

5. **Trade Closed:**
   ```
   Trade {trade_id} closed at {exit_timestamp}: exit_reason={exit_reason}, 
   PnL={pnl:.2f}, R={r_realized:.2f}
   ```

6. **Session Reset:**
   ```
   Session reset at {timestamp}
   Previous session date: {prev_date}
   Previous daily PnL: {daily_pnl:.2f}
   Previous trades today: {trades_today}
   ```

7. **Backtest Complete:**
   ```
   Backtest Replay Loop Complete
   Candles processed: {candle_count}
   Signals generated: {signal_count}
   Entries executed: {entry_count}
   Trades completed: {total_trades}
   Win rate: {win_rate:.1f}%
   Total PnL: {total_pnl:.2f} points
   Total PnL (dollars): ${total_pnl_dollars:.2f}
   Average R: {average_r:.2f}R
   Max consecutive losses: {max_consecutive_losses}
   PDLL hits: {pdll_hits}
   Session resets: {session_resets}
   ```

---

## Appendix: SOP Summary

### Critical SOP Rules Enforced

1. **PDLL (Per Day Loss Limit)**: $600 default, trading halts when reached
2. **Loss Streak**: Max 2 consecutive losses (1 in September)
3. **Session Time**: 10:00-13:00 ILT (Israel Local Time)
4. **Max Trades Per Day**: 2 (default)
5. **A+ Confidence Required**: Score ≥ 8.0 for entry execution
6. **HTF Alignment**: Signal direction must match HTF bias
7. **Structure-Based SL**: Never inside liquidity (FVG, sweep, VWAP wick)
8. **R-Multiple TP**: 2R (fade), 3R (continuation), seasonality adjustments
9. **Timeout Limits**: 20 bars (continuation), 10 bars (fade)
10. **+1R Time Limit**: Must reach +1R within timeout limits
11. **Exit Priority**: SL → TP → Invalidations → Timeout
12. **Seasonality**: September defensive (2R max), Nov-Dec trend (3R allowed)

---

**End of Documentation**







