# VWAP_RECLAIM SOP Alignment – Required Changes & New Features

## Purpose

This document defines **all required changes** to the `VWAP_RECLAIM` setup configuration so it is **fully aligned with the Shir Capital Trading Playbook SOP**.

It is written for **developers and system architects**. The goal is to:
- Eliminate misclassified VWAP reclaims
- Prevent late / chase continuation trades
- Improve A+ quality consistency
- Reduce avoidable losses without reducing opportunity

This document is **prescriptive**, not advisory.

---

## Executive Summary (TL;DR)

The current `VWAP_RECLAIM` configuration is **structurally sound but too permissive**.

Main issues:
1. VWAP distance logic allows *chase reclaims*
2. Late reclaims are penalized instead of blocked
3. BOS recency logic is too lenient for reclaim logic
4. No explicit requirement for VWAP interaction / acceptance

Result:
- Some invalid trades are classified as A+
- TP logic is forced to compensate for entry-side errors

**Fixing reclaim eligibility resolves both losing trades and false rejections.**

---

## SOP Ground Truth (Anchor)

From the Trading Playbook:

> "VWAP Test / Reclaim is a trend-continuation setup where price **pulls back to VWAP**, holds or reclaims it **quickly**, and resumes direction. The strongest trends do not give deep pullbacks."

Key implications:
- Reclaim ≠ momentum chase
- Reclaim ≠ post-expansion continuation
- Reclaim requires *location integrity*, not just trend strength

---

## REQUIRED CHANGES (MANDATORY)

### 1️⃣ Fix VWAP Distance Logic (Critical)

#### ❌ Current Logic
```yaml
min_vwap_deviation:
  expression: "abs(vwap_deviation_normalized) >= 0.5"
```

Problem:
- Allows extreme VWAP distances (e.g. ±8–10 ATR)
- Correct for VWAP_FADE
- **Incorrect for VWAP_RECLAIM**

#### ✅ Required Replacement
```yaml
vwap_reclaim_distance:
  expression: >
    vwap_deviation_normalized is not None and
    abs(vwap_deviation_normalized) >= 0.5 and
    abs(vwap_deviation_normalized) <= 3.0
  reject_reason: "VWAP reclaim invalid — price too far from VWAP (late/chase reclaim)"
```

Effect:
- Blocks chase entries
- Enforces reclaim proximity
- Would have rejected the losing trade example

---

### 2️⃣ Add Hard Late-Reclaim Kill Switch

#### ❌ Current State
```yaml
late_reclaim_penalty: -0.3
```

Problem:
- Late reclaim is a **classification failure**, not a scoring issue
- Penalties do not prevent invalid setups

#### ✅ Required Constraint
```yaml
no_late_reclaim:
  expression: "bos_recent is False or bos_age >= 20"
  reject_reason: "Late VWAP reclaim — structure still expanding"
```

Effect:
- Prevents reclaim entries immediately after BOS
- Aligns with SOP pullback → resume logic

---

### 3️⃣ Tighten BOS Logic for VWAP_RECLAIM

#### ❌ Current Behavior
```yaml
bos_direction == direction or bos_age > 15
```

Problem:
- Allows reclaim attempts **during active expansion**
- BOS logic is shared with continuation setups

#### ✅ Required VWAP_RECLAIM-Specific Gate
```yaml
bos_reclaim_gate:
  expression: "bos_recent is False or bos_age >= 20"
  reject_reason: "VWAP reclaim attempted during active expansion"
```

Note:
- BOS permissiveness may remain for other setup types
- VWAP_RECLAIM must be stricter by definition

---

## REQUIRED NEW FEATURES

### 4️⃣ VWAP Acceptance / Interaction Metric

#### Problem
The system does not verify that price actually **interacted with VWAP**.

This allows:
- Drive-by reclaims
- One-tick cross at speed

#### ✅ New Feature Required
```text
bars_near_vwap: int
```

Definition:
- Number of consecutive candles within a VWAP proximity band (e.g. ±0.2 ATR)

#### ✅ New Constraint
```yaml
min_vwap_acceptance:
  expression: "bars_near_vwap >= 3"
  reject_reason: "No acceptance near VWAP — drive-by reclaim"
```

---

### 5️⃣ Reclaim Timing Feature

#### New Feature
```text
bars_since_last_vwap_touch: int
```

Purpose:
- Ensure reclaim occurs *soon after pullback*

#### Optional Constraint (Recommended)
```yaml
reclaim_timing_gate:
  expression: "bars_since_last_vwap_touch <= 10"
  reject_reason: "VWAP reclaim too delayed — invalid continuation"
```

---

## SCORING ADJUSTMENT (SECONDARY)

### Location Integrity Multiplier

Problem:
- Strong trends inflate scores even with poor reclaim location

#### Recommended Enhancement

Introduce a **location multiplier**:
```python
location_score = f(vwap_distance, bos_age, reclaim_timing)
final_score = raw_score * location_score
```

Guidelines:
- Late reclaim → multiplier ≤ 0.7
- Clean reclaim → multiplier ≈ 1.0

This ensures:
- A+ score reflects *location quality*, not just momentum

---

## WHAT MUST NOT CHANGE

❌ Do NOT:
- Lower `min_score`
- Relax HTF structure rules
- Compensate with TP logic
- Convert reclaims into momentum buckets

This fix is about **classification purity**, not aggressiveness.

---

## Expected Outcomes After Changes

- Losing late-reclaim trades are blocked
- A+ VWAP_RECLAIM win rate improves
- TP logic becomes simpler and cleaner
- Continuation trades behave predictably

---

## Enforcer Statement (For Logs)

> "This is not a valid VWAP reclaim. Follow the SOP — nothing changed structurally."

---

## Final Verdict

The existing configuration is **close but incomplete**.

VWAP_RECLAIM must be treated as:
- A *location-sensitive* continuation setup
- Not a generic trend-following bucket

Implementing the changes above fully aligns the system with SOP intent and removes avoidable losses **without reducing edge**.

---

