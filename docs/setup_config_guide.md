# Setup Configuration Guide

This guide explains how to use the config-driven setup system to enable/disable trading setups and modify their parameters without changing Python code.

## Overview

The config-driven setup system allows you to:
- **Enable/disable setups** via boolean flags
- **Define constraints** using expressions (e.g., `"rsi < 40 or rsi > 60"`)
- **Configure parameters** like thresholds and weights
- **Modify scoring logic** by adjusting factor weights

Configuration file: `config/setups.yaml`

## Configuration Structure

```yaml
setups:
  SETUP_NAME:
    enabled: true|false           # Toggle setup on/off
    min_score: 8.0                # Minimum score for A+ confidence
    
    constraints:                  # ALL must pass for setup detection
      constraint_name:
        expression: "..."          # Boolean expression
        reject_reason: "..."       # Reason shown when constraint fails
    
    weights:                      # Factor weights for scoring (sum to ~10)
      factor_name: 2.5
    
    params:                       # Parameters used by factor calculators
      param_name: value
```

## Enabling/Disabling Setups

To disable a setup, set `enabled: false`:

```yaml
setups:
  VWAP_FADE:
    enabled: false  # VWAP_FADE will not be detected
    # ... rest of config
```

To re-enable:

```yaml
setups:
  VWAP_FADE:
    enabled: true  # VWAP_FADE detection is active
    # ... rest of config
```

## Expression Syntax

Constraints use Python-like expressions with access to feature values and HTF bias data.

### Supported Operators

- **Comparisons**: `<`, `>`, `<=`, `>=`, `==`, `!=`
- **Boolean**: `and`, `or`, `not`
- **Arithmetic**: `+`, `-`, `*`, `/`
- **Functions**: `abs()`
- **Membership**: `in`, `not in`
- **None checks**: `is None`, `is not None`

### Available Variables

**From Features:**
- Price data: `close`, `open`, `high`, `low`, `vwap`
- Indicators: `rsi`, `ema_9`, `ema_20`, `ema_50`
- DXY: `dxy_corr`, `dxy_corr_1m`, `dxy_corr_5m`
- Structure: `structure_clarity`, `structure_label`, `last_structure_label`, `trend_confidence`
- BOS/CHoCH: `bos_direction`, `bos_age`, `choch_detected`, `choch_direction`
- Other: `liquidity_sweep`, `is_chop`, `direction`
- Calculated: `body`, `lower_wick`, `upper_wick`

**From HTF Bias:**
- Structure: `structure_1h`, `structure_15m`
- Flags: `htf_liquidity_sweep_detected`, `conflict_detected`, `htf_bos_detected`
- Counts: `bars_since_bos`
- DXY: `dxy_structure`

### Expression Examples

**Simple comparisons:**
```yaml
expression: "rsi < 30"                    # RSI below 30
expression: "structure_clarity >= 0.5"    # Clarity at least 0.5
```

**Boolean logic:**
```yaml
expression: "rsi < 40 or rsi > 60"        # RSI extreme
expression: "clarity >= 0.5 and not is_chop"  # Good clarity, no chop
```

**Arithmetic:**
```yaml
expression: "abs((close - vwap) / vwap * 100) >= 0.15"  # VWAP deviation
expression: "lower_wick > body * 1.3"                   # Wick > 1.3x body
```

**None handling:**
```yaml
expression: "structure_1h is not None and structure_1h != ''"  # Has 1H structure
expression: "bos_direction is None or bos_direction == direction"  # No conflict
```

**Membership:**
```yaml
expression: "direction in ('long', 'short')"                   # Valid direction
expression: "dxy_structure not in ('LL', 'LH')"               # DXY not bearish
```

**Complex conditions:**
```yaml
expression: "(direction == 'long' and last_structure_label == 'LH') or (direction == 'short' and last_structure_label == 'HL')"
```

## Modifying Constraints

### Example: Relax RSI Threshold for VWAP_FADE

Current (strict):
```yaml
VWAP_FADE:
  constraints:
    rsi_extreme:
      expression: "rsi < 40 or rsi > 60"
      reject_reason: "RSI not at extreme"
```

Relaxed:
```yaml
VWAP_FADE:
  constraints:
    rsi_extreme:
      expression: "rsi < 45 or rsi > 55"  # Wider range
      reject_reason: "RSI not at extreme"
```

### Example: Add New Constraint

```yaml
VWAP_RECLAIM:
  constraints:
    # ... existing constraints ...
    
    min_volume:
      expression: "volume > 1000"
      reject_reason: "Volume too low for reliable signal"
```

### Example: Make Constraint Optional

To make a constraint pass when data is missing:

Before (strict):
```yaml
strong_correlation:
  expression: "dxy_corr < -0.6"
  reject_reason: "DXY correlation too weak"
```

After (optional):
```yaml
strong_correlation:
  expression: "dxy_corr is None or dxy_corr < -0.6"
  reject_reason: "DXY correlation too weak"
```

## Modifying Scoring Weights

Adjust factor importance by changing weights:

```yaml
VWAP_RECLAIM:
  weights:
    structure_alignment: 3.0  # Increased from 2.5
    vwap_relation: 1.5        # Decreased from 2.0
    rsi_state: 1.5
    # ... others unchanged
```

**Note**: Weights should sum to approximately 10 for proper A+ threshold (8.0).

## Modifying Parameters

Parameters control thresholds used in factor calculation and penalty logic:

```yaml
VWAP_RECLAIM:
  params:
    bos_recency_threshold: 20  # Increased from 15 (allow older BOS)
    clarity_high: 0.8          # Increased from 0.7 (stricter)
    expansion_gate:
      bos_recency_threshold: 15    # Increased from 10
      range_expansion_ratio: 1.3   # Decreased from 1.5 (easier to trigger)
```

## Common Adjustments

### Make Setup More Aggressive

1. Lower `min_score` threshold
2. Relax constraint thresholds  
3. Reduce factor weights for less important factors

```yaml
VWAP_FADE:
  min_score: 7.0  # Down from 8.0
  constraints:
    rsi_extreme:
      expression: "rsi < 45 or rsi > 55"  # Wider range
  weights:
    vwap_deviation: 3.0
    rsi_extreme: 2.0      # Reduced from 3.0
```

### Make Setup More Conservative

1. Raise `min_score` threshold
2. Tighten constraint thresholds
3. Add new constraints
4. Increase factor weights for critical factors

```yaml
VWAP_RECLAIM:
  min_score: 9.0  # Up from 8.0
  constraints:
    # ... existing ...
    high_clarity_required:
      expression: "structure_clarity >= 0.7"  # Stricter than 0.4
      reject_reason: "Clarity too low"
  weights:
    structure_alignment: 3.0  # Increased from 2.5
```

## Testing Configuration Changes

After modifying `config/setups.yaml`:

1. **Validate syntax:**
   ```bash
   poetry run python -c "
   from scp_shared.rule_engine.setup_validator import load_setups_config
   config = load_setups_config()
   print('Config valid!')
   "
   ```

2. **Run unit tests:**
   ```bash
   cd services/shared
   poetry run pytest tests/unit/rule_engine/test_setup_validator.py -v
   ```

3. **Run integration tests:**
   ```bash
   poetry run pytest tests/integration/test_setup_detection_parity.py -v
   ```

4. **Full test suite:**
   ```bash
   poetry run pytest tests/unit/rule_engine/ -v
   ```

## Priority Order

When multiple setups could match, they are checked in this priority order:

1. **VWAP_FADE** (most specific - counter-trend at extremes)
2. **VWAP_RECLAIM** (specific structural sequence)
3. **DXY_CONTINUATION** (broader correlation-based)

The first setup that passes all constraints is selected.

## Backward Compatibility

The config-driven system maintains full backward compatibility:
- All existing tests pass (713 tests)
- Setup detection behavior matches hardcoded detectors
- Field mappings handle both `"bullish"/"bearish"` and `"long"/"short"` formats
- Missing optional fields handled gracefully with defaults

## Expression Safety

The expression evaluator is designed for safety:
- ✅ Allowed: comparisons, boolean logic, arithmetic, `abs()`
- ❌ Blocked: imports, exec, eval, attribute access, function calls (except `abs`), comprehensions

Invalid expressions are caught at config load time with clear error messages.

## Examples

### Example 1: Disable VWAP_FADE During Low Volatility

```yaml
VWAP_FADE:
  enabled: false  # Temporarily disable during low vol environment
```

### Example 2: Require Stronger DXY Correlation

```yaml
DXY_CONTINUATION:
  constraints:
    strong_correlation:
      expression: "dxy_corr < -0.7"  # Stricter than -0.6
      reject_reason: "DXY correlation too weak"
```

### Example 3: Allow VWAP_RECLAIM with Lower Clarity

```yaml
# Note: clarity constraint was removed from VWAP_RECLAIM to match old behavior
# Low clarity results in score penalties, not hard rejection
# No change needed - already handles this correctly
```

### Example 4: Add Expansion Requirement to DXY_CONTINUATION

```yaml
DXY_CONTINUATION:
  constraints:
    # ... existing constraints ...
    has_expansion:
      expression: "expansion_detected"
      reject_reason: "No expansion signal detected"
```

## Troubleshooting

### Setup Always Rejected

1. Check `enabled: true` in config
2. Run with debug logging: `--log-cli-level=DEBUG`
3. Look for "Setup SETUP_NAME failed constraint" messages
4. Verify the failing constraint expression is correct
5. Check that all variables in expression are provided in context

### Expression Evaluation Error

```
ExpressionEvalError: Unknown variable: some_var
```

Solution: Ensure all variables used in expression are present in context (even if None).

### Setup Detected as Wrong Type

Check priority order - a higher-priority setup might be matching first.
Solution: Make the unwanted setup fail by adjusting its constraints.

## Migration from Hardcoded Detectors

The new config-driven system is now active by default. The old hardcoded detectors in `setup_detectors/` are no longer used by `scoring.py`.

If you need to reference the old behavior, check:
- `services/shared/src/scp_shared/rule_engine/setup_detectors/vwap_fade.py`
- `services/shared/src/scp_shared/rule_engine/setup_detectors/dxy_continuation.py`
- `services/shared/src/scp_shared/rule_engine/htf/vwap/reclaim.py`

These files are preserved for reference but not called by the scoring engine.
