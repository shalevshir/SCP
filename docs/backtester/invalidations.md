# Trade Invalidation Checker Documentation

## Overview

The `InvalidationChecker` class detects early exit conditions for trades, following Shir Capital SOP requirements. It tracks trade state across candles and checks for various invalidation conditions that should force an immediate exit.

## Key Features

- **Stateful tracking**: Maintains trade-specific state (e.g., +1R achievement, VWAP reclaim status)
- **Multiple invalidation types**: VWAP, HTF structure, DXY flip, session end, window expiration, daily risk
- **Setup-specific logic**: Different rules apply to different setup types
- **Priority-based checking**: Checks are performed in SOP-compliant priority order

## Core Class

### `InvalidationChecker`

Main class that tracks trade state and checks for invalidation conditions.

```python
from backtester.invalidations import InvalidationChecker

checker = InvalidationChecker()

# For each candle during simulation:
for candle in candles:
    features = get_features_for_candle(candle)
    is_invalid, reason = checker.check_all(
        trade=trade,
        candle=candle,
        bars_elapsed=bars_elapsed,
        features=features
    )
    if is_invalid:
        break  # Exit trade
```

## Invalidation Types

### 1. +1R Time Limit

**Method**: `check_no_1r_reached()`

**Rules:**
- Continuation setups (VWAP_RECLAIM, DXY_CONTINUATION): Must reach +1R within 20 bars
- Fade setups (VWAP_FADE): Must reach +1R within 10 bars

**State Tracking:**
- Tracks whether +1R price level was reached during trade
- Only checks at the time limit (not continuously)

**Example:**
```python
# Trade enters at 2650, risk = 5 points
# +1R target = 2655 (for long)
# If candle high never reaches 2655 within 20 bars → invalid
```

### 2. VWAP Invalidation

**Method**: `check_vwap_invalidation()`

**Rules:**
- Applies to: VWAP_RECLAIM and VWAP_FADE setups only
- Long: Invalid if `candle.close < vwap`
- Short: Invalid if `candle.close > vwap`

**Requirements:**
- VWAP value must be in features dictionary
- Only checked for VWAP-based setups

**Example:**
```python
features = {"vwap": 2650.0}
# Long trade, candle closes at 2648 → invalid
# Short trade, candle closes at 2652 → invalid
```

### 3. HTF Structure Invalidation

**Method**: `check_htf_structure_invalidation()`

**Rules:**
- Detects structure breaks against trade direction
- Long: Invalid if structure breaks bearish (LH, LL structure labels)
- Short: Invalid if structure breaks bullish (HH, HL structure labels)
- Uses entry HTF bias as baseline for comparison

**Requirements:**
- Structure label in features dictionary
- Entry HTF bias from trade signal

**Example:**
```python
# Long trade with bullish HTF bias
# Structure label changes to "LH" → invalid (bearish break)
```

### 4. DXY Flip

**Method**: `check_dxy_flip()`

**Rules:**
- Detects DXY correlation/structure flips opposite to trade
- Long: Invalid if DXY correlation > -0.3 (flips positive)
- Short: Invalid if DXY correlation < -0.6 (very negative)

**Requirements:**
- DXY correlation value in features dictionary

**Example:**
```python
features = {"dxy_corr": -0.2}
# Long trade → invalid (correlation flipped positive)
```

### 5. Session End

**Method**: `check_session_end()`

**Rules:**
- Force exit at session end (13:00 ILT default, configurable)
- Executes before timeout
- Handles both timezone-aware and naive timestamps

**Example:**
```python
# Candle timestamp = 13:00 ILT → invalid
# Trade must exit immediately
```

### 6. Setup Window Expiration

**Method**: `check_setup_window_expired()`

**Rules:**
- **VWAP_FADE**: Window expires when VWAP is reclaimed
  - Tracks VWAP reclaim status in state
  - Window closes when price closes above/below VWAP
- **VWAP_RECLAIM**: Window remains active after reclaim
- **DXY_CONTINUATION**: Window remains active during continuation

**State Tracking:**
- Tracks `vwap_reclaimed` status per trade
- Updates on each candle if VWAP is reclaimed

**Example:**
```python
# VWAP_FADE long trade
# Price closes above VWAP → vwap_reclaimed = True
# Next candle → window expired, exit trade
```

### 7. Daily Risk Stop

**Method**: `check_daily_risk_breach()`

**Rules:**
- **Loss Streak**: 
  - September: 1 consecutive loss max
  - Other months: 2 consecutive losses max
- **PDLL/PDRR**: Force exit if daily risk limit reached

**State Tracking:**
- Tracks `consecutive_losses` per day
- Tracks `daily_pnl` per day
- Resets at session start

**Usage:**
```python
# After trade closes:
checker.record_trade_outcome(trade, won=False)
# Updates consecutive_losses counter
```

## Priority Order

Invalidation checks are performed in this order (per SOP):

1. +1R not reached within time limits
2. VWAP invalidation
3. HTF structure invalidation
4. DXY flip
5. Session end
6. Setup window expiration
7. Daily risk stop

**Note**: These checks happen AFTER SL/TP checks in the simulator (SL and TP have highest priority).

## State Management

### Trade State

Each trade has its own state dictionary:

```python
{
    "reached_1r": False,        # Whether +1R was reached
    "vwap_reclaimed": False,    # Whether VWAP was reclaimed (for fades)
    "window_active": True,      # Whether setup window is active
}
```

### Daily State

Global daily state tracking:

```python
{
    "consecutive_losses": 0,    # Loss streak count
    "daily_pnl": 0.0,           # Total PnL for the day
    "last_session_date": None,  # Last session date (for reset)
}
```

## Usage Examples

### Basic Usage

```python
from backtester.invalidations import InvalidationChecker

checker = InvalidationChecker()

# During simulation:
for bars_elapsed, candle in enumerate(future_candles, start=1):
    # Get features for this candle
    features = future_features.loc[candle.timestamp].to_dict()
    
    # Check all invalidation conditions
    is_invalid, reason = checker.check_all(
        trade=trade,
        candle=candle,
        bars_elapsed=bars_elapsed,
        features=features
    )
    
    if is_invalid:
        print(f"Trade invalidated: {reason}")
        break
```

### Recording Trade Outcomes

```python
# After trade closes:
checker.record_trade_outcome(trade, won=(trade.pnl > 0))

# This updates:
# - consecutive_losses counter
# - daily_pnl total
# - Resets on new session
```

### Resetting State

```python
# Reset specific trade state
checker.reset_trade(trade_id)

# Clear all state
checker.clear_all()
```

## Integration with Simulator

The `InvalidationChecker` is integrated into `simulate_trade_outcome()`:

```python
from backtester.simulator import simulate_trade_outcome
from backtester.invalidations import InvalidationChecker

checker = InvalidationChecker()

closed_trade = simulate_trade_outcome(
    trade=trade,
    future_candles=future_candles,
    invalidation_checker=checker,
    future_features=future_features,  # Required for feature-based checks
    config=config,
)
```

The simulator automatically:
1. Extracts features per candle
2. Passes features to `check_all()`
3. Maps invalidation reasons to exit codes
4. Exits at appropriate priority

## Exit Reason Mapping

Invalidation reasons are mapped to exit codes:

| Reason Contains | Exit Code |
|----------------|-----------|
| "vwap" | `vwap_invalidation` |
| "htf" or "structure" | `htf_invalidation` |
| "dxy" | `dxy_flip` |
| "session" | `session_close` |
| "window" | `window_expired` |
| "daily" or "risk" | `daily_risk_stop` |
| Other | `invalidation` (default) |

## Testing

Comprehensive unit tests cover all invalidation types:

```bash
# Run invalidation tests
uv run pytest tests/unit/backtester/test_invalidations.py -v

# Test specific invalidation type
uv run pytest tests/unit/backtester/test_invalidations.py::TestVWAPInvalidation -v
```

## Related Modules

- `backtester/simulator.py` - Trade outcome simulation
- `backtester/pipeline.py` - Feature generation and passing
- `backtester/trade.py` - Trade object and exit handling
- `feature_engine/backtesting.py` - Feature computation

