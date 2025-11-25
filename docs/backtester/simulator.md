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
    future_features=features_df,  # Optional: Features for invalidation checks
)

print(f"Exit reason: {closed_trade.exit_reason}")
print(f"PnL: {closed_trade.pnl:.2f} points ({closed_trade.r_realized:.2f}R)")
```

**Exit Priority (checked in order per SOP):**
1. **Stop Loss** → exit at SL price (highest priority)
2. **Take Profit** → exit at TP price
3. **VWAP Invalidation** → exit at candle open (for VWAP_RECLAIM and VWAP_FADE)
4. **HTF Structure Invalidation** → exit at candle open (structure breaks against trade)
5. **DXY Flip** → exit at candle open (DXY structure flips opposite)
6. **Session End** → exit at candle open (13:00 ILT default)
7. **Setup Window Expiration** → exit at candle open (window closes)
8. **Timeout** (max bars reached) → exit at candle close (last resort)
9. **End of data** → exit at last candle close

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

**VWAP Invalidation:**
- Applies to: VWAP_RECLAIM and VWAP_FADE setups
- Long: Invalid if `close < VWAP`
- Short: Invalid if `close > VWAP`
- Requires VWAP value in features dictionary

**HTF Structure Invalidation:**
- Detects structure breaks against trade direction
- Long: Invalid if structure breaks bearish (LH, LL)
- Short: Invalid if structure breaks bullish (HH, HL)
- Uses entry HTF bias as baseline

**DXY Flip:**
- Detects DXY correlation/structure flips opposite to trade
- Long: Invalid if DXY correlation flips positive (> -0.3)
- Short: Invalid if DXY correlation becomes very negative (< -0.6)
- Requires DXY correlation in features dictionary

**Session End:**
- Force exit at session end (13:00 ILT default, configurable)
- Executes before timeout
- Handles timezone-aware and naive timestamps

**Setup Window Expiration:**
- VWAP_FADE: Window expires when VWAP is reclaimed
- VWAP_RECLAIM: Window remains active after reclaim
- DXY_CONTINUATION: Window remains active during continuation

**Daily Risk Stop:**
- Loss streak: 2 consecutive losses (1 in September)
- PDLL/PDRR breach: Force exit if daily risk limit reached

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
| `sl` | Stop loss hit (losing trade) |
| `tp` | Take profit hit (winning trade) |
| `vwap_invalidation` | VWAP structure lost (close < VWAP for long, close > VWAP for short) |
| `htf_invalidation` | HTF structure breaks against trade direction |
| `dxy_flip` | DXY structure/correlation flips opposite to trade |
| `session_close` | Session ended (13:00 ILT default) |
| `window_expired` | Setup-specific execution window expired |
| `daily_risk_stop` | Daily risk limit breached (loss streak or PDLL/PDRR) |
| `timeout` | Max time in trade exceeded (20 bars continuation, 10 bars fade) |
| `end_of_data` | Reached end of dataset while trade still open |
| `invalid_setup` | Trade had invalid setup (zero risk, NaN values) |

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
✓ VWAP invalidation for continuation/fade setups
✓ HTF structure invalidation detection
✓ DXY flip detection
✓ Session end enforcement (13:00 ILT)
✓ Setup window expiration tracking
✓ Daily risk stop (loss streak, PDLL/PDRR)
✓ Structure-based SL placement
✓ R-multiple based TP calculation

## Testing

The simulator has comprehensive test coverage with 139 unit tests covering:

- TP/SL hit detection for long and short trades
- Timeout logic for continuation and fade setups
- SL priority rule enforcement
- Gap handling (beyond SL and TP)
- End of data handling
- Invalidation detection (+1R time limit, VWAP, HTF, DXY, Session, Window, Daily Risk)
- Edge cases (NaN, zero risk, closed trades)
- Feature integration and priority ordering

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

## Implementation Status

All SOP exit conditions are now implemented:

✓ VWAP invalidation detection
✓ HTF structure invalidation detection
✓ DXY flip detection
✓ Session end enforcement
✓ Setup window expiration tracking
✓ Daily risk stop (loss streak, PDLL/PDRR)
✓ Proper exit priority ordering per SOP

**Future Enhancements:**
- News event exit (deferred per plan)
- Enhanced HTF structure detection with full BOS/CHoCH tracking
- Enhanced DXY structure detection with full BOS/CHoCH tracking

## Related Modules

- `backtester/trade.py` - Trade object and SL/TP calculation
- `backtester/entry_model.py` - Entry execution at next bar open
- `backtester/pnl_calculator.py` - Dollar-based PnL calculation
- `backtester/pipeline.py` - Complete backtesting orchestration

