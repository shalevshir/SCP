# Trade Simulator Documentation

## Overview

The Trade Simulator determines trade outcomes by processing future candles to detect which exit condition is met first: Take Profit (TP), Stop Loss (SL), Timeout, or Invalidation.

## Key Features

- **Realistic intra-candle order-of-operations**: SL takes priority over TP within same candle per SOP
- **Gap handling**: Exits at limit price (SL/TP), never worse than specified levels
- **Setup-specific timeout logic**: 20 bars for continuation, 10 bars for fade
- **Invalidation detection**: +1R must be reached within time limits
- **Edge case handling**: Validates trades and skips invalid candles (NaN/Inf)

## Core Functions

### `simulate_trade_outcome()`

Main function that simulates complete trade lifecycle from entry to exit.

```python
from backtester.simulator import simulate_trade_outcome
from backtester.invalidations import InvalidationChecker

# Create invalidation checker (optional)
checker = InvalidationChecker()

# Simulate trade
closed_trade = simulate_trade_outcome(
    trade=open_trade,
    future_candles=future_candles_df,  # DataFrame with DatetimeIndex
    invalidation_checker=checker,  # Optional
    config=config,  # Optional for dollar PnL
)

print(f"Exit reason: {closed_trade.exit_reason}")
print(f"PnL: {closed_trade.pnl:.2f} points ({closed_trade.r_realized:.2f}R)")
```

**Exit Priority (checked in order):**
1. **Invalidation** (if checker provided) → exit at candle open
2. **Stop Loss** → exit at SL price
3. **Take Profit** → exit at TP price
4. **Timeout** (max bars reached) → exit at candle close
5. **End of data** → exit at last candle close

### `check_tp_hit(trade, candle)`

Checks if take profit is hit within a candle.

```python
from backtester.simulator import check_tp_hit

if check_tp_hit(trade, candle):
    print("TP reached!")
```

**Logic:**
- Long: `candle.high >= trade.take_profit`
- Short: `candle.low <= trade.take_profit`

### `check_sl_hit(trade, candle)`

Checks if stop loss is hit within a candle.

```python
from backtester.simulator import check_sl_hit

if check_sl_hit(trade, candle):
    print("SL hit!")
```

**Logic:**
- Long: `candle.low <= trade.stop_loss`
- Short: `candle.high >= trade.stop_loss`

### `check_timeout(bars_elapsed, setup_type)`

Checks if maximum time in trade is exceeded.

```python
from backtester.simulator import check_timeout

if check_timeout(bars_elapsed=20, setup_type="VWAP_RECLAIM"):
    print("Trade timed out!")
```

**SOP Rules:**
- Continuation (VWAP_RECLAIM, DXY_CONTINUATION): 20 bars
- Fade (VWAP_FADE): 10 bars

## InvalidationChecker

Tracks trade state to detect invalidation conditions.

### Usage Example

```python
from backtester.invalidations import InvalidationChecker

checker = InvalidationChecker()

# For each candle in simulation:
for bars_elapsed, candle in enumerate(candles, start=1):
    # Update state (tracks +1R achievement)
    checker.update_state(trade, candle)
    
    # Check all invalidation conditions
    is_invalid, reason = checker.check_all(trade, candle, bars_elapsed)
    
    if is_invalid:
        print(f"Trade invalidated: {reason}")
        break
```

### Invalidation Rules

**+1R Time Limit:**
- Continuation: Must reach +1R within 20 bars
- Fade: Must reach +1R within 10 bars

**Future Invalidations (not yet implemented):**
- DXY flip
- VWAP invalidation (continuation trades)
- Structure break (microstructure)
- HTF bias flip
- Session end (13:00 ILT)

## Pipeline Integration

The simulator integrates seamlessly with the backtesting pipeline.

### Complete Backtest with Trades

```python
from backtester.pipeline import run_backtest_with_trades

# Define HTF bias function
def compute_htf_bias(features, context):
    # Your HTF calculation logic
    return HTFBias(...)

# Run complete backtest
trades = run_backtest_with_trades(
    gc_df=gc_data,
    dxy_df=dxy_data,
    timeframe="1m",
    market_state={
        "buffer_phase": "startup",
        "tier_active": "EarlyMild",
        "ceo_directive_active": True,
        "news_ok": True,
        "session_ok": True,
    },
    htf_bias_func=compute_htf_bias,
    risk_config={
        "risk_per_trade": 350.0,
        "buffer_phase": "startup",
        "max_contracts": 1,
    },
    config=config,  # For dollar PnL calculation
)

# Analyze results
winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
win_rate = len(winning_trades) / len(trades) * 100 if trades else 0

print(f"Total trades: {len(trades)}")
print(f"Win rate: {win_rate:.1f}%")
print(f"Average R: {sum(t.r_realized for t in trades) / len(trades):.2f}R")
```

### Entry-Only Backtest

For just entries without trade simulation:

```python
from backtester.pipeline import run_backtest_with_entries

executions = run_backtest_with_entries(
    gc_df=gc_data,
    dxy_df=dxy_data,
    timeframe="1m",
    market_state=market_state,
    htf_bias_func=compute_htf_bias,
)

executed = [e for e in executions if e.executed]
print(f"Executed entries: {len(executed)}/{len(executions)}")
```

## Exit Reasons

| Reason | Description |
|--------|-------------|
| `TP` | Take profit hit (winning trade) |
| `SL` | Stop loss hit (losing trade) |
| `TIME` | Max time in trade exceeded (20 bars continuation, 10 bars fade) |
| `INVALIDATION` | Trade invalidated (e.g., +1R not reached within time limit) |
| `END_OF_DATA` | Reached end of dataset while trade still open |
| `INVALID_SETUP` | Trade had invalid setup (zero risk, NaN values) |

## Edge Cases

### Gap Handling

**Gap beyond SL:**
- Long: Candle opens below SL → Exit at SL price (not worse)
- Short: Candle opens above SL → Exit at SL price (not worse)

**Gap beyond TP:**
- Long: Candle opens above TP → Exit at TP price
- Short: Candle opens below TP → Exit at TP price

```python
# Example: Gap down beyond SL on long trade
# Entry: 2650, SL: 2645, TP: 2665
# Next candle opens at 2640 (gap down)
# Exit: 2645 (SL price, not 2640)
```

### Invalid Candles

Candles with NaN or Inf values are automatically skipped:

```python
# Candle with NaN high is skipped
# Warning logged: "Skipping candle with NaN/Inf values..."
```

### Zero Risk Distance

Trades with zero risk (entry == SL) are immediately closed:

```python
# Entry: 2650, SL: 2650 → Invalid
# Exit reason: "INVALID_SETUP"
```

### SL Priority Rule

When both SL and TP hit in same candle, SL takes priority per SOP:

```python
# Long: Entry 2650, SL 2645, TP 2665
# Candle: low=2644 (hits SL), high=2666 (hits TP)
# Result: Exit at SL (2645), not TP
```

## SOP Compliance

The simulator follows all Shir Capital SOP rules:

✓ SL takes priority over TP within same candle
✓ Gaps handled realistically (exit at limit, not worse)
✓ Timeout: 20 bars continuation, 10 bars fade
✓ +1R must be reached within time limits
✓ Structure-based SL placement
✓ R-multiple based TP calculation

## Testing

The simulator has 100% test coverage with 29 unit tests covering:

- TP/SL hit detection for long and short trades
- Timeout logic for continuation and fade setups
- SL priority rule enforcement
- Gap handling (beyond SL and TP)
- End of data handling
- Invalidation detection (+1R time limit)
- Edge cases (NaN, zero risk, closed trades)

Run tests:

```bash
# Test simulator
uv run pytest tests/unit/backtester/test_simulator.py -v

# Test invalidation checker
uv run pytest tests/unit/backtester/test_invalidations.py -v

# Test pipeline integration
uv run pytest tests/unit/backtester/test_pipeline_with_trades.py -v

# All backtester tests
uv run pytest tests/unit/backtester/ -v
```

## Performance Considerations

- **Vectorization**: Candle checks use simple comparisons (O(1) per candle)
- **Memory**: InvalidationChecker stores minimal state per trade
- **Scalability**: Can simulate thousands of trades efficiently

## Future Enhancements

The simulator is designed to be extensible. Future invalidation checks can be added:

```python
# In InvalidationChecker.check_all():
# - check_dxy_flip(features)
# - check_vwap_invalidation(features)
# - check_structure_break(features)
# - check_htf_flip(features)
# - check_session_end(candle.timestamp)
```

## Related Modules

- `backtester/trade.py` - Trade object and SL/TP calculation
- `backtester/entry_model.py` - Entry execution at next bar open
- `backtester/pnl_calculator.py` - Dollar-based PnL calculation
- `backtester/pipeline.py` - Complete backtesting orchestration

