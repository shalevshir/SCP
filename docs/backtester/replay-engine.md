# Validation Replay Engine

## Overview

The Validation Replay Engine provides a historical replay system that runs all SOP validators incrementally over historical data, ensuring validation results match live behavior. The engine tracks evolving state (loss streaks, daily risk) that resets per session and ensures no lookahead bias.

## Key Features

- **Incremental Validation**: Runs all validators candle-by-candle (no lookahead)
- **State Evolution**: Tracks loss streaks, daily risk, and behavior guardrails
- **Session Resets**: Automatically resets state at session boundaries
- **No Lookahead Bias**: Only uses data up to current timestamp
- **Integration**: Works seamlessly with existing backtest pipeline

## Architecture

The replay engine wraps `BacktestProcessor` and adds state management for validation:

```
ReplayEngine
├── BacktestProcessor (feature computation, no lookahead)
├── SessionValidator (time windows, seasonality)
├── BehaviorGuardrails (loss streaks, fatigue flags)
└── ValidationEngine (SOP compliance)
```

## Usage

### Basic Replay

```python
from backtester.replay_engine import ReplayEngine

# Initialize engine
engine = ReplayEngine(timeframe="1m", enable_validation=True)

# Replay historical data
for features, validation_context in engine.replay(gc_df, dxy_df):
    # Process signal with validation
    signal = process_signal(features, validation_context)
    
    # Check validation flags
    if validation_context.get("session_ok"):
        # Session is active
        pass
    
    if validation_context.get("guardrail_result"):
        guardrail = validation_context["guardrail_result"]
        if not guardrail.allowed:
            # Blocked by guardrails (loss streak, fatigue, etc.)
            print(f"Blocked: {guardrail.reasons}")
```

### Recording Trade Outcomes

```python
# After a trade closes, record the outcome
engine.record_trade_outcome(won=True)  # or won=False

# This updates behavior state (loss streaks, etc.)
# Future validations will use the updated state
```

### Getting Validation Context at Specific Timestamp

```python
# Get validation context for a specific timestamp
timestamp = datetime(2025, 1, 15, 10, 30, tzinfo=UTC)
context = engine.get_validation_context_at_timestamp(
    gc_df, dxy_df, timestamp
)

if context:
    print(f"Session OK: {context.get('session_ok')}")
    print(f"Loss streak: {context.get('behavior_state').consecutive_losses}")
```

## Validation Context Structure

The validation context returned by `replay()` contains:

```python
{
    "session_ok": bool,  # Whether session is active
    "session_result": SessionResult,  # Full session evaluation
    "session_constraints": SessionConstraints,  # Season-specific constraints
    "guardrail_result": GuardrailResult,  # Behavior guardrail evaluation
    "behavior_state": BehaviorState,  # Current behavioral state snapshot
}
```

### SessionConstraints

Contains season-specific rules:
- `max_losses`: Maximum consecutive losses before halt
  - September: 1 loss
  - Other months: 2 losses
- `min_score`: Minimum signal score required
- `allowed_tiers`: Allowed enforcer tiers
- `allowed_setups`: Allowed setup types

### GuardrailResult

Indicates whether trading is allowed:
- `allowed`: True if trading allowed, False if blocked
- `reasons`: List of blocking reasons (if any)

### BehaviorState

Current behavioral state:
- `consecutive_losses`: Current loss streak count
- `fatigue_flag`: Whether fatigue flag is set
- `session_extended`: Whether session extended beyond window
- `last_reset`: Timestamp of last session reset

## State Evolution

### Loss Streak Tracking

Loss streaks are tracked per session and reset:
- **On session start**: Streak resets to 0
- **On winning trade**: Streak resets to 0
- **On losing trade**: Streak increments

### Session Resets

State automatically resets at session boundaries:
- New trading day triggers reset
- Loss streaks reset to 0
- Daily risk counters reset

## Integration with Backtest Pipeline

The replay engine integrates with the backtest pipeline:

```python
from backtester.pipeline import run_backtest_with_trades

# The pipeline automatically:
# 1. Uses ReplayEngine internally
# 2. Records trade outcomes
# 3. Updates behavior state
# 4. Applies validation to future signals

trades = run_backtest_with_trades(
    gc_df=gc_df,
    dxy_df=dxy_df,
    timeframe="1m",
    market_state=market_state,
    htf_bias_func=compute_htf_bias,
    risk_config=risk_config,
)

# Trade outcomes are automatically recorded
# Loss streaks evolve correctly during backtest
```

## Loss Streak Rules

### September (Defensive)

- **Max Losses**: 1
- **Behavior**: Halt after 1 consecutive loss
- **Rationale**: Defensive mode after volatile summer

### Other Months

- **Max Losses**: 2
- **Behavior**: Halt after 2 consecutive losses
- **Rationale**: Standard risk management

### Example

```python
engine = ReplayEngine(timeframe="1m", enable_validation=True)

# September: 1 loss blocks
results = list(engine.replay(sept_gc_df, sept_dxy_df))
constraints = results[0][1]["session_constraints"]
assert constraints.max_losses == 1

engine.record_trade_outcome(won=False)  # 1 loss
# Next validation will be blocked

# October: 2 losses block
results = list(engine.replay(oct_gc_df, oct_dxy_df))
constraints = results[0][1]["session_constraints"]
assert constraints.max_losses == 2

engine.record_trade_outcome(won=False)  # 1 loss - still allowed
engine.record_trade_outcome(won=False)  # 2 losses - blocked
```

## No Lookahead Guarantee

The replay engine ensures no lookahead bias:

1. **Feature Computation**: Only uses data up to current timestamp
2. **Validation**: Validators only see past data
3. **State Evolution**: State updates based on past outcomes only

### Verification

```python
# Modify future data
gc_df_modified = gc_df.copy()
gc_df_modified.iloc[-1]["close"] = 9999.0

# Replay both versions
results_original = list(engine.replay(gc_df, dxy_df))
results_modified = list(engine.replay(gc_df_modified, dxy_df))

# All features except last should be identical
for i in range(len(results_original) - 2):
    f1, _ = results_original[i]
    f2, _ = results_modified[i]
    assert f1["close"] == f2["close"]  # Not affected by future change
```

## Testing

Comprehensive tests verify:

1. **Incremental Validation**: Validators run candle-by-candle
2. **No Lookahead**: Future data doesn't affect past features
3. **State Evolution**: Loss streaks update correctly
4. **Session Resets**: State resets at session boundaries
5. **Loss Streak Rules**: September 1-loss, others 2-loss

See:
- `tests/unit/backtester/test_replay_engine.py`
- `tests/unit/backtester/test_loss_streak_replay.py`

## Best Practices

1. **Always Enable Validation**: Use `enable_validation=True` for accurate backtests
2. **Record Outcomes**: Always record trade outcomes to update state
3. **Check Guardrails**: Verify `guardrail_result.allowed` before trading
4. **Respect Session Constraints**: Check `session_constraints` for season-specific rules
5. **Monitor State**: Track `behavior_state` to understand current guardrail status

## Troubleshooting

### Validation Context Missing Keys

If validation context is missing expected keys:
- Ensure `enable_validation=True`
- Check that validation config is loaded correctly
- Verify session validator is initialized

### State Not Updating

If behavior state doesn't update:
- Ensure `record_trade_outcome()` is called after each trade
- Check that validation is enabled
- Verify trade outcomes are recorded correctly

### Loss Streak Not Resetting

If loss streak doesn't reset:
- Check session reset logic (new day triggers reset)
- Verify `record_trade_outcome(won=True)` is called for wins
- Ensure session boundaries are detected correctly

