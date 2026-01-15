# SCP Infrastructure - Docker Compose

This directory contains Docker Compose configurations for different deployment environments.

## File Structure

- **`docker-compose.yml`** - Base infrastructure (Redis + PostgreSQL)
- **`docker-compose.dev.yml`** - Development environment
- **`docker-compose.paper.yml`** - Paper trading environment
- **`docker-compose.live.yml`** - Live production environment
- **`docker-compose.test.yml`** - CI/testing environment
- **`docker-compose.replay.yml`** - Historical replay/validation

## Quick Start

### Development (Mock Data)

```bash
cd infra
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

**Features:**
- Mock data provider (no external dependencies)
- Debug logging enabled
- Verbose Postgres query logging
- Paper broker (no real trades)
- Session filtering disabled

**Access:**
- Data Adapter: http://localhost:8001/health
- Feature Engine: http://localhost:8002/health
- HTF Bias: http://localhost:8003/health
- Bot Core: http://localhost:8004/health
- Execution: http://localhost:8005/health

### Paper Trading (Live Data + Paper Broker)

```bash
cd infra
export DATABENTO_API_KEY="your-api-key"
# Make sure IB Gateway is running in paper trading mode (port 4002)
docker-compose -f docker-compose.yml -f docker-compose.paper.yml up --build
```

**Features:**
- Live market data via Databento
- IB Gateway paper trading broker
- Production-like settings
- Session filtering enabled
- Full risk management

**Prerequisites:**
1. `DATABENTO_API_KEY` environment variable
2. IB Gateway running on host (paper mode, port 4002)
3. IB API enabled in Gateway settings

### Live Production (Real Trading)

```bash
cd infra
export DATABENTO_API_KEY="your-api-key"
export IB_ACCOUNT="your-ib-account"
export POSTGRES_PASSWORD="strong-password"
# Make sure IB Gateway is running in LIVE mode (port 4001)
docker-compose -f docker-compose.yml -f docker-compose.live.yml up --build
```

**⚠️  WARNING: THIS PLACES REAL TRADES WITH REAL MONEY ⚠️**

**Features:**
- Live market data via Databento
- IB Gateway LIVE trading broker
- Conservative risk limits
- Full monitoring and alerting
- Production-grade settings

**Prerequisites:**
1. `DATABENTO_API_KEY` environment variable
2. `IB_ACCOUNT` environment variable (required)
3. `POSTGRES_PASSWORD` environment variable (required)
4. IB Gateway running on host (LIVE mode, port 4001)
5. Adequate funds in IB account
6. Risk limits configured in `config/validation.yaml`

### Testing (CI/Integration Tests)

```bash
cd infra
docker-compose -f docker-compose.yml -f docker-compose.services.yml -f docker-compose.test.yml up --build
```

**Features:**
- Ephemeral containers (no persistent volumes)
- Different ports (avoid conflicts)
- Test database credentials
- No restart policies

### Replay Mode (Historical Validation)

```bash
cd infra
docker-compose -f docker-compose.yml -f docker-compose.services.yml -f docker-compose.replay.yml up --build
```

**Features:**
- Session filtering disabled
- Mock data provider with historical data
- Paper broker
- Faster processing

## Environment Variables

### Common Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | PostgreSQL password | `scp_dev_password` (dev only) |
| `LOG_LEVEL` | Service log level | `INFO` (or `DEBUG` in dev) |

### Data Adapter Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_PROVIDER` | Data provider (`mock`, `databento`, `ib`) | `mock` |
| `DATABENTO_API_KEY` | Databento API key | - |
| `DATABENTO_DATASET` | Databento dataset | `GLBX.MDP3` |
| `DATABENTO_GC_SYMBOL` | Gold futures symbol | `GC.FUT` |
| `DATABENTO_DXY_SYMBOL` | Dollar index symbol | `DX.FUT` |
| `SESSION_FILTER_ENABLED` | Filter by trading hours | `true` |
| `GAP_BACKFILL_ENABLED` | Enable gap backfill | `true` |

### Execution Service Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BROKER_MODE` | Broker mode (`paper`, `ib_paper`, `ib_live`) | `paper` |
| `IB_HOST` | IB Gateway host | `host.docker.internal` |
| `IB_PORT` | IB Gateway port | `4002` (paper) / `4001` (live) |
| `IB_CLIENT_ID` | IB API client ID | `1` |
| `IB_ACCOUNT` | IB account number | - (required for live) |
| `MAX_ACTIVE_TRADES` | Max concurrent trades | `1` |
| `MAX_TRADES_PER_DAY` | Max trades per day | `3` |
| `PDLL_LIMIT` | Per-day loss limit (dollars) | `200.0` |

## Common Commands

### Start Services

```bash
# Development
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Paper trading
docker-compose -f docker-compose.yml -f docker-compose.paper.yml up --build

# Live (use with caution)
docker-compose -f docker-compose.yml -f docker-compose.live.yml up --build
```

### Stop Services

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
```

### View Logs

```bash
# All services
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

# Specific service
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f data-adapter
```

### Clean Volumes (Reset Database)

```bash
# Development
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down -v

# Paper/Live (careful - deletes persistent data)
docker-compose -f docker-compose.yml -f docker-compose.paper.yml down -v
```

### Rebuild Services

```bash
# Rebuild all services
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build --force-recreate

# Rebuild specific service
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build --force-recreate data-adapter
```

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Data Adapter | 8001 | Data ingestion service |
| Feature Engine | 8002 | Feature computation service |
| HTF Bias | 8003 | Higher-timeframe bias service |
| Bot Core | 8004 | Signal generation service |
| Execution | 8005 | Trade execution service |
| Redis | 6379 | Message queue |
| PostgreSQL | 5432 | Database (5433 for test) |

## Health Checks

All services expose health check endpoints:

```bash
# Check all services
curl http://localhost:8001/health  # Data Adapter
curl http://localhost:8002/health  # Feature Engine
curl http://localhost:8003/health  # HTF Bias
curl http://localhost:8004/health  # Bot Core
curl http://localhost:8005/health  # Execution
```

## Troubleshooting

### IB Gateway Connection Issues (Mac/Windows)

If `host.docker.internal` doesn't work, try:

1. Check IB Gateway is running and API is enabled
2. Verify correct port: 4002 (paper) or 4001 (live)
3. Check firewall settings

### IB Gateway Connection Issues (Linux)

On Linux, `host.docker.internal` may not work. Try:

1. Uncomment `network_mode: host` in the execution service
2. Or use host's IP address: `IB_HOST=172.17.0.1`
3. Or use host's actual IP: `IB_HOST=192.168.1.x`

### Service Won't Start

Check logs for the failing service:

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs service-name
```

### Database Connection Issues

Verify PostgreSQL is healthy:

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps postgres
```

Check migrations ran successfully:

```bash
docker exec -it scp-postgres psql -U scp -d scp_dev -c '\dt'
```

### Reset Everything

```bash
# Stop all containers
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down

# Remove volumes (warning: deletes all data)
docker volume rm scp_redis_data scp_postgres_data scp_postgres_dev_data

# Rebuild from scratch
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Development Workflow

1. **Start infrastructure:**
   ```bash
   docker-compose -f docker-compose.yml up -d
   ```

2. **Start specific service in dev mode:**
   ```bash
   # e.g., work on data-adapter
   cd ../services/data-adapter
   poetry run python -m data_adapter.main
   ```

3. **Run other services in containers:**
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml up feature-engine htf-bias bot-core execution
   ```

## Production Deployment

For production deployment:

1. Use `docker-compose.live.yml`
2. Set strong `POSTGRES_PASSWORD`
3. Configure monitoring/alerting
4. Set conservative risk limits in `config/validation.yaml`
5. Test thoroughly in paper trading first
6. Start with very small position sizes
7. Monitor logs and metrics continuously

## Next Steps

- [ ] Add Prometheus metrics endpoints
- [ ] Add OpenTelemetry tracing
- [ ] Add Grafana dashboards
- [ ] Add alerting (PagerDuty, Slack)
- [ ] Add kill switch endpoint
- [ ] Add backup/restore scripts
