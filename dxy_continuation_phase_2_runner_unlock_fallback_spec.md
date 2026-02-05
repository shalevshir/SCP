# DXY_CONTINUATION — Phase-2 Runner Unlock Fallback Spec

This document defines **exact fallback unlock rules** for Phase-2 runner management in the
`DXY_CONTINUATION` setup. It is written as a **downloadable, implementation-ready spec**.

The purpose is to **unlock a right-tail of outcomes (2–4R trades)** without reintroducing
Phase-0 problems (hope runners, widened risk, or execution bleed).

---

## 1. Scope & Preconditions

Applies **only after Phase-1 conditions are met**:

- TP1 hit at **+1R**
- **40% partial** taken at TP1
- SL moved to **BE + buffer (0.1R)**
- Remaining **60%** becomes `RUNNER_CANDIDATE`

This logic **never affects entry, SL placement, or TP1 logic**.

---

## 2. State Machine

```
ENTRY
  ↓
TP1_HIT (partial + BE)
  ↓
RUNNER_CANDIDATE
  ↓
 ┌───────────────┬──────────────────┐
 │               │                  │
UNLOCKED     INVALIDATED       WINDOW_EXPIRED
 │               │                  │
RUNNER → TP2   EXIT @ BE        EXIT REMAINDER
```

---

## 3. Required Inputs (per bar after TP1)

### Prices
- `open`, `high`, `low`, `close`
- `vwap`, `vwap_slope`

### Trade State
- `direction` (`long` / `short`)
- `entry_price`
- `sl_initial`
- `R_points = abs(entry_price - sl_initial)`
- `tp1_price = entry ± 1R`
- `tp1_hit_bar_idx`
- `bars_since_tp1`

### Regime / Invalidation Flags (hard)
- `dxy_aligned`
- `chop_detected`
- `htf_conflict_detected`

### BOS Events (primary unlock)
- `bos_detected`
- `bos_direction`
- `bos_bar_idx`

Optional:
- `htf_target_price`

---

## 4. Hard Invalidation (checked first)

At **any time after TP1**, immediately exit remainder if:

- `dxy_aligned == False` for ≥ 5 bars  
- OR `chop_detected == True`  
- OR `htf_conflict_detected == True`

Reason: continuation thesis invalidated.

---

## 5. Primary Unlock (Mode A — Post-TP1 Micro-BOS)

Unlock runner if **all** are true:

- `bars_since_tp1 <= unlock_window_bars` (default: 15)
- `bos_detected == True`
- `bos_direction` matches trade direction
- `bos_bar_idx > tp1_hit_bar_idx` (strictly post-TP1)

Result:
- `runner_unlocked = True`
- `runner_unlock_reason = "micro_bos"`

---

## 6. Fallback Unlock Rules (choose ONE)

Only evaluate fallback rules **if primary BOS unlock has not triggered**.

### Fallback A (RECOMMENDED): Hold + Impulse Continuation

Designed to capture strong continuation when BOS confirmation lags.

#### Parameters
- `hold_buffer_R = 0.25`
- `unlock_window_bars = 15`

#### Hold Condition

**Long**
```
hold_floor = tp1_price - 0.25R
min(low since TP1) >= hold_floor
```

**Short**
```
hold_ceiling = tp1_price + 0.25R
max(high since TP1) <= hold_ceiling
```

#### Impulse Condition (at least once in window)

**Long**
- `close > prior_high`
  OR
- `body_ratio >= 0.6`

**Short**
- `close < prior_low`
  OR
- `body_ratio >= 0.6`

Where:
```
body_ratio = abs(close - open) / max(high - low, ε)
```

#### Unlock Condition

Unlock if:
- `hold_condition == True`
- AND `impulse_condition == True`
- AND no hard invalidators

Result:
- `runner_unlocked = True`
- `runner_unlock_reason = "hold_impulse"`

---

### Fallback B: HTF Room Gate (Very Safe)

Unlock if **room exists to HTF target**.

Parameters:
- `min_runner_room_R = 1.5`

Condition:
```
room_R = abs(htf_target_price - close) / R_points
room_R >= 1.5
```

Plus:
- no invalidators

Result:
- `runner_unlocked = True`
- `runner_unlock_reason = "htf_room"`

---

### Fallback C: VWAP Separation Hold

Trend-acceptance proxy.

Within unlock window:

**Long**
- `close > vwap` in **≥ 8 of last 10 bars**
- `vwap_slope > 0`

**Short**
- `close < vwap` in **≥ 8 of last 10 bars**
- `vwap_slope < 0`

Plus:
- no invalidators

Result:
- `runner_unlocked = True`
- `runner_unlock_reason = "vwap_hold"`

---

## 7. Unlock Failure Behavior

If `bars_since_tp1 > unlock_window_bars` and runner not unlocked:

### Policy UF1 (Recommended)
- Close remainder at market (next bar open or close)
- Reason: `RUNNER_UNLOCK_FAILED_WINDOW`

### Policy UF2
- Keep remainder open with SL at BE+buffer
- Do **not** force synthetic BE fills

Pick **one policy** and standardize.

---

## 8. Post-Unlock Runner Management

### TP2 Target
- Primary: `htf_target_price`
- Cap: `tp2_max_r * R` (default: 4R)
- Fallback: `entry ± tp2_default_r * R` (default: 3R)

### Stop Policy (Phase-2)
- Keep SL at **BE + 0.1R**
  OR
- Lock profit at **+0.5R** after unlock (optional)

No trailing yet (Phase-3).

---

## 9. Logging (Mandatory)

For every TP1 trade:
- `runner_unlocked`
- `runner_unlock_reason`
- `bars_to_unlock`
- `runner_exit_reason`
- `runner_R_contribution`
- invalidate reason (if applicable)

Target metrics:
- Unlock rate: **20–40% of TP1 hits**
- Positive average `runner_R_contribution`

---

## 10. Enforcer Rule

Fallback unlock rules:
- apply **only after TP1**
- affect **only remaining size**
- must **not** weaken entry or SL discipline

> Follow the SOP — nothing changed structurally.

---

## Implementation Status

### ✅ Completed
- Hard invalidation checks (chop, htf_conflict, dxy_aligned 5-bar)
- Fallback A: Hold + Impulse unlock
- State tracking in InvalidationChecker
- TradeRecord fields for logging
- Trade manager integration (with htf_bias=None placeholder)
- Unit tests for hard invalidation and fallback

### ❌ TODO - Remaining Work
1. **HTF Bias Integration** (`services/execution/src/execution_svc/main.py`)
   - Subscribe to `htf.bias` Redis stream
   - Pass to `check_runner_unlock()` instead of `None`

2. **Database Migration** (`infra/migrations/012_add_runner_fields.sql`)
   - Add runner fields to trades table schema

3. **Fallback B & C** (`invalidation.py`) - Optional
   - HTF Room Gate (min 1.5R room to target)
   - VWAP Separation Hold (8/10 bars above VWAP)

4. **TP2 Dynamic Calculation** (`trade_manager.py`)
   - Calculate from HTF targets: `min(htf_target, entry ± 4R)`

5. **Broker Execution** (Phase 8+)
   - Actually close 40% at TP1
   - Actually close remaining 60% on runner exit

