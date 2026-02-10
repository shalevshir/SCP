# DXY_CONTINUATION — TP/SL & Management Spec (SOP-Aligned)

## Purpose
Define **exact, bot-implementable TP/SL rules** for `DXY_CONTINUATION` that:
- stop getting wicked out in normal volatility,
- prevent “hit +1R then full -1R,”
- keep risk bounded and SOP-consistent.

> Continuation trades must **breathe**. Stops must be **structural** and management must be **automatic**.

---

## Inputs (required)
At entry time you must have:
- `entry_price`
- `atr_ref` (choose **one**: 1m smoothed ATR or 5m ATR; standardize)
- Micro swing points:
  - **Long:** last confirmed micro **HL** (from 1m or 5m)
  - **Short:** last confirmed micro **LH**
- (Optional but recommended) HTF swing target levels for TP (e.g., last 15m/1h swing high/low)

If micro swing point is unavailable → treat as **degraded mode** (see fallback).

---

## Stop-loss model (MANDATORY)
### Principle
**SL = structural invalidation, but never tighter than a volatility floor.**

### Parameters (defaults)
- `k_atr = 1.7` (range 1.5–2.0)
- `sl_buffer_points = 0.3` (range 0.2–0.5) — avoids exact level tagging
- `min_sl_points = 2.5` (optional floor; only if your broker/contract requires it)

### Compute components
#### Long
1) `sl_struct = last_micro_HL - sl_buffer_points`
2) `sl_atr = entry_price - (k_atr * atr_ref)`
3) `sl_raw = min(sl_struct, sl_atr)`  
   (choose the **farther** stop; more room)
4) If using `min_sl_points`: `sl = min(sl_raw, entry_price - min_sl_points)`

#### Short
1) `sl_struct = last_micro_LH + sl_buffer_points`
2) `sl_atr = entry_price + (k_atr * atr_ref)`
3) `sl_raw = max(sl_struct, sl_atr)`
4) If using `min_sl_points`: `sl = max(sl_raw, entry_price + min_sl_points)`

### Fallback (degraded mode)
If micro swing point missing:
- `sl = sl_atr` (ATR-only)
- AND enforce stricter quality:
  - `min_score_degraded = 9.0`
  - OR block trade entirely (preferred for SOP purity)

### Risk sanity checks (reject if any)
- `risk_points = abs(entry - sl)`
- Reject if `risk_points <= 0`
- Reject if `risk_points > risk_points_cap` (define cap per account phase)

---

## TP model (choose ONE approach; do not mix)
You should pick a TP model that matches your system’s ability to manage.

### TP Option A (recommended): **Two-stage TP with runner**
Designed for continuation where big moves happen but reversals are common.

**Define:**
- `R = abs(entry - sl)`
- `TP1 = entry + 1.0R` (long) / `entry - 1.0R` (short)
- `TP2 = min(HTF_target, entry + 4.0R)` (long) / `max(HTF_target, entry - 4.0R)` (short)
  - If no HTF target available, use `TP2 = entry ± 3.0R` as default.

**Execution:**
- Take `partial_pct = 0.40` at TP1 (30–50% allowed)
- Leave remainder for TP2 (runner)

Why: your diagnostics show many trades reach +1R then reverse. This converts those into winners.

### TP Option B: **Single TP at realistic R**
If you cannot do partials:
- Set `TP = entry ± 2.5R` (default 2.0–3.0R)
- Avoid extreme RR (6R–10R) unless you have BE + partial logic.

### TP Option C: **HTF target only**
If you have reliable HTF liquidity levels:
- `TP = nearest 15m/1h swing target in direction`
- Enforce that `TP` is at least `2.0R` away; otherwise reject (not worth it).

---

## Trade management (MANDATORY)
### M1 — Break-even protection at +1R (non-negotiable)
When price reaches **+1.0R** (intrabar ok):
- Move SL to `BE` **or** `BE + 0.1R` (safer against spread/whipsaw)

This rule alone prevents the most common failure you observed.

### M2 — Trail for runner (only after BE)
After BE is set:
- Trail behind **new micro HL/LH** (structure trail), **not** by fixed ticks.
- Update no more than once per bar to avoid noise.

### M3 — Time stop (optional, but effective)
If trade has not reached **+0.5R** within `T = 30–45 minutes` (or X bars):
- Exit at market (continuation that doesn’t go is likely rotation).

---

## Anti-wick filters (optional, but recommended)
Use as additional rejection filters if you still see frequent wick-outs:
- Reject if `risk_points < 1.2 * atr_ref` (too tight for current regime)
- Reject if `k_atr * atr_ref` is below a floor (e.g., <2.0 pts) but volatility is expanding (use your volatility regime flag if available)

---

## Logging (must record)
Per trade:
- `sl_struct`, `sl_atr`, final `sl`, and which selected
- `risk_points` and `R`
- `tp_model` used (A/B/C)
- `TP1`, `TP2` (if applicable)
- `reached_1r`, `moved_to_BE`, `partial_taken`
- exit reason and final `R_multiple`

---

## Acceptance criteria (quick validation)
After implementing this TP/SL spec, in the same test window you should see:
- materially fewer -1R losses that previously hit +1R
- average R increases even if win rate stays similar
- fewer “tight stop noise” exits

> If you keep fixed 2.5-point stops on continuation, expectancy will remain broken.

