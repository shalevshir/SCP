# Trade Object Documentation

## Overview

The `Trade` dataclass represents a complete trade lifecycle from entry to exit, with SOP-compliant stop loss (SL) and take profit (TP) calculations.

## Key Features

- **Structure-based SL placement**: Never inside liquidity zones
- **SOP-compliant R-multiples**: 2R/3R based on setup type and seasonality
- **Immutable records**: Full auditability
- **JSON serialization**: Easy logging and analysis
- **PnL tracking**: Real-time and realized metrics

## Usage Examples

### Creating a Trade from Entry

```python
from backtester.trade import create_trade_from_entry
from backtester.entry_model import execute_entry_at_next_open

# 1. Execute entry
execution = execute_entry_at_next_open(signal, next_candle)

# 2. Create trade with SL/TP
trade = create_trade_from_entry(
    entry_execution=execution,
    confirmation_candle=confirmation_candle,
    bos_candle=bos_candle,  # Optional for continuation setups
    risk_config={
        "risk_per_trade": 350.0,
        "buffer_phase": "startup",
        "max_contracts": 1,
    },
    market_context={
        "month": 11,  # November (seasonality)
        "htf_aligned": True,
        "dxy_aligned": True,
    }
)

print(f"Trade ID: {trade.trade_id}")
print(f"Entry: {trade.entry_price}, SL: {trade.stop_loss}, TP: {trade.take_profit}")
print(f"R-multiple: {trade.r_multiple}R")
```

### Closing a Trade

```python
from backtester.trade import close_trade
from common.config import load_config

# Load config for dollar-based PnL calculation
config = load_config()

# Close at take profit
closed_trade = close_trade(
    trade=open_trade,
    exit_candle=exit_candle,
    exit_reason="TP",  # "TP", "SL", "TIME", "INVALIDATION"
    config=config  # Optional: enables dollar-based PnL
)

# Point-based PnL (always calculated)
print(f"PnL: {closed_trade.pnl:.2f} points ({closed_trade.r_realized:.2f}R)")

# Dollar-based PnL (if config provided)
if closed_trade.pnl_net is not None:
    print(f"Gross PnL: ${closed_trade.pnl_dollars:.2f}")
    print(f"Net PnL: ${closed_trade.pnl_net:.2f}")
    print(f"  - Slippage: ${closed_trade.slippage_cost:.2f}")
    print(f"  - Commission: ${closed_trade.commission_cost:.2f}")

print(f"Status: {closed_trade.status}")
print(f"Duration: {closed_trade.duration_bars} bars")
```

### JSON Serialization

```python
from backtester.trade import to_dict, from_dict
import json

# Serialize to JSON
trade_dict = to_dict(trade)
json_str = json.dumps(trade_dict, indent=2)

# Deserialize from JSON
reconstructed_trade = from_dict(json.loads(json_str))
```

## PnL Calculator

The `backtester.pnl_calculator` module converts point-based PnL to dollar amounts with realistic trading costs.

### Configuration

Dollar-based PnL requires configuration in `config/core.yaml`:

```yaml
assets:
  tick_values:
    GC: 10.0  # $10 per tick (0.1 point)
    ES: 12.5  # Example for other symbols
  tick_sizes:
    GC: 0.1   # Minimum price increment
    ES: 0.25

backtest:
  slippage_points: 0.5  # Slippage in points (0.5 default)
  commission_per_trade: 5.0  # Commission per contract per side
```

### PnL Components

1. **Gross PnL**: `(exit_price - entry_price) × contracts × (tick_value / tick_size)`
2. **Slippage**: `-slippage_ticks × tick_value × contracts`
3. **Commission**: `-commission_per_contract × 2 × contracts` (entry + exit)
4. **Net PnL**: `Gross PnL + Slippage + Commission`

### Example Calculation

**Winning Long Trade:**
- Entry: 2650.0, Exit: 2665.0 (15 points)
- Contracts: 1
- Gross PnL: 15 points × $10/point × 1 = **$1,500**
- Slippage: 0.5 points / 0.1 tick_size = 5 ticks × $10 = **-$50**
- Commission: $5 × 2 (entry+exit) × 1 = **-$10**
- **Net PnL: $1,440**

## SOP Rules

### Stop Loss Calculation

**Continuation Setups (VWAP_RECLAIM, DXY_CONTINUATION):**
- Long: `SL = min(confirmation_candle.low, bos_candle.low)`
- Short: `SL = max(confirmation_candle.high, bos_candle.high)`

**Fade Setups (VWAP_FADE):**
- Long: `SL = sweep_candle.low`
- Short: `SL = sweep_candle.high`

### Take Profit Calculation

**Continuation Setups:**
- Default: 3R
- September: 2R (defensive)
- November-December: 3R (trend window)

**Fade Setups:**
- Default: 2R
- Upgrade to 3R when:
  - HTF aligned AND
  - DXY aligned AND
  - November-December seasonality

**Formula:**
```python
risk_distance = |entry_price - stop_loss|
take_profit = entry_price ± (risk_distance × R_multiple)
```

### Exit Reasons

- **TP**: Take profit hit (winning trade)
- **SL**: Stop loss hit (losing trade)
- **TIME**: Max time in trade exceeded
  - Continuation: 20 bars
  - Fade: 10 bars
- **INVALIDATION**: DXY flip, structure break, VWAP invalidation, HTF bias flip

## Trade Attributes

### Core Fields

- `trade_id`: Unique UUID
- `symbol`: Asset (e.g., "GC")
- `direction`: "long" or "short"
- `entry_price`, `stop_loss`, `take_profit`: Prices
- `r_multiple`: R:R ratio (2.0, 3.0)

### Risk/Reward

- `risk_amount`: Risk in points
- `reward_amount`: Reward in points
- `contracts`: Number of contracts

### Exit & PnL

**Point-based (always calculated):**
- `exit_price`: Exit price (None if open)
- `exit_reason`: Why trade closed
- `pnl`: Realized PnL in points
- `pnl_percent`: PnL as % of risk
- `r_realized`: Actual R achieved

**Dollar-based (optional, requires config):**
- `pnl_dollars`: Gross PnL in dollars before costs
- `pnl_net`: Net PnL after slippage and commission
- `slippage_cost`: Slippage cost in dollars (negative)
- `commission_cost`: Commission cost in dollars (negative)

### Status

- `OPEN`: Trade still active
- `CLOSED_WIN`: Closed at profit
- `CLOSED_LOSS`: Closed at loss
- `STOPPED_OUT`: Hit stop loss

## Testing

The Trade module has 95.48% test coverage with 39 unit tests covering:
- SL calculation for all setups
- TP calculation with seasonality
- Trade creation and closing
- Dollar-based PnL calculation
- JSON serialization
- Edge cases and error handling

The PnL Calculator module has 100% test coverage with 27 unit tests.

Run tests:
```bash
# Test Trade module
uv run pytest tests/unit/backtester/test_trade.py -v

# Test PnL Calculator
uv run pytest tests/unit/backtester/test_pnl_calculator.py -v

# Test all backtester modules
uv run pytest tests/unit/backtester/ -v --cov=backtester
```

## Integration

The Trade object integrates with:
- `EntryExecution`: Entry details from entry model
- `Signal`: Trade signal from rule engine
- `Candle`: Market data from data layer
- Backtesting pipeline: Position tracking and PnL calculation

