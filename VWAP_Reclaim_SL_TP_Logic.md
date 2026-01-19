
## 3) Stop Loss (SL) Logic — Invalidation-Based

### 3.1 Principle
**SL must be placed at the first location where the reclaim thesis is proven wrong.**  
SL is not based on comfort, dollar amount, or arbitrary tick counts.

### 3.2 Long SL Placement (Choose First Valid Level by Priority)

**Priority A — Structure-Based (Preferred):**
1. Identify the **Micro-Structure Anchor (HL)** after reclaim.
2. Set `SL = HL_low - slBuffer`.

**Priority B — Reclaim Candle-Based:**
If a clean HL is not available (e.g., immediate entry on reclaim):
- Set `SL = reclaimCandle_low - slBuffer`.

**Priority C — VWAP Failure-Based (Last Resort / Tight Conditions Only):**
If structure is extremely tight and the reclaim is clean:
- Set `SL = (VWAP_zone_bottom) - slBuffer`.

> If SL must be placed inside chop or inside the VWAP zone, the setup is not clean and should be rejected.

### 3.3 Short SL Placement (Mirror)

**Priority A — Structure-Based (Preferred):**
- Identify **Micro-Structure Anchor (LH)** after reclaim.
- Set `SL = LH_high + slBuffer`.

**Priority B — Reclaim Candle-Based:**
- Set `SL = reclaimCandle_high + slBuffer`.

**Priority C — VWAP Failure-Based (Last Resort):**
- Set `SL = (VWAP_zone_top) + slBuffer`.

### 3.4 SL Buffer (`slBuffer`)
A configurable safety margin to prevent micro-stop-outs.
Implementation-agnostic options:
- fixed ticks/points  
- fraction of ATR  
- fraction of VWAP zone width  

**Rule:** Buffer exists to avoid noise; it must not be used to hide poor structure.

### 3.5 Hard Invalidation (Immediate Exit)
Regardless of initial SL method, the trade is invalid if:
- **Long:** price breaks below VWAP and **holds** below (definition in 3.6), OR HH/HL sequence is broken. :contentReference[oaicite:3]{index=3}  
- **Short:** price breaks above VWAP and holds above, OR LL/LH sequence is broken. :contentReference[oaicite:4]{index=4}  

This can be implemented as an emergency exit condition independent of the bracket SL.

### 3.6 “Holds” Definition (Implementation-agnostic)
A “hold” is a configurable confirmation that a VWAP break is real, e.g.:
- N consecutive closes beyond VWAP zone, OR
- a close beyond + retest rejection, OR
- time spent beyond zone > T seconds/minutes

Parameter: `vwapHoldConfirm`.

---

## 4) Take Profit (TP) Logic — Structure + Minimum R:R

### 4.1 Principle
TP must be:
1) **At or beyond 3R**, and  
2) **Structurally justified** by a real target (liquidity / prior high-low / HTF zone).

If no structure target exists at ≥3R, **the trade is skipped**. :contentReference[oaicite:5]{index=5}

### 4.2 Risk Unit (R)
Let:
- `entry` = executed entry price  
- `sl` = chosen stop loss  
- `riskDistance = abs(entry - sl)`  
- `R1 = riskDistance`  
- `R3 = entry ± 3 * riskDistance` (plus for longs, minus for shorts)

### 4.3 Target Selection (Pick First Valid Structural Target ≥ 3R)

Define a ranked list of candidate targets. For each candidate, compute if its distance from entry is ≥ 3R.

**Common candidates (ranked):**
1. **Nearest external liquidity pool** in trade direction (equal highs/lows, obvious swing).  
2. **Prior session High/Low** in trade direction.  
3. **HTF structural level** (BOS retest completion target, HTF supply/demand boundary).  
4. **FVG objective** (midpoint/fill/edge in direction of trend).  
5. **Measured move** based on prior impulse leg length.

**TP1 (Primary TP):**
- Choose the first candidate target that is **≥ 3R** and not blocked by immediate opposing structure.

If the nearest structural target is <3R:
- either (a) reject trade, or (b) treat it as a scalp strategy (NOT VWAP reclaim SOP).  
For VWAP reclaim under this SOP: **reject**.

### 4.4 No-Target Condition (Hard Reject)
If:
- no candidate target meets ≥3R, OR
- target exists but sits inside heavy opposing liquidity/structure that invalidates clean path,
then: **do not open the trade**.

---

## 5) Optional Multi-Stage TP (If Your Bot Supports Partials)

> Only use this if it does not reduce discipline or violate minimum R:R on the remainder.

A common structure-preserving approach:
- `TP_partial = 2R` (optional)
- `TP_final = chosen structural target ≥ 3R`

Rules:
- Partial is optional; final target must remain ≥3R from entry. :contentReference[oaicite:6]{index=6}  
- If partial is used, stop management must not turn discretionary (see Section 6).

---

## 6) Post-Entry SL Management (Mechanical, Not Emotional)

### 6.1 Break-Even (BE) Rule (Optional but common)
Once price achieves `+1R` (or `+X` ticks), SL may be moved to:
- `entry + beOffset` for longs  
- `entry - beOffset` for shorts  

Parameter: `beTriggerR` and `beOffset`.

### 6.2 Trailing (Optional)
Trailing is allowed only if rules are deterministic:
- trail behind micro-structure (new HL/LH)
- or trail by fixed distance once above a threshold (e.g., after 2R)

Parameter: `trailMethod`, `trailTrigger`, `trailDistance`.

### 6.3 Never Widen SL
SL may move only to reduce risk (toward BE / profit).  
No averaging down, no “give it room.” :contentReference[oaicite:7]{index=7}

---

## 7) Edge-Case Handling (Bot Must Decide deterministically)

### 7.1 Chop Around VWAP
If price oscillates within VWAP zone for longer than `maxChopTime` without clean reclaim+hold:
- Reject setup or force no-trade mode.

### 7.2 Single Candle “Reclaim” Spike
If reclaim occurs via one large candle but immediately retraces and closes back into zone:
- treat as failed reclaim unless “hold confirmation” triggers true.

### 7.3 Spread/Slippage Safety
If slippage would reduce effective R:R below 3:1 at the chosen TP:
- Reject trade.

---

## 8) Parameters Summary (Names are placeholders)

- `vwapZoneWidth`
- `slBuffer`
- `vwapHoldConfirm` (N closes / time / pattern)
- `minBodyRatio`, `minRange` (optional intent logic)
- `beTriggerR`, `beOffset` (optional)
- `trailMethod`, `trailTrigger`, `trailDistance` (optional)
- `maxChopTime`

---

## 9) Compliance Summary (What Devs Must Guarantee)

A VWAP Reclaim trade is valid only if:
1. SL is placed at structural invalidation (HL/LH or reclaim candle extreme), plus buffer.  
2. TP is a *structural* target and yields **≥ 3R** net of costs/slippage. :contentReference[oaicite:8]{index=8}  
3. If VWAP breaks and **holds against bias**, exit or invalidate trade. :contentReference[oaicite:9]{index=9}  
4. SL is never widened post-entry. :contentReference[oaicite:10]{index=10}  

---

## 10) Quick “If-Then” Blueprint (Developer-Friendly)

### LONG
- IF reclaimCloseAboveVWAP == true AND holdConfirm == true:
  - Determine HL after reclaim (if exists)
  - SL = (HL_low OR reclaimCandle_low OR VWAP_zone_bottom) - slBuffer
  - Find structural TP candidate where distance ≥ 3 * (entry - SL)
  - IF none: reject trade
  - ELSE: place bracket with TP at chosen target

### SHORT
- IF reclaimCloseBelowVWAP == true AND holdConfirm == true:
  - Determine LH after reclaim (if exists)
  - SL = (LH_high OR reclaimCandle_high OR VWAP_zone_top) + slBuffer
  - Find structural TP candidate where distance ≥ 3 * (SL - entry)
  - IF none: reject trade
  - ELSE: place bracket with TP at chosen target

