# HTF Bias Engine

This module implements the complete Higher Timeframe (HTF) bias calculation system according to Shir Capital's SOP.

## Overview

The HTF Bias Engine provides comprehensive market context by analyzing:
- **Structure**: Swing points, BOS, CHoCH, liquidity sweeps
- **VWAP**: Trend validation and FVG interaction
- **DXY**: Correlation analysis and chop detection
- **Seasonality**: Month-based scoring adjustments

## Architecture

```
rule_engine/htf/
├── __init__.py           # Package exports
├── types.py              # HTFBias dataclass and types
├── calculator.py         # Main orchestrator
├── integration.py        # RuleEngine integration
├── structure/            # Structure analysis
│   ├── swings.py        # Swing high/low detection
│   ├── bos.py           # Break of Structure
│   ├── choch.py         # Change of Character
│   └── liquidity.py     # Liquidity sweeps
├── vwap/                 # VWAP analysis
│   ├── calculator.py    # HTF VWAP calculation
│   ├── trend.py         # Trend validation
│   └── fvg.py           # FVG interaction
├── dxy/                  # DXY analysis
│   └── chop.py          # Chop detection
└── seasonality/          # Seasonality adjustments
    ├── rules.py         # Period detection
    └── scoring.py       # Score adjustments
```

## Usage

### Basic Usage (Legacy)

```python
from rule_engine.htf.calculator import compute_htf_bias_multi_timeframe

# Get HTF bias from 1h and 15m features
bias, direction, score = compute_htf_bias_multi_timeframe(
    features_1h=features_1h,
    features_15m=features_15m
)

# bias: "bullish", "bearish", "neutral"
# direction: "long", "short", "neutral"
# score: 0-10
```

### Full HTFBias Object

```python
from rule_engine.htf.calculator import compute_htf_bias

# Get comprehensive HTF bias
htf_bias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
    dxy_1h=dxy_1h,
    timestamp=current_timestamp
)

# Access all components
print(f"Bias: {htf_bias.bias}")
print(f"Score: {htf_bias.score}")
print(f"Structure 1H: {htf_bias.structure_1h}")
print(f"VWAP confirmed: {htf_bias.vwap_trend_confirmed}")
print(f"DXY chop: {htf_bias.dxy_chop_detected}")
print(f"Seasonality: {htf_bias.seasonality_period}")
```

### RuleEngine Integration

```python
from rule_engine.htf.integration import validate_signal_with_htf, adjust_score_with_htf

# Validate signal against HTF
is_valid, reason = validate_signal_with_htf(
    signal_direction="long",
    htf_bias=htf_bias
)

if not is_valid:
    print(f"Signal rejected: {reason}")
    return

# Adjust score with HTF alignment
adjusted_score, details = adjust_score_with_htf(
    base_score=7.5,
    htf_bias=htf_bias,
    signal_direction="long"
)
```

## Components

### Seasonality Module ✅

**Status**: Complete  
**Documentation**: [HTF Seasonality Guide](../../docs/rule-engine/htf-seasonality.md)

The seasonality module implements month-based scoring adjustments per SOP:

#### Key Features

- **Period Detection**: Classifies timestamps into 4 seasonality periods
- **Dynamic Thresholds**: Period-specific min scores and DXY correlation requirements
- **Score Adjustment**: Automatic bonus/penalty application based on month
- **Full Integration**: Seamlessly integrated into HTF calculator

#### Seasonality Periods

| Period | Min Score | DXY Threshold | Behavior |
|--------|-----------|---------------|----------|
| **September** | 8.5 | -0.65 | Defensive mode (-0.5 penalty if < 8.5) |
| **October** | 8.0 | -0.6 | Neutral baseline |
| **November-December** | 8.0 | -0.55 | Trend season (+0.3 bonus) |
| **Other** | 8.0 | -0.6 | Standard |

#### Usage

```python
# Seasonality is automatically applied when timestamp provided
htf_bias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
    timestamp=current_timestamp  # Enables seasonality
)

# Access seasonality fields
print(htf_bias.seasonality_period)      # "november_december"
print(htf_bias.seasonality_adjustment)  # 0.8
```

#### Testing

- **80 tests** (38 scoring + 42 rules)
- **100% coverage** (48/48 statements)
- All edge cases and integration scenarios covered

See [seasonality/README.md](seasonality/README.md) for module details.

---

## Development Roadmap

Tasks are tracked in Notion under epic: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)

### Phase 1: Structure Components
- [x] Set up folder structure
- [ ] Implement swing identification
- [ ] Implement BOS detection
- [ ] Implement CHoCH detection
- [ ] Implement liquidity sweep detection

### Phase 2: VWAP Components
- [ ] Add HTF VWAP calculation
- [ ] Add VWAP trend validation
- [ ] Add FVG interaction scoring

### Phase 3: DXY & Seasonality
- [ ] Add DXY chop detection
- [x] Add seasonality module
- [x] Integrate seasonality into scoring

### Phase 4: Integration & Testing
- [ ] Create final HTFBias object
- [ ] Integrate into RuleEngine scoring
- [ ] Parity tests (vectorized vs incremental)

## Testing

Each component should have:
1. Unit tests for isolated functionality
2. Integration tests with sample HTF data
3. Parity tests (vectorized vs incremental)
4. Edge case tests

Example test structure:
```
tests/unit/rule_engine/htf/
├── structure/
│   ├── test_swings.py
│   ├── test_bos.py
│   ├── test_choch.py
│   └── test_liquidity.py
├── vwap/
│   ├── test_calculator.py
│   ├── test_trend.py
│   └── test_fvg.py
├── dxy/
│   └── test_chop.py
├── seasonality/
│   ├── test_rules.py
│   └── test_scoring.py
└── test_calculator.py
```

## Migration Notes

The legacy `rule_engine/htf_calculator.py` has been migrated to `rule_engine/htf/calculator.py` with the following changes:

1. **Backward Compatibility**: The `compute_htf_bias_multi_timeframe()` function is preserved as-is
2. **New Interface**: `compute_htf_bias()` returns a full `HTFBias` object
3. **Modular Components**: All new functionality is organized in submodules

To migrate existing code:
```python
# Old import
from rule_engine.htf_calculator import compute_htf_bias_multi_timeframe

# New import (same function)
from rule_engine.htf.calculator import compute_htf_bias_multi_timeframe
```

## Contributing

When implementing a task:
1. Read the Notion task description and DoD
2. Write failing tests first (TDD)
3. Implement the feature
4. Ensure all tests pass
5. Update this README if needed
6. Submit PR with reference to Notion task

## Documentation

### Component Documentation

- [HTF Seasonality Guide](../../docs/rule-engine/htf-seasonality.md) - Complete seasonality reference
- [Seasonality Module](seasonality/README.md) - Module quick start

### General Documentation

- [Project Overview](../../docs/01-project-overview.md)
- [Rule Engine Docs](../../docs/README.md)
- [Notion Epic](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)

