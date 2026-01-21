# Config Migration: Unified setups.yaml

## Summary

Successfully migrated from dual-config system (`scoring_config.yaml` + `setups.yaml`) to a **unified `setups.yaml`** configuration. The scoring engine now loads weights, constraints, and thresholds from a single source.

---

## What Changed

### 1. Config Loader Migration

**File:** `services/shared/src/scp_shared/rule_engine/config_loader.py`

**Before:**
- Loaded from `config/scoring_config.yaml`
- Required `setup_types`, `confidence`, `validation`, `factors` keys

**After:**
- Loads from `config/setups.yaml` (unified config)
- Maps `setups` → `setup_types` for backward compatibility
- `validation` and `factors` are now optional (not in setups.yaml)
- Fully compatible with existing scoring code

### 2. Enhanced VWAP_RECLAIM Constraints

Added three institutional-grade safety gates to `config/setups.yaml`:

#### a) ATR-Normalized Deviation (Volatility-Aware)

```yaml
min_vwap_deviation:
  expression: "vwap_deviation_normalized is None or abs(vwap_deviation_normalized) >= 0.5"
  reject_reason: "VWAP deviation insufficient for reclaim (must be >= 0.5 ATR)"
```

**Benefits:**
- ✅ Uses existing `vwap_deviation_normalized` field: `(Price - VWAP) / ATR`
- ✅ 0.5 ATR threshold is institutional minimum (5M timeframe standard)
- ✅ Filters micro-fakeouts and single-bar spikes
- ✅ Prevents chop-zone magnet behavior
- ✅ Meaningful across all volatility regimes

**Replaced:**
- Old: `vwap == 0 or abs((close - vwap) / vwap * 100) >= 0.15` (percentage-based, volatility-blind)

#### b) HTF Structure Integrity

```yaml
htf_structure_integrity:
  expression: "(direction != 'long' or structure_1h in ('HH', 'HL')) and (direction != 'short' or structure_1h in ('LL', 'LH'))"
  reject_reason: "HTF structure no longer intact for reclaim"
```

**Benefits:**
- ✅ Enforces SOP invalidation rule: "Loss of HH/HL (longs) or LL/LH (shorts)"
- ✅ Prevents trading against broken HTF trend
- ✅ Closes gap where structure *existence* was checked but not *validity*

#### c) Updated VWAP_FADE Constraint

```yaml
vwap_deviation:
  expression: "vwap_deviation is None or vwap_deviation > 0.25"
  reject_reason: "VWAP deviation too small for fade"
```

**Rationale:**
- Left as percentage-based per guidance (fade already has strong filters: wick ratios, RSI extremes)
- Uses existing `vwap_deviation` field instead of recalculating

### 3. Test Updates

**File:** `services/shared/tests/unit/rule_engine/test_config_loader.py`

- Updated to accept `setups` key (new format)
- Made `validation` and `factors` tests optional
- All existing tests pass with new config structure

---

## Verification

### Config Loading
```bash
$ poetry run python -c "from scp_shared.rule_engine.config_loader import load_scoring_config; config = load_scoring_config(); print(f'Loaded config with {len(config.setup_types)} setup types')"
Loaded config with 3 setup types
```

### Constraints Loaded
```bash
$ poetry run python -c "from scp_shared.rule_engine.setup_validator import load_setups_config; config = load_setups_config(); print(config['setups']['VWAP_RECLAIM']['constraints']['min_vwap_deviation'])"
{'expression': 'vwap_deviation_normalized is None or abs(vwap_deviation_normalized) >= 0.5', 'reject_reason': 'VWAP deviation insufficient for reclaim (must be >= 0.5 ATR)'}
```

---

## Impact

### Before Migration
- **Problem:** Weights defined in `setups.yaml` were **not being used** by scoring engine
- `scoring.py` loaded from old `scoring_config.yaml`
- Constraint updates in `setups.yaml` had no effect on scoring weights

### After Migration
- **Solution:** Single source of truth for all setup configuration
- Weights, constraints, thresholds all come from `setups.yaml`
- Changes to `setups.yaml` immediately affect both:
  - Setup detection (constraints)
  - Signal scoring (weights)

---

## Backward Compatibility

✅ **Fully backward compatible** with existing code:
- `config.setup_types` still works (mapped from `setups`)
- `config.confidence` still works (present in both configs)
- `config.validation` and `config.factors` are optional (gracefully handled)

---

## Next Steps

### 1. Deprecate scoring_config.yaml (Optional)
- Can now remove `config/scoring_config.yaml` if desired
- All functionality moved to `setups.yaml`

### 2. Future Enhancement: Bars Away Counter
For "best-in-class" institutional filtering, consider adding:

```yaml
min_vwap_separation:
  expression: "abs(vwap_deviation_normalized) >= 0.5 and bars_away_from_vwap >= 5"
  reject_reason: "Insufficient VWAP separation (need 0.5 ATR AND 5 bars)"
```

Requires adding `bars_away_from_vwap` counter to feature engine (similar to existing `bars_since_vwap_reclaim`).

---

## Files Modified

1. `services/shared/src/scp_shared/rule_engine/config_loader.py` - Load from setups.yaml
2. `config/setups.yaml` - Enhanced constraints (ATR-normalized, HTF integrity)
3. `services/shared/tests/unit/rule_engine/test_config_loader.py` - Updated tests
4. `CONFIG_MIGRATION_SUMMARY.md` - This document

---

## Key Takeaway

**The scoring engine now uses the unified `setups.yaml` for all configuration.** Updates to constraints, weights, and thresholds in `setups.yaml` are immediately reflected in both setup detection and signal scoring.
