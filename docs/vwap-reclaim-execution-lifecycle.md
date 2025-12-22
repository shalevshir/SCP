# VWAP_RECLAIM Execution Lifecycle Analysis

This document provides comprehensive answers to questions about the VWAP_RECLAIM setup detection, execution, and state management lifecycle.

---

## Table of Contents

1. [Setup Persistence: Is VWAP_RECLAIM Persisted or Stateless?](#1-setup-persistence)
2. [Conditions for `executed=True` and Hidden Early Returns](#2-execution-conditions)
3. [Stop-Loss Logic for VWAP_RECLAIM](#3-stop-loss-logic)
4. [Post-Stop-Out: Is Reclaim Context Invalidated?](#4-post-stop-out-behavior)
5. [Decoupling of Confirmation, Scoring, and Execution](#5-decoupling)
6. [Summary Table](#summary-table)

---

## 1. Setup Persistence

**Question**: When a VWAP_RECLAIM setup is detected, is it persisted as a pending state across bars, or is it re-evaluated statelessly each bar (i.e., can it survive failing conditions temporarily)?

### Answer

**The VWAP reclaim state IS persisted across bars in the `StructureContextTracker`.**

The key state variables are maintained in `feature_engine/structure.py`:

```python
# VWAP reclaim tracking for second confirmation
self.vwap_reclaim_bar_idx: int | None = None
self.vwap_reclaim_direction: str | None = None  # "above" or "below"
self.vwap_buffer: deque[float] = deque(maxlen=20)  # Track recent VWAP values
self.close_buffer_vwap: deque[float] = deque(maxlen=20)  # Track recent closes
self.volume_buffer: deque[float] = deque(maxlen=20)  # Track recent volume
```

When price crosses VWAP (`update_vwap_state()`), the reclaim bar index and direction are recorded. This persists until:

- A new cross in the opposite direction resets it
- The reclaim expires (>10 bars old per `MAX_RECLAIM_AGE = 10`)

### Key Insight

The setup **can survive failing conditions temporarily** because the reclaim state persists. However, second confirmation must still be re-evaluated each bar. A setup detected on bar N can wait until bar N+5 for confirmation, as long as the reclaim hasn't expired or been invalidated by an opposite cross.

---

## 2. Execution Conditions

**Question**: What exact conditions must be true simultaneously for `executed=True` to occur, and is there any hidden early return (session guard, tier guard, active trade guard, score gate) that can silently block execution even when confirmation and score are valid?

### Answer

There are **3 gates in `execute_entry_at_next_open()`** that can block execution, plus **multiple upstream guards**.

### Execution Gates in `entry_model.py`

| Gate | Lines | Condition | Result |
|------|-------|-----------|--------|
| **Confidence gate** | 97-110 | `signal.confidence != "A+"` | Rejected |
| **Second confirmation gate** | 115-134 | VWAP_RECLAIM without `second_confirmation_satisfied` | Rejected |
| **Next candle availability** | 141-154 | `next_candle is None` | Rejected |

### Upstream Guards (Before `execute_entry_at_next_open` is called)

These guards in `replay_loop.py:_process_candle()` can silently block execution:

| Guard | Location | Effect |
|-------|----------|--------|
| **Active trade limit** | Line 464-470 | Returns `None` if `len(_active_trades) >= max_concurrent` |
| **PDLL hit** | Line 736 | Blocks all new entries after daily loss limit |
| **Loss streak** | Line 744 | 2 consecutive losses block further entries |
| **Max trades/day** | Line 757 | Configurable daily trade limit |
| **Session time** | Line 766 | Outside 10:00-13:00 ILT blocks entries |
| **DXY unavailable** | Line 786 | For DXY-requiring setups |

### Critical Hidden Gate: Second Confirmation

The second confirmation check in `entry_model.py` (lines 116-134) is the most commonly missed gate:

```python
if signal.setup_type == "VWAP_RECLAIM":
    second_confirmation = signal.diagnostics.get("second_confirmation_satisfied", False)
    if not second_confirmation:
        return EntryExecution(
            ...
            executed=False,
            rejection_reason="VWAP_RECLAIM entry not ready: no second confirmation detected",
        )
```

This requires `second_confirmation_satisfied = True`, which is computed in `StructureContextTracker.compute_second_confirmation()` and requires at least ONE of:

1. **VWAP hold**: Price holding above VWAP for 2+ consecutive bars (for long)
2. **Volume expansion**: Current volume > 1.5x average of pre-reclaim bars
3. **Micro HL above VWAP**: Higher low formed above VWAP (for long)

### Complete Execution Checklist

For `executed=True` to occur, ALL of the following must be true:

```
□ No active trade exists (or below max_concurrent limit)
□ PDLL not hit
□ Loss streak < 2
□ Trades today < max_trades_per_day
□ Within valid session (10:00-13:00 ILT)
□ DXY data available (if required)
□ Signal confidence == "A+" (score >= 8.0)
□ Second confirmation satisfied (VWAP hold, volume expansion, or micro HL)
□ Next candle exists
```

---

## 3. Stop-Loss Logic

**Question**: Does the stop-loss logic for VWAP_RECLAIM use micro candle lows/highs, or does it reference a reclaim zone / VWAP acceptance range, and is SL evaluated before or after invalidation checks each bar?

### Answer

**SL uses micro candle lows/highs (confirmation/BOS candle extremes), NOT VWAP acceptance range.**

### SL Calculation (from `backtester/trade.py`)

```python
# Continuation setups (VWAP_RECLAIM, DXY_CONTINUATION)
if direction == "long":
    # Long: SL below lower of confirmation/BOS
    if bos_candle is not None:
        sl = min(confirmation_candle.low, bos_candle.low)
    else:
        sl = confirmation_candle.low
```

### VWAP_RECLAIM-Specific Protections

1. **20-tick minimum buffer** (lines 381-408):
   - If SL distance < 20 ticks from entry, SL is expanded outward
   - For GC: `MIN_SL_TICKS_VWAP_RECLAIM = 20` (= $2.00)

2. **First retest bar protection** (lines 410-412):
   - `ignore_first_retest_bar = True` for all VWAP_RECLAIM trades
   - Prevents stop-out on immediate retest wick

### SL Evaluation Order (per bar)

From `simulator.py`, the check order is:

```
1. Grace period check (2 bars for RECLAIM)
   ├── If bars_elapsed <= 2: SKIP SL/TP AND invalidations
   └── If bars_elapsed > 2: Continue to checks below

2. Stop Loss check (PRIORITY 1)
   └── candle.low <= trade.stop_loss (for long)

3. Take Profit check (PRIORITY 2)
   └── candle.high >= trade.take_profit (for long)

4. Invalidation checks (PRIORITY 3-7)
   ├── VWAP invalidation (close < VWAP for long)
   ├── HTF structure break (LL for long)
   ├── DXY flip
   ├── Session end (disabled per FIX #6)
   └── Setup window expiration

5. Timeout (PRIORITY 8)
   └── bars_elapsed >= 20
```

### Key Points

- **SL is checked BEFORE invalidations** per-bar
- **During 2-bar grace period**: Neither SL nor invalidations are checked
- **Grace period logic** (from `simulator.py` lines 255-263):

```python
elif is_reclaim(trade):
    # RECLAIM: Skip SL/TP for first 2 bars, skip invalidations for 2 bars
    skip_sl_tp = bars_elapsed <= 2
    skip_invalidations = bars_elapsed <= 2
```

---

## 4. Post-Stop-Out Behavior

**Question**: After a VWAP_RECLAIM trade is stopped out, is the reclaim context invalidated, or can the system immediately re-enter on the same reclaim without a new sweep/BOS?

### Answer

**NO, the reclaim context is NOT invalidated. The system CAN immediately re-enter on the same reclaim.**

### Code Flow Analysis

1. Trade stop-out calls `close_trade()` in `trade.py`
2. Trade status is updated and removed from active trades
3. **The `StructureContextTracker` in the streaming processor is NOT reset**
4. `vwap_reclaim_bar_idx` persists until a new opposite cross occurs

### Implications

| Scenario | Result |
|----------|--------|
| Stop-out with `bars_since_reclaim < 10` | Setup still "active" |
| Second confirmation still satisfied | **Immediate re-entry is possible** |
| Same sweep/BOS context | **Remains valid** |

### What Invalidates Reclaim Context

The reclaim context is only invalidated when:

1. **Opposite VWAP cross**: Price crosses VWAP in the opposite direction (resets `vwap_reclaim_bar_idx`)
2. **Expiration**: 10+ bars elapse (`expired` confirmation type returned)
3. **Session reset**: If session reset is enabled, new session clears state

### Example Scenario

```
Bar 1: VWAP reclaim detected (long), setup formed
Bar 3: Entry executed, trade opened
Bar 5: Stop-loss hit, trade closed
Bar 6: If price still above VWAP and bars_since_reclaim < 10:
       → Second confirmation re-evaluated
       → If VWAP hold (2 bars) or volume expansion
       → NEW ENTRY POSSIBLE on same reclaim!
```

### Risk Consideration

This design allows "double-dipping" on the same reclaim, which could lead to:
- Multiple losses on the same failed setup
- Potentially unlimited re-entries until reclaim expires or opposite cross

---

## 5. Decoupling

**Question**: Can you confirm whether confirmation, scoring, and execution are decoupled (i.e., score can improve over time while pending), or whether a setup is permanently rejected the first time it fails the execution threshold?

### Answer

**They ARE decoupled. A setup is NOT permanently rejected if it fails once. Score can improve over time.**

### Per-Bar Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│ Each Bar                                                         │
├─────────────────────────────────────────────────────────────────┤
│ 1. Feature Computation (StreamingFeatureProcessor.update)       │
│    └── Updates: VWAP reclaim state, second confirmation, etc.   │
│                                                                  │
│ 2. HTF Bias Computation (htf_bias_func)                         │
│    └── Determines: direction, sweep, BOS, chop, etc.            │
│                                                                  │
│ 3. Guardrail Check (replay_loop._check_guardrails)              │
│    └── Blocks: PDLL, loss streak, session, max trades           │
│                                                                  │
│ 4. Signal Scoring (score_signal)                                │
│    └── Returns: Signal with score, confidence                   │
│    └── Score CAN improve over time (penalties may reduce)       │
│                                                                  │
│ 5. Entry Execution (execute_entry_at_next_open)                 │
│    └── Gates: confidence A+, second confirmation, next candle   │
└─────────────────────────────────────────────────────────────────┘
```

### Evidence of Decoupling

| Component | Behavior |
|-----------|----------|
| `compute_second_confirmation()` | Called fresh on every bar |
| `score_signal()` | Score recalculated from scratch each bar |
| Penalties (chop, noise, late reclaim) | Recomputed per-bar |
| Setup state | Persists, but validation is stateless |

### Example Flow

```
Bar 1: Reclaim detected
       Score = 6.5 (chop penalty -1.5)
       Confidence = "B" (below 8.0)
       → NOT EXECUTED

Bar 2: Chop clears, score improves
       Score = 7.8 (reduced penalties)
       Confidence = "B" (still below 8.0)
       → NOT EXECUTED

Bar 3: Sweep detected, HTF bonus applied
       Score = 8.5
       Confidence = "A+"
       Second confirmation = False (only 1 bar above VWAP)
       → NOT EXECUTED (confirmation gate)

Bar 4: VWAP hold satisfied (2 bars)
       Score = 8.3
       Confidence = "A+"
       Second confirmation = True
       → EXECUTED ✓
```

### Key Design Principles

1. **Stateless scoring**: Each bar is scored independently
2. **Stateful setup context**: Reclaim bar index persists
3. **Fresh confirmation check**: Second confirmation re-evaluated each bar
4. **No permanent rejection**: Failed bar N doesn't block bar N+1

---

## Summary Table

| Question | Answer |
|----------|--------|
| **Is setup persisted?** | **Yes** - `vwap_reclaim_bar_idx` persists across bars (max 10 bars) |
| **Hidden execution guards?** | **Yes** - Second confirmation gate in `entry_model.py` + upstream guardrails (PDLL, loss streak, session, active trade limit) |
| **SL logic** | **Micro candle lows/highs** (confirmation/BOS candle extremes), 20-tick minimum, 2-bar grace period |
| **SL vs invalidation order** | **SL checked first** (after grace period), then invalidations |
| **Post-stop-out re-entry** | **Allowed** - reclaim context NOT invalidated, can re-enter immediately on same reclaim |
| **Confirmation/scoring decoupled?** | **Yes** - fully stateless per-bar, score can improve over time, no permanent rejection |

---

## Architecture Diagram

```
                    ┌─────────────────────────────────────┐
                    │     StreamingFeatureProcessor       │
                    │  (Persists VWAP reclaim state)      │
                    └─────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
            ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
            │  HTF Bias     │ │   Scoring     │ │   Execution   │
            │  Computation  │ │  (Stateless)  │ │    Gates      │
            └───────────────┘ └───────────────┘ └───────────────┘
                    │                │                │
                    └────────────────┼────────────────┘
                                     ▼
                    ┌─────────────────────────────────────┐
                    │         Trade Created               │
                    │   (SL/TP from confirmation candle)  │
                    └─────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
            ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
            │  Grace Period │ │  SL/TP Check  │ │ Invalidations │
            │   (2 bars)    │ │  (Priority 1) │ │ (Priority 3+) │
            └───────────────┘ └───────────────┘ └───────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────┐
                    │         Trade Closed                │
                    │  (Reclaim context NOT invalidated)  │
                    └─────────────────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────┐
                    │   Re-entry possible on same reclaim │
                    │   if bars_since_reclaim < 10        │
                    └─────────────────────────────────────┘
```

---

## Related Files

- `feature_engine/structure.py` - StructureContextTracker with VWAP reclaim state
- `feature_engine/streaming.py` - StreamingFeatureProcessor calling second confirmation
- `backtester/entry_model.py` - Execution gates including second confirmation
- `backtester/trade.py` - SL calculation with 20-tick minimum
- `backtester/simulator.py` - SL/TP/invalidation check order and grace periods
- `backtester/invalidations.py` - VWAP invalidation logic for open trades
- `backtester/replay_loop.py` - Upstream guardrails (PDLL, loss streak, etc.)
- `rule_engine/scoring.py` - Signal scoring with penalty calculations



