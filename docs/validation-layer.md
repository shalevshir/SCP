# Validation Layer Documentation

## Overview

The Validation Layer enforces Shir Capital's Standard Operating Procedures (SOP) for trading discipline, risk management, and behavioral compliance. It integrates with the RuleEngine to ensure every trade signal satisfies SOP requirements before execution.

**Key Principles:**
- **Structure First**: No trade without confirmation
- **Discipline Automation**: SOP enforcement before profit pursuit
- **Transparency**: Every decision logged and auditable

## Architecture

The validation layer consists of four main components:

1. **SessionValidator**: Enforces time windows, seasonality rules, and holiday restrictions
2. **BehaviorGuardrails**: Tracks loss streaks, fatigue flags, and session extensions
3. **ValidationEngine**: Validates trade context against SOP requirements
4. **ValidationContextBuilder**: Extracts HTF bias and builds validation context from market data

## Seasonality Rules

### Date Ranges

The validation layer enforces season-specific trading rules:

| Season | Dates | Min Score | Max Losses | Allowed Tiers | Allowed Setups |
|--------|-------|-----------|------------|---------------|----------------|
| **September Defensive** | Sept 1-30 | 9.0 | 1 | Conservative, EarlyMild | VWAP_RECLAIM, DXY_CONTINUATION |
| **October Base/Reconstruction** | Oct 1-31 | 8.5 | 2 | Conservative, EarlyMild, Mild | VWAP_RECLAIM, DXY_CONTINUATION, VWAP_FADE |
| **November-December Trend Window** | Nov 1-Dec 31 | 8.0 | 2 | All tiers | All setups |
| **Default** | All other months | 8.0 | 2 | All tiers | VWAP_RECLAIM, DXY_CONTINUATION |

### Seasonal Behavior

**September Defensive:**
- Heightened caution after historically volatile summer months
- Strict score requirements (min 9.0)
- Halt after 1 consecutive loss
- Stricter DXY correlation requirement (<-0.7)
- Limited to Conservative and EarlyMild tiers

**October Base/Reconstruction:**
- Transitional phase rebuilding confidence
- Moderate score requirements (min 8.5)
- Allows VWAP_FADE setups
- Standard 2-loss halt

**November-December Trend Window:**
- Optimal trading conditions
- All setup types allowed
- All enforcer tiers allowed
- Standard scoring (min 8.0)

## Session Window Enforcement

### Default Trading Window

**London Session**: 10:00 - 13:00 (Europe/London timezone)

This window captures the London open and overlaps with early US session, providing optimal liquidity and volatility for Gold futures trading.

### Session Validation

The SessionValidator evaluates each timestamp against:
1. **Time window**: Is current time within permitted hours?
2. **Holiday calendar**: Is today a US market holiday?
3. **Seasonality**: What season-specific rules apply?

### Timezone Handling

- All session rules use `Europe/London` timezone
- Automatic DST (Daylight Saving Time) handling via `zoneinfo`
- Timestamps converted to local London time for evaluation

### Holiday Restrictions

**US Holidays Block All Trading:**
- New Year's Day
- Martin Luther King Jr. Day
- Presidents' Day
- Good Friday
- Memorial Day
- Juneteenth
- Independence Day
- Labor Day
- Thanksgiving
- Christmas Day

Holiday dates for 2024-2026 are pre-configured in `config/validation.yaml`.

## Loss Streak Tracking

### Reset Timing

**Loss streaks reset at session start**, not across days. This ensures:
- Clean slate each trading session
- No carry-over from previous day's performance
- Aligns with psychological reset at session open

### Seasonal Loss Limits

| Season | Max Consecutive Losses |
|--------|----------------------|
| September | 1 |
| October-December | 2 |
| Default | 2 |

### Behavior State

The `BehaviorStateTracker` maintains:
- `consecutive_losses`: Count of consecutive losing trades
- `fatigue_flag`: Manual operator fatigue indicator
- `session_extended`: Whether session exceeded permitted window
- `last_reset`: Timestamp of most recent state reset

### Loss Streak Logic

```python
# After each trade outcome
if won:
    consecutive_losses = 0  # Reset on win
else:
    consecutive_losses += 1  # Increment on loss

# Check against season-specific limit
if consecutive_losses >= max_losses_for_season:
    halt_trading()  # Reject all signals
```

## Tier-Based Setup Restrictions

### Enforcer Tiers

| Tier | Allowed Setups | Max Trades/Day | Risk Profile |
|------|----------------|----------------|--------------|
| **Conservative** | VWAP_RECLAIM, DXY_CONTINUATION | 2 | Baseline |
| **EarlyMild** | VWAP_RECLAIM, DXY_CONTINUATION | 2 | CEO Directive Required |
| **Mild** | VWAP_RECLAIM, DXY_CONTINUATION, VWAP_FADE | 3 | Standard |
| **Offensive** | All setups | 4 | Advanced |

### Tier Restrictions by Season

Some seasons further restrict which tiers are allowed:
- **September**: Only Conservative and EarlyMild
- **October**: Conservative, EarlyMild, and Mild
- **November-December**: All tiers

## HTF Bias Computation

### Methodology

HTF (Higher Timeframe) bias is computed internally from multiple signals:

1. **Structure Type** (HH/HL/LH/LL):
   - `HH` or `HL` → Bullish signal
   - `LH` or `LL` → Bearish signal

2. **EMA Alignment**:
   - `EMA9 > EMA20 > EMA50` → Bullish signal
   - `EMA9 < EMA20 < EMA50` → Bearish signal

3. **Price vs VWAP**:
   - `Close > VWAP` → Bullish signal
   - `Close < VWAP` → Bearish signal

4. **DXY Correlation** (Confirmation Signal):
   - Strong inverse correlation (`< -0.6`) acts as a **confirmation signal**
   - Strengthens whichever direction is currently leading (more signals)
   - Does NOT break ties when signals are equal (requires other signals to establish direction first)
   - Example: With 1 bullish signal + 0 bearish, DXY adds a 2nd bullish signal → BULLISH bias
   - Example: With 1 bullish + 1 bearish (tied), DXY does not add to either → NEUTRAL bias

**Implementation Note**: DXY correlation strengthens the majority direction by adding to the leading signal count. This ensures DXY confirms existing bias rather than creating bias from ambiguous market conditions.

### Bias Classification

The ValidationContextBuilder aggregates these signals:
- **BULLISH**: ≥2 bullish signals AND more bullish than bearish
- **BEARISH**: ≥2 bearish signals AND more bearish than bullish  
- **NEUTRAL**: Mixed or insufficient signals (< 2 signals in leading direction)

**Signal Counting Example**:
```python
# Scenario 1: Clear bullish bias
structure = "HH"           # +1 bullish
ema_stack = ascending      # +1 bullish  
price_vwap = above         # +1 bullish
dxy_corr = -0.75           # +1 bullish (confirms majority)
# Result: 4 bullish vs 0 bearish → BULLISH

# Scenario 2: DXY as tiebreaker
structure = "HH"           # +1 bullish
ema_stack = flat           # 0 signals
price_vwap = at_vwap       # 0 signals
dxy_corr = -0.75           # +1 bullish (confirms leader)
# Result: 2 bullish vs 0 bearish → BULLISH

# Scenario 3: DXY doesn't break ties
structure = "HH"           # +1 bullish
ema_stack = flat           # 0 signals
price_vwap = below         # +1 bearish
dxy_corr = -0.75           # No signal added (tied 1-1)
# Result: 1 bullish vs 1 bearish → NEUTRAL
```

### HTF Bias Alignment

Trade signals must align with HTF bias:
- Long trades require BULLISH or NEUTRAL HTF bias
- Short trades require BEARISH or NEUTRAL HTF bias
- Counter-trend trades require explicit confirmation

## DXY Unavailability Handling

### Setup-Specific Rules

When DXY correlation data is unavailable, the ValidationEngine applies different rules based on setup type:

| Setup Type | Action | Rationale |
|------------|--------|-----------|
| **VWAP_RECLAIM** | REJECT | Continuation setup requires DXY confirmation |
| **DXY_CONTINUATION** | REJECT | Core setup depends on DXY correlation |
| **VWAP_FADE** | ALLOW with WARNING | Counter-trend setup less reliant on DXY |

**ValidationEngine Integration**: Pass `setup_type` parameter to enable setup-specific validation:

```python
from validation.engine import ValidationEngine, TradeDirection

engine = ValidationEngine()
result = engine.validate(
    context=validation_context,
    direction=TradeDirection.LONG,
    setup_type="VWAP_RECLAIM"  # Enables setup-specific DXY checks
)
```

Without `setup_type`, all setups require clean DXY trends. With `setup_type="VWAP_FADE"`, DXY unavailability generates a warning but doesn't block the trade.

### DXY Trending Status

For continuation setups, DXY trend must be "clean":
- Correlation strength: `|dxy_corr| >= 0.6`
- Inverse correlation: `dxy_corr < -0.6` for Gold/DXY
- Clear directional bias in DXY structure

### Missing Data Detection

DXY data is considered unavailable if:
- `dxy_corr` field is `None`
- `dxy_corr` field is `NaN`
- Correlation strength is weak (`|dxy_corr| < 0.6`)

## CEO Early Mild Directive

### Directive Requirement

The **EarlyMild** tier can only be activated when:
1. CEO directive flag is active (`ceo_directive_active=True`)
2. Win rate threshold met (≥62% per SOP)
3. Buffer phase supports risk increase

### Directive Configuration

**Config flag** (persistent):
```yaml
# config/validation.yaml
ceo_directive:
  early_mild_enabled: true
```

**Runtime override** (daily reset):
```json
// config/dev.local.json
{
  "ceo_directive_active": true
}
```

### Validation Logic

```python
if tier_active == EnforcerTier.EARLY_MILD:
    if not ceo_directive_active:
        raise ValueError(
            "EarlyMild tier requires active CEO directive"
        )
```

This ensures the EarlyMild tier (62%+ win rate operation) is only activated with explicit CEO approval.

## Fatigue Flag Enforcement

### Purpose

The fatigue flag provides a manual override to halt trading when:
- Operator feels mentally fatigued
- Emotional state is compromised
- Multiple unexpected events occur
- Trading discipline feels shaky

### Behavior

When `fatigue_flag=True`:
- **All trading immediately halted**
- All signals downgraded to `confidence="Reject"`
- Rejection reason: `"Fatigue flag is set - trading blocked for safety"`

### Setting Fatigue Flag

**Via market state:**
```python
market_state = {
    "fatigue_flag": True,
    # ... other fields
}
```

**Via BehaviorStateTracker:**
```python
tracker.set_fatigue_flag(True)
```

### Clearing Fatigue Flag

Fatigue flag can be cleared:
1. Manually via API/config update
2. Automatically at session reset (if configured)
3. After break/rest period

## Validation Rejection Reasons

### Common Rejection Scenarios

1. **Session Window**: `"Trading session not active - outside permitted hours"`
2. **Holiday**: `"Holiday - trading blocked"`
3. **Low Score**: `"Score X.X below seasonal minimum Y.Y"`
4. **Setup Not Allowed**: `"Setup VWAP_FADE not allowed in September Defensive season"`
5. **Loss Streak**: `"Loss streak limit reached: 2 consecutive losses (max_losses=2)"`
6. **Fatigue**: `"Fatigue flag is set - trading blocked for safety"`
7. **DXY Unavailable**: `"VWAP_RECLAIM requires DXY data - rejecting due to unavailability"`
8. **HTF Mismatch**: `"HTF bias is BEARISH but trade direction is LONG"`
9. **News Event**: `"High-impact news event active - trading blocked per SOP"`
10. **Risk Budget**: `"Risk budget exhausted - no new positions allowed"`

### Rejection Logging

All rejections are logged with:
- **Timestamp**: When rejection occurred
- **Reason(s)**: Complete list of failed validations
- **Signal Details**: Score, setup type, direction
- **Market Context**: Season, tier, session status
- **Behavior State**: Loss streak, fatigue status

## Integration Example

### Complete Pipeline

```python
from feature_engine.backtesting import BacktestProcessor
from feature_engine.integration import process_features_with_validation

# Initialize processor with validation enabled
processor = BacktestProcessor(
    timeframe="1m",
    enable_validation=True
)

# Iterate through candles
for features, validation_context in processor.iterate_with_context(gc_df, dxy_df):
    # Build market state
    market_state = {
        "buffer_phase": "0-5k",
        "tier_active": "Conservative",
        "ceo_directive_active": False,
        "news_ok": True,
        "session_ok": validation_context["session_ok"],
        "htf_direction": "long",
        "htf_score": 9.0,
    }
    
    # Process through validation pipeline
    signal = process_features_with_validation(
        features=features,
        market_state=market_state,
        session_constraints=validation_context["session_constraints"],
        guardrail_result=validation_context.get("guardrail_result"),
        log_signals=True,
    )
    
    # Execute only A+ signals
    if signal.confidence == "A+":
        execute_trade(signal)
    
    # Record outcome for behavior tracking
    if trade_closed:
        processor.record_trade_outcome(won=trade_profitable)
```

## Configuration Files

### validation.yaml

Location: `config/validation.yaml`

Defines:
- Season-specific rules (dates, min_score, max_losses)
- Session time windows
- US holiday calendar
- Tier restrictions per season
- DXY handling rules
- CEO directive settings

### Updating Configuration

To modify validation rules:

1. Edit `config/validation.yaml`
2. Restart application (config loaded at startup)
3. Test changes with validation test suite

**Example: Add new holiday**
```yaml
holidays:
  - "2025-12-26"  # Boxing Day (if adding UK holidays)
```

## Testing

### Test Coverage

The validation layer has comprehensive test coverage:

1. **Unit Tests**:
   - `test_validation_context_builder.py`: HTF bias, DXY handling
   - `test_validation_layer_application.py`: 20+ scenarios covering all rules
   - `test_session_validator.py`: Time windows, holidays, DST
   - `test_behavior_guardrails.py`: Loss streaks, fatigue flags
   - `test_validation_engine.py`: Full SOP validation

2. **Integration Tests**:
   - `test_validation_integration_e2e.py`: Complete pipeline tests

### Running Tests

```bash
# Run all validation tests
pytest tests/unit/test_validation*.py -v

# Run with coverage
pytest tests/unit/test_validation*.py --cov=validation --cov-report=html

# Run specific scenario
pytest tests/unit/test_validation_layer_application.py::TestSeasonalityRules::test_september_defensive_blocks_low_scores -v
```

## Logging and Observability

### Signal Logs

All signals are logged to `logs/signals/YYYY-MM-DD.jsonl` with:

```json
{
  "timestamp": "2024-11-15T10:30:00+00:00",
  "symbol": "GC",
  "confidence": "Reject",
  "score": 8.5,
  "validation_result": {
    "valid": false,
    "errors": ["Score 8.5 below seasonal minimum 9.0"],
    "enforced_tier": "Conservative"
  },
  "session_constraints": {
    "name": "September Defensive",
    "window": "10:00-13:00",
    "min_score": 9.0,
    "max_losses": 1
  },
  "guardrail_state": {
    "consecutive_losses": 0,
    "fatigue_flag": false,
    "session_extended": false
  }
}
```

### Log Analysis

Query rejection reasons:
```bash
# Count rejections by reason
cat logs/signals/2024-11-*.jsonl | jq '.validation_result.errors[]' | sort | uniq -c

# Find all September rejections
cat logs/signals/2024-09-*.jsonl | jq 'select(.confidence=="Reject")'
```

## Troubleshooting

### Common Issues

**Issue**: "EarlyMild tier requires active CEO directive"
- **Solution**: Set `ceo_directive_active=True` in market state or config

**Issue**: All signals rejected in September
- **Solution**: Verify score >= 9.0, check September defensive rules

**Issue**: DXY correlation always missing
- **Solution**: Verify DXY data feed, check alignment logic in data layer

**Issue**: Session always blocked
- **Solution**: Check timezone configuration, verify holiday calendar

**Issue**: Loss streak not resetting
- **Solution**: Verify `reset_for_session()` called at session start

### Debug Logging

Enable debug logging:
```python
import logging
logging.getLogger("validation").setLevel(logging.DEBUG)
logging.getLogger("rule_engine").setLevel(logging.DEBUG)
```

## Future Enhancements

Planned improvements:
1. **Dynamic score adjustment**: Auto-adjust min_score based on win rate
2. **ML-based fatigue detection**: Predict operator fatigue from patterns
3. **Advanced DXY structure**: Analyze DXY swing structure for clean trends
4. **Multi-asset correlation**: Expand beyond DXY to other correlation pairs
5. **Real-time alerting**: Slack/email notifications for validation events

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-21  
**Maintained By**: SCP Engineering Team

