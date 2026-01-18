# Test Marker Classification Fix

## Issue

Integration tests were failing with errors like:
- "No trades opened after signal"
- "Features should be processed"
- "Trade not opened - cannot test X"

These failures occurred because the test runner script was only running infrastructure tests (no services needed), but some integration tests require microservices to be running.

## Root Cause

**Correct Test Taxonomy:**
- **Infrastructure tests** - Run against Redis + PostgreSQL only (no services required)
- **Integration tests** - Test service-to-service integration (REQUIRE microservices to be running)
- **E2E tests** - Full end-to-end workflows (in `tests/e2e/`)

The issue: Integration tests that need services were being run without services by the default test runner.

## Solution

### Test Marker Strategy

All tests in `tests/integration/` use **dual markers**:

#### Infrastructure Tests (No Services) - 30 tests

Tests that can run with just Redis + PostgreSQL (no microservices).

**Markers:** `@pytest.mark.integration` + `@pytest.mark.infrastructure`

| File | Tests | Description |
|------|-------|-------------|
| `test_multi_service_replay.py` | 9 | Multi-service replay scenarios |
| `test_state_recovery.py` | 9 | Service restart, state restoration |
| `test_stream_synchronization.py` | 11 | Stream edge cases, synchronizers |
| `test_vwap_reclaim_symmetry_integration.py` | 1 | VWAP reclaim symmetry |

**Example:**
```python
@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
async def test_synchronizer_handles_out_of_order(...):
    # Tests synchronizer logic without services
    ...
```

#### Integration Tests (Require Services) - 15 tests

Tests that require microservices to be running (service-to-service integration).

**Marker:** `@pytest.mark.integration` (WITHOUT `infrastructure`)

| File | Tests | Description |
|------|-------|-------------|
| `test_data_to_features.py` | 3 | Data Adapter → Feature Engine flow |
| `test_features_to_bias.py` | 4 | Feature Engine → HTF Bias flow |
| `test_full_pipeline.py` | 4 | Full pipeline candles → trades |
| `test_signals_to_trades.py` | 4 | Signals → Trade Execution flow |

**Example:**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_signal_triggers_trade_execution(...):
    # Publishes signal, expects Execution service to create trade
    ...
```

**Key Insight:** These tests are still marked `@pytest.mark.integration` (not `e2e`), because they test **integration between services**, which is what integration tests do!

## Running Tests

### Infrastructure Tests Only (Default - No Services Needed)

```bash
# Run with test runner script (default behavior)
./scripts/run_integration_tests.sh

# Or directly with pytest
poetry run pytest tests/integration/ -m "infrastructure" -v
```

**Expected:** 30 tests, ~20-30 seconds, **no services required** ✅

### Integration Tests (Require Services)

```bash
# 1. Start services first
cd infra
docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml up -d

# 2. Wait for services to be ready
sleep 30

# 3. Run integration tests that need services
poetry run pytest tests/integration/ -m "integration and not infrastructure" -v
```

**Expected:** 15 tests, ~2-3 minutes, **requires full service stack** ⚠️

### All Integration Tests

```bash
# Start services (needed for 15 tests)
cd infra
docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml up -d
sleep 30

# Run all integration tests
poetry run pytest tests/integration/ -m "integration" -v
```

**Expected:** 45 tests (30 infrastructure + 15 service-dependent).

## Verification

```bash
# Infrastructure tests (no services)
poetry run pytest tests/integration/ -m "infrastructure" --collect-only
# Expected: 30/50 tests collected (20 deselected)

# Integration tests needing services
poetry run pytest tests/integration/ -m "integration and not infrastructure" --collect-only
# Expected: 15/50 tests collected (35 deselected)

# All integration tests
poetry run pytest tests/integration/ -m "integration" --collect-only
# Expected: 45/50 tests collected (5 deselected)

# All tests in folder
poetry run pytest tests/integration/ --collect-only
# Expected: 50 tests collected
```

## CI/CD Impact

### Current Behavior (Correct)

The test runner script `./scripts/run_integration_tests.sh` defaults to running **infrastructure tests only**:
- ✅ Runs 30 tests without services
- ✅ Fast (~20-30 seconds)
- ✅ No Docker stack needed

### Recommended CI/CD Setup

**Fast CI (every commit):**
```yaml
# .github/workflows/ci.yml
- name: Integration Tests (Infrastructure)
  run: poetry run pytest tests/integration/ -m "infrastructure" --cov=services
```

**Full Integration Tests (with services):**
```yaml
- name: Integration Tests (Full)
  run: |
    docker-compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml up -d
    sleep 30
    poetry run pytest tests/integration/ -m "integration" -v
    docker-compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml down
```

**E2E Tests (separate workflow):**
```yaml
# For tests in tests/e2e/
- name: E2E Replay Validation
  run: poetry run pytest tests/e2e/ -v
```

## Files Modified

**No changes needed!** Tests are already correctly marked:

1. ✅ `test_signals_to_trades.py` - `@pytest.mark.integration` only (needs services)
2. ✅ `test_data_to_features.py` - `@pytest.mark.integration` only (needs services)
3. ✅ `test_features_to_bias.py` - `@pytest.mark.integration` only (needs services)
4. ✅ `test_full_pipeline.py` - `@pytest.mark.integration` only (needs services)
5. ✅ `test_multi_service_replay.py` - Both markers (no services needed)
6. ✅ `test_state_recovery.py` - Both markers (no services needed)
7. ✅ `test_stream_synchronization.py` - Both markers (no services needed)

## Expected Behavior

### Infrastructure Tests (No Services)

Marker: `@pytest.mark.infrastructure`

✅ Pass without any services running (just Redis + PostgreSQL)
✅ Complete in ~20-30 seconds
✅ Safe for pre-commit hooks
✅ Can run in CI without Docker stack
✅ Test synchronizer logic, state recovery, stream handling

### Integration Tests (With Services)

Marker: `@pytest.mark.integration` (without `infrastructure`)

❌ **Will fail if services not running** (expected behavior)
✅ Pass when full stack is up
✅ Take ~2-3 minutes
✅ Test service-to-service integration
✅ Validate data flows through microservices

### E2E Tests (Complete Workflows)

Marker: `@pytest.mark.e2e` (in `tests/e2e/`)

✅ Test complete workflows (backtester vs microservices)
✅ Replay validation
✅ Longest running tests

## Related Documentation

- **Quick Start:** `INTEGRATION_TESTS_QUICK_START.md`
- **Full Guide:** `tests/integration/README.md`
- **Summary:** `INTEGRATION_TESTS_FINAL_SUMMARY.md`
- **Test Runner:** `scripts/run_integration_tests.sh`

---

## Summary

**Correct Taxonomy:**

| Type | Marker(s) | Services? | Count | Run Time |
|------|-----------|-----------|-------|----------|
| Infrastructure | `@pytest.mark.infrastructure` | ❌ No | 30 | ~30s |
| Integration | `@pytest.mark.integration` only | ✅ Yes | 15 | ~2min |
| E2E | `@pytest.mark.e2e` | ✅ Yes | 2 | ~5min |

**Key Understanding:**
- **Integration tests** test integration between services → they NEED services running
- **Infrastructure tests** are a subset of integration tests that can run without services (just Redis/Postgres)
- **E2E tests** are complete workflow validation (separate folder: `tests/e2e/`)

**Status:** ✅ Complete

Tests are correctly marked. Default test runner runs infrastructure tests only (no services needed). Full integration tests require microservices to be running.
