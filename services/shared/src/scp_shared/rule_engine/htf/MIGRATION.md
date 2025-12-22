# HTF Module Migration Guide

## Overview

The HTF (Higher Timeframe) bias calculation has been refactored from a single file (`rule_engine/htf_calculator.py`) into a modular package (`rule_engine/htf/`) to support the Full HTF Bias Engine Upgrade.

## What Changed

### Before (Single File)
```
rule_engine/
└── htf_calculator.py  (169 lines)
    - compute_htf_bias_multi_timeframe()
    - is_london_or_ny_session()
```

### After (Modular Package)
```
rule_engine/htf/
├── __init__.py
├── types.py              # HTFBias dataclass
├── calculator.py         # Main orchestrator
├── integration.py        # RuleEngine integration
├── structure/            # 4 modules
│   ├── swings.py
│   ├── bos.py
│   ├── choch.py
│   └── liquidity.py
├── vwap/                 # 3 modules
│   ├── calculator.py
│   ├── trend.py
│   └── fvg.py
├── dxy/                  # 1 module
│   └── chop.py
└── seasonality/          # 2 modules
    ├── rules.py
    └── scoring.py
```

## Migration Steps

### Step 1: Update Imports (Backward Compatible)

The old file still works but shows a deprecation warning:

```python
# Old way (still works, shows warning)
from rule_engine.htf_calculator import compute_htf_bias_multi_timeframe

# New way (recommended)
from rule_engine.htf.calculator import compute_htf_bias_multi_timeframe
```

### Step 2: Upgrade to New HTFBias Object (Recommended)

For new code, use the enhanced `HTFBias` object:

```python
from rule_engine.htf.calculator import compute_htf_bias
from rule_engine.htf.types import HTFBias

# Get comprehensive HTF bias
htf_bias: HTFBias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
    dxy_1h=dxy_1h,  # optional
    timestamp=current_timestamp  # optional
)

# Access all components
print(htf_bias.bias)  # "bullish", "bearish", "neutral"
print(htf_bias.score)  # 0-10
print(htf_bias.confidence)  # "high", "medium", "low"
print(htf_bias.structure_1h)  # "HH", "HL", etc.
print(htf_bias.vwap_trend_confirmed)  # bool
print(htf_bias.dxy_chop_detected)  # bool
```

### Step 3: Integration with RuleEngine

```python
from rule_engine.htf.integration import (
    validate_signal_with_htf,
    adjust_score_with_htf
)

# Validate signal
is_valid, reason = validate_signal_with_htf("long", htf_bias)
if not is_valid:
    logger.info(f"Signal rejected: {reason}")
    return

# Adjust score
adjusted_score, details = adjust_score_with_htf(
    base_score=7.5,
    htf_bias=htf_bias,
    signal_direction="long"
)
```

## Component Status

| Component | Status | Notion Task |
|-----------|--------|-------------|
| Folder structure | ✅ Complete | - |
| HTFBias dataclass | ✅ Complete | [Create final HTFBias object](https://www.notion.so/2b42bd6fbda680b9a91ffd8b27027e78) |
| Swing identification | 🔄 In Progress | [Implement swing identification](https://www.notion.so/2b42bd6fbda680af8811ec757faffe73) |
| BOS detection | 📝 Pending | [Implement BOS detection](https://www.notion.so/2b42bd6fbda680888409d0cfcce590ed) |
| CHoCH detection | 📝 Pending | [Implement CHoCH detection](https://www.notion.so/2b42bd6fbda680328937dde1384c14c9) |
| Liquidity sweeps | 📝 Pending | [Implement liquidity sweep detection](https://www.notion.so/2b42bd6fbda680199823ed76ec78c685) |
| HTF VWAP | 📝 Pending | [Add HTF VWAP calculation](https://www.notion.so/2b42bd6fbda6807fabc8fdf2a44a4867) |
| VWAP trend | 📝 Pending | [Add VWAP trend validation](https://www.notion.so/2b42bd6fbda68032b07bd40d08d0e8dc) |
| FVG interaction | 📝 Pending | [Add FVG interaction scoring](https://www.notion.so/2b42bd6fbda6806281cbf1eb4cff5704) |
| DXY chop | 📝 Pending | [Add DXY chop detection](https://www.notion.so/2b42bd6fbda6800f8ba4c5f08d5d4f4a) |
| Seasonality | 📝 Pending | [Add seasonality module](https://www.notion.so/2b42bd6fbda6806b9ae2f498addb965a) |
| RuleEngine integration | 📝 Pending | [Integrate into RuleEngine scoring](https://www.notion.so/2b42bd6fbda680958607d46524b566f6) |
| Parity tests | 📝 Pending | [Parity tests for HTF Bias](https://www.notion.so/2b42bd6fbda680a9b4e5f645e8e91ca2) |

## Benefits of New Structure

1. **Modularity**: Each component in its own file (no 500+ line files)
2. **Testability**: Easy to unit test individual components
3. **Maintainability**: Clear separation of concerns
4. **Extensibility**: Easy to add new HTF features
5. **Documentation**: Each module self-documents its purpose
6. **Team Collaboration**: Multiple developers can work on different components

## Testing Strategy

Each component should have:

1. **Unit Tests**: Test individual functions in isolation
2. **Integration Tests**: Test component interactions
3. **Parity Tests**: Ensure vectorized and incremental modes match
4. **Edge Case Tests**: Cover boundary conditions

Example test file structure:
```
tests/unit/rule_engine/htf/
├── test_types.py
├── test_calculator.py
├── test_integration.py
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
└── seasonality/
    ├── test_rules.py
    └── test_scoring.py
```

## Timeline

1. **Phase 1** (Current): Folder structure and types ✅
2. **Phase 2**: Structure components (swings, BOS, CHoCH, liquidity)
3. **Phase 3**: VWAP components (calculation, trend, FVG)
4. **Phase 4**: DXY and seasonality
5. **Phase 5**: Integration and parity tests

## Questions?

- See [rule_engine/htf/README.md](./README.md) for detailed documentation
- Check Notion epic: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)
- Review individual task pages for implementation details

## Deprecation Timeline

- **Current**: Old `htf_calculator.py` shows deprecation warning but still works
- **Next Release**: All new code should use `rule_engine.htf`
- **Future Release**: Remove `htf_calculator.py` entirely (after full migration)

