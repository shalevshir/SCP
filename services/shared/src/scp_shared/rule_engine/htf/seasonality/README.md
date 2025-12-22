# HTF Seasonality Module

Month-based HTF scoring modifiers per Shir Capital SOP.

## Quick Start

```python
from datetime import datetime, timezone
from rule_engine.htf.seasonality import (
    get_seasonality_period,
    get_seasonality_config,
    apply_seasonality_adjustment,
)

# Detect period
timestamp = datetime(2024, 9, 15, 12, 0, tzinfo=timezone.utc)
period = get_seasonality_period(timestamp)
# Returns: "september"

# Get configuration
config = get_seasonality_config(period)
# Returns: {"min_score_threshold": 8.5, "dxy_corr_threshold": -0.65, ...}

# Apply adjustment
adjusted_score, adjustment = apply_seasonality_adjustment(
    base_score=8.2,
    period=period,
    dxy_corr=-0.7
)
# Returns: (8.2, 0.0) - DXY bonus offsets September penalty
```

## Modules

- **`rules.py`**: Period detection and configuration retrieval
- **`scoring.py`**: Score adjustment logic
- **`__init__.py`**: Public API exports

## Seasonality Periods

| Period | Min Score | DXY Threshold | Adjustment |
|--------|-----------|---------------|------------|
| September | 8.5 | -0.65 | -0.5 if score < 8.5 |
| October | 8.0 | -0.6 | None (baseline) |
| November-December | 8.0 | -0.55 | +0.3 trend bonus |
| Other | 8.0 | -0.6 | None (baseline) |

**DXY Bonus**: +0.5 when correlation exceeds seasonal threshold (all periods)

## Integration

Automatically integrated when timestamp provided to `compute_htf_bias()`:

```python
from rule_engine.htf.calculator import compute_htf_bias

htf_bias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
    timestamp=timestamp  # Enables seasonality
)

print(htf_bias.seasonality_period)      # "november_december"
print(htf_bias.seasonality_adjustment)  # 0.8
```

## Testing

```bash
# Run seasonality tests
uv run pytest tests/unit/rule_engine/htf/seasonality/ -v

# With coverage
uv run pytest tests/unit/rule_engine/htf/seasonality/ \
    --cov=rule_engine.htf.seasonality --cov-report=term-missing
```

**Coverage**: 100% (48/48 statements)  
**Tests**: 80 (38 scoring + 42 rules)

## Documentation

See [docs/rule-engine/htf-seasonality.md](/docs/rule-engine/htf-seasonality.md) for:
- Complete API reference
- SOP compliance details
- Integration examples
- Troubleshooting guide

## Status

✅ **Complete** - Production ready with full test coverage

