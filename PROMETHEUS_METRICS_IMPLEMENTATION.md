# Prometheus Metrics Implementation Summary

**Status:** ✅ Complete  
**Date:** January 15, 2026

## Overview

Comprehensive Prometheus metrics have been added to all 5 microservices following the principle: **"If a service can break trading, it must expose metrics that prove it isn't."**

## What Was Implemented

### 1. Shared Library (`scp_shared.metrics`)

**Location:** `services/shared/src/scp_shared/metrics/`

**Files Created:**
- `registry.py` - Metric factory functions with automatic `scp_` prefix and `mode`/`service` labels
- `router.py` - FastAPI router providing `GET /metrics` endpoint
- `__init__.py` - Public API exports

**Key Features:**
- Automatic labeling: Every metric includes `mode` and `service` labels
- Consistent naming: `scp_` prefix, `_total` suffix for counters, `_seconds` for histograms
- Type-safe helpers: `create_counter()`, `create_gauge()`, `create_histogram()`

**Dependency Added:** `prometheus-client = "^0.19.0"` in `services/shared/pyproject.toml`

### 2. Service Configurations

Added `service_mode` field to `BaseServiceConfig`:
```python
service_mode: str = Field(
    default="dev",
    description="Service mode for metrics: dev|test|replay|paper|live",
)
```

This enables environment-specific filtering in Prometheus queries.

### 3. Service Metrics

#### Data Adapter (Port 8001)
**File:** `services/data-adapter/src/data_adapter/metrics.py`

| Metric | Type | Description |
|--------|------|-------------|
| `scp_market_ticks_total` | Counter | Raw ticks received from provider |
| `scp_bars_emitted_total` | Counter | Candles published to Redis |
| `scp_market_data_lag_seconds` | Gauge | Time since last tick (staleness) |
| `scp_data_gaps_detected_total` | Counter | Gap detection events |
| `scp_gap_backfills_total` | Counter | Successful backfill operations |
| `scp_data_provider_connected` | Gauge | Provider connection status (1/0) |

#### Feature Engine (Port 8002)
**File:** `services/feature-engine/src/feature_engine_svc/metrics.py`

| Metric | Type | Description |
|--------|------|-------------|
| `scp_features_computed_total` | Counter | Features computed per timeframe |
| `scp_events_processed_total` | Counter | Total candle events processed |
| `scp_event_processing_seconds` | Histogram | Feature computation latency |
| `scp_feature_queue_depth` | Gauge | Pending items in sync buffer |
| `scp_invalid_feature_events_total` | Counter | Invalid events (NaN, missing data) |

#### HTF Bias (Port 8003)
**File:** `services/htf-bias/src/htf_bias_svc/metrics.py`

| Metric | Type | Description |
|--------|------|-------------|
| `scp_htf_bias_current` | Gauge | Current bias (1=bullish, 0=neutral, -1=bearish) |
| `scp_htf_bias_changes_total` | Counter | Bias state transitions |
| `scp_htf_bars_processed_total` | Counter | HTF candles processed |
| `scp_htf_processing_seconds` | Histogram | Bias computation latency |

#### Bot Core (Port 8004)
**File:** `services/bot-core/src/bot_core_svc/metrics.py`

| Metric | Type | Description |
|--------|------|-------------|
| `scp_signals_generated_total` | Counter | A+ signals published |
| `scp_signals_rejected_total` | Counter | Signals blocked by reason |
| `scp_signal_generation_seconds` | Histogram | Signal evaluation latency |

**Rejection Reasons (Finite Set):**
- `risk_limit` - PDLL or loss streak
- `session_filter` - Outside trading hours
- `confidence_filter` - Below A+ threshold
- `cooldown` - Re-entry cooldown active
- `invalid_context` - Missing DXY, bad features
- `warmup` - Warmup period active
- `kill_switch` - Kill switch active
- `active_trade` - Max concurrent trades reached

#### Execution (Port 8005) - CRITICAL
**File:** `services/execution/src/execution_svc/metrics.py`

| Metric | Type | Description |
|--------|------|-------------|
| `scp_trading_enabled` | Gauge | Trading status (1=enabled, 0=disabled) |
| `scp_unsafe_state` | Gauge | Unsafe state indicator (1=unsafe, 0=safe) |

**Note:** Foundation for additional metrics (orders, trades, P&L) is in place. Full instrumentation of TradeManager requires additional work.

### 4. Docker Infrastructure

**File:** `infra/docker-compose.infra.yml`

Added Prometheus service:
```yaml
prometheus:
  image: prom/prometheus:v2.48.0
  container_name: scp-prometheus
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - prometheus_data:/prometheus
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'
    - '--storage.tsdb.retention.time=15d'
```

**File:** `infra/prometheus/prometheus.yml`

Scrape configuration for all 5 services (15s interval).

### 5. Tests

**Files Created:**
- `services/shared/tests/unit/metrics/test_metrics_router.py` - Unit tests for metrics module
- `services/data-adapter/tests/test_metrics_endpoint.py` - Integration test example

## How to Use

### Starting Prometheus

**For local development (services running in terminal):**
```bash
# Start infrastructure only (uses prometheus.local.yml by default)
cd infra
docker-compose -f docker-compose.infra.yml up -d

# Then start your services in terminal
cd ../services/feature-engine
poetry run python -m feature_engine_svc.main

# Access Prometheus UI
open http://localhost:9090
```

**For Docker-based deployment (all services in Docker):**
```bash
# Start infrastructure + services (automatically uses prometheus.yml)
cd infra
docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.dev.yml up -d

# Access Prometheus UI
open http://localhost:9090
```

**Note:** `docker-compose.infra.yml` defaults to `prometheus.local.yml` (targets `host.docker.internal`) for local development. Environment overlays (services.yml, dev.yml, paper.yml, live.yml) automatically override to `prometheus.yml` (targets Docker service names).

### Querying Metrics

#### Check service health
```promql
# All services reporting
up{job=~"data-adapter|feature-engine|htf-bias|bot-core|execution"}

# Trading enabled status
scp_trading_enabled{mode="live"}

# Market data lag (should be < 1s in live mode)
scp_market_data_lag_seconds{mode="live", symbol="GC"}
```

#### Monitor signal flow
```promql
# Signals generated per minute (rate over 5m window)
rate(scp_signals_generated_total{mode="live"}[5m]) * 60

# Signal rejection rate by reason
rate(scp_signals_rejected_total{mode="live"}[5m]) by (reason)
```

#### Track data pipeline health
```promql
# Features computed per timeframe
rate(scp_features_computed_total{mode="live"}[5m]) by (timeframe)

# HTF bias changes (should be low)
rate(scp_htf_bias_changes_total{mode="live"}[1h])
```

### Setting Environment Mode

Set `SERVICE_MODE` environment variable in docker-compose or .env:
```bash
# In docker-compose.services.yml or overlay file
environment:
  - SERVICE_MODE=paper  # dev|test|replay|paper|live
```

### Accessing Metrics Directly

Each service exposes metrics at `/metrics`:
```bash
# Data Adapter
curl http://localhost:8001/metrics

# Feature Engine
curl http://localhost:8002/metrics

# HTF Bias
curl http://localhost:8003/metrics

# Bot Core
curl http://localhost:8004/metrics

# Execution
curl http://localhost:8005/metrics
```

## Next Steps (Future Work)

### High Priority
1. **Execution Service - Complete Order Tracking**
   - Add `scp_orders_sent_total`, `scp_orders_filled_total`, `scp_orders_rejected_total`
   - Add `scp_order_ack_seconds`, `scp_order_fill_seconds` histograms
   - Add `scp_open_positions`, `scp_daily_pnl`, `scp_daily_drawdown` gauges
   - Requires updating `TradeManager` class

2. **Alert Rules**
   - Create `infra/prometheus/alerts.yml` with critical alerts:
     - Trading enabled while unsafe_state == 1
     - Market data lag > thresholds
     - Orders rejected spike
     - Daily drawdown breach

3. **Grafana Dashboards**
   - System Overview dashboard
   - Trading Performance dashboard
   - Data Pipeline Health dashboard

### Medium Priority
4. **Infrastructure Metrics**
   - Add `scp_redis_connected`, `scp_db_pool_saturation`, `scp_db_query_seconds`
   - Requires instrumentation in database and Redis client wrappers

5. **Additional Tests**
   - Integration tests for Feature Engine, HTF Bias, Bot Core, Execution
   - Tests verifying metric increments on actual events

### Low Priority
6. **OpenTelemetry Tracing**
   - Distributed tracing across services
   - Trace signal flow from candle → trade

## Testing

Run tests for metrics:
```bash
# Test shared metrics module
cd services/shared
poetry run pytest tests/unit/metrics/ -v

# Test Data Adapter metrics endpoint
cd services/data-adapter
poetry run pytest tests/test_metrics_endpoint.py -v
```

## Architecture Compliance

This implementation follows the architecture principles defined in `.cursor/rules/microservices_architecture.mdc`:

✅ All services expose `/metrics` endpoint  
✅ Consistent `scp_` prefix on all metrics  
✅ Global labels (`mode`, `service`) on all metrics  
✅ Finite label sets for high-cardinality fields (rejection reasons, etc.)  
✅ Prometheus container in infrastructure stack  
✅ Health checks remain independent of metrics  

## References

- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Plan Document](.cursor/plans/prometheus_metrics_implementation_2052e8b3.plan.md)
- [Microservices Architecture](.cursor/rules/microservices_architecture.mdc)
