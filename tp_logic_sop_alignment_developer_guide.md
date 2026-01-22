# TP Logic SOP Alignment – Required Improvements

## Purpose

This document defines **mandatory improvements** to the Take-Profit (TP) validation logic so it fully aligns with the **Shir Capital Trading Playbook SOP**.

The current TP logic is **technically correct** but **structurally incomplete**: it enforces a **single, static 3R target for all setups**, which is **not SOP-compliant for trend continuation (VWAP Reclaim) trades**.

This file is written for **developers**, not traders. Every change below maps directly to SOP intent and Enforcer rules.

---

## Current State (Summary)

The existing TP logic:
- Enforces **static ≥3R upfront**
- Requires **one structural level** to satisfy full R:R
- Rejects trades if no such level exists

This logic is correct for:
- VWAP Fade (mean reversion)
- Counter-trend trades
- Chop / fragile structure

It is **misaligned** for:
- VWAP Reclaim
- HTF continuation
- Seasonal expansion regimes (Nov–Dec)

---

## SOP Truth (Non-Negotiable)

The SOP defines **two distinct TP philosophies**:

| Setup Type | TP Philosophy |
|----------|---------------|
| VWAP Fade / Countertrend | Static, upfront R:R (≥3R) |
| VWAP Reclaim / Continuation | Dynamic, staged, expansion-based |

**Important:**
SOP does **NOT** require a single upfront 3R target for continuation trades.
It requires **risk control + expansion potential**.

---

## Core Problem in Current Logic

### ❌ Universal Static R:R Gate

The current implementation assumes **one TP must pay the entire trade**.

Consequences:
- Valid A+ VWAP Reclaims are rejected
- Structure quality is ignored at TP stage
- Rejection reason misrepresents SOP intent

---

## Required Design Change (High Level)

### Introduce TP Modes

TP validation **must branch by setup type**.

```
TP_MODE = STATIC | CONTINUATION
```

This is **mandatory**.

---

## TP Mode Definitions

### 1️⃣ STATIC MODE (No Change)

**Applies to:**
- VWAP_FADE
- Countertrend setups
- Chop / weak HTF conditions
- Conservative / Early Mild enforcement

**Rules:**
- Require ≥3R upfront
- Single TP
- Existing logic remains unchanged

✅ Current code is correct here.

---

### 2️⃣ CONTINUATION MODE (Required New Logic)

**Applies to:**
- VWAP_RECLAIM
- HTF Bias = A+
- Structure intact
- No immediate opposing HTF liquidity

This mode does **not** lower standards.
It changes **how targets are validated**.

---

## Continuation TP Validation Rules

### Step A — Initial Structural TP (TP1)

- TP1 may be **sub-3R**
- Minimum allowed: **≥1.5R**
- Must be a real structural level:
  - Nearest liquidity
  - Nearest swing
  - Micro range high/low

Purpose:
- Partial exit **or**
- Secure SL → Break Even

---

### Step B — Expansion Path Validation (Mandatory)

After TP1, verify that **expansion potential exists**.

At least **one** must be true:
- HTF range extends beyond TP1
- Untouched HTF liquidity exists beyond TP1
- HTF structure is not capped by opposing liquidity

If no expansion path exists → **reject trade**.

This replaces the old “single 3R target” rule.

---

### Step C — Return a TP Plan (Not Just a Price)

Continuation mode must return a **TP plan object**, not a single price.

Example:

```json
{
  "tp_mode": "continuation",
  "tp1": 4026.5,
  "tp2": 4038.7,
  "rr_tp1": 1.7,
  "rr_potential": 4.2,
  "be_after_tp1": true
}
```

Execution logic decides partials and scaling based on Enforcer tier.

---

## What Must NOT Change

❌ Do NOT:
- Lower risk thresholds
- Lower score thresholds
- Allow continuation without HTF A+
- Allow continuation in chop
- Assume future BOS without validation

This change is about **accuracy**, not looseness.

---

## Rejection Semantics (Mandatory Update)

The current rejection message:

```
No structural target at ≥3R
```

is **incorrect** for continuation setups.

### Required Rejection States

- `A+_NO_STATIC_TP_CONTINUATION_REQUIRED`
- `CONTINUATION_NO_EXPANSION_PATH`
- `A+_STRUCTURE_VALID_BUT_LOCATION_POOR`

This is required for:
- Journaling accuracy
- Review clarity
- Future analytics

---

## Minimal Code-Level Change (Conceptual)

### Updated Function Signature

```python
def validate_tp_target(
    direction: str,
    entry_price: float,
    sl_price: float,
    features: FeaturesMessage,
    htf_bias: HTFBiasMessage,
    setup_type: str,
    min_rr: float = 3.0,
) -> tuple[TPPlan | None, str | None]:
```

### Routing Logic

```python
if setup_type == "VWAP_RECLAIM" and htf_bias.confidence == "A+":
    return validate_continuation_tp(...)
else:
    return validate_static_tp(...)
```

---

## Enforcer Language (Logging Requirement)

When applicable, logs must include:
- “This is A+ — no static 3R target.”
- “Continuation TP logic applied.”
- “Follow the SOP — nothing changed structurally.”

---

## Final Enforcer Statement

The existing TP logic is **correct but incomplete**.
SOP compliance requires **TP mode separation**.

Static logic stays.
Continuation logic must be added.

**Capital protection remains absolute.
Execution geometry becomes SOP-accurate.**

