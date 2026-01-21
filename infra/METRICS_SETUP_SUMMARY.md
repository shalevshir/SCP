# Metrics Setup Summary

## Overview

The metrics infrastructure is now configured with **local development as the default**. When you run `docker-compose -f docker-compose.infra.yml up -d`, Prometheus automatically targets services running on your host machine (`host.docker.internal`). When you add environment overlays for Docker-based deployments, Prometheus automatically switches to target Docker service names.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Prometheus Configuration Strategy                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  docker-compose.infra.yml (DEFAULT)                         │
│  ├── Uses: prometheus.local.yml                            │
│  └── Targets: host.docker.internal:8001-8005               │
│                                                             │
│  ↓ Override when services run in Docker                    │
│                                                             │
│  Environment Overlays (services.yml + {env}.yml)           │
│  ├── Override to: prometheus.yml                           │
│  └── Targets: data-adapter:8001, feature-engine:8002, etc. │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Files Structure

```
infra/
├── prometheus/
│   ├── prometheus.yml         # Docker service names (data-adapter:8001, etc.)
│   └── prometheus.local.yml   # Host machine targets (host.docker.internal:8001-8005)
│
├── docker-compose.infra.yml   # Uses prometheus.local.yml by default
│
└── Environment overlays (all override to prometheus.yml):
    ├── docker-compose.services.yml  # Base services (overrides Prometheus)
    ├── docker-compose.dev.yml       # Development environment
    ├── docker-compose.test.yml      # Test environment
    ├── docker-compose.replay.yml    # Replay mode
    ├── docker-compose.paper.yml     # Paper trading
    └── docker-compose.live.yml      # Live trading
```

## Configuration Details

### docker-compose.infra.yml (Base Infrastructure)

```yaml
prometheus:
  image: prom/prometheus:v2.48.0
  volumes:
    # Default: Local development (services on host.docker.internal)
    - ./prometheus/prometheus.local.yml:/etc/prometheus/prometheus.yml:ro
```

### Environment Overlays (Override)

All environment files that include services override Prometheus configuration:

```yaml
prometheus:
  volumes:
    # Override: Use Docker service names
    - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
```

## Usage Examples

### Local Development (Default)

**Scenario:** Services running in terminal for debugging

```bash
# 1. Start infrastructure
cd infra
docker-compose -f docker-compose.infra.yml up -d

# 2. Start services in terminal
cd ../services/feature-engine
poetry run python -m feature_engine_svc.main

cd ../services/bot-core
poetry run python -m bot_core_svc.main

# 3. View metrics
open http://localhost:9090  # Prometheus
open http://localhost:3000  # Grafana
```

**Result:** Prometheus scrapes `host.docker.internal:8001-8005`

### Docker-Based Development

**Scenario:** All services running in Docker

```bash
cd infra
docker-compose \
  -f docker-compose.infra.yml \
  -f docker-compose.services.yml \
  -f docker-compose.dev.yml \
  up -d

# View metrics
open http://localhost:9090  # Prometheus
open http://localhost:3000  # Grafana
```

**Result:** Prometheus scrapes Docker service names (`data-adapter:8001`, etc.)

### Paper Trading

**Scenario:** Paper trading with IB Gateway

```bash
cd infra
docker-compose \
  -f docker-compose.infra.yml \
  -f docker-compose.services.yml \
  -f docker-compose.paper.yml \
  up -d
```

**Result:** Prometheus scrapes Docker service names

### Live Trading

**Scenario:** Production deployment

```bash
cd infra
docker-compose \
  -f docker-compose.infra.yml \
  -f docker-compose.services.yml \
  -f docker-compose.live.yml \
  up -d
```

**Result:** Prometheus scrapes Docker service names

## Benefits

1. **No extra steps for local development** - Just run infra and start your services
2. **Automatic configuration** - Environment overlays handle Prometheus switching
3. **Single source of truth** - All environments defined in compose files
4. **Clear separation** - Infrastructure vs services vs environment
5. **Production-ready** - Same pattern works from dev to live

## Verification

### Check Active Configuration

```bash
# View the mounted Prometheus config
docker exec scp-prometheus cat /etc/prometheus/prometheus.yml | head -20

# For local dev, you should see: host.docker.internal:8001
# For Docker services, you should see: data-adapter:8001
```

### Check Prometheus Targets

1. Open Prometheus: http://localhost:9090
2. Navigate to: Status → Targets
3. Verify all services show "UP" status

### Test Metrics Endpoints

```bash
# If services running in terminal (local dev)
curl http://localhost:8002/metrics

# If services running in Docker
curl http://localhost:8002/metrics  # Same URL works!
```

## Troubleshooting

### "No Data" in Grafana

1. **Check Prometheus targets:** http://localhost:9090/targets
2. **Verify service is running:**
   ```bash
   curl http://localhost:8002/metrics
   ```
3. **Check time range in Grafana** - Ensure it covers when services were running

### Linux: "host.docker.internal" Not Found

On Linux, add to `docker-compose.infra.yml`:

```yaml
prometheus:
  extra_hosts:
    - "host.docker.internal:host-gateway"
```

Then restart:
```bash
docker-compose -f docker-compose.infra.yml restart prometheus
```

## References

- [PROMETHEUS_METRICS_IMPLEMENTATION.md](../PROMETHEUS_METRICS_IMPLEMENTATION.md) - Full metrics architecture
- [LOCAL_DEVELOPMENT_METRICS.md](./LOCAL_DEVELOPMENT_METRICS.md) - Detailed setup guide
- [Microservices Architecture](../.cursor/rules/microservices_architecture.mdc) - System design
