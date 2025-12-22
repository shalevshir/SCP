# SCP Microservices

Microservices architecture for the SCP trading bot.

## Services

| Service | Port | Description |
|---------|------|-------------|
| **data-adapter** | 8001 | Live data ingestion and normalization |
| **feature-engine** | 8002 | Indicator computation (EMA, VWAP, RSI, structure) |
| **htf-bias** | 8003 | Higher-timeframe structure analysis |
| **bot-core** | 8004 | Signal generation, scoring, guardrails |
| **execution** | 8005 | Trade lifecycle, SL/TP, broker integration |
| **shared** | N/A | Shared utilities library |

## Development Workflow

### 1. Install Shared Library

```bash
make shared-install
```

### 2. Start Infrastructure

```bash
make infra-up
```

### 3. Develop Individual Service

```bash
cd services/data-adapter
poetry install
poetry run python -m data_adapter.main
```

### 4. Run Tests

```bash
# Shared library tests
make shared-test

# Service-specific tests
cd services/data-adapter
poetry run pytest

# Run tests with coverage for a single service
make service-test-coverage SERVICE=data-adapter

# Run tests with coverage for all services
make service-test-coverage-all
```

### 5. Coverage Reports

The project includes comprehensive test coverage tracking:

**Individual Service Coverage:**
```bash
# Test a specific service with detailed coverage
./scripts/test_coverage_service.sh execution

# Or using Make
make service-test-coverage SERVICE=execution
```

**Combined Coverage Report:**
```bash
# Test all services and generate combined report
./scripts/test_coverage_all.sh

# Or using Make
make service-test-coverage-all
```

**Output:**
- Individual reports: `services/<service-name>/coverage_html/index.html`
- Combined report: `coverage_reports/coverage_report.md`
- JSON summary: `coverage_reports/coverage_summary.json`

**Coverage Thresholds:**
- 🟢 Excellent: ≥ 80% coverage
- 🟡 Good: ≥ 60% coverage
- 🔴 Needs Improvement: < 60% coverage

## Service Architecture

```
┌─────────────┐
│ Data Adapter│ → candles.1m.{symbol}
└─────────────┘
       ↓
┌─────────────┐
│Feature Engine│ → features.{timeframe}
└─────────────┘
       ↓                    ↓
┌─────────────┐      ┌─────────────┐
│  HTF Bias   │      │  Bot Core   │ → signals.pending
└─────────────┘      └─────────────┘
       ↓                    ↓
       └──────────┬─────────┘
                  ↓
           ┌─────────────┐
           │ Execution   │ → trades.{opened,closed}
           └─────────────┘
```

## Communication

Services communicate via **Redis Streams**:
- `candles.1m.{symbol}` - Raw 1m candles
- `features.{timeframe}` - Computed features
- `htf.bias` - HTF bias updates
- `signals.pending` - Pending trade signals
- `trades.{opened,closed,invalidated}` - Trade events

## Configuration

Each service uses environment variables for configuration. See `.env.example` in `infra/` directory.

Common variables:
- `REDIS_URL` - Redis connection URL
- `DATABASE_URL` - PostgreSQL connection URL
- `SERVICE_NAME` - Service name for logging
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

## Next Steps

See [microservices_development_plan.mdc](../.cursor/rules/microservices_development_plan.mdc) for the complete implementation roadmap.

Phase 0 (Infrastructure Foundation) is complete. Next:
- **Phase 1:** Implement Redis Streams message flow
- **Phase 2:** Implement Data Adapter service
- **Phase 3:** Implement Feature Engine service
- **Phase 4:** Implement HTF Bias service
- **Phase 5:** Implement Bot Core service
- **Phase 6:** Implement Execution service

