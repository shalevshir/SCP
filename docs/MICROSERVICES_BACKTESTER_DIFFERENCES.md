# Microservices vs Backtester: Logic Differences Analysis

**Date:** 2025-12-28  
**Author:** Engineering Team  
**Status:** Action Required  

---

## Executive Summary

This document catalogs all logic differences between the microservices architecture (`services/`) and the backtester (`backtester/replay_loop.py`). These differences can cause discrepancies in trade execution, invalidation, and performance metrics between the two systems.

**Critical Finding:** The services have a **simplified invalidation checker** that misses several SOP-mandated exit conditions, which will cause trades to be held longer than the backtester would allow.

---

## Table of Contents

1. [Invalidation Checker Differences](#1-invalidation-checker-differences)
2. [VWAP Invalidation Logic](#2-vwap-invalidation-logic)
3. [Time-Stop Protection](#3-time-stop-protection)
4. [SL/TP Grace Periods](#4-sltp-grace-periods)
5. [Trade Creation & SL/TP Calculation](#5-trade-creation--sltp-calculation)
6. [Features Message Limitations](#6-features-message-limitations)
7. [HTF Bias Timing](#7-htf-bias-timing)
8. [Guardrails Integration](#8-guardrails-integration)
9. [State Machine Differences](#9-state-machine-differences)
10. [Scoring Logic Parity](#10-scoring-logic-parity)
11. [Action Items](#11-action-items)

---

## 1. Invalidation Checker Differences

### 🔴 CRITICAL

The backtester's `InvalidationChecker` (`backtester/invalidations.py`) has **7 exit condition checks** while the services version (`scp_shared/execution/invalidation.py`) only has **3**.

### Backtester Checks (Complete)

```python
# backtester/invalidations.py - check_all()
1. check_no_1r_reached()        # +1R time limit with September protection
2. check_vwap_invalidation()    # VWAP structure loss (with slope confirmation)
3. check_micro_structure_invalidation()  # 1m HH/LL detection
4. check_dxy_flip()             # DXY correlation flip (3-bar for VWAP_RECLAIM)
5. check_session_end()          # Session boundary (disabled per FIX #6)
6. check_setup_window_expired() # Setup-specific window expiration
7. check_daily_risk_breach()    # PDLL and loss streak enforcement
```

### Services Checks (Incomplete)

```python
# scp_shared/execution/invalidation.py - check_all()
1. check_sl_tp()                # SL/TP hit detection
2. check_no_1r_reached()        # Basic +1R time limit (no September protection)
3. check_vwap_invalidation()    # VWAP structure loss (NO slope confirmation)
```

### Missing Checks

| Check | Impact | Priority |
|-------|--------|----------|
| `check_micro_structure_invalidation()` | Trades won't exit on 1m HH/LL breaks | 🔴 Critical |
| `check_dxy_flip()` | DXY correlation flip won't trigger exit | 🔴 Critical |
| `check_setup_window_expired()` | VWAP_FADE won't exit when VWAP reclaimed | 🟡 Medium |
| `check_daily_risk_breach()` | Loss streak won't force exit mid-trade | 🟡 Medium |

### Action Required

```python
# Add to scp_shared/execution/invalidation.py

def check_all(self, trade, candle, bars_elapsed, features=None):
    # ... existing checks ...
    
    # ADD: Micro structure invalidation (Priority 3)
    is_invalid, reason = self.check_micro_structure_invalidation(trade, candle, features)
    if is_invalid:
        return is_invalid, reason
    
    # ADD: DXY flip detection (Priority 4)
    is_invalid, reason = self.check_dxy_flip(trade, candle, features)
    if is_invalid:
        return is_invalid, reason
    
    # ADD: Setup window expiration (Priority 5)
    is_invalid, reason = self.check_setup_window_expired(trade, candle, features)
    if is_invalid:
        return is_invalid, reason
    
    return False, None
```

---

## 2. VWAP Invalidation Logic

### 🟡 MEDIUM

The backtester requires **VWAP slope confirmation** for FADE invalidation to prevent premature exits on noise.

### Backtester (With Slope Filter)

```python
# backtester/invalidations.py:267-281
if trade.direction == "long":
    # Requires BOTH close > VWAP AND positive slope
    if candle.close > vwap and (vwap_slope is not None and vwap_slope > 0):
        condition_met = True
else:  # short
    if candle.close < vwap and (vwap_slope is not None and vwap_slope < 0):
        condition_met = True
```

### Services (No Slope Filter)

```python
# scp_shared/execution/invalidation.py:256-265
if trade.direction == "long":
    # Only checks close > VWAP (no slope confirmation)
    if candle.close > vwap:
        condition_met = True
else:
    if candle.close < vwap:
        condition_met = True
```

### Impact

Services will trigger FADE invalidations more aggressively, potentially exiting trades on micro-noise that the backtester would filter out.

### Action Required

1. Add `vwap_slope` to `FeaturesMessage` schema
2. Update `check_vwap_invalidation()` to require slope confirmation for FADE setups

---

## 3. Time-Stop Protection

### 🟡 MEDIUM

The backtester has **September defensive mode** that exits VWAP_RECLAIM trades early if they're deep red.

### Backtester Logic

```python
# backtester/invalidations.py:177-195
if (
    trade.setup_type == "VWAP_RECLAIM"
    and candle is not None
    and month == 9  # September only
    and bars_elapsed >= time_limit // 2  # Half of 60 bars = 30 bars
):
    current_r = current_pnl / trade.risk_amount
    if current_r < -0.2:  # Deep red threshold
        reason = f"time_stop_protection: {current_r:.2f}R at bar {bars_elapsed}"
        return True, reason
```

### Services Logic

```python
# scp_shared/execution/invalidation.py:170-203
def check_no_1r_reached(self, trade: TradeRecord, bars_elapsed: int):
    # No candle parameter - cannot calculate current R
    # No month parameter - cannot apply September logic
    # Simple time limit check only
```

### Impact

September VWAP_RECLAIM trades may stay in losing positions longer in services than in backtester.

### Action Required

1. Add `candle` and `month` parameters to services `check_no_1r_reached()`
2. Implement September time-stop protection logic

---

## 4. SL/TP Grace Periods

### 🟡 MEDIUM

The backtester has **setup-specific grace periods** before SL/TP checks to allow trades breathing room.

### Backtester Grace Periods

```python
# backtester/simulator.py - check_trade_exit_single_bar()
GRACE_PERIODS = {
    "VWAP_RECLAIM": {
        "sl_tp_grace": 2,       # 2 bars before SL/TP active
        "acceptance_grace": 8,  # Extended grace for retest
    },
    "DXY_CONTINUATION": {
        "sl_tp_grace": 6,
        "invalidation_grace": 6,
    },
    "VWAP_FADE": {
        "sl_tp_grace": 0,       # Immediate SL/TP
        "invalidation_grace": 3,
    },
}
```

### Services Implementation

```python
# scp_shared/execution/invalidation.py - check_sl_tp()
# No grace period logic - SL/TP checks active from bar 1
```

### Impact

Services will stop out trades on bars 1-2 that the backtester would protect.

### Action Required

Add grace period logic to `InvalidationChecker.check_sl_tp()`:

```python
def check_sl_tp(self, trade, candle, bars_elapsed=0):
    # Get grace period for setup type
    grace_periods = {
        "VWAP_RECLAIM": 2,
        "DXY_CONTINUATION": 6,
        "VWAP_FADE": 0,
    }
    grace = grace_periods.get(trade.setup_type, 2)
    
    # Skip SL/TP check during grace period
    if bars_elapsed < grace:
        return False, None
    
    # ... existing SL/TP check logic ...
```

---

## 5. Trade Creation & SL/TP Calculation

### 🟢 LOW

The backtester uses structure-based SL placement from `bos_candle` and `confirmation_candle`, while services use simpler VWAP-based calculation.

### Backtester (Structure-Based)

```python
# backtester/trade.py - create_trade_from_entry()
trade = create_trade_from_entry(
    entry_execution=execution,
    confirmation_candle=confirmation_candle,  # Used for structure-based SL
    bos_candle=bos_candle,                    # Used for swing-level SL
    risk_config=risk_config,
    market_context=market_context,
    vwap_value=vwap_value,
)
```

### Services (Simplified)

```python
# bot_core_svc/signal_engine.py - signal_to_message()
if setup_type == "VWAP_RECLAIM" and features.vwap is not None:
    # Simple VWAP ± buffer calculation
    buffer_amount = VWAP_SL_BUFFER_TICKS * TICK_SIZE_GC  # 30 ticks
    sl_price = features.vwap - buffer_amount  # Long
```

### Impact

SL placement may differ slightly between systems. Services uses consistent VWAP-zone SL which is actually the Phase 2 standard.

### Action Required

**None** - This is an acceptable simplification. Document that services use VWAP-zone SL exclusively.

---

## 6. Features Message Limitations

### 🔴 CRITICAL

The `FeaturesMessage` schema in services has fewer fields than the feature series in the backtester.

### Backtester Features (Complete)

```python
# Features available in backtester
features = pd.Series({
    "timestamp", "symbol", "timeframe",
    "open", "high", "low", "close", "volume",
    "vwap", "vwap_deviation", "vwap_slope",       # VWAP fields
    "rsi",                                          # Momentum
    "ema_9", "ema_20", "ema_50",                   # Trend
    "dxy_corr", "dxy_5m_corr",                     # DXY correlation (two windows)
    "structure_label", "micro_bos", "bos_direction", "bos_age",  # Structure
    "expansion_detected", "expansion_reasons",     # VWAP_RECLAIM entry quality
    "second_confirmation_long", "second_confirmation_short",  # Confirmation
    "volume_sma_20",                               # Volume analysis
    # ... and more
})
```

### Services FeaturesMessage (Limited)

```python
# scp_shared/messaging/schemas.py - FeaturesMessage
class FeaturesMessage:
    timestamp: datetime
    symbol: str
    timeframe: str
    close: float
    vwap: float | None
    rsi: float | None
    ema_9: float | None
    ema_20: float | None
    ema_50: float | None
    dxy_correlation: float | None  # Only one window
    structure_label: str | None
    vwap_deviation: float | None
    # Missing: vwap_slope, dxy_5m_corr, expansion_*, second_confirmation_*, etc.
```

### Impact

- Scoring may differ due to missing factors
- Invalidation checks that need these fields will fail silently
- VWAP_RECLAIM expansion gate cannot be applied

### Action Required

Expand `FeaturesMessage` to include critical fields:

```python
class FeaturesMessage(BaseModel):
    # ... existing fields ...
    
    # ADD: Required for VWAP invalidation
    vwap_slope: float | None = None
    
    # ADD: Required for DXY_CONTINUATION scoring
    dxy_5m_corr: float | None = None
    
    # ADD: Required for expansion gate
    expansion_detected: bool = False
    expansion_reasons: list[str] = []
    
    # ADD: Required for confirmation tracking
    second_confirmation_long: bool = False
    second_confirmation_short: bool = False
```

---

## 7. HTF Bias Timing

### 🟡 MEDIUM

The backtester computes HTF bias on **every 1m bar**, while services only compute at **HTF boundaries** (15m/1h).

### Backtester Logic

```python
# backtester/replay_loop.py:446-457
# Step 3: Compute HTF bias FIRST (must happen every bar to accumulate HTF data)
try:
    htf_bias = self._htf_bias_func(features, validation_context)
```

### Services Logic

```python
# htf_bias_svc/processor.py
def process(self, gc_message, dxy_message):
    htf_bias = self.calculator.update(gc_candle, dxy_candle)
    
    # Return None if no bias computed yet (not at boundary)
    if htf_bias is None:
        return None  # No update between HTF boundaries
```

### Impact

- Bot Core caches the last HTF bias and uses it for all 1m bars
- This is actually the correct behavior for a streaming system
- The backtester's per-bar computation is for structure warmup (handled by Feature Engine in services)

### Action Required

**None** - This is expected behavior. The HTF Bias Service correctly updates at 15m/1h boundaries, and Bot Core uses `HTFBiasCache` to provide the most recent bias for each 1m bar.

---

## 8. Guardrails Integration

### 🟡 MEDIUM

The backtester has more guardrail checks at signal generation time.

### Backtester Guardrails

```python
# backtester/replay_loop.py:775-898
def _check_guardrails(self, validation_context, current_timestamp, features):
    # 1. PDLL enforcement
    # 2. Daily trade limit
    # 3. Session time check
    # 4. Behavior guardrails (loss streak, fatigue)
    # 5. DXY availability check  ← Missing in services
    # 6. Risk ladder constraint
```

### Services Guardrails

```python
# bot_core_svc/main.py:161-183
# 1. Session validation
# 2. Behavior guardrails
# 3. Max concurrent trades (in Execution Service)
# Missing: DXY availability check before scoring
```

### Impact

Services may generate signals when DXY data is unavailable, which could lead to incorrect scoring.

### Action Required

Add DXY availability check to Bot Core:

```python
# In process_feature_message()
if features.dxy_correlation is None:
    logger.debug(f"DXY data unavailable at {features.timestamp}")
    return  # Skip signal generation
```

---

## 9. State Machine Differences

### 🟢 LOW

Both systems use the `VWAPReclaimStateMachine` for re-entry protection. The integration is slightly different but functionally equivalent.

### Backtester

```python
# backtester/replay_loop.py:541-565
if signal.setup_type == "VWAP_RECLAIM":
    state_machine = self._processor._streaming.structure_tracker.vwap_reclaim_sm
    if not state_machine.can_execute():
        # Block execution
```

### Services

```python
# execution_svc/trade_manager.py:268-279
confirmation_result = self._sm_manager.check_confirmation(signal.id)
if not confirmation_result:
    # Block execution
```

### Action Required

**None** - Functionally equivalent. Services use a dedicated `StateMachineManager` which is the correct pattern for a distributed system.

---

## 10. Scoring Logic Parity

### 🟢 OK

The scoring logic in `scp_shared/rule_engine/scoring.py` appears to be identical to `rule_engine/scoring.py` in the monolith. Both use:

- Same `score_signal()` function
- Same factor weights from `scoring_config.yaml`
- Same HTF bias integration
- Same chop handling

### Validation

The services use `scp_shared.rule_engine.scoring.score_signal()` which is a direct port of the monolith's scoring logic.

### Action Required

**None** - Scoring parity confirmed.

---

## 11. Action Items

### Priority Matrix

| # | Item | Priority | Effort | Owner |
|---|------|----------|--------|-------|
| 1 | Add missing invalidation checks to services | 🔴 Critical | High | - |
| 2 | Expand FeaturesMessage schema | 🔴 Critical | Medium | - |
| 3 | Add VWAP slope to invalidation | 🟡 Medium | Low | - |
| 4 | Add September time-stop protection | 🟡 Medium | Medium | - |
| 5 | Add SL/TP grace periods | 🟡 Medium | Medium | - |
| 6 | Add DXY availability check | 🟡 Medium | Low | - |
| 7 | Document SL/TP differences | 🟢 Low | Low | - |

### Implementation Order

1. **Phase 1 (Critical):**
   - Implement missing invalidation checks
   - Expand FeaturesMessage schema
   - Deploy and test

2. **Phase 2 (Medium):**
   - Add VWAP slope confirmation
   - Add September time-stop protection
   - Add grace periods
   - Add DXY availability check

3. **Phase 3 (Documentation):**
   - Document all intentional differences
   - Create integration test suite comparing backtester vs services output

---

## Appendix: Files Reviewed

### Backtester
- `backtester/replay_loop.py` - Main backtest loop
- `backtester/invalidations.py` - Trade invalidation checker
- `backtester/trade.py` - Trade creation and SL/TP
- `backtester/simulator.py` - Trade simulation with grace periods
- `feature_engine/streaming.py` - Feature computation
- `feature_engine/integration.py` - Feature integration layer
- `rule_engine/scoring.py` - Signal scoring
- `rule_engine/validation.py` - Signal validation

### Services
- `services/bot-core/src/bot_core_svc/main.py` - Bot Core main loop
- `services/bot-core/src/bot_core_svc/signal_engine.py` - Signal generation
- `services/bot-core/src/bot_core_svc/guardrails.py` - Guardrails integration
- `services/execution/src/execution_svc/main.py` - Execution Service
- `services/execution/src/execution_svc/trade_manager.py` - Trade lifecycle
- `services/execution/src/execution_svc/daily_state.py` - PDLL tracking
- `services/feature-engine/src/feature_engine_svc/main.py` - Feature Engine
- `services/htf-bias/src/htf_bias_svc/main.py` - HTF Bias Service
- `services/shared/src/scp_shared/execution/invalidation.py` - Services invalidation
- `services/shared/src/scp_shared/rule_engine/scoring.py` - Shared scoring
- `services/shared/src/scp_shared/indicators/streaming.py` - Shared streaming indicators

