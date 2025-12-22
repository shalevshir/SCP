# Backtest System - Quick Reference Guide

This is a condensed reference for the Shir Capital backtest system. For detailed documentation, see [comprehensive-backtest-system.md](./comprehensive-backtest-system.md).

---

## Quick Start

### Running a Backtest

```python
from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
from backtester.replay_loop import BacktestReplayLoop

# Load multi-timeframe data
sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
multi_tf_data = sync_layer.load(start_date, end_date)

# Configure market state
market_state = {
    "buffer_phase": "growth",
    "tier_active": "EarlyMild",
    "ceo_directive_active": True,
    "news_ok": True,
    "session_ok": True,
}

# Configure risk
risk_config = {
    "risk_per_trade": 600.0,
    "buffer_phase": "growth",
    "max_contracts": 1,
}

# Run backtest
loop = BacktestReplayLoop(
    multi_tf_data=multi_tf_data,
    timeframe="1m",
    market_state=market_state,
    risk_config=risk_config,
    htf_approach="streaming",  # or "vectorized"
)

results = loop.run()

# Analyze results
print(f"Total trades: {results.total_trades}")
print(f"Win rate: {results.win_rate:.1f}%")
print(f"Total PnL: ${results.total_pnl_dollars:.2f}")
print(f"Average R: {results.average_r:.2f}R")
```

---

## System Flow (One Candle)

```
1. Session Check → Reset state if new day
2. Update Active Trades → Check exits on current candle
3. Guardrails Check → PDLL, loss streak, session, DXY
4. Compute HTF Bias → 1H + 15M structure analysis
5. Generate Signal → Confluence scoring (0-10)
6. Execute Entry → Next bar open if score ≥ 8.0
7. Create Trade → Calculate SL/TP, track state
8. Update State → PnL, loss streak, daily counters
```

---

## Key Thresholds

| Metric | Threshold | Description |
|--------|-----------|-------------|
| **A+ Entry** | Score ≥ 8.0 | Required for trade execution |
| **HTF High Confidence** | Score ≥ 7.5 | +1.5 bonus to signal score |
| **PDLL (Default)** | -$600 | Per Day Loss Limit |
| **Loss Streak** | 2 (1 in Sept) | Max consecutive losses before halt |
| **Max Trades/Day** | 2 | Default daily trade limit |
| **Session Time** | 10:00-13:00 ILT | Trading session window |
| **+1R Time Limit** | 20 bars (cont), 10 bars (fade) | Must reach +1R or exit |
| **Timeout** | 20 bars (cont), 10 bars (fade) | Max time in trade |

---

## Guardrails

### Pre-Signal Guardrails (Block Signal Generation)

1. **PDLL Hit**: Daily loss ≤ -$600 → Stop trading
2. **Daily Trade Limit**: Max 2 trades per day → No new entries
3. **Session Time**: Outside 10:00-13:00 ILT → No trading
4. **DXY Availability**: DXY feed missing → No signals
5. **Risk Ladder**: Max contracts = 0 → No entries

### Behavior Guardrails (Block Entry)

1. **Loss Streak**: 2+ consecutive losses (1 in Sept) → Halt
2. **Fatigue Flag**: Manual operator halt → Block all trades
3. **Session Extension**: Trading beyond allowed window → Halt

### Validation Engine (Signal-Level)

1. **HTF Alignment**: Signal direction must match HTF bias
2. **DXY Structure**: Must be clean for continuation setups
3. **Risk Budget**: Daily risk allowance not exhausted
4. **News Events**: No high-impact news during trade

---

## Signal Scoring

### Factor Weights (VWAP_RECLAIM)

| Factor | Weight | Description |
|--------|--------|-------------|
| Structure | 2.5 | HH/HL (bullish) or LH/LL (bearish) |
| VWAP | 2.0 | Price relation to VWAP |
| EMA Stack | 1.5 | EMA 9 > 20 > 50 (bullish) |
| DXY | 1.0 | Inverse correlation |
| RSI | 1.0 | Momentum confirmation |
| FVG | 1.0 | Fair value gap alignment |
| Sweep | 0.5 | Liquidity sweep detected |
| **HTF Bonus** | **+1.5** | **HTF aligned & high confidence** |

**Max Score**: 10.0 (capped)  
**A+ Threshold**: ≥ 8.0

### Setup Types

| Setup | When | Default R | Seasonality |
|-------|------|-----------|-------------|
| **VWAP_RECLAIM** | Price reclaims VWAP with volume | 3R | Sept: 2R |
| **VWAP_FADE** | Extreme RSI, large VWAP deviation | 2R | Nov-Dec + HTF + DXY: 3R |
| **DXY_CONTINUATION** | Strong inverse DXY correlation | 3R | Sept: 2R |

---

## Risk Management

### Stop Loss (SL) Calculation

**Continuation (VWAP_RECLAIM, DXY_CONTINUATION):**
```python
# Long
SL = min(confirmation_candle.low, bos_candle.low)

# Short
SL = max(confirmation_candle.high, bos_candle.high)
```

**Fade (VWAP_FADE):**
```python
# Long
SL = sweep_candle.low

# Short
SL = sweep_candle.high
```

### Take Profit (TP) Calculation

```python
risk_distance = abs(entry_price - stop_loss)

# Long
TP = entry_price + (risk_distance × R_multiple)

# Short
TP = entry_price - (risk_distance × R_multiple)
```

**R-Multiple Rules:**
- Continuation: 3R (2R in September)
- Fade: 2R (upgrade to 3R with Nov-Dec + HTF + DXY alignment)

### Risk Ladder (Phase-Aware)

| Phase | Buffer | Risk/Trade | Max Loss/Day | Contracts |
|-------|--------|------------|--------------|-----------|
| Startup | $0-5K | $350 | $600 | 1 |
| Growth | $5-15K | $450-600 | $900-1K | 1-2 |
| Scaling | $15-40K | $700-1K | $1.5-2K | 2-3 |
| Institutional | $40K+ | $1.2K+ | $2.5K+ | 3-4 |

---

## Trade Exits

### Exit Priority (Checked in Order)

1. **Stop Loss** → Exit at SL price (highest priority)
2. **Take Profit** → Exit at TP price
3. **VWAP Invalidation** → Exit at candle open
4. **HTF Invalidation** → Exit at candle open
5. **DXY Flip** → Exit at candle open
6. **Session End** → Exit at candle open (13:00 ILT)
7. **Setup Window Expired** → Exit at candle open
8. **Timeout** → Exit at candle close (20/10 bars)
9. **End of Data** → Exit at last candle close

### Invalidation Rules

| Invalidation | Condition | Exit |
|--------------|-----------|------|
| **+1R Time Limit** | Not reached +1R within 20/10 bars | Candle open |
| **VWAP (Continuation)** | Close breaks VWAP against direction | Candle open |
| **VWAP (Fade)** | VWAP reclaimed | Candle open |
| **HTF Structure** | Structure breaks opposite direction | Candle open |
| **DXY Flip** | DXY correlation flips | Candle open |
| **Session End** | Time ≥ 13:00 ILT | Candle open |
| **PDLL During Trade** | Consecutive losses ≥ 2 (1 in Sept) | Candle open |

---

## HTF Bias Calculation

### Timeframes

- **1H**: Primary structure (BOS/CHoCH), FVGs, sweeps
- **15M**: Swing highs/lows, microstructure, VWAP trend

### HTF Score Components

| Component | Weight | Criteria |
|-----------|--------|----------|
| Structure | 0-3.0 | BOS (3.0), CHoCH (2.0), Swing break (1.5) |
| FVG | 0-2.0 | Fair value gap aligned (2.0) |
| Sweep | 0-2.0 | Liquidity sweep detected (2.0) |
| VWAP | 0-1.5 | Price > VWAP (bullish, 1.5) |
| DXY | 0-1.5 | Strong inverse correlation (1.5) |

**Total**: 0-10.0

### HTF Confidence

| Score Range | Confidence | Signal Bonus |
|-------------|------------|--------------|
| ≥ 7.5 | High | +1.5 |
| 5.0-7.4 | Medium | +1.0 |
| < 5.0 | Low | +0.0 |

---

## State Management

### Daily State (Resets Each Session)

```python
_daily_pnl: float = 0.0
_trades_today: int = 0
_pdll_hit: bool = False
_session_date: date | None = None
```

### Behavior State (Across Session)

```python
consecutive_losses: int = 0
fatigue_flag: bool = False
session_extended: bool = False
```

### Trade State (Per Trade)

```python
reached_1r: bool = False
vwap_reclaimed: bool = False
window_active: bool = True
```

---

## Performance Metrics

### BacktestResults

```python
total_trades: int          # Number of closed trades
win_rate: float            # Percentage (0-100)
total_pnl: float           # Total PnL in points
total_pnl_dollars: float   # Total PnL in dollars
average_r: float           # Average R achieved
max_consecutive_losses: int
pdll_hits: int             # Times PDLL was hit
session_resets: int        # Number of session resets
```

### Per-Trade Metrics

```python
pnl: float                 # PnL in points
pnl_dollars: float         # Gross PnL in dollars
pnl_net: float             # Net PnL after costs
slippage_cost: float       # Slippage cost
commission_cost: float     # Commission cost
r_realized: float          # Actual R achieved (e.g., 2.5R)
duration_bars: int         # Trade duration in candles
exit_reason: str           # "tp", "sl", "timeout", etc.
```

---

## Common Patterns

### Accessing Trade Details

```python
for trade in results.trades:
    if trade.status == "CLOSED_WIN":
        print(f"Trade {trade.trade_id}: +{trade.pnl:.2f} points ({trade.r_realized:.2f}R)")
    else:
        print(f"Trade {trade.trade_id}: {trade.exit_reason}")
```

### Filtering Signals by Confidence

```python
a_plus_signals = [e for e in results.executions if e.signal.confidence == "A+"]
executed = [e for e in a_plus_signals if e.executed]
rejected = [e for e in a_plus_signals if not e.executed]

print(f"A+ signals: {len(a_plus_signals)}, Executed: {len(executed)}, Rejected: {len(rejected)}")
```

### Analyzing Exit Reasons

```python
from collections import Counter

exit_reasons = [t.exit_reason for t in results.trades]
reason_counts = Counter(exit_reasons)

print("Exit Reason Distribution:")
for reason, count in reason_counts.most_common():
    print(f"  {reason}: {count}")
```

---

## Module Reference

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `backtester/replay_loop.py` | Main backtest orchestrator | `BacktestReplayLoop`, `BacktestResults` |
| `backtester/simulator.py` | Trade outcome simulation | `simulate_trade_outcome()` |
| `backtester/trade.py` | Trade lifecycle management | `Trade`, `create_trade_from_entry()`, `close_trade()` |
| `backtester/invalidations.py` | Invalidation detection | `InvalidationChecker` |
| `backtester/entry_model.py` | Entry execution | `execute_entry_at_next_open()` |
| `backtester/pnl_calculator.py` | Dollar PnL calculation | `calculate_net_pnl()` |
| `feature_engine/backtesting.py` | Incremental feature computation | `BacktestProcessor` |
| `rule_engine/scoring.py` | Signal scoring | `score_signal()` |
| `rule_engine/htf/streaming.py` | Streaming HTF bias | `StreamingHTFBiasCalculator` |
| `rule_engine/htf/calculator.py` | Vectorized HTF bias | `compute_htf_bias_multi_timeframe()` |
| `validation/engine.py` | SOP validation | `ValidationEngine` |
| `validation/guardrails.py` | Behavior guardrails | `BehaviorGuardrails` |

---

## Troubleshooting

### Common Issues

**Issue**: "No signals generated"
- **Check**: Guardrails blocking (PDLL hit, loss streak, session time)
- **Solution**: Review logs for blocking reasons, adjust market_state

**Issue**: "A+ signals but no entries executed"
- **Check**: Next candle availability (end of data)
- **Solution**: Ensure dataset has enough future candles

**Issue**: "All trades hitting SL immediately"
- **Check**: SL calculation, structure candles provided
- **Solution**: Verify confirmation_candle and bos_candle are correct

**Issue**: "HTF bias always neutral"
- **Check**: HTF data availability (1H/15M resampling)
- **Solution**: Ensure MultiTimeframeData has 1H and 15M data

**Issue**: "PDLL hit too frequently"
- **Check**: Risk per trade too high for buffer phase
- **Solution**: Adjust risk_config to match SOP Risk Ladder

---

## Best Practices

1. **Always use MultiTimeframeData**: Ensures HTF bias calculation works
2. **Match risk_config to buffer phase**: Follow Risk Ladder SOP
3. **Enable signal logging for debugging**: `log_signals=True, log_dir="output/signals"`
4. **Check guardrails before blaming scoring**: Most rejections are guardrail-based
5. **Validate results against CEO directives**: Win rate, R:R, PDLL compliance
6. **Use streaming HTF for realistic simulation**: Mimics live trading behavior
7. **Always provide config for dollar PnL**: Enables realistic cost accounting

---

**For detailed explanations and code examples, see [comprehensive-backtest-system.md](./comprehensive-backtest-system.md).**









