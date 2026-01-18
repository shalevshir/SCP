# SERVICE_MODE Environment Variable Added to All Docker Compose Files

**Date:** January 16, 2026  
**Status:** ✅ Complete

## Summary

Added `SERVICE_MODE` environment variable to all microservices across all Docker Compose files in the `infra/` directory. This ensures proper metrics labeling and service identification across different deployment environments.

## Changes Made

### 1. Base Services File (`docker-compose.services.yml`)

Added `SERVICE_MODE: ${SERVICE_MODE:-dev}` to all services:
- ✅ data-adapter
- ✅ feature-engine
- ✅ htf-bias
- ✅ bot-core
- ✅ execution

Default value: `dev` (used when environment overlay is not applied)

### 2. Development Environment (`docker-compose.dev.yml`)

Added `SERVICE_MODE: dev` to all services:
- ✅ data-adapter
- ✅ feature-engine
- ✅ htf-bias
- ✅ bot-core
- ✅ execution

### 3. Test Environment (`docker-compose.test.yml`)

Added `SERVICE_MODE: test` to all services:
- ✅ data-adapter
- ✅ feature-engine
- ✅ htf-bias
- ✅ bot-core
- ✅ execution

### 4. Replay Mode (`docker-compose.replay.yml`)

Added `SERVICE_MODE: replay` to all services:
- ✅ data-adapter
- ✅ feature-engine
- ✅ htf-bias
- ✅ bot-core
- ✅ execution

### 5. Paper Trading (`docker-compose.paper.yml`)

Already had `SERVICE_MODE: paper` for all services:
- ✅ data-adapter (already present)
- ✅ feature-engine (already present)
- ✅ htf-bias (already present)
- ✅ bot-core (already present)
- ✅ execution (already present)

### 6. Live Trading (`docker-compose.live.yml`)

Added `SERVICE_MODE: live` to all services:
- ✅ data-adapter
- ✅ feature-engine
- ✅ htf-bias
- ✅ bot-core
- ✅ execution

### 7. Infrastructure (`docker-compose.infra.yml`)

No changes needed - this file only contains infrastructure services (redis, postgres, prometheus, grafana) which don't need SERVICE_MODE.

## Impact

### Metrics Labeling

All Prometheus metrics now include the correct `mode` label:

```promql
# Before (some services missing mode label)
scp_signals_generated_total{service="bot-core"}

# After (consistent across all services)
scp_signals_generated_total{mode="paper", service="bot-core"}
scp_trading_halt_reason{mode="paper", service="execution", reason="NONE"}
```

### Service Identification

Services can now self-identify their deployment mode:
- Useful for conditional logic (e.g., stricter validation in live mode)
- Better logging context
- Easier debugging across environments

### Grafana Dashboard

The Grafana dashboard variable `$mode` can now correctly filter metrics:
- Dev metrics: `mode="dev"`
- Test metrics: `mode="test"`
- Replay metrics: `mode="replay"`
- Paper trading: `mode="paper"`
- Live trading: `mode="live"`

## Environment Mode Matrix

| Environment | SERVICE_MODE | Database | Broker | Session Filter |
|-------------|--------------|----------|--------|----------------|
| dev | `dev` | scp_dev | paper | disabled |
| test | `test` | scp_test | paper | disabled |
| replay | `replay` | scp | paper | disabled |
| paper | `paper` | scp | ib_paper | enabled |
| live | `live` | scp | ib_live | enabled |

## Usage Examples

### Start Paper Trading Environment
```bash
docker compose -f infra/docker-compose.infra.yml \
               -f infra/docker-compose.services.yml \
               -f infra/docker-compose.paper.yml \
               up --build
# All services will have SERVICE_MODE=paper
```

### Start Development Environment
```bash
docker compose -f infra/docker-compose.infra.yml \
               -f infra/docker-compose.services.yml \
               -f infra/docker-compose.dev.yml \
               up --build
# All services will have SERVICE_MODE=dev
```

### Start Replay Mode
```bash
docker compose -f infra/docker-compose.infra.yml \
               -f infra/docker-compose.services.yml \
               -f infra/docker-compose.replay.yml \
               up --build
# All services will have SERVICE_MODE=replay
```

## Verification

After restarting services, verify the SERVICE_MODE is set correctly:

```bash
# Check bot-core service mode
curl -s http://localhost:8004/metrics | grep 'mode="paper"'

# Check execution service mode
curl -s http://localhost:8005/metrics | grep 'mode="paper"'

# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, mode: .labels.mode}'
```

Expected output:
```json
{
  "job": "bot-core",
  "mode": "paper"
}
{
  "job": "execution",
  "mode": "paper"
}
```

## Files Modified

1. ✅ `infra/docker-compose.services.yml` - Added SERVICE_MODE with dev default
2. ✅ `infra/docker-compose.dev.yml` - Added SERVICE_MODE: dev
3. ✅ `infra/docker-compose.test.yml` - Added SERVICE_MODE: test
4. ✅ `infra/docker-compose.replay.yml` - Added SERVICE_MODE: replay
5. ✅ `infra/docker-compose.paper.yml` - Already had SERVICE_MODE: paper
6. ✅ `infra/docker-compose.live.yml` - Added SERVICE_MODE: live
7. ⏭️ `infra/docker-compose.infra.yml` - No changes (infrastructure only)

## Next Steps

Services need to be restarted to pick up the new SERVICE_MODE environment variable:

```bash
# For currently running paper trading environment
docker compose -f infra/docker-compose.infra.yml \
               -f infra/docker-compose.services.yml \
               -f infra/docker-compose.paper.yml \
               restart
```

Or rebuild if service code changed:

```bash
docker compose -f infra/docker-compose.infra.yml \
               -f infra/docker-compose.services.yml \
               -f infra/docker-compose.paper.yml \
               up --build -d
```

## Related Changes

This complements the earlier fixes:
- **Grafana Dashboard**: Fixed "Execution Service Up" panel (removed mode filter from `up` metric)
- **Signal Rejection Tracking**: Added specific rejection reasons (htf_validity, neutral_direction)
- **Trading Halt Reason**: Initialized metric at service startup

All metrics now have consistent `mode` and `service` labels for proper Grafana filtering and aggregation.
