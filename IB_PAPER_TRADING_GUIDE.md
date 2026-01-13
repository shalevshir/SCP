# Interactive Brokers Paper Trading Integration Guide

## Overview

The Execution service now supports **three broker modes**:
1. **`paper`** - In-memory simulation (no real broker connection)
2. **`ib_paper`** - Interactive Brokers paper trading account (realistic execution)
3. **`live`** - Live trading (not yet implemented)

This guide covers setting up and using IB paper trading mode.

## Architecture

```
┌─────────────────┐
│ TradeManager    │
└────────┬────────┘
         │ place_order()
         ▼
┌─────────────────┐
│ IBPaperBroker   │  ◄─── Internal tracking (source of truth)
└────────┬────────┘
         │ IBClient wrapper
         ▼
┌─────────────────┐
│ IB TWS/Gateway  │  ◄─── Realistic order execution
│ (Paper Account) │
└─────────────────┘
```

**Key Design**:
- **Internal tracking is primary**: Database is the source of truth
- **IB provides realistic execution**: Orders sent to IB paper account
- **Fire-and-forget**: Send order, wait for fill callback
- **No position sync from IB**: Positions tracked internally only

## Prerequisites

### 1. Interactive Brokers Paper Trading Account

1. **Sign up**: Create a paper trading account at [interactivebrokers.com](https://www.interactivebrokers.com/)
2. **Download TWS or IB Gateway**:
   - TWS (Trader Workstation): Full GUI
   - IB Gateway: Lightweight, no GUI
3. **Enable API Access**:
   - Open TWS/Gateway settings
   - Navigate to API Settings
   - Enable "ActiveX and Socket Clients"
   - Enable "Allow connections from localhost"
   - Note the port number (default: 7497 for TWS paper)

### 2. Start TWS/Gateway

```bash
# On macOS (example for TWS)
open /Applications/Trader\ Workstation.app

# On Linux (example for IB Gateway)
/path/to/ibgateway &
```

**Login with paper trading credentials** (not your live account!)

## Configuration

### Environment Variables

```bash
# Broker mode
BROKER_MODE=ib_paper

# IB connection settings
IB_HOST=127.0.0.1           # IB Gateway/TWS host
IB_PORT=7497                # 7497=TWS paper, 4002=Gateway paper
IB_CLIENT_ID=1              # Unique client ID (increment if running multiple instances)
IB_ACCOUNT=                 # Optional: specify account ID (leave empty for default)
```

### Port Numbers Reference

| Application | Paper Trading | Live Trading |
|------------|---------------|--------------|
| TWS        | 7497          | 7496         |
| IB Gateway | 4002          | 4001         |

**Important**: Always verify you're connecting to the paper trading port!

## Usage

### Starting the Service

```bash
# Start with IB paper trading
export BROKER_MODE=ib_paper
export IB_PORT=7497

# Start services
cd /Users/shalev/Code/SCP
make services-up
```

### Logs to Watch

```bash
# Watch execution service logs
docker logs -f scp-execution

# Look for these messages:
# ✅ Broker connected (mode: ib_paper)
# Connected to IB. Next order ID: 1
# IB order filled: long 1 GC @ 2650.00 (orderId=123)
```

### Verifying Connection

```bash
# Check service status
curl http://localhost:8005/health

# Check if broker is connected (look for mode in logs)
docker logs scp-execution 2>&1 | grep "Broker"
```

## How It Works

### Order Placement Flow

1. **Signal Generated**: Bot Core generates a signal
2. **TradeManager**: Calls `broker.place_order()`
3. **IBPaperBroker**: Creates IB contract and order
4. **IBClient**: Sends order to IB via API
5. **IB Executes**: Order fills at market price
6. **Callback**: `orderStatus()` callback receives fill
7. **OrderResult**: Returned to TradeManager
8. **Database**: TradeManager saves trade to PostgreSQL

### Position Tracking

- **Internal tracking only**: Positions stored in `_positions` dict
- **Not synced from IB**: We don't query IB for positions
- **Reconciliation on startup**: Restores positions from database
- **Why**: Internal tracking is source of truth, IB just executes

### Supported Features

✅ **Implemented**:
- Market orders for GC (Gold Futures)
- Long and short positions
- Position tracking (internal)
- Order fill callbacks
- Connection/disconnection
- Async API (runs IB client in background thread)
- Automatic reconnection attempts

❌ **Not Yet Implemented**:
- Limit orders (only market orders)
- Multiple contracts (only GC supported)
- Dynamic contract month selection (hardcoded to 202502)
- Stop-loss/take-profit orders at IB level
- Partial fills
- Position sync from IB

## Contract Specification

Currently only **GC (Gold Futures)** is supported:

```python
Symbol: GC
Exchange: COMEX
Contract Type: FUT (Futures)
Currency: USD
Multiplier: 100 (1 point = $100)
Contract Month: 202502 (Feb 2025) - needs periodic update
```

## Troubleshooting

### Connection Fails

**Error**: `Failed to connect to IB at 127.0.0.1:7497 (timeout after 10s)`

**Solutions**:
1. Verify TWS/Gateway is running
2. Check paper trading mode (not live!)
3. Verify port number matches TWS settings
4. Check API access is enabled in TWS settings
5. Ensure "Allow connections from localhost" is enabled

### Orders Rejected

**Error**: `IB order rejected: long 1 GC (orderId=123)`

**Solutions**:
1. Check IB paper account has sufficient funds
2. Verify GC futures are available in paper account
3. Check contract month (may need to update to current month)
4. Look at IB TWS error messages for specific reason

### Service Won't Start

**Error**: `Failed to connect broker: ...`

**Solutions**:
1. Set `BROKER_MODE=paper` temporarily to bypass IB
2. Check IB is running before starting service
3. Check firewall isn't blocking port 7497
4. Verify no other client is using same `IB_CLIENT_ID`

## Testing Without IB

If you don't have IB set up yet, use in-memory paper mode:

```bash
# Use in-memory simulation (no IB required)
export BROKER_MODE=paper

# Start services
make services-up
```

This mode provides instant fills at exact prices (no slippage, no latency).

## Switching Modes

### Development (In-Memory)
```bash
BROKER_MODE=paper
```

### IB Paper Trading
```bash
BROKER_MODE=ib_paper
IB_PORT=7497  # TWS paper
```

### Live Trading (Future)
```bash
BROKER_MODE=live  # Not yet implemented - will raise error
IB_PORT=7496  # TWS live
```

## Monitoring

### Check Active Positions

Positions are tracked internally and saved to PostgreSQL:

```sql
-- Query active trades
SELECT * FROM trades WHERE state = 'OPEN';

-- Check position reconciliation on startup
docker logs scp-execution 2>&1 | grep "Reconciled"
```

### Monitor Order Flow

```bash
# Watch order execution logs
docker logs -f scp-execution | grep "IB order"

# Look for:
# IB order filled: long 1 GC @ 2650.00 (orderId=123)
# IB position closed: long 1 GC @ 2660.00 (pnl=10.00 points)
```

## Limitations

1. **GC Only**: Only Gold Futures supported currently
2. **Market Orders Only**: No limit/stop orders yet
3. **Single Position**: One position per symbol at a time
4. **Hardcoded Contract Month**: Needs manual update periodically
5. **No Slippage Simulation**: IB fills at market (realistic but no slippage model)

## Next Steps

After validating IB paper trading:
1. Update contract month selection to be dynamic
2. Add support for multiple contract types (ES, NQ, etc.)
3. Implement limit orders
4. Add IB-level stop-loss/take-profit orders
5. Implement live trading mode (with additional safety checks)

## API Reference

### Broker Factory

```python
from execution_svc.broker import create_broker
from execution_svc.config import ExecutionConfig

config = ExecutionConfig(broker_mode="ib_paper", ib_port=7497)
broker = create_broker(config.broker_mode, config)

# Connect to IB
await broker.connect()

# Place order
result = await broker.place_order("GC", "long", 1, price=2650.0)

# Disconnect
await broker.disconnect()
```

### Order Result

```python
@dataclass
class OrderResult:
    order_id: str           # IB order ID
    symbol: str             # "GC"
    side: str               # "long" or "short"
    quantity: int           # Number of contracts
    filled_price: float     # Actual fill price
    filled_at: datetime     # Fill timestamp
    status: str             # "filled", "rejected", or "pending"
```

## Support

For issues or questions:
1. Check TWS/Gateway logs for IB-side errors
2. Check service logs: `docker logs scp-execution`
3. Verify configuration with `docker exec scp-execution env | grep IB`
