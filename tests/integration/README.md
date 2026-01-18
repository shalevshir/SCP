# Integration Tests

Comprehensive integration tests for the SCP microservices architecture.

## Overview

These tests verify multi-service interactions, state recovery, and stream synchronization across the distributed trading system.

## Test Classification

Integration tests are divided into two categories:

### Infrastructure Tests ✅ (Run with Infrastructure Only)
Tests that verify data flow, state management, and synchronization logic **without** requiring microservices to be running. These tests run against Redis and PostgreSQL only.

**Files:**
- `test_multi_service_replay.py`
- `test_state_recovery.py`
- `test_stream_synchronization.py`

**Total:** 33 tests

### End-to-End Tests ⚠️ (Require Full Service Stack)
Tests that verify actual service interactions and require all microservices to be running in Docker.

**Files:**
- `test_data_to_features.py`
- `test_features_to_bias.py`
- `test_full_pipeline.py`
- `test_signals_to_trades.py`
- `test_vwap_reclaim_symmetry_integration.py`

**Total:** 17 tests

**Note:** E2E tests require services to be started with:
```bash
cd infra
docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml up -d
```

---

## Test Coverage

### 1. Multi-Service Replay (`test_multi_service_replay.py`) - Infrastructure Test

Tests the full pipeline from data ingestion through trade execution:

- **Full Pipeline Replay**: Sequential candles → features → signals → trades
- **HTF Bias Updates**: 15m/1h boundary detection and bias propagation
- **Signal Generation**: DXY correlation and HTF bias requirements
- **Gap Detection**: Missing candles and gap handling
- **Synchronizer Timeouts**: Unmatched GC/DXY candles
- **Multi-Day Replay**: Session resets and HTF bias cache correctness
- **Trade Execution**: VWAP reclaim state machine lifecycle
- **Trade Invalidation**: SL/TP hit detection

**Test Classes:**
- `TestFullPipelineReplay`: Basic pipeline functionality
- `TestReplayWithGaps`: Gap detection and handling
- `TestMultiDayReplay`: Multi-day scenarios with session resets
- `TestTradeExecution`: Trade lifecycle and invalidation

### 2. State Recovery (`test_state_recovery.py`)

Tests service restart and state recovery from database:

- **Feature Engine Warmup**: EMA, VWAP, DXY correlation state restoration
- **HTF Aggregator Warmup**: Mid-period restart with partial candles
- **Active Trades Recovery**: Open positions restored on restart
- **State Machine Recovery**: VWAP reclaim state machines from snapshots
- **Daily State Recovery**: Guardrails and limits enforced after restart
- **HTF Bias Cache Rebuild**: History reconstruction from Redis streams
- **Error Handling**: Corrupted snapshots and missing fields

**Test Classes:**
- `TestFeatureEngineRecovery`: Feature computation state
- `TestExecutionServiceRecovery`: Trade and state machine restoration
- `TestHTFBiasCacheRecovery`: Bias cache history rebuild
- `TestRecoveryErrorHandling`: Graceful degradation

### 3. Stream Synchronization (`test_stream_synchronization.py`)

Tests edge cases in message streaming and synchronization:

- **Out-of-Order Delivery**: Candles arriving in non-chronological order
- **Duplicate Messages**: Idempotency and duplicate detection
- **Synchronizer Timeouts**: Missing DXY candles with cleanup
- **Buffer Stats**: Monitoring and observability
- **Features Before Candle**: CandleFeatureSynchronizer buffering
- **Multi-Day Replay Timeout**: 7-day timeout for replay mode
- **Consumer Groups**: Message acknowledgment and distribution
- **Message Replay**: Replay from specific message ID
- **Idempotent Processing**: Database upserts for features
- **High Volume Stress**: 1000+ candles per minute
- **Buffer Overflow Protection**: Bounded buffer sizes

**Test Classes:**
- `TestCandleSynchronizerEdgeCases`: GC/DXY pairing edge cases
- `TestCandleFeatureSynchronizerEdgeCases`: Candle/features pairing
- `TestConsumerGroupCoordination`: Redis consumer groups
- `TestMessageReplayIdempotency`: Replay and idempotency
- `TestHighVolumeStress`: Performance and stress testing

## Prerequisites

### Required Services

Integration tests require the following services to be running:

1. **Redis** (port 6379)
2. **PostgreSQL/TimescaleDB** (port 5432) with migrations applied

### Start Infrastructure

```bash
# Start Redis and PostgreSQL
cd infra
docker-compose up -d redis postgres

# Wait for PostgreSQL to be ready
docker-compose exec postgres pg_isready -U scp

# Verify migrations applied
docker-compose exec postgres psql -U scp -d scp -c "\dt"
```

### Environment Variables

Set the following environment variables (or use defaults):

```bash
export REDIS_URL="redis://localhost:6379"
export DATABASE_URL="postgresql://scp:scp_dev_password@localhost:5432/scp"
```

## Running Tests

### Run Infrastructure Tests Only (Recommended for Development)

Infrastructure tests run quickly and don't require services:

```bash
# Run only infrastructure tests (33 tests)
poetry run pytest tests/integration/ -v -m "infrastructure"

# With coverage
poetry run pytest tests/integration/ -m "infrastructure" --cov=services --cov-report=term-missing

# Using the test runner (excludes slow tests)
./scripts/run_integration_tests.sh
```

### Run End-to-End Tests (Requires Services)

E2E tests require all services to be running:

```bash
# 1. Start full service stack
cd infra
docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml up -d

# 2. Wait for services to be healthy
sleep 30

# 3. Run E2E tests
poetry run pytest tests/integration/ -v -m "e2e"
```

### Run All Integration Tests

```bash
# From project root (will have failures if services not running)
poetry run pytest tests/integration/ -v

# With coverage
poetry run pytest tests/integration/ --cov=services --cov-report=term-missing
```

### Run Specific Test File

```bash
# Multi-service replay tests
poetry run pytest tests/integration/test_multi_service_replay.py -v

# State recovery tests
poetry run pytest tests/integration/test_state_recovery.py -v

# Stream synchronization tests
poetry run pytest tests/integration/test_stream_synchronization.py -v
```

### Run Specific Test Class

```bash
# Full pipeline tests only
poetry run pytest tests/integration/test_multi_service_replay.py::TestFullPipelineReplay -v

# Recovery tests only
poetry run pytest tests/integration/test_state_recovery.py::TestExecutionServiceRecovery -v
```

### Run with Markers

```bash
# Run all integration tests
poetry run pytest -m integration

# Skip slow tests
poetry run pytest -m "integration and not slow"

# Run only slow tests
poetry run pytest -m "integration and slow"
```

## Test Architecture

### Fixtures (`conftest.py`)

Shared fixtures for integration tests:

- **Database**: `db_pool`, `postgres_url` - PostgreSQL connection with cleanup
- **Redis**: `redis_client`, `redis_url` - Redis client with stream cleanup
- **Factories**: `candle_message_factory`, `features_message_factory`, `htf_bias_message_factory`
- **Helpers**: `publish_to_stream`, `read_from_stream`, `cleanup_consumer_groups`
- **Mocks**: `mock_broker` - Async mock for broker testing

### Cleanup Strategy

Tests automatically clean up after themselves:

1. **Redis Streams**: Deleted after each test
2. **Database Tables**: Truncated after each test (preserves schema)
3. **Consumer Groups**: Destroyed after tests using them

### Test Data

Tests use realistic data:

- **GC (Gold)**: ~$2050/oz with 0.10-1.00 point moves
- **DXY (Dollar Index)**: ~103.50 with 0.10 point moves
- **Timestamps**: Recent dates in UTC with minute-level precision

## CI/CD Integration

### GitHub Actions

Add to `.github/workflows/integration-tests.yml`:

```yaml
name: Integration Tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    
    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
      
      postgres:
        image: timescale/timescaledb:latest-pg15
        env:
          POSTGRES_DB: scp
          POSTGRES_USER: scp
          POSTGRES_PASSWORD: scp_test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install Poetry
        run: pip install poetry
      
      - name: Install Dependencies
        run: poetry install
      
      - name: Apply Migrations
        run: |
          poetry run python scripts/apply_migrations.py
        env:
          DATABASE_URL: postgresql://scp:scp_test_password@localhost:5432/scp
      
      - name: Run Integration Tests
        run: |
          poetry run pytest tests/integration/ -v --cov=services
        env:
          REDIS_URL: redis://localhost:6379
          DATABASE_URL: postgresql://scp:scp_test_password@localhost:5432/scp
      
      - name: Upload Coverage
        uses: codecov/codecov-action@v3
        if: always()
```

## Best Practices

### 1. Test Independence

Each test should be independent and not rely on other tests:

```python
# Good: Self-contained test
async def test_feature_computation(db_pool, publish_to_stream):
    # Setup: Insert required data
    # Act: Perform operation
    # Assert: Verify result
    # Cleanup: Automatic via fixtures
```

### 2. Realistic Data

Use realistic timestamps and prices:

```python
# Good: Realistic timestamp
timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)

# Bad: Mock timestamp
timestamp = datetime(1970, 1, 1, 0, 0, 0)
```

### 3. Explicit Assertions

Make assertions explicit and descriptive:

```python
# Good: Explicit assertion with message
assert len(candles) == 10, f"Expected 10 candles, got {len(candles)}"

# Bad: Silent assertion
assert len(candles) == 10
```

### 4. Async Sleep for Propagation

Allow time for message propagation:

```python
# Publish messages
await publish_to_stream("candles.1m.gc", candle.model_dump())

# Wait for propagation
await asyncio.sleep(0.1)

# Assert
messages = await read_from_stream("candles.1m.gc")
```

### 5. Database Transactions

Use database transactions for complex setups:

```python
async with db_pool.acquire() as conn:
    async with conn.transaction():
        # Multiple inserts in transaction
        await conn.execute("INSERT INTO ...")
        await conn.execute("INSERT INTO ...")
```

## Troubleshooting

### Tests Fail to Connect to Redis

```bash
# Check Redis is running
docker-compose ps redis

# Check Redis connectivity
redis-cli ping

# Restart Redis
docker-compose restart redis
```

### Tests Fail to Connect to PostgreSQL

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check migrations applied
docker-compose exec postgres psql -U scp -d scp -c "\dt"

# Re-apply migrations
docker-compose exec postgres psql -U scp -d scp -f /docker-entrypoint-initdb.d/100_initial_schema.sql
```

### Tests Timeout

Increase test timeouts in `pytest.ini`:

```ini
[pytest]
timeout = 300  # 5 minutes
asyncio_mode = auto
```

### Stream Already Has Consumer Group

```bash
# Delete consumer groups manually
redis-cli XGROUP DESTROY candles.1m.gc test-consumer-group

# Or restart Redis (removes all data)
docker-compose restart redis
```

## Performance Benchmarks

Expected performance for integration tests:

- **Single test**: < 1 second
- **Test class**: < 10 seconds
- **Full suite**: < 2 minutes (without slow tests)
- **Full suite with slow tests**: < 5 minutes

### Slow Tests

Tests marked with `@pytest.mark.slow`:

- Multi-day replay (1000+ candles)
- High-volume stress tests (10,000+ messages)
- Timeout scenarios (long waits)

Run without slow tests during development:

```bash
poetry run pytest tests/integration/ -m "not slow"
```

## Contributing

When adding new integration tests:

1. **Follow TDD**: Write failing test first
2. **Use fixtures**: Leverage existing fixtures from `conftest.py`
3. **Add docstrings**: Explain scenario, actions, and assertions
4. **Mark slow tests**: Use `@pytest.mark.slow` for tests > 10 seconds
5. **Clean up**: Ensure fixtures handle cleanup automatically
6. **Document**: Update this README with new test coverage

## Related Documentation

- [Microservices Architecture](../../microservices_architecture.md)
- [Test Coverage Report](../../COVERAGE_QUICK_REFERENCE.md)
- [Development Guidelines](../../.cursor/rules/development_guidelines.mdc)
