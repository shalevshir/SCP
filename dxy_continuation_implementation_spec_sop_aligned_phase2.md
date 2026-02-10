# DXY_CONTINUATION — Phase‑2 Spec (Conditional Runner Unlock)

## Goal
Transition from **Phase‑1 stabilization** (mostly TP at +1R) to **Phase‑2 exploitation** by allowing **some winners** to extend to **2.5R–4R** *without reintroducing bleed*.

Phase‑2 is **not** full trailing. It is **conditional runner permission** after confirmation.

**Primary objective:** flip expectancy positive by creating a right‑tail of outcomes.

---

## Scope
Applies only to:
- `setup_type == DXY_CONTINUATION`
- Trades that **reach +1R**.

Out of scope (defer):
- Full structure trailing (Phase‑3)
- Pyramiding/add-ons
- Dynamic scaling by volatility regimes

---

## Preconditions (hard requirements)
Phase‑2 runner logic is enabled only if all are true:
1. Phase‑1 TP/SL spec is implemented (hybrid SL + BE at +1R).
2. `min_score >= 8.5` hard gate remains.
3. `dxy_aligned == True`, `chop_detected == False` remain hard gates.
4. Backtest shows **stable left tail**:
   - Max losing streak ≤ 3
   - Max drawdown ≤ 6R over the validation window

If preconditions fail → Phase‑2 must stay OFF.

---

## Phase‑2 trade plan (TP/SL & management)

### Definitions
- `R = abs(entry_price - sl_initial)`
- `TP1 = entry_price ± 1.0R`
- `BE_buffer = 0.1R` (default)

### Base actions at +1R (MANDATORY)
When price reaches **+1.0R** (intrabar OK):
1. **Move SL → BE + buffer**
   - Long: `sl = entry_price + BE_buffer`
   - Short: `sl = entry_price - BE_buffer`
2. **Take partial at TP1**
   - `partial_pct = 0.40` (30–50 allowed)
3. Mark trade state:
   - `tp1_hit = True`
   - `be_set = True`

> This ensures: a trade that confirms cannot become a full −1R loss.

---

## Runner unlock (the core of Phase‑2)
After TP1 is hit and BE is set, the remaining position becomes a **candidate runner**.

### Runner permission must be binary
Runner is allowed only if the market shows **post‑TP1 continuation evidence**.

Phase‑2 uses **ONE** of the following unlock modes. Pick a mode and standardize.

---

## Unlock Mode A (recommended): Post‑TP1 Micro‑BOS

### Rationale
This is the cleanest, least overfit proof that momentum continued *after* confirmation.

### Requirements to unlock
Within `unlock_window_bars` after TP1 hit:
- `micro_bos_in_direction == True`
- BOS must occur **after** TP1 timestamp (not before)

Defaults:
- `unlock_window_bars = 15` (1m bars) OR `unlock_window_minutes = 20`

If BOS does not occur within window → runner is **not** unlocked; exit remainder at BE per rules.

### Implementation notes
- Define micro BOS using your existing structure engine:
  - Long: break above last micro LH formed after entry
  - Short: break below last micro HL formed after entry
- Ensure BOS detection uses confirmed swings to avoid repaint.

---

## Unlock Mode B: HTF Target Availability (distance gate)

### Rationale
Allow runner when there is enough room to the next HTF liquidity target.

### Requirements to unlock
At TP1 hit:
- `htf_target_price` exists
- `distance_to_target_R >= min_runner_room_R`

Defaults:
- `min_runner_room_R = 1.5` (meaning: from TP1 to target there is ≥ 1.5R)

If insufficient room → no runner; exit remainder at BE.

---

## Unlock Mode C: DXY Acceleration Confirmation

### Rationale
Use DXY momentum as a post‑confirmation filter.

### Requirements to unlock
Within `unlock_window_minutes` after TP1 hit:
- `dxy_alignment == True` remains
- AND `dxy_trend_strength` increases vs entry snapshot (or crosses a threshold)

Defaults:
- `unlock_window_minutes = 20`

---

## Runner exit policy (once unlocked)
Once runner is unlocked, the position remains open toward TP2.

### TP2 selection
Choose **one** policy:

**TP2 Policy 1 (recommended): HTF target capped by R**
- `TP2_raw = htf_target_price`
- `TP2_cap = entry_price ± tp2_max_r * R`
- `TP2 = min(TP2_raw, TP2_cap)` for longs; `max()` for shorts

Defaults:
- `tp2_default_r = 3.0`
- `tp2_max_r = 4.0`

If `htf_target_price` missing:
- `TP2 = entry_price ± tp2_default_r * R`

### Runner stop policy (Phase‑2)
Do **not** do full trailing yet.
Use one of these simple, safe options:

**Stop Policy S1 (recommended): BE+buffer holds until TP2 or invalidate**
- Keep SL at `BE + buffer` until TP2 hit.
- Exit runner if:
  - `htf_conflict_detected == True` OR
  - `dxy_alignment == False` OR
  - `chop_detected == True` (post‑TP1)

**Stop Policy S2: Lock profit at +0.5R after unlock**
- After runner unlock, set SL to:
  - Long: `entry + 0.5R`
  - Short: `entry - 0.5R`
This reduces BE scratches but may cut some runners.

---

## If runner NOT unlocked
If TP1 hit but unlock conditions fail within the window:
- Exit remainder at **BE + buffer** (or immediately close remainder once window expires).

This prevents “hope runners” and keeps Phase‑2 controlled.

---

## Risk & frequency controls (mandatory)

### Two-loss halt
- After 2 consecutive losses (full −1R losses) → halt DXY_CONTINUATION for the session/day.

### One-idea-one-attempt lock
- If a DXY_CONTINUATION trade hits full SL → cooldown `cooldown_minutes_after_sl`.

Defaults:
- `cooldown_minutes_after_sl = 45`
- `max_attempts_per_session = 2`

---

## Config structure (recommended)
Add under `DXY_CONTINUATION`:

```yaml
risk_management:
  dxy_continuation:
    phase: 2
    tp:
      model: two_stage_runner
      tp1_r: 1.0
      tp1_partial_pct: 0.40
      tp2_default_r: 3.0
      tp2_max_r: 4.0
    be:
      enable: true
      at_r: 1.0
      buffer_r: 0.10
    runner_unlock:
      mode: micro_bos  # micro_bos | htf_room | dxy_acceleration
      unlock_window_minutes: 20
      min_runner_room_r: 1.5  # used in htf_room
    runner_stop:
      policy: be_hold  # be_hold | lock_0_5r
      lock_profit_r: 0.5
    controls:
      cooldown_minutes_after_sl: 45
      max_attempts_per_session: 2
```

---

## Logging requirements
Per trade, log:
- `tp1_hit`, timestamp of TP1 hit
- `be_set`, `be_price`
- `partial_taken`, `partial_pct`
- `runner_unlocked`, unlock mode, unlock timestamp
- unlock evidence (e.g., BOS level/time, HTF room in R, DXY strength delta)
- runner exit reason (TP2, BE, invalidate)
- final `R_multiple_total` including partials

---

## Acceptance tests

### Unit tests
1. TP1 hit triggers BE move and partial close.
2. Runner unlock only if unlock condition occurs **after TP1**.
3. Runner not unlocked → remainder exits at BE after window expires.
4. TP2 computed correctly (HTF target with cap; fallback to R-based).
5. Post‑TP1 invalidate flags (DXY alignment false / chop true / HTF conflict) force runner exit.

### Behavioral expectations (backtest)
Across the Phase‑2 window:
- Win rate may stay similar (45–55%).
- Expectancy should improve via right tail:
  - Some trades > +2R total outcome.
  - Average win should rise above 1.0R.
- Max drawdown should not materially worsen.

---

## Enforcer note
Phase‑2 is allowed only when it **increases expectancy without increasing trade frequency**.
If runner unlock creates overtrading or worsens DD → revert to Phase‑1.

> “This is not A+” if runners are enabled without post‑TP1 evidence.

