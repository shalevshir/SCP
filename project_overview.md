---
description: high-level overview of the project - architecture, module structure, development phases, and key configuration. It's a reference guide for understanding how the system is organized.
alwaysApply: false
---
# Shir Capital Partners — Trading Bot Project Overview

**Structure before signal. Discipline before profit. Legacy above all.**

## 1. Current Status

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| **Phase 0** | Infrastructure Foundation | ✅ Complete | Docker, Redis, PostgreSQL/TimescaleDB |
| **Phase 1** | Shared Messaging Layer | ✅ Complete | Redis Streams pub/sub, Pydantic schemas |
| **Phase 2** | Data Adapter Service | ✅ Complete | Live data ingestion, candle aggregation |
| **Phase 3** | Feature Engine Service | ✅ Complete | Indicator computation, HTF aggregation |
| **Phase 4** | HTF Bias Service | ✅ Complete | Higher-timeframe structure analysis |
| **Phase 5** | Bot Core Service | ✅ Complete | Signal generation, guardrails |
| **Phase 6** | Execution Service | ✅ Complete | Trade lifecycle, SL/TP, broker integration |
| **Phase 7** | Integration Testing | ✅ Complete | End-to-end pipeline validation |
| **Phase 8** | Replay Mode Validation | ⏳ Pending | Compare with backtester results |
| **Phase 9** | Paper Trading | ⏳ Pending | Live market validation |

**Progress:** 7/10 Phases Complete (70%)

---

## 2. System Architecture

```
                    ┌─────────────────┐
                    │   DATABENTO /   │
                    │   BROKER WS     │
                    └────────┬────────┘
                             │ ticks (real-time)
                             ▼
┌───────────────────────────────────────────────────────────────┐
│                      DATA ADAPTER (8001)                      │
│   • Tick aggregation → 1m candles                             │
│   • Gap detection & historical backfill                       │
│   • Session awareness (trading hours filter)                  │
└─────────────────────────────┬─────────────────────────────────┘
                              │ Redis: candles.1m.{gc,dxy}
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                  FEATURE ENGINE (8002)                        │
│   • EMA (9, 20, 50), VWAP, RSI, DXY correlation               │
│   • Structure labels (HH/HL/LH/LL, BOS, CHoCH)                │
│   • HTF aggregation (15m, 1h)                                 │
└───────────────┬───────────────────────────┬───────────────────┘
                │ features.1m               │ features.15m/1h
                │                           ▼
                │               ┌───────────────────────────┐
                │               │    HTF BIAS (8003)        │
                │               │  • 15m/1h structure       │
                │               │  • Chop/conflict detect   │
                │               └───────────┬───────────────┘
                │                           │ htf.bias
                ▼                           ▼
┌───────────────────────────────────────────────────────────────┐
│                      BOT CORE (8004)                          │
│   • Setup detection (VWAP_RECLAIM, VWAP_FADE, DXY_CONT)       │
│   • Signal scoring (8+/10 threshold)                          │
│   • BehaviorGuardrails (loss streak, fatigue)                 │
│   • Session validation                                        │
└─────────────────────────────┬─────────────────────────────────┘
                              │ signals.pending (A+ only)
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                    EXECUTION (8005)                           │
│   • VWAPReclaimStateMachine lifecycle                         │
│   • Entry at next bar open                                    │
│   • SL/TP monitoring                                          │
│   • InvalidationChecker (PDLL, structure break)               │
│   • Paper / Live broker integration                           │
└─────────────────────────────┬─────────────────────────────────┘
                              │ trades.{opened,closed}
                              ▼
                    ┌─────────────────┐
                    │   PostgreSQL /  │
                    │   TimescaleDB   │
                    └─────────────────┘
```

---

## 3. Services

| Service | Port | Path | Description |
|---------|------|------|-------------|
| **data-adapter** | 8001 | `services/data-adapter/` | Live data ingestion, candle aggregation |
| **feature-engine** | 8002 | `services/feature-engine/` | Indicator computation (EMA, VWAP, RSI, structure) |
| **htf-bias** | 8003 | `services/htf-bias/` | Higher-timeframe structure analysis |
| **bot-core** | 8004 | `services/bot-core/` | Signal generation, scoring, guardrails |
| **execution** | 8005 | `services/execution/` | Trade lifecycle, SL/TP, broker integration |
| **shared** | N/A | `services/shared/` | Shared library used by all services |

---

## 4. Shared Library (`scp_shared`)

The shared library contains all business logic and is imported by all services.

| Module | Path | Function |
|--------|------|----------|
| **common** | `scp_shared/common/` | Logger, types, config, exceptions |
| **messaging** | `scp_shared/messaging/` | Redis Streams pub/sub, Pydantic schemas |
| **database** | `scp_shared/database/` | PostgreSQL connection, repositories |
| **health** | `scp_shared/health/` | FastAPI health check endpoints |
| **indicators** | `scp_shared/indicators/` | EMA, RSI, VWAP, structure detection, DXY correlation |
| **rule_engine** | `scp_shared/rule_engine/` | HTF bias, scoring, signal generation, setup detectors |
| **validation** | `scp_shared/validation/` | Session validator, behavior guardrails |
| **execution** | `scp_shared/execution/` | Invalidation logic, trade types |

---

## 5. Service Details

### 5.1 Data Adapter (`services/data-adapter/`)

Connects to Databento, aggregates ticks into candles, publishes to Redis.

| Module | Function |
|--------|----------|
| `candle_aggregator.py` | Tick → 1m candle aggregation |
| `databento_client.py` | WebSocket connection to Databento |
| `gap_detector.py` | Detect and backfill missing candles |
| `session_filter.py` | Filter non-trading hours |
| `publisher.py` | Publish candles to Redis Streams |

### 5.2 Feature Engine (`services/feature-engine/`)

Consumes candles, computes indicators, publishes enriched features.

| Module | Function |
|--------|----------|
| `processor.py` | Wraps `StreamingFeatureProcessor` |
| `htf_aggregator.py` | Aggregate 1m → 15m/1h candles |
| `publisher.py` | Publish features to Redis Streams |
| `repository.py` | Persist features to database |

### 5.3 HTF Bias (`services/htf-bias/`)

Analyzes higher-timeframe structure for trade direction.

| Module | Function |
|--------|----------|
| `processor.py` | Wraps `StreamingHTFBiasCalculator` |
| `publisher.py` | Publish bias updates to Redis |
| `repository.py` | Persist bias history to database |

### 5.4 Bot Core (`services/bot-core/`)

Generates signals based on features and HTF bias.

| Module | Function |
|--------|----------|
| `signal_engine.py` | Wraps `score_signal`, generates signals |
| `guardrails.py` | Loss streak, fatigue detection |
| `session.py` | Session validation with caching |
| `bias_cache.py` | HTF bias caching with TTL |
| `publisher.py` | Publish A+ signals to Redis |
| `state_repository.py` | Persist daily state to database |

### 5.5 Execution (`services/execution/`)

Manages trade lifecycle and broker integration.

| Module | Function |
|--------|----------|
| `state_machine_manager.py` | Manage `VWAPReclaimStateMachine` instances |
| `trade_manager.py` | Trade lifecycle, SL/TP monitoring |
| `trade_repository.py` | Persist trades to database |
| `trade_publisher.py` | Publish trade events to Redis |
| `daily_state.py` | Daily P&L tracking |
| `broker/paper.py` | Paper trading simulation |
| `broker/base.py` | Broker interface (for live integration) |

---

## 6. Communication (Redis Streams)

| Stream | Publisher | Consumer | Content |
|--------|-----------|----------|---------|
| `candles.1m.gc` | Data Adapter | Feature Engine | 1m Gold candles |
| `candles.1m.dxy` | Data Adapter | Feature Engine | 1m DXY candles |
| `features.1m` | Feature Engine | Bot Core | Enriched 1m features |
| `features.15m` | Feature Engine | HTF Bias | 15m features |
| `features.1h` | Feature Engine | HTF Bias | 1h features |
| `htf.bias` | HTF Bias | Bot Core | Bias updates |
| `signals.pending` | Bot Core | Execution | A+ trade signals |
| `trades.opened` | Execution | — | Trade opened events |
| `trades.closed` | Execution | — | Trade closed events |

---

## 7. Test Coverage

| Service | Coverage | Status |
|---------|----------|--------|
| **shared** | 73.5% | 🟡 Good |
| **execution** | 64.3% | 🟡 Good |
| **feature-engine** | 63.9% | 🟡 Good |
| **htf-bias** | 63.4% | 🟡 Good |
| **data-adapter** | 45.8% | 🔴 Needs Improvement |
| **bot-core** | 37.6% | 🔴 Needs Improvement |
| **TOTAL** | **68.8%** | 🟡 Good |

**Test Files:** 250+ across all services

---

## 8. Setup Types & Scoring

Trades must score **8+/10** to qualify as A+ confidence:

| Setup Type | Key Factors | Min Score |
|------------|-------------|-----------|
| **VWAP_RECLAIM** | Structure alignment, VWAP relation, RSI mid-reset, EMA stack, DXY correlation | 8 |
| **VWAP_FADE** | VWAP deviation, RSI extreme, rejection candle, volume spike | 8 |
| **DXY_CONTINUATION** | DXY correlation (primary), structure alignment, RSI mid-reset | 8 |

---

## 9. Risk & Capital Framework

| Phase | Buffer | Risk/Trade | Daily Max Loss | Target R:R |
|-------|--------|------------|----------------|------------|
| Startup | 0–5K | $350 | $600 | 3:1 |
| Growth | 5–15K | $450–600 | $900–1K | 3:1 |
| Scaling | 15–40K | $700–1K | $1.5–2K | 3:1 |
| Institutional | 40K+ | $1.2K+ | $2.5K+ | 3:1 |

**Enforcer Tiers:** Conservative, Early Mild, Mild, Offensive

---

## 10. Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Core** | Python 3.11+ | All services |
| **Data** | Pandas, NumPy | Time-series processing |
| **Data Source** | Databento | Market data API |
| **Messaging** | Redis Streams | Inter-service communication |
| **Database** | PostgreSQL + TimescaleDB | Persistence, time-series |
| **API** | FastAPI | Health endpoints |
| **Container** | Docker, Docker Compose | Deployment |
| **Testing** | pytest, pytest-xdist | TDD framework |
| **Linting** | ruff, black, isort, mypy | Code quality |
| **Package Manager** | Poetry | Dependency management |

---

## 11. Development Workflow

```bash
# Start infrastructure (Redis + PostgreSQL)
make infra-up

# Install shared library
make shared-install

# Run service tests
cd services/bot-core
poetry run pytest tests/ -v

# Run all service tests with coverage
make service-test-coverage-all

# Start all services
docker-compose -f infra/docker-compose.yml -f infra/docker-compose.services.yml up -d

# Check service health
curl http://localhost:8001/health  # data-adapter
curl http://localhost:8002/health  # feature-engine
curl http://localhost:8003/health  # htf-bias
curl http://localhost:8004/health  # bot-core
curl http://localhost:8005/health  # execution
```

---

## 12. Configuration

| File | Purpose |
|------|---------|
| `services/shared/config/scoring_config.yaml` | Setup types, factor weights, thresholds |
| `config/validation.yaml` | Validation rules, session constraints |
| `infra/docker-compose.yml` | Infrastructure (Redis, PostgreSQL) |
| `infra/docker-compose.services.yml` | Service definitions |

**Environment Variables:**
- `REDIS_URL` — Redis connection URL
- `DATABASE_URL` — PostgreSQL connection URL
- `SERVICE_NAME` — Service name for logging
- `LOG_LEVEL` — Logging level (DEBUG, INFO, WARNING, ERROR)
- `DATABENTO_API_KEY` — Databento API key (data-adapter)
- `BROKER_MODE` — `paper` or `live` (execution)

---

## 13. Key Concepts

- **HTF Bias**: Higher timeframe (15m/1H) structure analysis determining trade direction
- **BOS (Break of Structure)**: Confirmation of trend continuation
- **CHoCH (Change of Character)**: Potential trend reversal signal
- **FVG (Fair Value Gap)**: Imbalance zones for price targets/stops
- **Liquidity Sweep**: Institutional order flow indication
- **Protected Levels**: Swing points that define SL placement
- **VWAP Reclaim**: Price reclaiming VWAP as entry signal

---

## 14. Next Steps

1. **Phase 8: Replay Mode Validation** — Compare microservices output with backtester results
2. **Phase 9: Paper Trading** — Live market validation for 1+ week
3. **Phase 10: Production Deployment** — Gradual rollout with live orders

---

*See `services/README.md` for service-specific documentation, `.cursor/rules/microservices_development_plan.mdc` for complete implementation roadmap.*
