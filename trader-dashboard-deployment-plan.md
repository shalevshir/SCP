# Trader Dashboard Deployment Plan

**Objective:** Deploy a real-time dashboard that provides market insights and signal scoring to help the trader make better decisions. No automated execution—signals are for display only.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRADER DASHBOARD ARCHITECTURE                        │
│                    (Decision Support - No Execution)                    │
└─────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │   IB GATEWAY    │
                    │  (Paper Mode)   │
                    └────────┬────────┘
                             │ ticks
                             ▼
┌───────────────────────────────────────────────────────────────┐
│               DATA ADAPTER (port 8001)                        │
│   • Tick aggregation → 1m candles                             │
│   • Multi-symbol: GC + DXY                                    │
│   • Publishes to Redis Streams                                │
└─────────────────────────────┬─────────────────────────────────┘
                              │ candles.1m.gc, candles.1m.dxy
                              ▼
┌───────────────────────────────────────────────────────────────┐
│            FEATURE ENGINE (port 8002)                         │
│   • EMA (9, 20, 50), VWAP, RSI, DXY correlation               │
│   • Structure labels, BOS/CHoCH                               │
│   • Persists to PostgreSQL                                    │
│   • Exposes Prometheus metrics                                │
└────────────────┬──────────────────────────────────────────────┘
                 │ features.1m
                 ▼
┌───────────────────────────────────────────────────────────────┐
│              HTF BIAS SERVICE (port 8003)                     │
│   • 15m/1h structure analysis                                 │
│   • Chop/conflict detection                                   │
│   • DXY alignment scoring                                     │
│   • Exposes Prometheus metrics                                │
└────────────────┬──────────────────────────────────────────────┘
                 │ htf.bias
                 ▼
┌───────────────────────────────────────────────────────────────┐
│                  BOT CORE (port 8004)                         │
│   • SignalEngine scoring                                      │
│   • Session validation                                        │
│   • Guardrails (display only)                                 │
│   • Exposes Prometheus metrics                                │
│   ┌─────────────────────────────────────────────────────────┐ │
│   │ ⚠️  signals.pending stream EXISTS but NOT CONSUMED      │ │
│   │    (No Execution Service in Trader Dashboard)           │ │
│   └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                    GRAFANA DASHBOARD                          │
│   ┌─────────────────────────────────────────────────────────┐ │
│   │ ROW 0: Hard Gates (Session, Enforcer, HTF, DXY, Psych)  │ │
│   │ ROW 0.5: GC/DXY Price Charts + VWAP Deviation           │ │
│   │ ROW 1-4: HTF Bias, Features, Structure                  │ │
│   │ ROW 5: A+ Scorecard & Decision Panel                    │ │
│   └─────────────────────────────────────────────────────────┘ │
│   Data Sources: Prometheus (metrics) + PostgreSQL (OHLC)      │
└───────────────────────────────────────────────────────────────┘
```

---

## 2. Services Matrix

| Service | Port | Deployed | Purpose |
|---------|------|---------|---------|
| Redis | 6379 | ✅ | Message streams |
| PostgreSQL | 5432 | ✅ | Data persistence |
| Prometheus | 9090 | ✅ | Metrics scraping |
| Grafana | 3000 | ✅ | Dashboard |
| Data Adapter | 8001 | ✅ | Live data ingestion |
| Feature Engine | 8002 | ✅ | Indicator computation |
| HTF Bias | 8003 | ✅ | Higher-timeframe analysis |
| Bot Core | 8004 | ✅ | Signal scoring (display only) |
| Execution | 8005 | ❌ | **NOT DEPLOYED** |

---

## 3. Prometheus Metrics Status

### ✅ Metrics Already Implemented

All services already expose `/metrics` endpoints with the `scp_` prefix convention:

| Service | Key Metrics | Status |
|---------|-------------|--------|
| Data Adapter | `scp_market_data_lag_seconds`, `scp_bars_emitted_total`, `scp_data_provider_connected` | ✅ Complete |
| Feature Engine | `scp_features_computed_total`, `scp_event_processing_seconds`, `scp_feature_queue_depth` | ✅ Complete |
| HTF Bias | `scp_htf_bias_current`, `scp_htf_bias_changes_total`, `scp_htf_processing_seconds` | ✅ Complete |
| Bot Core | `scp_signals_generated_total`, `scp_signals_rejected_total`, `scp_signal_generation_seconds` | ✅ Complete |
| Execution | `scp_trading_enabled`, `scp_unsafe_state` | ✅ Foundation |

### ⚠️ Dashboard Metric Mapping

The Grafana dashboard queries specific metric names. Verify these mappings match your implementation:

| Dashboard Query | Expected Metric | Notes |
|-----------------|-----------------|-------|
| `scp_session_valid` | May need alias or new metric | Check bot-core |
| `scp_htf_conflict_detected` | `scp_htf_bias_current` or derive | May need addition |
| `scp_htf_chop_detected` | Not in current metrics | May need addition |
| `scp_htf_dxy_aligned` | Not in current metrics | May need addition |
| `scp_signal_score` | Not in current metrics | May need addition |

**Action Required:** Either update the Grafana dashboard queries to use existing metrics, or add the missing metrics to the services.

### PostgreSQL Queries (Working)

These panels use TimescaleDB and work immediately:

| Query | Table | Dashboard Panel |
|-------|-------|-----------------|
| OHLC candles | `candles` | GC/DXY Price Charts |
| VWAP deviation | `features` | VWAP Deviation strip |
| EMA values | `features` | EMA overlays |

---

## 4. Implementation Tasks

### Phase 1A: Dashboard Metric Alignment (If Needed)

The existing metrics may not exactly match the Grafana dashboard queries. You have two options:

**Option 1: Update Dashboard Queries (Recommended)**

Modify the Grafana dashboard to use existing metrics:

```promql
# Instead of scp_htf_bias_direction, use:
scp_htf_bias_current{mode="$mode"}

# For session validity, check data flow:
scp_data_provider_connected{mode="$mode"}
```

**Option 2: Add Missing Dashboard Metrics**

If specific dashboard metrics are required, add them to the respective services:

```python
# htf-bias/src/htf_bias_svc/metrics.py - add these gauges:
htf_conflict_detected = create_gauge("htf_conflict_detected", "Timeframe conflict detected")
htf_chop_detected = create_gauge("htf_chop_detected", "Chop market detected")  
htf_dxy_aligned = create_gauge("htf_dxy_aligned", "DXY correlation aligned")

# bot-core/src/bot_core_svc/metrics.py - add these gauges:
session_valid = create_gauge("session_valid", "Trading session is valid")
signal_score = create_gauge("signal_score", "Current signal score 0-10")
```

### Phase 1B: Docker Compose for Trader Dashboard

Create `docker-compose.trader-dashboard.yml` (already provided in output files).

```yaml
# Trader Dashboard (No Execution)
# Usage: docker compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.trader-dashboard.yml up --build

services:
  data-adapter:
    container_name: scp-data-adapter-dashboard
    environment:
      SERVICE_MODE: dashboard
      DATA_PROVIDER: ib
      IB_HOST: ${IB_HOST:-host.docker.internal}
      IB_PORT: ${IB_PORT:-4002}  # Paper trading port
      IB_CLIENT_ID: 1
      SESSION_FILTER_ENABLED: "true"
      LOG_LEVEL: INFO
    extra_hosts:
      - "host.docker.internal:host-gateway"

  feature-engine:
    container_name: scp-feature-engine-dashboard
    environment:
      SERVICE_MODE: dashboard
      LOG_LEVEL: INFO
      WARMUP_ENABLED: "true"

  htf-bias:
    container_name: scp-htf-bias-dashboard
    environment:
      SERVICE_MODE: dashboard
      LOG_LEVEL: INFO

  bot-core:
    container_name: scp-bot-core-dashboard
    environment:
      SERVICE_MODE: dashboard
      SESSION_VALIDATION_ENABLED: "true"
      # Signal generation active, but no consumer
      LOG_LEVEL: INFO

  # EXECUTION SERVICE IS NOT STARTED IN TRADER DASHBOARD
  execution:
    profiles:
      - disabled  # Prevents this service from starting

  prometheus:
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
```

### Phase 1C: Prometheus Configuration

✅ **Already configured** per `PROMETHEUS_METRICS_IMPLEMENTATION.md`.

Verify `prometheus/prometheus.yml` includes these targets:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'scp-services'
    static_configs:
      - targets:
          - 'data-adapter:8001'
          - 'feature-engine:8002'
          - 'htf-bias:8003'
          - 'bot-core:8004'
    metrics_path: /metrics
    scrape_interval: 5s
```

### Phase 1D: Grafana Provisioning

Ensure datasources are configured in `grafana/provisioning/datasources/datasources.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    uid: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false

  - name: PostgreSQL
    type: postgres
    uid: postgres
    access: proxy
    url: postgres:5432
    database: scp
    user: scp
    secureJsonData:
      password: ${POSTGRES_PASSWORD}
    jsonData:
      sslmode: disable
      maxOpenConns: 10
      maxIdleConns: 10
      connMaxLifetime: 14400
    editable: false
```

---

## 5. Deployment Steps

### Step 1: Pre-flight Checks

```bash
# 1. Verify IB Gateway is running (paper mode, port 4002)
nc -zv localhost 4002

# 2. Check environment variables
cat .env
# Should contain:
# POSTGRES_PASSWORD=your_secure_password
# GRAFANA_PASSWORD=your_grafana_password
# IB_HOST=host.docker.internal
# IB_PORT=4002
```

### Step 2: Build and Deploy Infrastructure

```bash
# Start infrastructure only first
docker compose -f docker-compose.infra.yml up -d

# Wait for PostgreSQL migrations
docker logs -f scp-postgres 2>&1 | grep -m1 "database system is ready"

# Verify Grafana is accessible
curl -s http://localhost:3000/api/health | jq
```

### Step 3: Deploy Trader Dashboard Services

```bash
# Build and start Trader Dashboard services
docker compose \
  -f docker-compose.infra.yml \
  -f docker-compose.services.yml \
  -f docker-compose.trader-dashboard.yml \
  up --build -d

# Check service health
for port in 8001 8002 8003 8004; do
  echo "Port $port: $(curl -s http://localhost:$port/health | jq -r '.status')"
done
```

### Step 4: Verify Data Flow

```bash
# 1. Check Redis streams are receiving data
docker exec scp-redis redis-cli XLEN candles.1m.gc

# 2. Check PostgreSQL has candles
docker exec scp-postgres psql -U scp -d scp -c \
  "SELECT COUNT(*) FROM candles WHERE timestamp > NOW() - INTERVAL '5 minutes';"

# 3. Check Prometheus is scraping metrics
curl -s "http://localhost:9090/api/v1/targets" | jq '.data.activeTargets[].health'

# 4. Query a metric
curl -s "http://localhost:9090/api/v1/query?query=scp_htf_bias_direction" | jq
```

### Step 5: Access Dashboard

1. Open Grafana: http://localhost:3000
2. Login: admin / (your GRAFANA_PASSWORD)
3. Navigate to: Dashboards → SCP Trader A+ Decision Dashboard
4. Select Mode: `dashboard` from dropdown

---

## 6. Validation Checklist

### Data Pipeline

- [ ] IB Gateway connected and streaming ticks
- [ ] Data Adapter publishing candles to Redis
- [ ] Feature Engine computing indicators
- [ ] HTF Bias calculating direction/confidence
- [ ] Bot Core generating signal scores
- [ ] Prometheus scraping all services successfully

### Dashboard Panels

| Panel | Data Source | Expected Behavior |
|-------|-------------|-------------------|
| Session/Mode | Prometheus | Shows VALID during trading hours |
| Enforcer Tier | Prometheus | Shows current tier (1-4) |
| HTF Verdict | Prometheus | PASS when no conflict/chop |
| DXY Alignment | Prometheus | ALIGNED when inverse correlation holds |
| GC Price Chart | PostgreSQL | Live OHLC candlesticks |
| DXY Price Chart | PostgreSQL | Live OHLC candlesticks |
| VWAP Deviation | PostgreSQL | Colored zones based on deviation |
| HTF Bias | Prometheus | Bullish/Bearish/Neutral with score |
| A+ Verdict | Prometheus | Score × gates = final verdict |

### What the Trader Should See

1. **Before Market Open:**
   - Session: INVALID (red)
   - All gates in standby mode
   - Historical charts visible

2. **During Session:**
   - Session: VALID (green)
   - Real-time price updates
   - HTF Bias updating at 15m/1h boundaries
   - Signal score updating each minute
   - A+ Verdict panel showing GO/NO-GO

3. **A+ Signal Scenario:**
   - Session: VALID
   - HTF Verdict: PASS
   - DXY Alignment: ALIGNED
   - Signal Score: ≥8.0
   - **A+ VERDICT: "A+ — EXECUTION PERMITTED"** (green)

---

## 7. Troubleshooting

### No Data in Charts

```bash
# Check if candles are being stored
docker exec scp-postgres psql -U scp -d scp -c \
  "SELECT * FROM candles ORDER BY timestamp DESC LIMIT 5;"

# Check data adapter logs
docker logs scp-data-adapter-stage1 --tail 100
```

### Prometheus Metrics Empty

```bash
# Check if metrics endpoint exists
curl http://localhost:8002/metrics

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job, health, lastError}'
```

### Dashboard Shows "No Data"

1. Verify `mode` variable matches `SERVICE_MODE` in environment (use `dashboard`)
2. Check time range (dashboard defaults to last 15m)
3. Verify PostgreSQL datasource credentials in Grafana

---

## 8. Success Criteria for Trader Dashboard

Before proceeding to Paper Trading, validate:

| Criteria | Target | Validation Method |
|----------|--------|-------------------|
| Data latency | < 2 seconds | Compare candle timestamp to wall clock |
| Feature accuracy | Match TradingView | Spot-check EMA/RSI values |
| HTF Bias stability | No flip-flopping | Review bias changes over 1 day |
| Signal quality | Trader agrees with A+ calls | Manual review of 20+ signals |
| System uptime | > 99% during session | Check container restart counts |
| Dashboard usability | Trader can use effectively | Feedback session |

**Minimum Duration:** 1-2 weeks of live observation before Stage 2.

---

## 9. What's NOT in Trader Dashboard

| Component | Reason | Stage |
|-----------|--------|-------|
| Execution Service | No automated trading yet | Paper Trading |
| Position Management | No trades to manage | Paper Trading |
| P&L Tracking | No trades to track | Paper Trading |
| Kill Switch | No execution to halt | Live Trading |
| Alerting (PagerDuty) | Decision support only | Live Trading |

---

## Appendix: Files to Create/Modify

### New Files

1. `infra/docker-compose.trader-dashboard.yml` - Trader Dashboard overlay (provided)

### Already Implemented (per PROMETHEUS_METRICS_IMPLEMENTATION.md)

- ✅ `services/*/metrics.py` - All services have metrics
- ✅ `infra/prometheus/prometheus.yml` - Scrape config exists
- ✅ `/metrics` endpoint on all services

### May Need Updates

1. `infra/grafana/dashboards/trader-decision.json` - Update queries to match existing metrics
2. HTF Bias service - Add `scp_htf_conflict_detected`, `scp_htf_chop_detected`, `scp_htf_dxy_aligned` if needed
3. Bot Core service - Add `scp_session_valid`, `scp_signal_score` if needed

---

*Document Version: 1.1*
*Last Updated: Trader Dashboard Planning (metrics already implemented)*
