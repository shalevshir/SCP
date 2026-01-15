# Local Paper Trading Setup Guide

This guide walks you through setting up paper trading locally with **live data** from Databento and **Interactive Brokers paper trading** integration.

## Overview

The system will:
- ✅ Stream **live tick data** from Databento (real-time GC and DXY futures)
- ✅ Compute features and generate signals in real-time
- ✅ Execute trades through **Interactive Brokers paper trading account**
- ✅ Track all trades in PostgreSQL database
- ✅ Support kill switch for emergency halts

## Prerequisites

### 1. Databento Account & API Key

1. Sign up at [databento.com](https://databento.com)
2. Get your API key from the dashboard
3. Ensure you have access to `GLBX.MDP3` dataset (CME futures)

**Cost**: ~$100-500/month depending on usage

### 2. Interactive Brokers Paper Trading Account

1. Sign up for IB paper trading at [interactivebrokers.com](https://www.interactivebrokers.com)
2. Download **IB Gateway** (lightweight) or **TWS** (full GUI)
   - IB Gateway recommended for automated trading
   - Download: https://www.interactivebrokers.com/en/index.php?f=16457
3. **Enable API Access**:
   - Open IB Gateway/TWS
   - Go to **Configure → API → Settings**
   - ✅ Enable "Enable ActiveX and Socket Clients"
   - ✅ Enable "Allow connections from localhost only"
   - ✅ Enable "Read-Only API" (optional, for safety)
   - Note the port number:
     - **TWS Paper**: 7497 (default)
     - **Gateway Paper**: 4002 (default)
     - **TWS Live**: 7496 (DO NOT USE for paper trading!)
     - **Gateway Live**: 4001 (DO NOT USE for paper trading!)

### 3. Start IB Gateway/TWS

```bash
# On macOS
open /Applications/IB\ Gateway.app

# On Linux
/path/to/ibgateway &

# On Windows
# Launch IB Gateway from Start Menu
```

**Important**: 
- Login with your **paper trading credentials** (not live account!)
- Verify you see "Paper Trading" in the title bar
- Keep IB Gateway/TWS running while trading

### 4. Docker & Docker Compose

Ensure Docker is installed and running:
```bash
docker --version
docker compose version
```

## Quick Start

### Step 1: Set Environment Variables

Create a `.env` file in the project root (optional, or export directly):

```bash
# Databento Configuration
export DATABENTO_API_KEY="db-your-actual-key-here"
export DATABENTO_DATASET="GLBX.MDP3"
export DATABENTO_GC_SYMBOL="GC.FUT"
export DATABENTO_DXY_SYMBOL="DX.FUT"

# IB Configuration
export IB_HOST="host.docker.internal"  # Mac/Windows (use host IP on Linux)
export IB_PORT="7497"                  # TWS paper port (or 4002 for Gateway)
export IB_CLIENT_ID="1"                # Unique client ID
export IB_ACCOUNT=""                    # Leave empty for default account

# Optional: Override broker mode
export BROKER_MODE="ib_paper"          # Options: paper, ib_paper
```

**For Linux users**: If `host.docker.internal` doesn't work, use your host's IP address:
```bash
# Find your host IP
ip addr show docker0 | grep inet

# Or use Docker bridge gateway
export IB_HOST="172.17.0.1"
```

### Step 2: Start Infrastructure

```bash
cd /Users/shalev/Code/SCP
make infra-up
```

This starts Redis and PostgreSQL. Wait ~30 seconds for PostgreSQL to initialize.

### Step 3: Start All Services with Paper Trading Config

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.services.yml \
  -f infra/docker-compose.paper-trading.yml \
  up -d --build
```

Or use the helper script (see below).

### Step 4: Verify Services

```bash
# Check all services are healthy
curl http://localhost:8001/health  # Data Adapter
curl http://localhost:8002/health  # Feature Engine
curl http://localhost:8003/health  # HTF Bias
curl http://localhost:8004/health  # Bot Core
curl http://localhost:8005/health  # Execution

# Check execution service broker connection
docker logs scp-execution | grep -i "broker"
# Should see: "✅ Broker connected (mode: ib_paper)"
```

### Step 5: Monitor Logs

```bash
# Watch all service logs
make services-logs

# Or watch specific service
docker logs -f scp-execution
docker logs -f scp-data-adapter
```

## Helper Script

Create a convenience script for starting paper trading:

```bash
#!/bin/bash
# scripts/start-paper-trading.sh

set -e

echo "🚀 Starting Paper Trading with Live Data + IB Integration"
echo ""

# Check prerequisites
# if [ -z "$DATABENTO_API_KEY" ]; then
#   echo "❌ Error: DATABENTO_API_KEY not set"
#   echo "   export DATABENTO_API_KEY='db-your-key'"
#   exit 1
# fi

echo "✅ Databento API key found"
echo ""

# Check if IB Gateway/TWS is running (basic check)
if ! nc -z localhost ${IB_PORT:-7497} 2>/dev/null; then
  echo "⚠️  Warning: IB Gateway/TWS may not be running on port ${IB_PORT:-7497}"
  echo "   Please start IB Gateway/TWS and ensure API is enabled"
  echo ""
fi

# Start infrastructure
echo "📦 Starting infrastructure..."
make infra-up
sleep 5

# Start services
echo "🚀 Starting all services..."
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.services.yml \
  -f infra/docker-compose.paper-trading.yml \
  up -d --build

echo ""
echo "✅ Services started!"
echo ""
echo "📊 Service URLs:"
echo "   Data Adapter:   http://localhost:8001/health"
echo "   Feature Engine: http://localhost:8002/health"
echo "   HTF Bias:       http://localhost:8003/health"
echo "   Bot Core:       http://localhost:8004/health"
echo "   Execution:     http://localhost:8005/health"
echo ""
echo "📝 Monitor logs:"
echo "   make services-logs"
echo "   docker logs -f scp-execution"
echo ""
echo "🛑 Stop services:"
echo "   make services-down"
```

Make it executable:
```bash
chmod +x scripts/start-paper-trading.sh
```

## Configuration Options

### Data Adapter Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_PROVIDER` | `databento` | Data provider (databento or mock) |
| `DATABENTO_API_KEY` | *required* | Your Databento API key |
| `DATABENTO_DATASET` | `GLBX.MDP3` | Databento dataset |
| `SESSION_FILTER_ENABLED` | `true` | Filter to trading hours |
| `GAP_BACKFILL_ENABLED` | `true` | Auto-backfill missing candles |

### Execution Service Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKER_MODE` | `ib_paper` | Broker mode: `paper`, `ib_paper` |
| `IB_HOST` | `host.docker.internal` | IB Gateway/TWS host |
| `IB_PORT` | `7497` | IB port (7497=TWS paper, 4002=Gateway paper) |
| `IB_CLIENT_ID` | `1` | Unique client ID |
| `IB_ACCOUNT` | `` | IB account ID (empty for default) |

### Broker Mode Options

1. **`paper`**: In-memory simulation (no real broker)
   - Fast, no external dependencies
   - Good for testing signal generation
   - No realistic execution

2. **`ib_paper`**: Interactive Brokers paper trading
   - Realistic order execution
   - Real market data from IB
   - Paper money only (safe)

## Monitoring & Management

### Check Service Status

```bash
# All services
make services-ps

# Individual service health
curl http://localhost:8005/health | jq
```

### View Trades

```bash
# Connect to database
make db-shell

# Query recent trades
SELECT * FROM trades ORDER BY opened_at DESC LIMIT 10;

# Query active trades
SELECT * FROM trades WHERE state = 'OPEN';
```

### Kill Switch

The execution service has a kill switch to halt trading:

```bash
# Activate kill switch
curl -X POST "http://localhost:8005/admin/kill?reason=Manual%20halt"

# Check status
curl http://localhost:8005/admin/status | jq

# Resume trading
curl -X POST http://localhost:8005/admin/resume
```

### View Logs

```bash
# All services
make services-logs

# Specific service
docker logs -f scp-execution
docker logs -f scp-data-adapter
docker logs -f scp-bot-core

# Filter for specific events
docker logs scp-execution | grep "order filled"
docker logs scp-execution | grep "signal"
docker logs scp-data-adapter | grep "candle published"
```

## Troubleshooting

### IB Connection Issues

**Problem**: Execution service can't connect to IB Gateway/TWS

**Solutions**:
1. Verify IB Gateway/TWS is running
2. Check API settings are enabled
3. Verify port number (7497 for TWS paper, 4002 for Gateway paper)
4. On Linux, try using host IP instead of `host.docker.internal`:
   ```bash
   export IB_HOST="172.17.0.1"  # Docker bridge gateway
   # Or find your host IP: ip addr show docker0
   ```

### Databento Connection Issues

**Problem**: Data Adapter can't connect to Databento

**Solutions**:
1. Verify `DATABENTO_API_KEY` is set correctly
2. Check API key is valid in Databento dashboard
3. Ensure you have access to `GLBX.MDP3` dataset
4. Check logs: `docker logs scp-data-adapter`

### No Signals Generated

**Problem**: Bot Core not generating signals

**Check**:
1. Verify data is flowing: `docker logs scp-data-adapter | grep "candle published"`
2. Check features are computed: `docker logs scp-feature-engine | grep "features"`
3. Check HTF bias: `docker logs scp-htf-bias | grep "bias"`
4. Check session validation: `docker logs scp-bot-core | grep "session"`
5. Verify kill switch is not active: `curl http://localhost:8005/admin/status`

### Trades Not Executing

**Problem**: Signals generated but trades not executing

**Check**:
1. Verify broker connection: `docker logs scp-execution | grep "Broker connected"`
2. Check guardrails: `docker logs scp-execution | grep "guardrail"`
3. Check kill switch: `curl http://localhost:8005/admin/status`
4. Verify IB Gateway/TWS is running and accepting orders

## Stopping Services

```bash
# Stop all services
make services-down

# Stop infrastructure (Redis, PostgreSQL)
make infra-down

# Stop everything
make services-down
make infra-down
```

## Next Steps

Once paper trading is running successfully:

1. **Monitor for 1 week**: Validate system behavior with live data
2. **Review trades**: Compare to backtester expectations
3. **Test kill switch**: Ensure emergency halt works
4. **Check state recovery**: Restart services and verify state restoration
5. **Review logs**: Look for errors, warnings, or unexpected behavior

## Safety Reminders

⚠️ **Important**:
- Always use **paper trading mode** for testing
- Verify `BROKER_MODE=ib_paper` (not `live`)
- Verify IB port is paper trading port (7497 or 4002, NOT 7496 or 4001)
- Keep kill switch accessible for emergency halts
- Monitor logs regularly for errors
- Start with conservative limits (PDLL, max trades per day)

## Support

For issues:
1. Check logs: `make services-logs`
2. Check service health: `curl http://localhost:800X/health`
3. Review this guide's troubleshooting section
4. Check service-specific documentation in `docs/`
