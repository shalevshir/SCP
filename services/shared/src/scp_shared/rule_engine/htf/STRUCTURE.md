# HTF Module Structure Visualization

## Directory Tree

```
rule_engine/htf/
├── __init__.py              # Package exports: HTFBias
├── types.py                 # HTFBias dataclass and type definitions
├── calculator.py            # Main orchestrator and legacy interface
├── integration.py           # RuleEngine integration helpers
│
├── structure/               # Structure Analysis Components
│   ├── __init__.py         # Exports: detect_swings
│   ├── swings.py           # Swing high/low identification
│   ├── bos.py              # Break of Structure (BOS) detection
│   ├── choch.py            # Change of Character (CHoCH) detection
│   └── liquidity.py        # Liquidity sweep detection
│
├── vwap/                    # VWAP Analysis Components
│   ├── __init__.py         # Exports: calculate_htf_vwap
│   ├── calculator.py       # 1H VWAP calculation
│   ├── trend.py            # VWAP trend validation
│   └── fvg.py              # FVG interaction scoring
│
├── dxy/                     # DXY Analysis Components
│   ├── __init__.py         # Exports: detect_dxy_chop
│   └── chop.py             # DXY chop/ranging detection
│
└── seasonality/             # Seasonality Components
    ├── __init__.py         # Exports: get_seasonality_period
    ├── rules.py            # Seasonality period detection
    └── scoring.py          # Seasonality-based score adjustments
```

## Component Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                       HTF Bias Engine                            │
│                     (rule_engine/htf)                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Types      │    │  Calculator  │    │ Integration  │
│              │    │              │    │              │
│ • HTFBias    │◄───│ • compute    │◄───│ • validate   │
│   dataclass  │    │   htf_bias   │    │   signal     │
│              │    │ • legacy     │    │ • adjust     │
│              │    │   interface  │    │   score      │
└──────────────┘    └──────────────┘    └──────────────┘
                            │
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Structure   │    │    VWAP      │    │ DXY & Season │
│              │    │              │    │              │
│ • Swings     │    │ • Calculator │    │ • Chop       │
│ • BOS        │    │ • Trend      │    │   detection  │
│ • CHoCH      │    │ • FVG        │    │ • Seasonality│
│ • Liquidity  │    │   interaction│    │   rules      │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Data Flow

```
Input: 1H + 15M Features, DXY Data, Timestamp
                    │
                    ▼
        ┌───────────────────────┐
        │  compute_htf_bias()   │
        └───────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
  ┌─────────┐ ┌─────────┐ ┌─────────┐
  │Structure│ │  VWAP   │ │DXY/Season│
  │Analysis │ │Analysis │ │Analysis │
  └─────────┘ └─────────┘ └─────────┘
        │           │           │
        └───────────┼───────────┘
                    ▼
        ┌───────────────────────┐
        │    HTFBias Object     │
        │  • bias, direction    │
        │  • score, confidence  │
        │  • structure summary  │
        │  • liquidity summary  │
        │  • VWAP summary       │
        │  • seasonality flags  │
        │  • DXY flags          │
        └───────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │   RuleEngine Scoring  │
        │  • validate_signal    │
        │  • adjust_score       │
        └───────────────────────┘
                    │
                    ▼
              Trade Signal
         (approved/rejected)
```

## Task Mapping to Components

| Component | File | Task | Status |
|-----------|------|------|--------|
| **Types** | `types.py` | HTFBias dataclass | ✅ Done |
| **Calculator** | `calculator.py` | Main orchestrator | ✅ Done (legacy) |
| **Swings** | `structure/swings.py` | [Swing identification](https://www.notion.so/2b42bd6fbda680af8811ec757faffe73) | 🔄 In Progress |
| **BOS** | `structure/bos.py` | [BOS detection](https://www.notion.so/2b42bd6fbda680888409d0cfcce590ed) | 📝 Pending |
| **CHoCH** | `structure/choch.py` | [CHoCH detection](https://www.notion.so/2b42bd6fbda680328937dde1384c14c9) | 📝 Pending |
| **Liquidity** | `structure/liquidity.py` | [Liquidity sweeps](https://www.notion.so/2b42bd6fbda680199823ed76ec78c685) | 📝 Pending |
| **VWAP Calc** | `vwap/calculator.py` | [HTF VWAP calculation](https://www.notion.so/2b42bd6fbda6807fabc8fdf2a44a4867) | 📝 Pending |
| **VWAP Trend** | `vwap/trend.py` | [VWAP trend validation](https://www.notion.so/2b42bd6fbda68032b07bd40d08d0e8dc) | 📝 Pending |
| **FVG** | `vwap/fvg.py` | [FVG interaction](https://www.notion.so/2b42bd6fbda6806281cbf1eb4cff5704) | 📝 Pending |
| **DXY Chop** | `dxy/chop.py` | [DXY chop detection](https://www.notion.so/2b42bd6fbda6800f8ba4c5f08d5d4f4a) | 📝 Pending |
| **Seasonality** | `seasonality/rules.py` | [Seasonality module](https://www.notion.so/2b42bd6fbda6806b9ae2f498addb965a) | 📝 Pending |
| **Season Score** | `seasonality/scoring.py` | [Seasonality scoring](https://www.notion.so/2b42bd6fbda68094a7d3d66534da8d66) | 📝 Pending |
| **Integration** | `integration.py` | [RuleEngine integration](https://www.notion.so/2b42bd6fbda680958607d46524b566f6) | 📝 Pending |

## File Size Guidelines

To maintain modularity and avoid large files:

- **Individual modules**: < 200 lines
- **Calculator orchestrator**: < 300 lines
- **Types/schemas**: < 150 lines
- **Tests**: < 300 lines per test file

If a file exceeds these limits, consider breaking it into smaller modules.

## Import Patterns

### Public API (recommended for external use)

```python
# Main entry point
from rule_engine.htf.calculator import compute_htf_bias

# Types
from rule_engine.htf.types import HTFBias

# RuleEngine integration
from rule_engine.htf.integration import validate_signal_with_htf
```

### Internal API (for HTF module internals only)

```python
# Structure components
from rule_engine.htf.structure.swings import detect_swings
from rule_engine.htf.structure.bos import detect_bos

# VWAP components
from rule_engine.htf.vwap.calculator import calculate_htf_vwap

# etc.
```

## Testing Patterns

Each component should have comprehensive tests:

```python
# tests/unit/rule_engine/htf/structure/test_swings.py

def test_detect_swings_basic():
    """Test basic swing detection."""
    # Arrange
    df = create_test_dataframe()
    
    # Act
    highs, lows = detect_swings(df, lookback=5)
    
    # Assert
    assert len(highs) > 0
    assert len(lows) > 0

def test_detect_swings_edge_cases():
    """Test swing detection with edge cases."""
    # Test with flat data, single candle, etc.
    pass

def test_detect_swings_parity():
    """Test vectorized vs incremental mode produces same results."""
    # Ensure both modes match
    pass
```

## Next Steps for Implementation

1. **Read the Notion task** for the component you're implementing
2. **Write failing tests** first (TDD)
3. **Implement the function** to make tests pass
4. **Add docstrings** with examples
5. **Update this document** if you add new files/modules
6. **Submit PR** with reference to Notion task

## Questions?

- Main documentation: [README.md](./README.md)
- Migration guide: [MIGRATION.md](./MIGRATION.md)
- Notion epic: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)

