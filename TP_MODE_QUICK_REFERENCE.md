# TP Mode Quick Reference

## TL;DR

VWAP_RECLAIM with A+ HTF now uses **continuation mode**: accepts TP1 at ≥1.5R (not 3R) if expansion path exists beyond TP1.

All other setups use **static mode**: requires TP at ≥3R upfront (unchanged).

---

## Quick Test

```bash
# Verify all tests pass
poetry run pytest services/bot-core/tests/unit/ -v

# Expected: 151 passed, 7 skipped, 0 failures
```

---

## When Does Continuation Mode Apply?

```python
setup_type == "VWAP_RECLAIM"
AND htf_confidence == "A+"
AND chop_detected == False
AND conflict_detected == False
```

If ANY condition fails → **static mode** (3R required)

---

## TP1 Requirements by Mode

| Mode | TP1 Minimum | Additional Requirement |
|------|-------------|------------------------|
| Static | 3R | Single target must satisfy full R:R |
| Continuation | 1.5R | Expansion path beyond TP1 must exist |

---

## Expansion Path Criteria

For continuation mode, AT LEAST ONE must be true:
- `htf_range_high > tp1` (longs) or `htf_range_low < tp1` (shorts)
- `untouched_liquidity_high > tp1` or `untouched_liquidity_low < tp1`
- `nearest_fvg_high > tp1` or `nearest_fvg_low < tp1`

---

## New SignalMessage Fields

```python
tp_mode: str                 # "static" or "continuation"
tp2_price: float | None      # Secondary TP (continuation only)
rr_tp1: float | None         # R:R at TP1
rr_potential: float | None   # Total R:R potential
be_after_tp1: bool           # Move SL to BE after TP1
tp_target_source: str | None # Source of TP1 target
```

---

## Diagnostic Data Location

TP plan data stored in `signal_history.diagnostics` JSONB field:

```sql
SELECT 
    timestamp, 
    direction, 
    setup_type,
    diagnostics->'tp_plan'->>'tp_mode' as tp_mode,
    diagnostics->'tp_plan'->>'tp1' as tp1,
    diagnostics->'tp_plan'->>'tp2' as tp2,
    diagnostics->'tp_plan'->>'rr_potential' as rr_potential
FROM signal_history
WHERE diagnostics->'tp_plan'->>'tp_mode' = 'continuation';
```

---

## Example Scenarios

### ✅ Continuation Mode (Accepted)
- Setup: VWAP_RECLAIM
- HTF: A+ bullish
- Entry: 2650.0, SL: 2640.0 (Risk: 10)
- nearest_liquidity_long: 2665.0 (1.5R)
- htf_range_high: 2700.0 (expansion path ✓)
- **Result**: TP1=2665.0, TP2=2700.0, approved

### ❌ Continuation Mode (Rejected - No Expansion)
- Setup: VWAP_RECLAIM
- HTF: A+ bullish
- Entry: 2650.0, SL: 2640.0
- nearest_liquidity_long: 2665.0 (1.5R)
- htf_range_high: 2660.0 (below TP1 - no expansion ✗)
- **Result**: Rejected "CONTINUATION_NO_EXPANSION_PATH"

### ✅ Static Mode (VWAP_FADE)
- Setup: VWAP_FADE
- HTF: A+ bullish
- Entry: 2650.0, SL: 2648.5 (Risk: 1.5)
- nearest_liquidity_long: 2655.0 (3.33R)
- **Result**: TP=2655.0, approved (static mode)

---

## Files Modified

1. `services/bot-core/src/bot_core_svc/signal_engine.py` (+180 lines)
2. `services/shared/src/scp_shared/messaging/schemas.py` (+6 fields)
3. `services/bot-core/tests/unit/test_tp_validation.py` (+16 tests)
4. `services/bot-core/tests/unit/test_signal_engine.py` (updates)
5. `services/bot-core/tests/unit/test_tp_mode_e2e.py` (new file, 7 tests)

---

## Test Summary

- **Total tests**: 151 passed
- **New tests added**: 23
- **Updated tests**: ~15
- **Test time**: ~4 seconds
- **Coverage**: Eligibility, TP1 validation, expansion path, routing, schema, diagnostics

---

## Key Functions

```python
# Check if trade qualifies for continuation mode
is_continuation_eligible(setup_type: str, htf_bias: HTFBiasMessage) -> bool

# Validate continuation TP (1.5R + expansion)
validate_continuation_tp(...) -> tuple[TPPlan | None, str | None]

# Validate static TP (3R upfront)
validate_static_tp(...) -> tuple[float | None, str | None]

# Route between modes
validate_tp_target(..., setup_type: str) -> tuple[TPPlan | None, str | None]
```

---

## Rejection Codes

| Code | Meaning | Mode |
|------|---------|------|
| `CONTINUATION_TP1_BELOW_MIN_RR` | No target at ≥1.5R | Continuation |
| `CONTINUATION_NO_EXPANSION_PATH` | TP1 found but no expansion | Continuation |
| `No structural target at ≥3.0R` | No target at ≥3R | Static |
| `Invalid SL: ... must be below entry` | SL validation failed | Both |

---

## SOP Compliance Checklist

- ✅ Separate TP modes by setup type
- ✅ Continuation allows sub-3R TP1
- ✅ Expansion path mandatory for continuation
- ✅ Static mode unchanged (FADE, countertrend)
- ✅ No risk threshold lowering
- ✅ Rejection states accurate
- ✅ Diagnostic transparency
- ✅ SOP-compliant logging

**Status: Fully SOP-compliant**
