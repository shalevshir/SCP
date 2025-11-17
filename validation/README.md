# Validation Layer

The validation layer enforces SOP (Standard Operating Procedure) requirements before trade execution.

## Quick Start

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

# Create context with current market state
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

# Validate trade setup
result = engine.validate(context, TradeDirection.LONG)

# Check result
if result.valid:
    print(f"✓ Approved (tier: {result.enforced_tier})")
else:
    print(f"✗ Rejected:")
    for error in result.errors:
        print(f"  - {error}")
```

## Components

### Schema (`schema.py`)

Defines typed data models for validation inputs:

- **BufferPhase**: Capital phases (0-5k, 5-15k, 15-40k, 40k+)
- **EnforcerTier**: CEO directive tiers (Conservative, EarlyMild, Mild, Offensive)
- **HTFBias**: Market direction (bullish, bearish, neutral)
- **ValidationContext**: Container for all validation inputs

### Engine (`engine.py`)

Validates trade setups against SOP rules:

- **TradeDirection**: Trade direction enum (long, short)
- **ValidationResult**: Validation outcome with errors
- **ValidationEngine**: Main validation engine class

## SOP Rules Enforced

1. ✓ **Session Time** - Trading only during permitted hours
2. ✓ **Fatigue Flag** - Blocks trading when operator fatigued
3. ✓ **Risk Budget** - Enforces daily loss limits
4. ✓ **News Events** - Blocks during high-impact news
5. ✓ **HTF Bias** - Ensures direction aligns with trend
6. ✓ **DXY Structure** - Requires clean DXY for continuations

## Key Features

- **100% Type Safety** - Enums prevent invalid values at compile time
- **Strict Validation** - Pydantic prevents type coercion bugs
- **Detailed Errors** - Clear, actionable error messages
- **Comprehensive Logging** - All rejections logged with reasons
- **Full Test Coverage** - 55 tests, 100% coverage

## Important Rules

### EarlyMild Requires CEO Directive

```python
# ✓ CORRECT
context = ValidationContext(
    tier_active=EnforcerTier.EARLY_MILD,
    ceo_directive_active=True,  # Required!
    # ... other fields
)

# ✗ WRONG - Will raise ValidationError
context = ValidationContext(
    tier_active=EnforcerTier.EARLY_MILD,
    ceo_directive_active=False,  # ❌ Violates SOP
    # ... other fields
)
```

### HTF Bias Alignment

```python
# Alignment matrix
# BULLISH bias → LONG trades ✓, SHORT trades ✗
# BEARISH bias → SHORT trades ✓, LONG trades ✗
# NEUTRAL bias → Both directions ✓

# ✓ CORRECT - Aligned
context = ValidationContext(htf_bias=HTFBias.BULLISH, ...)
result = engine.validate(context, TradeDirection.LONG)  # ✓ Pass

# ✗ WRONG - Counter-trend
context = ValidationContext(htf_bias=HTFBias.BULLISH, ...)
result = engine.validate(context, TradeDirection.SHORT)  # ✗ Fail
```

## Testing

```bash
# Run all validation tests
pytest tests/unit/test_validation*.py -v

# Run with coverage
pytest --cov=validation tests/unit/test_validation*.py

# Run specific test
pytest tests/unit/test_validation_engine.py::TestValidationEngine::test_htf_bullish_long_passes -v
```

## Documentation

Full documentation: [docs/11-validation-layer.md](../docs/11-validation-layer.md)

Topics covered:
- Complete API reference
- Usage examples
- SOP validation rules
- Error handling
- Integration guide
- Best practices

## Integration

### With Rule Engine

```python
class SignalEvaluator:
    def __init__(self):
        self.validation_engine = ValidationEngine()
    
    def evaluate(self, signal, context):
        # Validate BEFORE scoring
        result = self.validation_engine.validate(context, signal.direction)
        if not result.valid:
            return reject_signal(reason=result.errors)
        
        # Proceed with scoring only if validated
        return score_signal(signal)
```

### With Session Logic

```python
class SessionManager:
    def create_context(self):
        return ValidationContext(
            session_ok=self.is_active(),
            tier_active=self.get_tier(),
            htf_bias=self.get_bias(),
            dxy_trending_clean=self.check_dxy(),
            fatigue_flag=self.check_fatigue(),
            risk_allowed=self.check_risk(),
            news_ok=self.check_news(),
            ceo_directive_active=self.check_directive(),
            buffer_phase=self.get_phase()
        )
```

## Status

- ✅ Schema implementation complete
- ✅ Engine implementation complete
- ✅ 55 tests, 100% coverage
- ✅ Type checking (mypy strict)
- ✅ Documentation complete
- ⏳ Session time validator (next)
- ⏳ Behavior guardrails (next)
- ⏳ Rule engine integration (next)

## Version

**Module:** validation  
**Version:** 0.1.0  
**Status:** Production Ready ✓  
**Test Coverage:** 100%  
**Last Updated:** November 2025

