# Integration Tests - Quick Start Guide

## 🚀 TL;DR

```bash
# 1. Start infrastructure
cd infra && docker-compose up -d redis postgres

# 2. Run tests
./scripts/run_integration_tests.sh

# 3. View results
# ✓ All tests passed!
```

## 📋 Prerequisites

### Required Services
- ✅ **Redis** (port 6379)
- ✅ **PostgreSQL/TimescaleDB** (port 5432)

### Start Services

```bash
cd infra
docker-compose up -d redis postgres
```

### Verify Services

```bash
# Check Redis
redis-cli ping
# Expected: PONG

# Check PostgreSQL
docker-compose exec postgres psql -U scp -d scp -c "\dt"
# Expected: List of tables (candles, features, trades, etc.)
```

## 🧪 Running Tests

### All Tests (Fast)

```bash
./scripts/run_integration_tests.sh
```

Runs all integration tests **except** slow tests (~30 seconds).

### All Tests (Including Slow)

```bash
./scripts/run_integration_tests.sh --slow
```

Includes high-volume stress tests (~3 minutes).

### With Coverage Report

```bash
./scripts/run_integration_tests.sh --coverage
```

Generates HTML coverage report in `htmlcov/index.html`.

### Specific Test File

```bash
./scripts/run_integration_tests.sh --test tests/integration/test_state_recovery.py
```

### Verbose Output

```bash
./scripts/run_integration_tests.sh -v
```

## 📊 Test Categories

### 1. Multi-Service Replay (13 tests)

Tests full pipeline from candles → features → signals → trades.

```bash
poetry run pytest tests/integration/test_multi_service_replay.py -v
```

**Key Tests:**
- Sequential candles produce features
- HTF bias updates at boundaries
- Signal generation with DXY + HTF bias
- Gap detection and handling
- Multi-day replay correctness
- Trade execution lifecycle

### 2. State Recovery (9 tests)

Tests service restart and state restoration from database.

```bash
poetry run pytest tests/integration/test_state_recovery.py -v
```

**Key Tests:**
- Feature Engine warmup (EMA, VWAP, DXY)
- HTF aggregator partial period recovery
- Active trades restoration
- State machine recovery
- Daily limits enforcement
- HTF bias cache rebuild

### 3. Stream Synchronization (11 tests)

Tests edge cases in message streaming and pairing.

```bash
poetry run pytest tests/integration/test_stream_synchronization.py -v
```

**Key Tests:**
- Out-of-order messages
- Duplicate detection
- Timeout scenarios
- Buffer overflow protection
- Consumer group coordination
- Idempotent processing
- High-volume stress (1000+ msgs/sec)

## 🎯 Common Use Cases

### Before Committing Code

```bash
# Run fast tests only (30 seconds)
./scripts/run_integration_tests.sh -v
```

### Before Pushing to Main

```bash
# Run all tests with coverage (3 minutes)
./scripts/run_integration_tests.sh --slow --coverage
```

### Debugging a Specific Scenario

```bash
# Run single test with verbose output
poetry run pytest tests/integration/test_state_recovery.py::TestExecutionServiceRecovery::test_restore_active_trades_from_database -vv
```

### Testing Multi-Day Replay

```bash
# Run multi-day tests only
poetry run pytest tests/integration/test_multi_service_replay.py::TestMultiDayReplay -v
```

## 🔧 Troubleshooting

### ❌ "Cannot connect to Redis"

**Solution:**
```bash
cd infra
docker-compose up -d redis
sleep 2
redis-cli ping  # Should return PONG
```

### ❌ "Cannot connect to PostgreSQL"

**Solution:**
```bash
cd infra
docker-compose up -d postgres
sleep 5
docker-compose exec postgres pg_isready -U scp
```

### ❌ "Database schema not found"

**Solution:**
```bash
# Restart PostgreSQL to apply migrations
cd infra
docker-compose restart postgres
sleep 5
```

### ❌ "Consumer group already exists"

**Solution:**
```bash
# Delete consumer groups
redis-cli XGROUP DESTROY candles.1m.gc test-consumer-group

# Or restart Redis (removes all data)
docker-compose restart redis
```

### ❌ "Tests hang or timeout"

**Solution:**
1. Check Redis and PostgreSQL are running
2. Increase timeout in `pytest.ini`:
   ```ini
   [pytest]
   timeout = 300  # 5 minutes
   ```
3. Run with `-vv` for detailed output

## 📈 Performance Benchmarks

Expected execution times:

| Test Suite | Duration | Tests |
|------------|----------|-------|
| Fast tests (default) | ~30s | ~40 tests |
| All tests (--slow) | ~3min | ~50 tests |
| Single test file | ~10s | ~10 tests |
| Single test | <1s | 1 test |

## 🎓 Test Patterns

### Factory Pattern

```python
# Create realistic test data
candle = candle_message_factory(
    timestamp=my_time,
    symbol="GC",
    close=2051.0,
)

features = features_message_factory(
    timestamp=my_time,
    vwap=2050.5,
    dxy_correlation=-0.75,
)
```

### Async Testing

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_my_scenario(redis_client, db_pool):
    # Publish messages
    await publish_to_stream("candles.1m.gc", data)
    
    # Wait for propagation
    await asyncio.sleep(0.1)
    
    # Assert results
    messages = await read_from_stream("features.1m")
    assert len(messages) > 0
```

### Database Cleanup

```python
# Automatic cleanup via fixture
async def test_my_scenario(db_pool):
    # Insert test data
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO ...")
    
    # No cleanup needed - fixture handles it
```

## 📚 Documentation

- **Full README**: `tests/integration/README.md`
- **Implementation Summary**: `INTEGRATION_TESTS_SUMMARY.md`
- **Fixtures Reference**: `tests/integration/conftest.py`

## 🎯 Success Criteria

Tests pass when:
- ✅ All assertions pass
- ✅ No timeout errors
- ✅ Services connect successfully
- ✅ Database operations complete
- ✅ Messages flow through streams
- ✅ State recovery works correctly

## 🚦 CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run Integration Tests
  run: ./scripts/run_integration_tests.sh
  env:
    REDIS_URL: redis://localhost:6379
    DATABASE_URL: postgresql://scp:password@localhost:5432/scp
```

### Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/bash
./scripts/run_integration_tests.sh
```

### Pre-push Hook

```bash
# .git/hooks/pre-push
#!/bin/bash
./scripts/run_integration_tests.sh --slow --coverage
```

## ✨ Best Practices

### 1. Run Fast Tests Frequently

```bash
# During development
./scripts/run_integration_tests.sh
```

### 2. Run All Tests Before PR

```bash
# Before creating pull request
./scripts/run_integration_tests.sh --slow --coverage
```

### 3. Use Markers for Filtering

```bash
# Skip slow tests
poetry run pytest -m "integration and not slow"

# Run only async tests
poetry run pytest -m "integration and asyncio"
```

### 4. Debug with Verbose Output

```bash
# Maximum verbosity
poetry run pytest tests/integration/test_*.py -vv -s
```

### 5. Parallel Execution (Careful!)

```bash
# Use pytest-xdist (may have race conditions)
poetry run pytest tests/integration/ -n 4
```

## 🎊 Quick Wins

### Generate Coverage Badge

```bash
./scripts/run_integration_tests.sh --coverage
coverage-badge -o coverage.svg
```

### Watch Mode (Development)

```bash
# Install pytest-watch
pip install pytest-watch

# Run tests on file changes
ptw tests/integration/ -- -v
```

### Profile Slow Tests

```bash
poetry run pytest tests/integration/ --durations=10
```

## 📞 Need Help?

- **Documentation**: `tests/integration/README.md`
- **Examples**: See test files for patterns
- **Issues**: Check troubleshooting section above
- **Logs**: Check `docker-compose logs redis postgres`

---

**Remember**: Integration tests verify the **full system** works correctly. They complement unit tests by testing **service interactions** and **end-to-end flows**. 🚀
