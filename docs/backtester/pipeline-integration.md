# Backtesting Pipeline Integration

## Overview

The backtesting pipeline integrates all components of the Shir Capital trading system into a unified execution flow. It orchestrates feature generation, HTF bias computation, signal scoring, validation, and entry execution to produce a complete backtest with realistic entry timing.

## Architecture

The pipeline follows a strict sequential flow to prevent look-ahead bias:

1. **Feature Generation** (`BacktestProcessor`)
   - Computes all technical indicators vectorized (VWAP, RSI, EMA, DXY correlation)
   - Provides bar-by-bar iteration with next candle preview for entry execution
   - Maintains session state for validation

2. **HTF Bias Computation** (User-provided function)
   - Analyzes higher timeframe structure (1H, 15M)
   - Returns structured `HTFBias` with confidence scoring
   - Integrates VWAP trend, seasonality, DXY alignment

3. **Signal Scoring** (`RuleEngine`)
   - Scores signals based on SOP rules (structure, VWAP relation, DXY alignment)
   - Produces scores 0-10 with confidence levels (A+, A, B, C, D, Reject, Watch)

4. **Signal Validation** (`ValidationEngine`)
   - Enforces session windows, enforcer tiers, guardrails
   - Rejects signals that violate SOP constraints
   - Logs rejection reasons for auditability

5. **Entry Execution** (`EntryModel`)
   - Executes entries at next bar open (realistic timing)
   - Only A+ signals with next_candle available are executed
   - Returns `EntryExecution` for all signals (including rejected)

## Key Components

### BacktestProcessor.iterate_with_entry_context()

**Purpose**: Yields features, validation context, and next candle for entry execution.

**No Look-Ahead Bias**: The `next_candle` is provided to support entry execution but is NOT available during feature calculation or signal scoring. Features are computed using only data up to the current timestamp.

**Usage**:
```python
from feature_engine.backtesting import BacktestProcessor

processor = BacktestProcessor(timeframe="1m")

for features, validation_context, next_candle in processor.iterate_with_entry_context(
    gc_df, dxy_df
):
    # features: Current bar features (pd.Series)
    # validation_context: Session/guardrail state (dict)
    # next_candle: Next bar's Candle object or None (end of dataset)
    
    # Signal generation uses features (current bar)
    signal = generate_signal(features)
    
    # Entry execution uses next_candle (realistic timing)
    entry = execute_entry_at_next_open(signal, next_candle)
```

**Returns**:
- `features`: pd.Series with timestamp, OHLCV, indicators, structure labels
- `validation_context`: dict with session_constraints, guardrail_result, behavior_state
- `next_candle`: Candle object with next bar's OHLCV data (or None if last bar)

### run_backtest_with_entries()

**Purpose**: Complete pipeline orchestration from features to entry executions.

**Signature**:
```python
def run_backtest_with_entries(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    market_state: dict,
    htf_bias_func: Callable[[pd.Series, dict], HTFBias],
    log_signals: bool = False,
    log_dir: str | None = None,
) -> list[EntryExecution]:
```

**Parameters**:
- `gc_df`: GC DataFrame with DatetimeIndex and OHLCV columns
- `dxy_df`: DXY DataFrame with DatetimeIndex and OHLCV columns
- `timeframe`: Timeframe string (e.g., "1m", "15m", "1h")
- `market_state`: Market context dict with:
  - `buffer_phase`: Capital phase ("startup", "growth", "scaling", "institutional")
  - `tier_active`: Enforcer tier ("Conservative", "EarlyMild", "Mild", "Offensive")
  - `ceo_directive_active`: Whether CEO directive is active (bool)
  - `news_ok`: Whether trading is allowed during news events (bool)
  - `session_ok`: Whether current session is valid for trading (bool)
- `htf_bias_func`: Function that computes HTFBias given (features, context)
- `log_signals`: Whether to log signals to disk (default: False)
- `log_dir`: Directory for signal logs (required if log_signals=True)

**Returns**:
- List of `EntryExecution` objects, one per signal generated
- Includes both executed entries (`executed=True`) and rejected entries (`executed=False`)

## Complete Example

```python
from datetime import datetime, timedelta
from backtester.pipeline import run_backtest_with_entries
from rule_engine.htf.integration import compute_htf_bias
import pandas as pd

# Load data
gc_df = pd.read_csv("data/GC_1m_2025.csv", index_col="timestamp", parse_dates=True)
dxy_df = pd.read_csv("data/DXY_1m_2025.csv", index_col="timestamp", parse_dates=True)

# Define market state
market_state = {
    "buffer_phase": "growth",           # 5-15K buffer
    "tier_active": "EarlyMild",         # Active enforcer tier
    "ceo_directive_active": True,       # CEO directive active
    "news_ok": True,                    # No news restrictions
    "session_ok": True,                 # Within valid session
}

# Define HTF bias function
def htf_bias_function(features, context):
    """Compute HTF bias using 1H and 15M data."""
    return compute_htf_bias(
        gc_1h=features.get("gc_1h"),
        gc_15m=features.get("gc_15m"),
        current_price=features["close"],
        timestamp=features["timestamp"],
    )

# Run complete backtest
executions = run_backtest_with_entries(
    gc_df=gc_df,
    dxy_df=dxy_df,
    timeframe="1m",
    market_state=market_state,
    htf_bias_func=htf_bias_function,
    log_signals=True,
    log_dir="logs/backtest_2025",
)

# Analyze results
executed = [e for e in executions if e.executed]
rejected = [e for e in executions if not e.executed]

print(f"Total signals: {len(executions)}")
print(f"Executed entries: {len(executed)} ({100*len(executed)/len(executions):.1f}%)")
print(f"Rejected entries: {len(rejected)} ({100*len(rejected)/len(executions):.1f}%)")

# Entry price distribution
entry_prices = [e.entry_price for e in executed]
print(f"Entry prices: min={min(entry_prices):.2f}, max={max(entry_prices):.2f}")

# Rejection reasons
rejection_reasons = {}
for e in rejected:
    reason = e.rejection_reason
    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

print("\nRejection reasons:")
for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
    print(f"  {reason}: {count}")
```

## Integration with Rule Engine

The pipeline uses `process_features_with_validation()` from `feature_engine.integration` to score and validate signals. This function:

1. Scores signal using `RuleEngine.score_signal()`
2. Validates signal using `ValidationEngine.validate_signal()`
3. Returns structured `Signal` object with confidence and rationale

The HTF bias function must return a valid `HTFBias` object:

```python
from rule_engine.htf.types import HTFBias

def example_htf_bias_func(features, context):
    """Example HTF bias computation."""
    return HTFBias(
        bias="bullish",                 # "bullish", "bearish", "neutral"
        direction="long",                # "long", "short", "neutral"
        score=8.5,                       # 0-10 confidence score
        confidence="high",               # "high", "medium", "low"
        vwap_trend_confirmed=True,      # VWAP trend aligned with bias
        seasonality_adjustment=0.5,     # Seasonality score modifier
        structure_1h="HH",              # 1H structure label
        structure_15m="HL",             # 15M structure label
        dxy_alignment=True,             # DXY aligned with bias
        # ... other HTF fields (all have defaults)
    )
```

## Entry Execution Behavior

The `EntryModel` executes entries with strict timing rules:

**Executed Entry** (A+ signal, next candle available):
```python
EntryExecution(
    signal_timestamp=datetime(2025, 1, 1, 10, 0),  # Signal generated at 10:00
    entry_timestamp=datetime(2025, 1, 1, 10, 1),   # Entry executed at 10:01
    entry_price=2650.0,                             # Entry at next bar open
    signal=signal,                                  # Original signal object
    executed=True,
    rejection_reason=None,
)
```

**Rejected Entry** (No next candle):
```python
EntryExecution(
    signal_timestamp=datetime(2025, 1, 1, 12, 59),  # Signal at last bar
    entry_timestamp=datetime(2025, 1, 1, 12, 59),   # Same timestamp
    entry_price=0.0,                                 # No entry price
    signal=signal,
    executed=False,
    rejection_reason="No next candle available (end of dataset)",
)
```

**Rejected Entry** (Low confidence):
```python
EntryExecution(
    signal_timestamp=datetime(2025, 1, 1, 10, 0),
    entry_timestamp=datetime(2025, 1, 1, 10, 0),   # Same timestamp
    entry_price=0.0,
    signal=signal,
    executed=False,
    rejection_reason="Signal confidence Reject not tradeable",
)
```

## Testing

Comprehensive integration tests are in `tests/unit/backtester/test_pipeline_integration.py`:

- **BacktestProcessor.iterate_with_entry_context()**: 5 tests
  - Yields correct tuple structure
  - Next candle has correct timestamp
  - Next candle is None at dataset end
  - Next candle contains only OHLCV (no derived features)
  - No look-ahead bias in next_candle

- **run_backtest_with_entries()**: 5 tests
  - Returns list of EntryExecution objects
  - Only executes A+ confidence signals
  - Entry timestamp always after signal timestamp
  - Handles end of dataset gracefully
  - Entry prices are deterministic

Run tests:
```bash
uv run pytest tests/unit/backtester/test_pipeline_integration.py -v
```

## Trade Simulation (NEW)

The pipeline now supports complete trade lifecycle simulation with the `run_backtest_with_trades()` function:

```python
from backtester.pipeline import run_backtest_with_trades

# Run complete backtest with trade outcomes
trades = run_backtest_with_trades(
    gc_df=gc_df,
    dxy_df=dxy_df,
    timeframe="1m",
    market_state=market_state,
    htf_bias_func=htf_bias_function,
    risk_config={
        "risk_per_trade": 350.0,
        "buffer_phase": "startup",
        "max_contracts": 1,
    },
    config=config,  # For dollar PnL calculation
)

# All trades are closed with outcomes
for trade in trades:
    print(f"Trade {trade.trade_id}: {trade.exit_reason}")
    print(f"  PnL: {trade.pnl:.2f} points ({trade.r_realized:.2f}R)")
    if trade.pnl_net:
        print(f"  Net: ${trade.pnl_net:.2f}")
```

**Features:**
- ✓ Structure-based SL placement
- ✓ R-multiple TP targets (2R/3R based on setup and seasonality)
- ✓ Invalidation detection (+1R time limit)
- ✓ Timeout logic (20 bars continuation, 10 bars fade)
- ✓ Gap handling (exit at limit, never worse)
- ✓ SL priority over TP (per SOP)
- ✓ Dollar-based PnL with slippage and commission

See [Trade Simulator Documentation](./simulator.md) for details.

## Next Steps

Remaining components to implement:

1. **Advanced Trade Management**
   - Trailing SL after +1R
   - Partial profit taking
   - Dynamic risk ladder adjustments

2. **Performance Metrics Dashboard**
   - Win rate, R:R ratio
   - Max drawdown, Sharpe ratio
   - SOP adherence percentage
   - Equity curve visualization

3. **Multi-Session Backtesting**
   - Cumulative PnL tracking across sessions
   - Session-level guardrails (2-loss halt)
   - Buffer phase progression

4. **LLM Enforcer Integration**
   - Pre-trade validation with GPT
   - Post-trade analysis and journaling
   - SOP drift detection

## References

- [Next Bar Open Entry Model](./next-bar-open-entry.md)
- [Backtesting Framework](../feature-engine/backtesting.md)
- [HTF Integration](../rule-engine/htf-integration.md)
- [Validation Engine](../validation-layer.md)

