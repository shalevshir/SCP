# Microservices Roadmap

**Document Version:** 1.0  
**Last Updated:** 2026-01-12  
**Status:** Active Development

This document outlines the comprehensive plan for completing the microservices architecture migration. Work is organized into **Epics** (large initiatives), **Stories** (user-facing deliverables), and **Tasks** (specific implementation work).

---

## Current State Summary

### ✅ Completed
- All 5 core services implemented (Data Adapter, Feature Engine, HTF Bias, Bot Core, Execution)
- Docker Compose infrastructure (Redis, TimescaleDB)
- Redis Streams messaging with consumer groups
- Database migrations and state persistence
- Warmup/recovery from DB for all services
- Replay mode support

### 🔄 In Progress
- Backtester parity validation
- Integration test suite

### ⏳ Pending
- Live data integration (Databento)
- Real broker integration
- Observability stack
- Production deployment

---

## Epic 1: Integration Testing & Parity Validation

**Goal:** Ensure microservices produce identical results to the legacy backtester for the same input data.

**Priority:** 🔴 Critical  
**Estimated Duration:** 2-3 weeks

### Story 1.1: Backtester Parity Test Suite

**As a** developer  
**I want** automated tests comparing microservices output to backtester output  
**So that** I can verify the microservices implementation is correct

#### Task 1.1.1: Create Parity Test Framework

**Description:**  
Build a test framework that:
1. Runs the legacy backtester on a known dataset
2. Runs the same data through the microservices pipeline
3. Compares signals, trades, and final P&L
4. Reports discrepancies with detailed diffs

**Acceptance Criteria:**
- Framework can run both systems on same CSV data
- Comparison report shows signal-by-signal and trade-by-trade diffs
- Clear pass/fail status for each comparison category

**Implementation Notes:**
- Use `scripts/compare_microservices_backtester.py` as starting point
- Output JSON comparison report (like `output/comparison_report_*.json`)
- Include timestamp, direction, score, entry/exit prices in comparison

---

#### Task 1.1.2: Signal Generation Parity Tests

**Description:**  
Create tests verifying that Bot Core generates identical signals to the backtester's `score_signal()` for the same features and HTF bias.

**Acceptance Criteria:**
- Test with known feature snapshots and expected signal output
- Verify signal timing (same bar index generates signal)
- Verify signal fields: direction, setup_type, score, confidence, entry/SL/TP prices
- Test edge cases: neutral bias, missing DXY, session boundaries

**Implementation Notes:**
- Create fixtures with captured features from backtester runs
- Compare `SignalMessage` output field-by-field
- Log any scoring differences with contributing factors

---

#### Task 1.1.3: Trade Execution Parity Tests

**Description:**  
Verify Execution Service produces same trade outcomes as backtester simulator for identical signals and candle data.

**Acceptance Criteria:**
- Same entry timing (next bar open after signal)
- Same SL/TP calculations
- Same invalidation triggers (structure breaks, time expiry, VWAP slope)
- Same exit prices and P&L calculations

**Implementation Notes:**
- Test `TradeManager.execute_pending_signals()` with known candle sequences
- Test `InvalidationChecker` with known invalidation scenarios
- Compare `TradeMessage` pnl_points to backtester `trade.pnl_points`

---

#### Task 1.1.4: Multi-Day Replay Parity Test

**Description:**  
Run a full multi-day (e.g., Nov 5-11, 2024) replay through both systems and compare all outputs.

**Acceptance Criteria:**
- Same number of signals generated
- Same number of trades executed
- Same win/loss distribution
- Final P&L within acceptable tolerance (< 0.1% difference)

**Implementation Notes:**
- Use `make replay-validate` as baseline
- Store backtester results in JSON for comparison
- Create diff report showing any discrepancies

---

### Story 1.2: Integration Test Suite

**As a** developer  
**I want** end-to-end integration tests for the microservices pipeline  
**So that** I can catch regressions when making changes

#### Task 1.2.1: Docker-Based Integration Test Infrastructure

**Description:**  
Create a test infrastructure that spins up all services in Docker and runs integration tests against them.

**Acceptance Criteria:**
- `make test-integration` starts all services and runs tests
- Tests can inject candles into Redis streams
- Tests can read trade output from Redis streams
- Cleanup after tests (reset state via `/admin/reset`)

**Implementation Notes:**
- Use `docker-compose.test.yml` for test environment
- Add pytest fixtures for service health checks
- Use `httpx` for async HTTP calls to services

---

#### Task 1.2.2: Message Flow Integration Tests

**Description:**  
Test that messages flow correctly through the entire pipeline: candles → features → bias → signals → trades.

**Acceptance Criteria:**
- Test candle published to `candles.1m.gc` appears in `features.1m`
- Test feature message with setup conditions generates signal in `signals.pending`
- Test signal results in trade in `trades.opened`
- Test trade SL/TP hit results in `trades.closed`

**Implementation Notes:**
- Create helper functions to publish test candles
- Use `RedisStreamConsumer` to verify message arrival
- Add timeouts for message propagation (services may have processing delays)

---

#### Task 1.2.3: State Recovery Integration Tests

**Description:**  
Test that services correctly recover state after restart.

**Acceptance Criteria:**
- Feature Engine resumes with correct indicator values after restart
- HTF Bias Service resumes with correct bias after restart
- Execution Service restores active trades after restart
- Bot Core restores daily state (loss streak, trade count) after restart

**Implementation Notes:**
- Start services, process some data, stop services, restart, verify state
- Use database queries to verify persisted state
- Compare pre-restart and post-restart outputs for same input

---

#### Task 1.2.4: Error Handling Integration Tests

**Description:**  
Test system behavior under error conditions.

**Acceptance Criteria:**
- System handles Redis connection drops gracefully
- System handles database connection drops gracefully
- System handles malformed messages without crashing
- Services reconnect automatically after transient failures

**Implementation Notes:**
- Use `docker pause` to simulate service/infrastructure failures
- Verify services log errors appropriately
- Verify no data loss or corruption after recovery

---

### Story 1.3: Scoring Parity Deep Dive

**As a** developer  
**I want** detailed analysis of any scoring differences between systems  
**So that** I can identify and fix root causes

#### Task 1.3.1: Scoring Factor Comparison

**Description:**  
Create detailed comparison of each scoring factor between backtester and microservices.

**Acceptance Criteria:**
- Compare: HTF alignment, VWAP reclaim, DXY correlation, structure, seasonality
- Identify which factors diverge
- Document root causes of divergence

**Implementation Notes:**
- Instrument both systems to log individual factor scores
- Create side-by-side comparison for same timestamp
- Use `test_scoring_parity.py` as starting point

---

#### Task 1.3.2: HTF Bias Calculation Parity

**Description:**  
Ensure HTF Bias Service calculates identical bias to backtester's `calculate_htf_bias()`.

**Acceptance Criteria:**
- Same bias direction (bullish/bearish/neutral)
- Same confidence level (A+/A/B/C)
- Same score (within 0.1 tolerance)
- Same dxy_aligned, chop_detected flags

**Implementation Notes:**
- Compare `HTFBiasMessage` to backtester's `htf_bias` dict
- Test at 15m and 1h boundaries
- Verify seasonality_adjustment and vwap_trend_confirmed

---

---

## Epic 2: Observability & Monitoring

**Goal:** Add comprehensive observability to all services for production readiness.

**Priority:** 🟡 High  
**Estimated Duration:** 1-2 weeks

### Story 2.1: Prometheus Metrics

**As an** operator  
**I want** Prometheus metrics from all services  
**So that** I can monitor system health and performance

#### Task 2.1.1: Add Metrics Library to Shared

**Description:**  
Add `prometheus-client` to `scp_shared` with helper functions for common metric types.

**Acceptance Criteria:**
- `scp_shared.metrics` module with Counter, Gauge, Histogram helpers
- Consistent metric naming convention (e.g., `scp_service_metric_name`)
- Labels for service, instance, environment

**Implementation Notes:**
```python
# scp_shared/metrics/registry.py
from prometheus_client import Counter, Gauge, Histogram, REGISTRY

def create_counter(name: str, description: str, labels: list[str]) -> Counter:
    return Counter(f"scp_{name}_total", description, labels)
```

---

#### Task 2.1.2: Data Adapter Metrics

**Description:**  
Add metrics to Data Adapter service.

**Metrics to implement:**
- `scp_candles_published_total{symbol, timeframe}` - Candles published
- `scp_gaps_detected_total{symbol}` - Gap detection events
- `scp_tick_processing_seconds` - Tick processing latency histogram

**Acceptance Criteria:**
- Metrics available at `/metrics` endpoint
- Metrics update in real-time as data flows

---

#### Task 2.1.3: Feature Engine Metrics

**Description:**  
Add metrics to Feature Engine service.

**Metrics to implement:**
- `scp_features_computed_total{timeframe}` - Features computed
- `scp_feature_computation_seconds{timeframe}` - Computation latency
- `scp_warmup_complete{timeframe}` - Warmup status gauge
- `scp_synchronizer_buffer_size{symbol}` - Candle sync buffer size

**Acceptance Criteria:**
- Metrics show warmup progress
- Latency histogram shows processing time distribution

---

#### Task 2.1.4: HTF Bias Metrics

**Description:**  
Add metrics to HTF Bias service.

**Metrics to implement:**
- `scp_bias_updates_total{bias}` - Bias updates by direction
- `scp_chop_detected_total` - Chop detection events
- `scp_bias_computation_seconds` - Computation latency

---

#### Task 2.1.5: Bot Core Metrics

**Description:**  
Add metrics to Bot Core service.

**Metrics to implement:**
- `scp_signals_generated_total{setup_type, confidence}` - Signals by type
- `scp_signals_rejected_total{reason}` - Rejected signals by reason
- `scp_guardrail_blocks_total{guardrail}` - Guardrail blocks
- `scp_bias_cache_size` - HTFBiasCache entries gauge

---

#### Task 2.1.6: Execution Service Metrics

**Description:**  
Add metrics to Execution service.

**Metrics to implement:**
- `scp_trades_opened_total{direction, setup_type}` - Trades opened
- `scp_trades_closed_total{exit_reason}` - Trades closed by reason
- `scp_active_trades` - Active trades gauge
- `scp_pending_signals` - Pending signals gauge
- `scp_daily_pnl_points` - Daily P&L gauge
- `scp_loss_streak` - Current loss streak gauge

---

#### Task 2.1.7: Grafana Dashboards

**Description:**  
Create Grafana dashboards for monitoring the trading system.

**Dashboards to create:**
1. **System Overview** - All services health, message rates, latencies
2. **Trading Performance** - Signals, trades, P&L, win rate
3. **Data Pipeline** - Candle flow, feature computation, sync buffer health

**Acceptance Criteria:**
- Dashboards importable via JSON
- Key metrics visible at a glance
- Alerts configurable from dashboard

---

### Story 2.2: Distributed Tracing

**As an** operator  
**I want** distributed tracing across services  
**So that** I can debug latency issues and trace request flows

#### Task 2.2.1: Add OpenTelemetry to Shared

**Description:**  
Add OpenTelemetry instrumentation to `scp_shared`.

**Acceptance Criteria:**
- Trace context propagates across Redis messages
- Spans created for key operations (candle processing, signal generation)
- Configurable exporter (Jaeger, OTLP)

**Implementation Notes:**
- Use `opentelemetry-instrumentation-fastapi` for HTTP
- Use `opentelemetry-instrumentation-redis` for Redis
- Create custom spans for business logic

---

#### Task 2.2.2: Instrument All Services

**Description:**  
Add tracing spans to all services.

**Key spans:**
- `data_adapter.candle_published`
- `feature_engine.features_computed`
- `htf_bias.bias_computed`
- `bot_core.signal_generated`
- `execution.trade_opened`
- `execution.trade_closed`

**Acceptance Criteria:**
- Full trace visible from candle → trade in Jaeger
- Span tags include relevant context (symbol, direction, setup_type)

---

### Story 2.3: Enhanced Logging

**As an** operator  
**I want** structured, queryable logs  
**So that** I can debug issues efficiently

#### Task 2.3.1: Structured Log Format

**Description:**  
Ensure all services use consistent structured JSON logging.

**Acceptance Criteria:**
- All logs in JSON format with consistent fields
- Fields: timestamp, level, service, message, context
- Correlation IDs for tracing related log entries

**Implementation Notes:**
- Use `structlog` or enhance `scp_shared.common.logger`
- Add request_id/trace_id to log context
- Configure log level via environment variable

---

#### Task 2.3.2: Log Aggregation Setup

**Description:**  
Set up log aggregation for all services.

**Options:**
- Loki + Grafana (lightweight, good with Prometheus)
- ELK Stack (more powerful, heavier)

**Acceptance Criteria:**
- All service logs visible in single UI
- Searchable by service, level, timestamp
- Log retention policy configured

---

---

## Epic 3: Live Data Integration

**Goal:** Connect to real-time market data from Databento.

**Priority:** 🟡 High  
**Estimated Duration:** 2 weeks

### Story 3.1: Databento Client Implementation

**As a** system  
**I want** to receive real-time tick data from Databento  
**So that** I can generate live trading signals

#### Task 3.1.1: Databento SDK Integration

**Description:**  
Implement real `DatabentoClient` class that connects to Databento WebSocket API.

**Acceptance Criteria:**
- Connects to Databento with API key
- Subscribes to GC and DXY tick streams
- Handles reconnection on disconnect
- Logs connection state changes

**Implementation Notes:**
```python
# services/data-adapter/src/data_adapter/databento_client.py
class DatabentoClient(DatabentoClientBase):
    def __init__(self, api_key: str, symbols: list[str]):
        self.api_key = api_key
        self.symbols = symbols
        self._client = databento.Live(key=api_key)
    
    async def stream_ticks(self) -> AsyncIterator[Tick]:
        async for record in self._client.live(dataset="GLBX.MDP3", symbols=self.symbols):
            yield self._convert_to_tick(record)
```

---

#### Task 3.1.2: Connection Resilience

**Description:**  
Implement robust connection handling for Databento client.

**Acceptance Criteria:**
- Automatic reconnection with exponential backoff
- Connection state metrics (connected, disconnected, reconnecting)
- Graceful handling of API rate limits
- Alert on prolonged disconnection (> 1 minute)

**Implementation Notes:**
- Use circuit breaker pattern
- Log all connection state transitions
- Emit metric on disconnect duration

---

#### Task 3.1.3: Historical Backfill on Gap

**Description:**  
Implement automatic backfill when gaps are detected.

**Acceptance Criteria:**
- GapDetector identifies missing candles
- Triggers historical data request to Databento
- Backfilled candles published to Redis with correct timestamps
- Downstream services process backfill seamlessly

**Implementation Notes:**
- Use `databento.Historical` for gap fill
- Mark backfilled candles with metadata flag
- Ensure backfill doesn't duplicate existing data

---

### Story 3.2: Market Hours Handling

**As a** system  
**I want** proper handling of market hours and sessions  
**So that** I only trade during valid market hours

#### Task 3.2.1: Session Filter Implementation

**Description:**  
Enhance `SessionFilter` to handle real market hours for Gold futures.

**Acceptance Criteria:**
- Configurable trading hours (default: Gold futures hours)
- Handles timezone correctly (market hours are in ET)
- Filters pre-market and post-market data
- Allows bypass for testing/replay

**Implementation Notes:**
- Gold futures: Sunday 6pm - Friday 5pm ET (with daily break)
- Use `pytz` or `zoneinfo` for timezone handling
- Config via environment variable or YAML

---

#### Task 3.2.2: Session Boundary Events

**Description:**  
Emit events at session boundaries for downstream services.

**Acceptance Criteria:**
- Emit `session.opened` at market open
- Emit `session.closed` at market close
- Execution service resets daily state on `session.opened`

**Implementation Notes:**
- Publish to `session.events` Redis stream
- Include session date and timezone info

---

---

## Epic 4: Broker Integration

**Goal:** Connect to real brokers for live trading.

**Priority:** 🟠 Medium  
**Estimated Duration:** 3 weeks

### Story 4.1: Broker Abstraction Layer

**As a** developer  
**I want** a clean broker abstraction  
**So that** I can support multiple brokers with same interface

#### Task 4.1.1: Define Broker Interface

**Description:**  
Finalize the `BrokerBase` interface with all required methods.

**Interface:**
```python
class BrokerBase(ABC):
    @abstractmethod
    async def connect(self) -> None: ...
    
    @abstractmethod
    async def place_order(
        self, symbol: str, side: str, quantity: int, order_type: str
    ) -> Order: ...
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Position | None: ...
    
    @abstractmethod
    async def get_account(self) -> Account: ...
```

**Acceptance Criteria:**
- Interface covers all trading operations
- PaperBroker implements interface correctly
- Interface supports both sync and async patterns

---

#### Task 4.1.2: Position Reconciliation

**Description:**  
Implement position reconciliation between service state and broker state.

**Acceptance Criteria:**
- On startup, query broker for current positions
- Reconcile with trades in database
- Log discrepancies and alert if positions don't match
- Option to auto-close orphaned positions

**Implementation Notes:**
- Run reconciliation on Execution service startup
- Store reconciliation results in database
- Expose reconciliation status via health endpoint

---

### Story 4.2: Interactive Brokers Integration

**As a** trader  
**I want** to trade through Interactive Brokers  
**So that** I can execute live trades

#### Task 4.2.1: IB Client Implementation

**Description:**  
Implement `InteractiveBrokersClient` using `ib_insync` library.

**Acceptance Criteria:**
- Connects to IB Gateway/TWS
- Places market and limit orders
- Receives fill notifications
- Handles partial fills correctly

**Implementation Notes:**
```python
from ib_insync import IB, Contract, MarketOrder

class InteractiveBrokersClient(BrokerBase):
    def __init__(self, host: str, port: int, client_id: int):
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
```

---

#### Task 4.2.2: IB Order Management

**Description:**  
Implement full order lifecycle management for IB.

**Acceptance Criteria:**
- Place orders with stop-loss and take-profit
- Modify orders (SL adjustment)
- Cancel orders
- Handle order rejections gracefully

**Implementation Notes:**
- Use bracket orders for SL/TP
- Implement order status callbacks
- Persist order state to database

---

#### Task 4.2.3: IB Position Tracking

**Description:**  
Track positions and account state from IB.

**Acceptance Criteria:**
- Real-time position updates
- Account balance and margin tracking
- P&L tracking per position
- Daily P&L for PDLL enforcement

---

### Story 4.3: Broker Mode Selection

**As an** operator  
**I want** to switch between paper and live modes  
**So that** I can validate before going live

#### Task 4.3.1: Mode Configuration

**Description:**  
Implement broker mode selection via configuration.

**Acceptance Criteria:**
- `BROKER_MODE=paper|live` environment variable
- Paper mode uses PaperBroker
- Live mode uses configured broker (IB, etc.)
- Clear logging of which mode is active

**Implementation Notes:**
```python
def create_broker(mode: str, config: BrokerConfig) -> BrokerBase:
    if mode == "paper":
        return PaperBroker()
    elif mode == "live":
        return InteractiveBrokersClient(config.ib_host, config.ib_port, config.ib_client_id)
```

---

#### Task 4.3.2: Safety Guards for Live Mode

**Description:**  
Implement additional safety checks for live trading.

**Acceptance Criteria:**
- Require explicit confirmation for live mode
- Maximum position size limits
- Daily loss limit enforced at broker level
- Kill switch to halt all trading

---

---

## Epic 5: Production Readiness

**Goal:** Prepare the system for production deployment.

**Priority:** 🟠 Medium  
**Estimated Duration:** 2 weeks

### Story 5.1: Kill Switch & Emergency Controls

**As an** operator  
**I want** emergency controls to halt trading  
**So that** I can stop losses in case of system malfunction

#### Task 5.1.1: Kill Switch Endpoint

**Description:**  
Implement a kill switch endpoint that immediately halts all trading.

**Acceptance Criteria:**
- `POST /admin/kill` stops all signal processing
- `POST /admin/resume` resumes signal processing
- Kill state persists across restarts
- Kill switch state exposed in health check

**Implementation Notes:**
```python
@app.post("/admin/kill")
async def kill_switch():
    global trading_enabled
    trading_enabled = False
    await close_all_positions()  # Optional: close positions
    return {"status": "trading_halted"}
```

---

#### Task 5.1.2: Position Liquidation

**Description:**  
Implement emergency position liquidation.

**Acceptance Criteria:**
- `POST /admin/liquidate` closes all positions at market
- Logs all liquidation actions
- Disables new trades until manually re-enabled

---

#### Task 5.1.3: Alert Integration

**Description:**  
Integrate alerts for critical conditions.

**Alerts to implement:**
- PDLL hit (daily loss limit)
- Multiple consecutive losses
- System errors (service crashes, connection failures)
- Kill switch activated

**Acceptance Criteria:**
- Alerts sent via configured channel (Slack, email, PagerDuty)
- Alert includes relevant context
- Rate limiting to prevent alert storms

---

### Story 5.2: Configuration Management

**As an** operator  
**I want** centralized configuration management  
**So that** I can update settings without redeployment

#### Task 5.2.1: Environment-Based Config

**Description:**  
Ensure all services use environment-based configuration.

**Acceptance Criteria:**
- All config via environment variables
- Sensible defaults for development
- Required variables fail fast with clear error
- Secrets handled securely (not in logs)

---

#### Task 5.2.2: Runtime Config Updates

**Description:**  
Implement runtime configuration updates for key parameters.

**Parameters:**
- Position size (contracts)
- Risk limits (PDLL, max trades)
- Tier settings (tier_active)

**Acceptance Criteria:**
- Update via HTTP endpoint
- Changes take effect immediately
- Changes logged for audit

---

### Story 5.3: Database Operations

**As an** operator  
**I want** database maintenance procedures  
**So that** I can manage data growth and ensure performance

#### Task 5.3.1: Data Retention Policies

**Description:**  
Implement data retention policies using TimescaleDB features.

**Policies:**
- Candles: 1 year retention
- Features: 90 days retention
- Trades: Permanent (audit trail)
- HTF Bias History: 90 days retention

**Acceptance Criteria:**
- Retention policies configured in TimescaleDB
- Old data automatically removed
- No manual intervention required

**Implementation Notes:**
```sql
SELECT add_retention_policy('candles', INTERVAL '1 year');
SELECT add_retention_policy('features', INTERVAL '90 days');
```

---

#### Task 5.3.2: Backup Procedures

**Description:**  
Document and automate database backup procedures.

**Acceptance Criteria:**
- Daily backups of PostgreSQL
- Backup verification (restore test)
- Backup retention policy (30 days)
- Offsite backup storage

---

### Story 5.4: Deployment Pipeline

**As a** developer  
**I want** automated deployment pipeline  
**So that** I can deploy changes safely

#### Task 5.4.1: CI/CD Pipeline

**Description:**  
Set up CI/CD pipeline for automated testing and deployment.

**Pipeline stages:**
1. Lint & type check
2. Unit tests
3. Integration tests
4. Build Docker images
5. Deploy to staging
6. Deploy to production (manual approval)

**Acceptance Criteria:**
- Pipeline runs on every PR
- Deployment blocked if tests fail
- Docker images tagged with git SHA

---

#### Task 5.4.2: Blue-Green Deployment

**Description:**  
Implement blue-green deployment for zero-downtime updates.

**Acceptance Criteria:**
- Two environments (blue/green)
- Traffic switch after health check passes
- Automatic rollback on failure
- Database migrations handle both versions

---

---

## Epic 6: Paper Trading Validation

**Goal:** Validate system behavior with live market data before real trading.

**Priority:** 🔴 Critical  
**Estimated Duration:** 2 weeks (minimum 1 week of live validation)

### Story 6.1: Paper Trading Environment

**As a** trader  
**I want** to run the system with live data in paper mode  
**So that** I can validate behavior before risking real money

#### Task 6.1.1: Production-Like Paper Setup

**Description:**  
Deploy full system with live Databento data but paper broker.

**Acceptance Criteria:**
- All services running with production configuration
- Real-time data from Databento
- PaperBroker simulates trade execution
- Full monitoring and alerting active

---

#### Task 6.1.2: Paper Trading Dashboard

**Description:**  
Create dashboard for monitoring paper trading performance.

**Dashboard shows:**
- Real-time signals and trades
- Daily P&L (paper)
- Win rate and R-multiple distribution
- Comparison to expected behavior

---

### Story 6.2: Validation Criteria

**As a** trader  
**I want** clear validation criteria for go-live  
**So that** I know when the system is ready

#### Task 6.2.1: Define Go-Live Criteria

**Description:**  
Document specific criteria that must be met before live trading.

**Criteria:**
1. **Stability:** 7 days continuous operation without crashes
2. **Accuracy:** Signal generation matches backtester expectations
3. **Latency:** Signal-to-trade latency < 1 second
4. **Recovery:** Successful recovery from simulated failures
5. **Performance:** Paper P&L within expected range based on backtests

---

#### Task 6.2.2: Validation Report

**Description:**  
Create automated validation report generation.

**Report includes:**
- Uptime statistics
- Signal count and distribution
- Trade outcomes
- System error count
- Latency percentiles

**Acceptance Criteria:**
- Report generated daily
- Clear pass/fail status for each criterion
- Historical comparison to previous periods

---

---

## Timeline & Priorities

| Epic | Priority | Duration | Dependencies |
|------|----------|----------|--------------|
| 1. Integration Testing | 🔴 Critical | 2-3 weeks | None |
| 2. Observability | 🟡 High | 1-2 weeks | None |
| 3. Live Data Integration | 🟡 High | 2 weeks | Epic 1 |
| 4. Broker Integration | 🟠 Medium | 3 weeks | Epic 3 |
| 5. Production Readiness | 🟠 Medium | 2 weeks | Epic 2 |
| 6. Paper Trading Validation | 🔴 Critical | 2 weeks | Epic 3, 4, 5 |

### Recommended Order

```
Week 1-2:   Epic 1 (Integration Testing) + Epic 2 (Observability)
Week 3-4:   Epic 3 (Live Data Integration)
Week 5-6:   Epic 4 (Broker Integration) + Epic 5 (Production Readiness)
Week 7-8:   Epic 6 (Paper Trading Validation)
Week 9+:    Go-Live (with conservative limits)
```

---

## Risk Register

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Scoring parity issues | High | Medium | Extensive testing, factor-by-factor comparison |
| Databento connection instability | Medium | Low | Reconnection logic, gap backfill |
| Broker API changes | Medium | Low | Abstraction layer, version pinning |
| Data loss during failures | High | Low | State persistence, idempotent processing |
| Latency spikes | Medium | Medium | Metrics monitoring, alerting |

---

## Success Metrics

1. **System Uptime:** > 99.9% during market hours
2. **Signal Latency:** < 500ms from candle close to signal publish
3. **Trade Latency:** < 1s from signal to order placement
4. **Parity Score:** > 99% match with backtester signals
5. **Paper P&L:** Within 10% of backtester expectations

---

## Appendix: Task Checklist

### Epic 1: Integration Testing
- [ ] 1.1.1 Create Parity Test Framework
- [ ] 1.1.2 Signal Generation Parity Tests
- [ ] 1.1.3 Trade Execution Parity Tests
- [ ] 1.1.4 Multi-Day Replay Parity Test
- [ ] 1.2.1 Docker-Based Integration Test Infrastructure
- [ ] 1.2.2 Message Flow Integration Tests
- [ ] 1.2.3 State Recovery Integration Tests
- [ ] 1.2.4 Error Handling Integration Tests
- [ ] 1.3.1 Scoring Factor Comparison
- [ ] 1.3.2 HTF Bias Calculation Parity

### Epic 2: Observability
- [ ] 2.1.1 Add Metrics Library to Shared
- [ ] 2.1.2 Data Adapter Metrics
- [ ] 2.1.3 Feature Engine Metrics
- [ ] 2.1.4 HTF Bias Metrics
- [ ] 2.1.5 Bot Core Metrics
- [ ] 2.1.6 Execution Service Metrics
- [ ] 2.1.7 Grafana Dashboards
- [ ] 2.2.1 Add OpenTelemetry to Shared
- [ ] 2.2.2 Instrument All Services
- [ ] 2.3.1 Structured Log Format
- [ ] 2.3.2 Log Aggregation Setup

### Epic 3: Live Data Integration
- [ ] 3.1.1 Databento SDK Integration
- [ ] 3.1.2 Connection Resilience
- [ ] 3.1.3 Historical Backfill on Gap
- [ ] 3.2.1 Session Filter Implementation
- [ ] 3.2.2 Session Boundary Events

### Epic 4: Broker Integration
- [ ] 4.1.1 Define Broker Interface
- [ ] 4.1.2 Position Reconciliation
- [ ] 4.2.1 IB Client Implementation
- [ ] 4.2.2 IB Order Management
- [ ] 4.2.3 IB Position Tracking
- [ ] 4.3.1 Mode Configuration
- [ ] 4.3.2 Safety Guards for Live Mode

### Epic 5: Production Readiness
- [ ] 5.1.1 Kill Switch Endpoint
- [ ] 5.1.2 Position Liquidation
- [ ] 5.1.3 Alert Integration
- [ ] 5.2.1 Environment-Based Config
- [ ] 5.2.2 Runtime Config Updates
- [ ] 5.3.1 Data Retention Policies
- [ ] 5.3.2 Backup Procedures
- [ ] 5.4.1 CI/CD Pipeline
- [ ] 5.4.2 Blue-Green Deployment

### Epic 6: Paper Trading Validation
- [ ] 6.1.1 Production-Like Paper Setup
- [ ] 6.1.2 Paper Trading Dashboard
- [ ] 6.2.1 Define Go-Live Criteria
- [ ] 6.2.2 Validation Report
