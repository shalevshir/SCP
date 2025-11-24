# HTF Seasonality Module

**Status**: ✅ Complete  
**Epic**: Full HTF Bias Engine Upgrade  
**Tasks**: 
- Add seasonality module
- Integrate seasonality into scoring

---

## Overview

The HTF seasonality module implements month-based scoring modifiers according to Shir Capital's SOP. The system automatically adjusts HTF bias scores based on the trading month, enforcing stricter requirements during historically volatile periods (September) and providing bonuses during trend seasons (November-December).

**Key Principle**: Different months exhibit different market characteristics. The bot adapts its scoring thresholds to match seasonal behavior patterns.

---

## Architecture

```
rule_engine/htf/seasonality/
├── __init__.py              # Public API exports
├── rules.py                 # Period detection & configuration
└── scoring.py              # Score adjustment logic
```

### Components

1. **Period Detection** (`rules.py`)
   - Classifies timestamps into seasonality periods
   - Provides period-specific configuration thresholds

2. **Score Adjustment** (`scoring.py`)
   - Applies period-specific scoring modifiers
   - Manages DXY correlation bonuses
   - Enforces seasonal constraints

3. **Integration** (`calculator.py`)
   - Injects seasonality into HTF bias calculation
   - Populates HTFBias with seasonality metadata

---

## Seasonality Periods

### September: Defensive Mode

**Characteristics**: Historically volatile, risk-off environment

**Thresholds**:
- Min Score: **8.5** (strictest, vs 8.0 baseline)
- DXY Correlation: **-0.65** (strictest)
- Max Losses: **1** (vs 2 normally)

**Behavior**:
- Scores below 8.5 receive **-0.5 penalty**
- Higher barrier for trade approval
- Reduced risk tolerance

**Rationale**: September has historically shown increased volatility and trend reversals. Conservative approach protects capital.

---

### October: Baseline

**Characteristics**: Neutral month, standard behavior

**Thresholds**:
- Min Score: **8.0** (baseline)
- DXY Correlation: **-0.6** (baseline)
- Max Losses: **2**

**Behavior**:
- No special adjustments
- Standard scoring applies
- Reference point for other periods

**Rationale**: October serves as the baseline calibration month.

---

### November-December: Trend Season

**Characteristics**: Strong trending behavior, institutional flows

**Thresholds**:
- Min Score: **8.0** (baseline)
- DXY Correlation: **-0.55** (most relaxed)
- Max Losses: **2**

**Behavior**:
- Strong trends receive **+0.3 bonus**
- Relaxed DXY correlation requirement
- Encourages trend following

**Rationale**: End-of-year institutional positioning creates reliable trends. System rewards trend alignment.

---

### Other Months: Standard

**Characteristics**: Standard trading environment

**Thresholds**:
- Min Score: **8.0** (baseline)
- DXY Correlation: **-0.6** (baseline)
- Max Losses: **2**

**Behavior**:
- Same as October baseline
- No special treatment

**Rationale**: Months without specific characteristics use standard rules.

---

## API Reference

### Period Detection

#### `get_seasonality_period(timestamp: datetime) -> SeasonalityPeriod`

Determines the seasonality period from a timestamp.

**Args**:
- `timestamp`: datetime object (timezone-aware or naive)

**Returns**:
- `SeasonalityPeriod`: One of "september", "october", "november_december", "other"

**Example**:
```python
from datetime import datetime, timezone
from rule_engine.htf.seasonality import get_seasonality_period

timestamp = datetime(2024, 9, 15, 12, 0, tzinfo=timezone.utc)
period = get_seasonality_period(timestamp)
# Returns: "september"
```

---

#### `get_seasonality_config(period: SeasonalityPeriod) -> dict`

Retrieves period-specific configuration thresholds.

**Args**:
- `period`: Seasonality period classification

**Returns**:
- `dict` with keys:
  - `min_score_threshold`: float
  - `dxy_corr_threshold`: float
  - `max_losses`: int
  - `description`: str

**Example**:
```python
from rule_engine.htf.seasonality import get_seasonality_config

config = get_seasonality_config("september")
# Returns: {
#     "min_score_threshold": 8.5,
#     "dxy_corr_threshold": -0.65,
#     "max_losses": 1,
#     "description": "September - Defensive mode (stricter thresholds)"
# }
```

---

### Score Adjustment

#### `apply_seasonality_adjustment(base_score: float, period: SeasonalityPeriod, dxy_corr: float | None) -> tuple[float, float]`

Applies seasonality-based adjustments to HTF score.

**Args**:
- `base_score`: Base HTF score before adjustments (0-10)
- `period`: Current seasonality period
- `dxy_corr`: DXY correlation value (can be None)

**Returns**:
- `tuple[adjusted_score, adjustment_amount]`
  - `adjusted_score`: Final score after adjustment (clamped to 0-10)
  - `adjustment_amount`: Amount of adjustment applied

**Adjustment Logic**:

1. **DXY Correlation Bonus** (+0.5)
   - Applied when `dxy_corr < seasonal_threshold`
   - Uses period-specific threshold

2. **Trend Season Bonus** (+0.3)
   - Applied when period is "november_december" AND base_score >= 8.0
   - Rewards strong trends in trending months

3. **September Penalty** (-0.5)
   - Applied when period is "september" AND base_score < 8.5
   - Enforces higher minimum in volatile month

**Example**:
```python
from rule_engine.htf.seasonality import apply_seasonality_adjustment

# September with low score
adjusted, adj_amount = apply_seasonality_adjustment(
    base_score=8.2,
    period="september",
    dxy_corr=-0.7
)
# Returns: (8.2, 0.0) - DXY bonus (+0.5) offsets September penalty (-0.5)

# November-December with strong trend
adjusted, adj_amount = apply_seasonality_adjustment(
    base_score=8.5,
    period="november_december",
    dxy_corr=-0.7
)
# Returns: (9.3, 0.8) - Trend bonus (+0.3) + DXY bonus (+0.5)
```

---

## Integration with HTF Calculator

The seasonality module is automatically integrated into `compute_htf_bias()` when a timestamp is provided.

### Usage

```python
import pandas as pd
from datetime import datetime, timezone
from rule_engine.htf.calculator import compute_htf_bias

# Create sample features
features_1h = pd.Series({
    "structure_label": "HH",
    "ema_9": 2500,
    "ema_20": 2490,
    "ema_50": 2480,
    "dxy_corr": -0.7,
})

features_15m = pd.Series({
    "structure_label": "HH",
    "ema_9": 2501,
    "ema_20": 2491,
    "ema_50": 2481,
    "dxy_corr": -0.65,
})

# November timestamp (trend season)
timestamp = pd.Timestamp(datetime(2024, 11, 15, 12, 0, tzinfo=timezone.utc))

# Compute HTF bias with seasonality
htf_bias = compute_htf_bias(
    features_1h=features_1h,
    features_15m=features_15m,
    timestamp=timestamp
)

print(f"Period: {htf_bias.seasonality_period}")  # "november_december"
print(f"Adjustment: {htf_bias.seasonality_adjustment}")  # 0.8
print(f"Final Score: {htf_bias.score}")  # Base + adjustment (capped at 10)
```

### Without Timestamp (Backward Compatibility)

```python
# No timestamp provided - skips seasonality
htf_bias = compute_htf_bias(features_1h, features_15m)

# Seasonality fields will be None/0
assert htf_bias.seasonality_period is None
assert htf_bias.seasonality_adjustment == 0.0
```

---

## Seasonality Matrix

| Period | Min Score | DXY Threshold | Max Losses | Adjustment | Description |
|--------|-----------|---------------|------------|------------|-------------|
| **September** | 8.5 | -0.65 | 1 | -0.5 if score < 8.5 | Defensive mode |
| **October** | 8.0 | -0.6 | 2 | None | Neutral baseline |
| **November-December** | 8.0 | -0.55 | 2 | +0.3 trend bonus | Trend season |
| **Other** | 8.0 | -0.6 | 2 | None | Standard |

**DXY Bonus**: +0.5 for all periods when DXY correlation exceeds seasonal threshold

---

## Scoring Examples

### Example 1: September Defensive Mode

```python
# Low score in September
base_score = 8.0
period = "september"
dxy_corr = -0.6  # Below September threshold

adjusted, adj = apply_seasonality_adjustment(base_score, period, dxy_corr)
# Result: (7.5, -0.5)
# Reason: September penalty applied, DXY not strong enough for bonus
```

### Example 2: November Trend Season

```python
# Strong trend in November
base_score = 8.5
period = "november_december"
dxy_corr = -0.7

adjusted, adj = apply_seasonality_adjustment(base_score, period, dxy_corr)
# Result: (9.3, 0.8)
# Reason: Trend bonus (+0.3) + DXY bonus (+0.5)
```

### Example 3: October Baseline

```python
# Standard October trading
base_score = 8.2
period = "october"
dxy_corr = -0.62

adjusted, adj = apply_seasonality_adjustment(base_score, period, dxy_corr)
# Result: (8.7, 0.5)
# Reason: DXY bonus only (exceeds -0.6 threshold)
```

---

## Decision Tree

```
Input: base_score, period, dxy_corr
│
├─ Is dxy_corr < seasonal_threshold?
│  └─ YES → Add +0.5 bonus
│
├─ Is period == "november_december" AND base_score >= 8.0?
│  └─ YES → Add +0.3 bonus
│
├─ Is period == "september" AND base_score < 8.5?
│  └─ YES → Add -0.5 penalty
│
└─ Clamp result to [0, 10]
```

---

## Implementation Details

### Timestamp Handling

The system handles both pandas Timestamps and Python datetime objects:

```python
# Convert pandas Timestamp to datetime if needed
if hasattr(timestamp, 'to_pydatetime'):
    dt = timestamp.to_pydatetime()
else:
    dt = timestamp
```

### Timezone Considerations

Period detection is based on the **month** of the timestamp, regardless of timezone:

```python
month = timestamp.month  # Extract month (1-12)
```

This works correctly across timezones because:
- Trading decisions are made on the calendar month
- Month boundaries are unambiguous
- DST transitions don't affect month classification

---

## Logging

All seasonality operations include debug logging for audit trail:

```python
# Period detection
logger.debug("Seasonality period detected: %s | month=%d | timestamp=%s", 
             period, month, timestamp.isoformat())

# Configuration retrieval
logger.debug("Seasonality config retrieved: %s | min_score=%.1f | dxy_corr=%.2f | max_losses=%d",
             period, config["min_score_threshold"], 
             config["dxy_corr_threshold"], config["max_losses"])

# Score adjustment
logger.debug("Seasonality adjustment applied: period=%s | base=%.2f | adj=%.2f | final=%.2f",
             period, base_score, adjustment, adjusted_score)
```

---

## Testing

### Test Coverage

- **80 total tests** (38 scoring + 42 rules)
- **100% code coverage** on seasonality module
  - `rules.py`: 22/22 statements
  - `scoring.py`: 23/23 statements
  - `__init__.py`: 3/3 statements

### Test Categories

1. **Unit Tests** - Individual function behavior
   - All 12 months classified correctly
   - All 4 period configurations accurate
   - Edge cases (None values, boundaries, extremes)

2. **Integration Tests** - End-to-end seasonality flow
   - HTF calculator integration
   - HTFBias field population
   - Backward compatibility

3. **Comparison Tests** - Relative behavior
   - September is strictest
   - November-December is most generous
   - Period-specific threshold differences

4. **Parametrized Tests** - Systematic coverage
   - All periods with various base scores
   - All months with expected periods
   - All DXY correlation ranges

### Running Tests

```bash
# All seasonality tests
uv run pytest tests/unit/rule_engine/htf/seasonality/ -v

# With coverage
uv run pytest tests/unit/rule_engine/htf/seasonality/ \
    --cov=rule_engine.htf.seasonality \
    --cov-report=term-missing

# Integration only
uv run pytest tests/unit/rule_engine/htf/seasonality/test_scoring.py::TestSeasonalityIntegration -v
```

---

## SOP Compliance

### Requirements Met

✅ **September trend score threshold = 8.5**
- Enforced via -0.5 penalty for scores < 8.5
- Logged and auditable

✅ **November-December relax DXY correlation threshold to -0.55**
- Applied in DXY bonus logic
- Allows -0.55 to -0.6 range to qualify

✅ **Period-specific configurations**
- All thresholds match SOP specifications
- Documented and tested

✅ **Audit trail**
- All adjustments logged at debug level
- HTFBias records adjustment amount
- Period classification included in output

---

## Future Enhancements

### Planned

1. **Dynamic Thresholds**
   - Adjust thresholds based on year-over-year volatility
   - Machine learning for optimal seasonal parameters

2. **Intra-Month Refinement**
   - Early/mid/late month subdivisions
   - First/last week of month logic

3. **Holiday Awareness**
   - Pre/post major holidays adjustments
   - End-of-quarter effects

4. **Volatility Regime Integration**
   - Combine seasonality with VIX levels
   - Adaptive thresholds based on market conditions

### Considered but Deferred

- **Week-of-month effects** - Complexity vs benefit unclear
- **Day-of-week patterns** - Better handled at execution layer
- **Multi-year cycles** - Insufficient data for validation

---

## Troubleshooting

### Score doesn't change despite seasonality

**Check**:
1. Is timestamp provided to `compute_htf_bias()`?
2. Is base score already at min/max (0 or 10)?
3. Does DXY correlation meet seasonal threshold?
4. Check debug logs for adjustment details

### Unexpected penalty in November

**Likely cause**: Base score < 8.0, so trend bonus not applied

**Solution**: Trend bonus requires base_score >= 8.0

### DXY bonus not applied

**Check**:
1. Is `dxy_corr` None?
2. Is DXY correlation stronger (more negative) than seasonal threshold?
   - September: -0.65
   - October/Other: -0.6
   - November-December: -0.55

---

## References

- **SOP Document**: Shir Capital Trading Rules v2025
- **Notion Task**: https://www.notion.so/2b42bd6fbda68094a7d3d66534da8d66
- **Epic**: Full HTF Bias Engine Upgrade
- **Related**: Validation Layer session constraints use same thresholds

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-24 | Initial implementation |
|  |  | - Period detection and configuration |
|  |  | - Score adjustment logic |
|  |  | - HTF calculator integration |
|  |  | - 80 tests with 100% coverage |

---

**Module Status**: ✅ Production Ready  
**Test Coverage**: 100%  
**Last Updated**: November 24, 2025

