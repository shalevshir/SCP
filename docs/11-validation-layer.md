# Validation Layer Guide

This guide covers the validation layer components for SOP enforcement, including the validation schema and validation engine.

## Overview

The validation layer is responsible for:
- Enforcing SOP (Standard Operating Procedure) requirements before trade execution
- Validating CEO directives and tier compliance
- Checking session timing, fatigue flags, and risk budgets
- Ensuring HTF (Higher Timeframe) bias alignment with trade direction
- Validating DXY structure requirements
- Providing detailed error reporting for validation failures

**Current Status:** Fully implemented with 100% test coverage. Ready for integration with Rule Engine and Session Logic.

## Table of Contents

- [Validation Schema](#validation-schema)
- [Validation Engine](#validation-engine)
- [Session Validator](#session-validator)
- [Usage Examples](#usage-examples)
- [SOP Validation Rules](#sop-validation-rules)
- [Error Handling](#error-handling)
- [Logging](#logging)
- [Testing](#testing)
- [Integration Guide](#integration-guide)

---

## Validation Schema

The validation schema defines strongly-typed data models for all validation inputs required for SOP enforcement.

### Enums

**Location:** `validation/schema.py`

#### BufferPhase

Defines capital buffer phases per Risk Ladder SOP.

```python
from validation import BufferPhase

# Available phases
BufferPhase.STARTUP         # "0-5k"
BufferPhase.GROWTH          # "5-15k"
BufferPhase.SCALING         # "15-40k"
BufferPhase.INSTITUTIONAL   # "40k+"
```

**Purpose:** Determines risk parameters, contract sizes, and daily loss limits based on account equity.

#### EnforcerTier

Defines enforcer tier levels per CEO directives.

```python
from validation import EnforcerTier

# Available tiers
EnforcerTier.CONSERVATIVE   # "Conservative"
EnforcerTier.EARLY_MILD     # "EarlyMild" (requires CEO directive)
EnforcerTier.MILD           # "Mild"
EnforcerTier.OFFENSIVE      # "Offensive"
```

**Purpose:** Operational mode that determines setup requirements, risk tolerance, and session behavior.

**Important:** `EarlyMild` tier requires `ceo_directive_active=True` in ValidationContext.

#### HTFBias

Defines higher timeframe directional bias.

```python
from validation import HTFBias

# Available bias values
HTFBias.BULLISH    # "bullish"
HTFBias.BEARISH    # "bearish"
HTFBias.NEUTRAL    # "neutral"
```

**Purpose:** Represents the market's primary trend direction for structure-first validation.

### ValidationContext

Container for all validation inputs required for SOP enforcement.

```python
from validation import ValidationContext, BufferPhase, EnforcerTier, HTFBias

context = ValidationContext(
    session_ok=True,                          # Trading session is active
    tier_active=EnforcerTier.CONSERVATIVE,    # Current enforcer tier
    htf_bias=HTFBias.BULLISH,                # Higher timeframe bias
    dxy_trending_clean=True,                  # DXY structure is clean
    fatigue_flag=False,                       # Operator not fatigued
    risk_allowed=True,                        # Risk budget available
    news_ok=True,                            # No blocking news events
    ceo_directive_active=False,               # CEO directive status
    buffer_phase=BufferPhase.STARTUP         # Current capital phase
)
```

#### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `session_ok` | `bool` | Whether current time is within permitted trading hours (default: London 10:00-13:00) |
| `tier_active` | `EnforcerTier` | Active enforcement tier determining setup requirements |
| `htf_bias` | `HTFBias` | Higher timeframe directional bias (bullish/bearish/neutral) |
| `dxy_trending_clean` | `bool` | DXY structure clarity for continuation setups |
| `fatigue_flag` | `bool` | Operator fatigue indicator (True blocks trading) |
| `risk_allowed` | `bool` | Risk budget available for new positions |
| `news_ok` | `bool` | No high-impact news events blocking trading |
| `ceo_directive_active` | `bool` | Whether CEO directive is currently active |
| `buffer_phase` | `BufferPhase` | Current capital buffer phase (0-5k, 5-15k, 15-40k, 40k+) |

#### Validation Rules

- **All fields are required** - No optional fields
- **Strict type checking** - No implicit type coercion (e.g., "yes" won't convert to True)
- **EarlyMild enforcement** - `tier_active=EnforcerTier.EARLY_MILD` requires `ceo_directive_active=True`

```python
from pydantic import ValidationError

# This will raise ValidationError
try:
    context = ValidationContext(
        session_ok=True,
        tier_active=EnforcerTier.EARLY_MILD,  # Requires CEO directive
        htf_bias=HTFBias.BULLISH,
        dxy_trending_clean=True,
        fatigue_flag=False,
        risk_allowed=True,
        news_ok=True,
        ceo_directive_active=False,  # ❌ This violates SOP
        buffer_phase=BufferPhase.STARTUP
    )
except ValidationError as e:
    print(e)  # "EarlyMild tier requires active CEO directive"
```

---

## Validation Engine

The `ValidationEngine` evaluates whether trade signals satisfy SOP requirements.

### TradeDirection

```python
from validation import TradeDirection

# Available directions
TradeDirection.LONG   # "long"
TradeDirection.SHORT  # "short"
```

### ValidationResult

Result of validation engine evaluation.

```python
from validation import ValidationResult

# Result structure
result = ValidationResult(
    valid=False,                                # Validation passed?
    errors=["Error 1", "Error 2"],             # List of error messages
    enforced_tier="Conservative"                # Tier enforced during validation
)

# Check if valid
if result.valid:
    print("Trade setup approved")
else:
    print(f"Trade rejected: {result.errors}")
```

**Properties:**
- `valid: bool` - Whether validation passed (True) or failed (False)
- `errors: list[str]` - List of validation error messages (empty if valid)
- `enforced_tier: str` - The tier that was enforced during validation

**Note:** `ValidationResult` is immutable (frozen dataclass).

### ValidationEngine

The main engine class for validating trade setups.

```python
from validation import ValidationEngine, ValidationContext, TradeDirection

# Initialize engine
engine = ValidationEngine()

# Create validation context
context = ValidationContext(...)

# Validate a LONG trade
result = engine.validate(context, TradeDirection.LONG)

# Check result
if result.valid:
    print(f"✓ Validation passed (tier: {result.enforced_tier})")
else:
    print(f"✗ Validation failed:")
    for error in result.errors:
        print(f"  - {error}")
```

---

## Session Validator

The `SessionValidator` determines whether the current timestamp is within the SOP-approved trading session and exposes additional guardrails (tiers, setup types, minimum scores, DXY correlation thresholds, and loss halts) for downstream modules.

### Location

- **Module:** `validation/session_validator.py`
- **Exports:** `SessionValidator`, `SessionConfig`, `SeasonRule`, `SessionConstraints`, `SessionResult`

### API Overview

```python
from datetime import datetime, time, timezone

from validation import SeasonRule, SessionConfig, SessionValidator

default_rule = SeasonRule(
    name="Default",
    months=frozenset({1, 2, 3, 4, 5, 6, 7, 8}),
    window_start=time(10, 0),
    window_end=time(13, 0),
    allowed_tiers=frozenset({"Conservative", "Early Mild", "Mild", "Offensive"}),
    allowed_setups=frozenset({"continuation"}),
    min_score=8.0,
    max_losses=2,
    dxy_correlation_max=-0.6,
)

trend_rule = SeasonRule(
    name="Trend Season",
    months=frozenset({11, 12}),
    window_start=time(9, 30),
    window_end=time(14, 0),
    allowed_tiers=frozenset({"Conservative", "Early Mild", "Mild", "Offensive"}),
    allowed_setups=frozenset({"continuation", "fade"}),
    min_score=8.0,
    max_losses=2,
    dxy_correlation_max=-0.55,
)

config = SessionConfig(
    timezone="Asia/Jerusalem",
    default_rule=default_rule,
    seasons=(trend_rule,),
    holidays=frozenset(),
)

validator = SessionValidator(config)
result = validator.evaluate(datetime.now(tz=timezone.utc))

if result.session_ok:
    logger.info("Session status: allowed | %s", result.constraints.describe())
else:
    logger.warning("Session status: blocked | reason=%s", result.reason)
```

### SOP Seasonality Summary

| Season | Months | Window (ILT) | Guardrails |
| --- | --- | --- | --- |
| **September (Defensive)** | 9 | 11:00–12:30 | Conservative/Early Mild only, continuations only, min score ≥ 8.5, halt after 1 loss, DXY corr < -0.7 |
| **October (Base)** | 10 | 10:00–13:00 | Conservative/Early Mild/Mild, continuations only, min score ≥ 8.0, halt after 2 losses, DXY corr < -0.6 |
| **November–December (Trend)** | 11–12 | 09:30–14:00 | All tiers, continuations + fades, min score ≥ 8.0, halt after 2 losses, DXY corr < -0.55 |
| **Default** | Remaining months | 10:00–13:00 | All tiers, continuations only, min score ≥ 8.0, halt after 2 losses, DXY corr < -0.6 |

### Result Structure

- `session_ok`: Boolean flag (True when trading is allowed)
- `constraints`: `SessionConstraints` describing the active window and guardrails
- `reason`: Optional string (`holiday`, `outside_window`, etc.) when blocked

### Logging & Holidays

- Logs always include `"Session status: allowed/blocked"` with season metadata.
- Holidays (configured via `SessionConfig.holidays`) always block trading.
- Timezone handling relies on `zoneinfo.ZoneInfo`, ensuring DST transitions work automatically.
- Windows are inclusive of the start time and exclusive of the end time.

---

## Usage Examples

### Example 1: Valid Setup

```python
from validation import (
    ValidationEngine,
    ValidationContext,
    TradeDirection,
    BufferPhase,
    EnforcerTier,
    HTFBias
)

# Create engine
engine = ValidationEngine()

# All conditions favorable
context = ValidationContext(
    session_ok=True,
    tier_active=EnforcerTier.CONSERVATIVE,
    htf_bias=HTFBias.BULLISH,
    dxy_trending_clean=True,
    fatigue_flag=False,
    risk_allowed=True,
    news_ok=True,
    ceo_directive_active=False,
    buffer_phase=BufferPhase.STARTUP
)

# Validate LONG trade (aligned with BULLISH bias)
result = engine.validate(context, TradeDirection.LONG)

print(result.valid)  # True
print(result.errors)  # []
print(result.enforced_tier)  # "Conservative"
```

### Example 2: Session Outside Hours

```python
# Session not active
context = ValidationContext(
    session_ok=False,  # ❌ Outside London 10:00-13:00
    tier_active=EnforcerTier.CONSERVATIVE,
    htf_bias=HTFBias.BULLISH,
    dxy_trending_clean=True,
    fatigue_flag=False,
    risk_allowed=True,
    news_ok=True,
    ceo_directive_active=False,
    buffer_phase=BufferPhase.STARTUP
)

result = engine.validate(context, TradeDirection.LONG)

print(result.valid)  # False
print(result.errors)
# ["Trading session not active - outside permitted hours (default: London 10:00-13:00)"]
```

### Example 3: HTF Bias Mismatch

```python
# HTF is BULLISH but trying to go SHORT
context = ValidationContext(
    session_ok=True,
    tier_active=EnforcerTier.CONSERVATIVE,
    htf_bias=HTFBias.BULLISH,  # BULLISH bias
    dxy_trending_clean=True,
    fatigue_flag=False,
    risk_allowed=True,
    news_ok=True,
    ceo_directive_active=False,
    buffer_phase=BufferPhase.STARTUP
)

# Try SHORT trade (counter-trend)
result = engine.validate(context, TradeDirection.SHORT)  # ❌

print(result.valid)  # False
print(result.errors)
# ["HTF bias is BULLISH but trade direction is SHORT - counter-trend trades require explicit confirmation"]
```

### Example 4: Multiple Violations

```python
# Multiple blocking conditions
context = ValidationContext(
    session_ok=False,           # ❌ Session not active
    tier_active=EnforcerTier.CONSERVATIVE,
    htf_bias=HTFBias.BULLISH,
    dxy_trending_clean=False,   # ❌ DXY not clean
    fatigue_flag=True,          # ❌ Operator fatigued
    risk_allowed=False,         # ❌ Risk budget exhausted
    news_ok=False,              # ❌ News event blocking
    ceo_directive_active=False,
    buffer_phase=BufferPhase.STARTUP
)

result = engine.validate(context, TradeDirection.SHORT)  # ❌ Also counter-trend

print(result.valid)  # False
print(len(result.errors))  # 6 errors accumulated

# All violations are reported
for error in result.errors:
    print(f"- {error}")
```

### Example 5: EarlyMild Tier with CEO Directive

```python
# EarlyMild tier requires CEO directive
context = ValidationContext(
    session_ok=True,
    tier_active=EnforcerTier.EARLY_MILD,  # Special tier
    htf_bias=HTFBias.BULLISH,
    dxy_trending_clean=True,
    fatigue_flag=False,
    risk_allowed=True,
    news_ok=True,
    ceo_directive_active=True,  # ✓ Required for EarlyMild
    buffer_phase=BufferPhase.GROWTH
)

result = engine.validate(context, TradeDirection.LONG)

print(result.valid)  # True
print(result.enforced_tier)  # "EarlyMild"
```

---

## SOP Validation Rules

The `ValidationEngine` enforces the following SOP rules (in order):

### 1. Session Time Check

**Rule:** Trading only permitted during active session hours.

**Default:** London 10:00-13:00 ILT (configurable via session logic).

**Blocking Condition:** `session_ok=False`

**Error Message:** 
```
"Trading session not active - outside permitted hours (default: London 10:00-13:00)"
```

---

### 2. Fatigue Flag Check

**Rule:** Trading blocked when operator fatigue is flagged.

**Blocking Condition:** `fatigue_flag=True`

**Error Message:**
```
"Fatigue flag is set - trading blocked for safety"
```

---

### 3. Risk Budget Check

**Rule:** No new positions when daily loss limit reached.

**Blocking Condition:** `risk_allowed=False`

**Error Message:**
```
"Risk budget exhausted - no new positions allowed (check daily loss limit)"
```

---

### 4. News Event Check

**Rule:** Trading blocked during high-impact news events.

**Blocking Condition:** `news_ok=False`

**Error Message:**
```
"High-impact news event active - trading blocked per SOP"
```

---

### 5. HTF Bias Alignment Check

**Rule:** Trade direction must align with higher timeframe bias (counter-trend trades require explicit confirmation).

**Alignment Matrix:**

| HTF Bias | LONG Trade | SHORT Trade |
|----------|------------|-------------|
| BULLISH  | ✓ Pass     | ✗ Fail      |
| BEARISH  | ✗ Fail     | ✓ Pass      |
| NEUTRAL  | ✓ Pass     | ✓ Pass      |

**Error Messages:**
```
"HTF bias is BULLISH but trade direction is SHORT - counter-trend trades require explicit confirmation"
"HTF bias is BEARISH but trade direction is LONG - counter-trend trades require explicit confirmation"
```

---

### 6. DXY Structure Check

**Rule:** Continuation setups require clean DXY trend alignment.

**Blocking Condition:** `dxy_trending_clean=False`

**Error Message:**
```
"DXY structure not clean - continuation setups require clear DXY trend alignment"
```

---

## Error Handling

### ValidationError (from Pydantic)

Raised when ValidationContext creation fails due to invalid data:

```python
from pydantic import ValidationError

try:
    context = ValidationContext(
        session_ok="yes",  # ❌ Should be bool, not string
        # ... other fields
    )
except ValidationError as e:
    print("Invalid context data:", e.errors())
```

### ValidationResult Errors

The engine never raises exceptions. All validation failures are returned in `ValidationResult.errors`:

```python
result = engine.validate(context, direction)

if not result.valid:
    # Handle validation failures
    for error in result.errors:
        logger.warning(f"Setup rejected: {error}")
    
    # Reject the trade signal
    return reject_signal(reason=result.errors)
```

---

## Logging

The validation engine logs all validation attempts with detailed context.

### Log Levels

**INFO:** Successful validation
```
Validation passed: tier=Conservative, direction=long, buffer_phase=0-5k
```

**WARNING:** Validation failures (one per violation)
```
Rejected by ValidationEngine: session not active
Rejected by ValidationEngine: fatigue flag set
Rejected by ValidationEngine: risk not allowed
Rejected by ValidationEngine: news event blocking
Rejected by ValidationEngine: HTF bias mismatch (bias=bullish, direction=short)
Rejected by ValidationEngine: DXY structure unclear
```

### Log Format

All rejection logs use the standardized format:
```
"Rejected by ValidationEngine: <reason>"
```

This enables easy filtering and monitoring in production:
```bash
# Filter validation rejections
grep "Rejected by ValidationEngine" logs/dev/app.log

# Count rejection types
grep "Rejected by ValidationEngine" logs/dev/app.log | sort | uniq -c
```

---

## Testing

The validation layer has 100% test coverage with 55 comprehensive tests.

### Running Tests

```bash
# Run all validation tests
pytest tests/unit/test_validation_schema.py tests/unit/test_validation_engine.py -v

# Run with coverage report
pytest --cov=validation --cov-report=term-missing tests/unit/test_validation*.py

# Run specific test class
pytest tests/unit/test_validation_engine.py::TestValidationEngine -v
```

### Test Categories

**Schema Tests (26 tests):**
- Enum validation (all values and error cases)
- ValidationContext field requirements
- CEO directive enforcement
- Type safety and strict mode
- Serialization/deserialization

**Engine Tests (29 tests):**
- Basic structure and initialization
- Individual SOP rule validation
- HTF bias alignment logic
- Multi-error accumulation
- Tier enforcement
- Logging verification

### Example Test

```python
def test_htf_bullish_short_fails() -> None:
    """SHORT trade with BULLISH HTF bias should fail (counter-trend)."""
    engine = ValidationEngine()
    context = ValidationContext(
        session_ok=True,
        tier_active=EnforcerTier.CONSERVATIVE,
        htf_bias=HTFBias.BULLISH,  # BULLISH
        dxy_trending_clean=True,
        fatigue_flag=False,
        risk_allowed=True,
        news_ok=True,
        ceo_directive_active=False,
        buffer_phase=BufferPhase.STARTUP
    )
    
    result = engine.validate(context, TradeDirection.SHORT)  # Counter-trend
    
    assert result.valid is False
    assert any("htf bias" in err.lower() for err in result.errors)
```

---

## Integration Guide

### Integrating with Rule Engine

```python
from validation import ValidationEngine, ValidationContext, TradeDirection
from rule_engine import Signal

class SignalEvaluator:
    def __init__(self):
        self.validation_engine = ValidationEngine()
    
    def evaluate_signal(self, signal: Signal, context: ValidationContext) -> bool:
        """Evaluate if signal passes validation."""
        # Determine direction from signal
        direction = (
            TradeDirection.LONG if signal.direction == "long" 
            else TradeDirection.SHORT
        )
        
        # Validate
        result = self.validation_engine.validate(context, direction)
        
        if not result.valid:
            # Log rejection reasons
            for error in result.errors:
                logger.warning(f"Signal {signal.id} rejected: {error}")
            return False
        
        # Validation passed - proceed with scoring
        logger.info(f"Signal {signal.id} passed validation (tier: {result.enforced_tier})")
        return True
```

### Integrating with Session Logic

```python
from validation import ValidationContext, BufferPhase, EnforcerTier, HTFBias

class SessionManager:
    def create_validation_context(self) -> ValidationContext:
        """Create validation context from current session state."""
        return ValidationContext(
            session_ok=self.is_session_active(),
            tier_active=self.get_current_tier(),
            htf_bias=self.get_htf_bias(),
            dxy_trending_clean=self.is_dxy_clean(),
            fatigue_flag=self.check_fatigue(),
            risk_allowed=self.check_risk_budget(),
            news_ok=self.check_news_events(),
            ceo_directive_active=self.is_ceo_directive_active(),
            buffer_phase=self.get_buffer_phase()
        )
```

### Integrating with State Tracking

```python
class StateTracker:
    def __init__(self):
        self.consecutive_losses = 0
        self.fatigue_detected = False
    
    def update_fatigue_flag(self) -> bool:
        """Determine if fatigue flag should be set."""
        # Halt after 2 consecutive losses (per SOP)
        if self.consecutive_losses >= 2:
            self.fatigue_detected = True
            logger.warning("Fatigue flag set: 2 consecutive losses")
        
        return self.fatigue_detected
    
    def record_trade_outcome(self, won: bool) -> None:
        """Update state based on trade outcome."""
        if won:
            self.consecutive_losses = 0
            self.fatigue_detected = False
        else:
            self.consecutive_losses += 1
            if self.consecutive_losses >= 2:
                self.fatigue_detected = True
```

---

## Best Practices

### 1. Always Validate Before Scoring

Validation should happen **before** signal scoring:

```python
# ✓ CORRECT: Validate first
result = engine.validate(context, direction)
if not result.valid:
    return reject_signal()

score = calculate_score(signal)  # Only if validation passed

# ✗ WRONG: Don't score before validation
score = calculate_score(signal)
if score >= 8:
    result = engine.validate(context, direction)  # Too late!
```

### 2. Log All Validation Failures

Always log why a signal was rejected:

```python
result = engine.validate(context, direction)
if not result.valid:
    logger.warning(f"Signal {signal.id} failed validation")
    for error in result.errors:
        logger.warning(f"  - {error}")
```

### 3. Use Enums, Not Strings

Use the enum types for type safety:

```python
# ✓ CORRECT: Type-safe
tier = EnforcerTier.CONSERVATIVE
bias = HTFBias.BULLISH

# ✗ WRONG: String literals (no type checking)
tier = "Conservative"
bias = "bullish"
```

### 4. Handle ValidationContext Creation Errors

Wrap context creation in try/except:

```python
from pydantic import ValidationError

try:
    context = ValidationContext(...)
except ValidationError as e:
    logger.error(f"Invalid validation context: {e}")
    # Handle error appropriately
```

### 5. Don't Bypass Validation

Never skip validation based on score or other factors:

```python
# ✗ WRONG: Don't skip validation
if score >= 9:
    # "Score is so good, skip validation"
    return approve_signal()  # DANGEROUS!

# ✓ CORRECT: Always validate
result = engine.validate(context, direction)
if not result.valid:
    return reject_signal()
```

---

## Future Enhancements

Planned improvements for the validation layer:

1. **Risk Ladder Integration** - Automatic contract size and DD limits per buffer phase
2. **Seasonality Rules** - September defensive mode, Nov-Dec trend allowance
3. **Session Extensions** - Configurable session hours beyond default London window
4. **Loss Streak Tracking** - Automatic halt after 2 consecutive losses
5. **Performance Metrics** - Track validation pass/fail rates by tier and condition

---

## API Reference

### Quick Reference

```python
# Imports
from validation import (
    # Enums
    BufferPhase,
    EnforcerTier,
    HTFBias,
    TradeDirection,
    # Models
    ValidationContext,
    ValidationResult,
    # Engine
    ValidationEngine
)

# Create context
context = ValidationContext(
    session_ok=bool,
    tier_active=EnforcerTier,
    htf_bias=HTFBias,
    dxy_trending_clean=bool,
    fatigue_flag=bool,
    risk_allowed=bool,
    news_ok=bool,
    ceo_directive_active=bool,
    buffer_phase=BufferPhase
)

# Validate
engine = ValidationEngine()
result = engine.validate(context, TradeDirection.LONG)

# Check result
if result.valid:
    # Proceed with trade
    pass
else:
    # Handle rejection
    print(result.errors)
```

---

## Related Documentation

- [08-logging.md](./08-logging.md) - Logging system configuration
- [09-error-handling.md](./09-error-handling.md) - Exception hierarchy
- [06-testing.md](./06-testing.md) - Testing guidelines

---

## Support

For questions or issues with the validation layer:

1. Check the test files for usage examples: `tests/unit/test_validation_*.py`
2. Review the source code: `validation/schema.py` and `validation/engine.py`
3. Check logs for detailed rejection reasons: `logs/dev/app.log`

---

**Last Updated:** November 2025  
**Module Version:** 0.1.0  
**Status:** Production Ready ✓

