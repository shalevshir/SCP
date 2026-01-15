# SCP Infrastructure - Docker Compose

This directory contains Docker Compose configurations for different deployment environments.

## File Structure

Docker Compose uses a **layered approach** with three files in every command:

1. **`docker-compose.infra.yml`** - Infrastructure layer (Redis + PostgreSQL)
2. **`docker-compose.services.yml`** - Services layer (all microservice builds)
3. **Environment overlay** - Environment-specific overrides

### Infrastructure Layer
- **`docker-compose.infra.yml`** - Redis + PostgreSQL/TimescaleDB with migrations

### Services Layer
- **`docker-compose.services.yml`** - Build definitions for all 5 microservices

### Environment Overlays
- **`docker-compose.dev.yml`** - Development (mock data, debug logging)
- **`docker-compose.paper.yml`** - Paper trading (live data + IB paper broker)
- **`docker-compose.live.yml`** - Production (live data + IB live broker)
- **`docker-compose.test.yml`** - CI/testing (ephemeral containers, different ports)
- **`docker-compose.replay.yml`** - Historical replay (session filtering disabled)

**Why this structure?**
- No duplication: Service builds defined once in `services.yml`
- Clean overrides: Environment files only change what's different
- Composable: Mix and match infrastructure, services, and environments
- Easy maintenance: Update service config in one place

## Quick Start

### Development (Mock Data)

```bash
cd infra
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up --build
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

### Paper Trading (IB Paper)

```bash
cd infra
# Make sure IB Gateway is running in paper trading mode (port 4002)
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.paper.yml up --build
```

**Features:**
- Live market data via IB Gateway
- IB Gateway paper trading broker
- Production-like settings
- Session filtering enabled
- Full risk management

**Prerequisites:**
1. IB Gateway running on host (paper mode, port 4002)
2. IB API enabled in Gateway settings

### Live Production (Real Trading)

```bash
cd infra
export IB_ACCOUNT="your-ib-account"
export POSTGRES_PASSWORD="strong-password"
# Make sure IB Gateway is running in LIVE mode (port 4001)
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.live.yml up --build
```

**⚠️  WARNING: THIS PLACES REAL TRADES WITH REAL MONEY ⚠️**

**Features:**
- Live market data via IB Gateway
- IB Gateway LIVE trading broker
- Conservative risk limits
- Full monitoring and alerting
- Production-grade settings

**Prerequisites:**
1. `IB_ACCOUNT` environment variable (required)
2. `POSTGRES_PASSWORD` environment variable (required)
3. IB Gateway running on host (LIVE mode, port 4001)
4. Adequate funds in IB account
5. Risk limits configured in `config/validation.yaml`

### Testing (CI/Integration Tests)

```bash
cd infra
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.test.yml up --build
```

**Features:**
- Ephemeral containers (no persistent volumes)
- Different ports (6380 for Redis, 5433 for PostgreSQL)
- Test database credentials
- Mock data provider
- No restart policies (for CI environments)

### Replay Mode (Historical Validation)

```bash
cd infra
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.replay.yml up --build
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
| `DATA_PROVIDER` | Data provider (`mock`, `ib`) | `mock` |
| `IB_HOST` | IB Gateway host | `host.docker.internal` |
| `IB_PORT` | IB Gateway port | `4002` (paper) / `4001` (live) |
| `IB_CLIENT_ID` | IB API client ID (data adapter) | `1` |
| `IB_GC_CONTRACT` | Gold futures contract symbol | `GC` |
| `IB_DXY_CONTRACT` | Dollar index contract symbol | `DX` |
| `SESSION_FILTER_ENABLED` | Filter by trading hours | `true` |
| `GAP_BACKFILL_ENABLED` | Enable gap backfill | `true` |

### Execution Service Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BROKER_MODE` | Broker mode (`paper`, `ib_paper`, `ib_live`) | `paper` |
| `IB_HOST` | IB Gateway host | `host.docker.internal` |
| `IB_PORT` | IB Gateway port | `4002` (paper) / `4001` (live) |
| `IB_CLIENT_ID` | IB API client ID (execution) | `2` |
| `IB_ACCOUNT` | IB account number | - (required for live) |
| `MAX_ACTIVE_TRADES` | Max concurrent trades | `1` |
| `MAX_TRADES_PER_DAY` | Max trades per day | `3` |
| `PDLL_LIMIT` | Per-day loss limit (dollars) | `200.0` |

**Note:** Data Adapter uses `IB_CLIENT_ID=1`, Execution uses `IB_CLIENT_ID=2` to avoid conflicts when both connect to the same IB Gateway.

## Common Commands

### Start Services

```bash
# Development (mock data)
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up --build

# Paper trading (IB Gateway required on port 4002)
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.paper.yml up --build

# Live trading (⚠️  use with caution - requires IB Gateway on port 4001)
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.live.yml up --build
```

### Stop Services

```bash
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml down
```

### View Logs

```bash
# All services
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml logs -f

# Specific service
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml logs -f data-adapter
```

### Clean Volumes (Reset Database)

```bash
# Development
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml down -v

# Paper/Live (careful - deletes persistent data)
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.paper.yml down -v
```

### Rebuild Services

```bash
# Rebuild all services
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up --build --force-recreate

# Rebuild specific service
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up --build --force-recreate data-adapter
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
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml logs service-name
```

### Database Connection Issues

Verify PostgreSQL is healthy:

```bash
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml ps postgres
```

Check migrations ran successfully:

```bash
docker exec -it scp-postgres psql -U scp -d scp_dev -c '\dt'
```

### Reset Everything

```bash
# Stop all containers
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml down

# Remove volumes (warning: deletes all data)
docker volume rm scp_redis_data scp_postgres_data scp_postgres_dev_data

# Rebuild from scratch
docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up --build
```

## Development Workflow

1. **Start infrastructure:**
   ```bash
   docker compose -f docker-compose.infra.yml up -d
   ```

2. **Start specific service in dev mode:**
   ```bash
   # e.g., work on data-adapter
   cd ../services/data-adapter
   poetry run python -m data_adapter.main
   ```

3. **Run other services in containers:**
   ```bash
   docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up feature-engine htf-bias bot-core execution
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
