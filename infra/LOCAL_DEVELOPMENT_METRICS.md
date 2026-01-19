# Local Development Metrics Setup

## TL;DR

**It just works!** 🎉

For local development (services running in terminal):
```bash
cd infra
docker-compose -f docker-compose.infra.yml up -d
# Then start your services in terminal as usual
```

For Docker-based deployment:
```bash
cd infra
docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up -d
```

Prometheus automatically targets the right endpoints based on which compose files you use.

---

## Problem

When running microservices in the terminal (not Docker), Grafana and Prometheus can't scrape metrics because:

1. Prometheus runs in Docker and is configured to scrape Docker service names (`data-adapter:8001`, etc.)
2. These DNS names only resolve within the Docker network
3. Services running on the host machine are on `localhost`, not the Docker network

## Solution

**The infrastructure is now configured for local development by default!**

`docker-compose.infra.yml` uses `prometheus.local.yml` which scrapes `host.docker.internal:8001-8005`. When you use environment overlays (services.yml, paper.yml, live.yml), they override Prometheus to use `prometheus.yml` for Docker service names.

## Setup Instructions

### 1. Start Infrastructure Only (Default for Local Development)

**Start infrastructure for local development:**
```bash
cd infra
docker-compose -f docker-compose.infra.yml up -d
```

This will:
- Start Redis, PostgreSQL, Prometheus, and Grafana in Docker
- Configure Prometheus to scrape `host.docker.internal:8001-8005` (for services running in terminal)
- Allow Prometheus to reach your terminal-based services

### 2. Start Your Services in Terminal

Run your services as usual:
```bash
# Example: Feature Engine
cd services/feature-engine
poetry run python -m feature_engine_svc.main

# Or use your existing scripts/commands
```

### 3. Verify Metrics Are Being Scraped

**Check Prometheus targets:**
1. Open Prometheus UI: http://localhost:9090
2. Go to Status → Targets
3. Verify all services show "UP" status

**Test metrics endpoint directly:**
```bash
# Feature Engine
curl http://localhost:8002/metrics

# Bot Core
curl http://localhost:8004/metrics

# Execution
curl http://localhost:8005/metrics
```

**Query metrics in Prometheus:**
```promql
# Check if metrics are being collected
up{job=~"data-adapter|feature-engine|htf-bias|bot-core|execution"}

# See signal generation rate
rate(scp_signals_generated_total[5m])

# Check feature computation
rate(scp_features_computed_total[5m]) by (timeframe)
```

### 4. View Grafana Dashboards

1. Open Grafana: http://localhost:3000
2. Login (default: admin/admin)
3. Navigate to your dashboards

Metrics should now populate correctly!

## When to Use Each Configuration

### Infrastructure Only (Default - Local Development)
- **When:** Running services in terminal for debugging/development
- **Command:** `docker-compose -f docker-compose.infra.yml up -d`
- **Config:** `prometheus.local.yml` (targets `host.docker.internal:8001-8005`)
- **Use Case:** Day-to-day development, debugging, testing

### Infrastructure + Services (Docker Deployment)
- **When:** Running all services in Docker
- **Command:** `docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.{env}.yml up -d`
- **Config:** `prometheus.yml` (targets Docker service names: `data-adapter:8001`, etc.)
- **Use Case:** Integration testing, paper trading, live trading

**Environment overlays automatically switch to `prometheus.yml`:**
- `docker-compose.dev.yml` - Development with mock data
- `docker-compose.test.yml` - Test environment
- `docker-compose.replay.yml` - Historical data replay
- `docker-compose.paper.yml` - Paper trading with IB Gateway
- `docker-compose.live.yml` - Live trading (real money)

## Troubleshooting

### Prometheus Can't Reach Services

**Error:** "Get http://host.docker.internal:8001/metrics: dial tcp: lookup host.docker.internal: no such host"

**Solution (Linux only):**
On Linux, `host.docker.internal` doesn't work by default. Add to `docker-compose.infra.yml`:

```yaml
services:
  prometheus:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

Then restart:
```bash
cd infra
docker-compose -f docker-compose.infra.yml restart prometheus
```

### Services Not Showing in Prometheus Targets

1. **Verify service is running and exposing metrics:**
   ```bash
   curl http://localhost:8002/metrics
   ```

2. **Check Prometheus logs:**
   ```bash
   docker logs scp-prometheus
   ```

3. **Reload Prometheus configuration:**
   ```bash
   docker exec scp-prometheus kill -HUP 1
   # Or restart Prometheus
   docker-compose -f docker-compose.infra.yml -f docker-compose.local-services.yml restart prometheus
   ```

### Grafana Shows "No Data"

1. **Check Prometheus data source in Grafana:**
   - Go to Configuration → Data Sources → Prometheus
   - Verify URL is `http://prometheus:9090`
   - Click "Test" button

2. **Verify metrics exist in Prometheus:**
   - Open http://localhost:9090
   - Go to Graph tab
   - Query: `up{job="feature-engine"}`
   - Should show data points

3. **Check time range in Grafana:**
   - Ensure you're viewing a time range where services were running

## Switching to Docker Services

When you want to run all services in Docker instead of in the terminal:

```bash
# Stop local services in terminal (Ctrl+C)

# Stop infrastructure only
cd infra
docker-compose -f docker-compose.infra.yml down

# Start infrastructure + services in Docker (choose your environment)
docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up -d
```

Prometheus will automatically switch to `prometheus.yml` and scrape Docker service names.

## Files

- `infra/prometheus/prometheus.yml` - Docker services configuration (service names: `data-adapter:8001`, etc.)
- `infra/prometheus/prometheus.local.yml` - Local development configuration (default, targets: `host.docker.internal:8001-8005`)
- `infra/docker-compose.infra.yml` - Infrastructure base (uses `prometheus.local.yml` by default)
- `infra/docker-compose.services.yml` - Services base (overrides to `prometheus.yml`)
- `infra/docker-compose.{env}.yml` - Environment overlays (all override to `prometheus.yml`)

## References

- [PROMETHEUS_METRICS_IMPLEMENTATION.md](../PROMETHEUS_METRICS_IMPLEMENTATION.md) - Metrics architecture
- [GRAFANA_DASHBOARD_SETUP.md](./grafana/README.md) - Dashboard setup guide
