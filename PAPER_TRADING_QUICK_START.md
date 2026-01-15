# Paper Trading Quick Start

## Prerequisites Checklist

- [ ] Databento API key (`DATABENTO_API_KEY`)
- [ ] IB Gateway/TWS installed and running
- [ ] IB API enabled (port 7497 for TWS paper, 4002 for Gateway paper)
- [ ] Docker installed and running

## Quick Start (3 Steps)

### 1. Set Environment Variables

```bash
export DATABENTO_API_KEY="db-your-key-here"
export IB_PORT="7497"  # TWS paper (or 4002 for Gateway)
export IB_HOST="host.docker.internal"  # Mac/Windows (use 172.17.0.1 on Linux)
```

### 2. Start Services

```bash
make paper-trading-up
```

Or manually:
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.services.yml \
  -f infra/docker-compose.paper-trading.yml \
  up -d --build
```

### 3. Verify

```bash
# Check all services
curl http://localhost:8001/health  # Data Adapter
curl http://localhost:8005/health   # Execution

# Check broker connection
docker logs scp-execution | grep "Broker connected"

# Monitor logs
make services-logs
```

## Common Commands

```bash
# Start paper trading
make paper-trading-up

# Stop paper trading
make paper-trading-down

# View logs
make services-logs
docker logs -f scp-execution

# Check kill switch status
curl http://localhost:8005/admin/status

# Activate kill switch (emergency halt)
curl -X POST "http://localhost:8005/admin/kill?reason=Manual%20halt"

# Resume trading
curl -X POST http://localhost:8005/admin/resume
```

## Troubleshooting

### IB Connection Failed

**On Mac/Windows**: `host.docker.internal` should work automatically.

**On Linux**: Use Docker bridge IP:
```bash
export IB_HOST="172.17.0.1"
# Or find your host IP: ip addr show docker0
```

### No Data Coming In

1. Check Databento API key: `echo $DATABENTO_API_KEY`
2. Check logs: `docker logs scp-data-adapter`
3. Verify Databento account has access to `GLBX.MDP3`

### No Signals Generated

1. Check data flow: `docker logs scp-data-adapter | grep "candle published"`
2. Check features: `docker logs scp-feature-engine | grep "features"`
3. Check session: `docker logs scp-bot-core | grep "session"`
4. Check kill switch: `curl http://localhost:8005/admin/status`

## Port Reference

| Service | Port | URL |
|---------|------|-----|
| Data Adapter | 8001 | http://localhost:8001/health |
| Feature Engine | 8002 | http://localhost:8002/health |
| HTF Bias | 8003 | http://localhost:8003/health |
| Bot Core | 8004 | http://localhost:8004/health |
| Execution | 8005 | http://localhost:8005/health |

| IB Application | Paper Port | Live Port |
|----------------|------------|-----------|
| TWS | 7497 | 7496 |
| Gateway | 4002 | 4001 |

**⚠️ Always use paper ports (7497 or 4002) for testing!**

## Full Documentation

See [LOCAL_PAPER_TRADING_GUIDE.md](./LOCAL_PAPER_TRADING_GUIDE.md) for complete setup instructions.
