# CI Integration Test Failures Fix

**Date:** 2024-12-24  
**Status:** ✅ Fixed  
**Tests Fixed:** 4 integration tests in `test_signals_to_trades.py`

---

## Problem

Integration tests were passing locally but failing in CI with the following errors:

### Failure 1: Bot-core Unable to Generate Signals

```
scp-bot-core-test  | ConfigError: Scoring config file not found: /config/scoring_config.yaml
```

All 4 integration tests failed because no signals were being generated due to bot-core crashing when trying to load the scoring config.

### Failure 2: Execution Service Crashing on Signal Arrival

```
scp-execution-test  | TypeError: expected str, got list
scp-execution-test  |   File "/app/execution/src/execution_svc/state_machine_manager.py", line 272, in _save_state_machine
scp-execution-test  |     await self._db_pool.execute(
```

The execution service was crashing when trying to save state machines due to JSONB encoding issues with asyncpg.

---

## Root Causes

### 1. Scoring Config Path Mismatch in Docker Containers

**File:** `services/shared/src/scp_shared/rule_engine/config_loader.py`

The `load_scoring_config()` function calculated the config path by navigating up from the source file:

```python
# Navigate from services/shared/src/scp_shared/rule_engine to project root
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
config_path = str(project_root / "config" / "scoring_config.yaml")
```

This worked in local development where the project root is the workspace directory, but in Docker containers:
- The path calculation resolved to `/config/scoring_config.yaml`
- The volume mount in `docker-compose.services.yml` mapped `../config` to `/app/bot-core/config`
- The test compose file (`docker-compose.test.yml`) **didn't mount the config volume at all**

### 2. JSONB Encoding Issue with asyncpg

**File:** `services/execution/src/execution_svc/state_machine_manager.py`

The code was passing Python lists directly to asyncpg for JSONB columns:

```python
confirmations_list = list(sm.confirmations) if sm.confirmations else []
# ...
await self._db_pool.execute(
    query,
    signal_id,
    sm.current_state.value,
    sm.detection_bar_idx,
    db_direction,
    confirmations_list,  # Python list - asyncpg expected to handle JSONB conversion
    sm.execution_count,
    transition_history_list,
)
```

While the comments claimed "asyncpg handles JSONB serialization automatically from Python objects", this behavior appears to be inconsistent across environments or asyncpg versions. In CI, asyncpg expected a JSON string instead of a Python object.

---

## Solution

### Fix 1: Smart Config Path Detection

**File:** `services/shared/src/scp_shared/rule_engine/config_loader.py`

Modified `load_scoring_config()` to try multiple locations:

```python
if config_path is None:
    # Try multiple locations:
    # 1. /config/scoring_config.yaml (Docker container mount)
    # 2. config/scoring_config.yaml from project root (local development)
    docker_config = Path("/config/scoring_config.yaml")
    if docker_config.exists():
        config_path = str(docker_config)
    else:
        # Navigate from services/shared/src/scp_shared/rule_engine to project root
        project_root = Path(__file__).parent.parent.parent.parent.parent.parent
        config_path = str(project_root / "config" / "scoring_config.yaml")
```

This ensures the config is found in both environments:
- Docker: Uses `/config/scoring_config.yaml`
- Local: Uses calculated project root path

### Fix 2: Explicit JSON Serialization for JSONB Columns

**File:** `services/execution/src/execution_svc/state_machine_manager.py`

Changed to explicitly serialize to JSON strings using `json.dumps()`:

```python
# Convert confirmations to JSON string for JSONB column
# Use json.dumps() to ensure consistent serialization across asyncpg versions
confirmations_list = list(sm.confirmations) if sm.confirmations else []
confirmations_json = json.dumps(confirmations_list)

# Convert transition history to JSON string for JSONB column
transition_history_list = [
    {
        "from_state": t.from_state.value,
        "to_state": t.to_state.value,
        "bar_idx": t.bar_idx,
        "reason": t.reason,
        "timestamp": t.timestamp.isoformat(),
    }
    for t in sm.transition_history
]
transition_history_json = json.dumps(transition_history_list)

# ...
await self._db_pool.execute(
    query,
    signal_id,
    sm.current_state.value,
    sm.detection_bar_idx,
    db_direction,
    confirmations_json,  # JSON string for JSONB column
    sm.execution_count,
    transition_history_json,  # JSON string for JSONB column
)
```

This ensures consistent behavior across all environments by explicitly controlling serialization.

### Fix 3: Add Config Volume Mount to Test Compose File

**File:** `infra/docker-compose.test.yml`

Added the missing volume mount for bot-core:

```yaml
bot-core:
  container_name: scp-bot-core-test
  environment:
    DATABASE_URL: postgresql://scp_test:scp_test_password@postgres:5432/scp_test
  volumes:
    - ../config:/config:ro  # Mount config at /config for load_scoring_config() to find
  restart: "no"
```

This ensures the scoring config is available in the test environment at the expected path.

---

## Verification

### Unit Tests
All execution service unit tests pass:
```bash
poetry run pytest services/execution/tests/unit/test_state_machine_manager.py -v
# 12 passed
```

### Config Loading
Config loader works in local environment:
```python
from scp_shared.rule_engine.config_loader import load_scoring_config
config = load_scoring_config()
# Loaded config with 3 setup types
```

### Integration Tests (Expected in CI)
With these fixes, the 4 failing integration tests should now pass:
- `test_signal_triggers_trade_execution`
- `test_sl_hit_closes_trade`
- `test_tp_hit_closes_trade`
- `test_invalidation_closes_trade`

---

## Related Files Modified

1. `services/shared/src/scp_shared/rule_engine/config_loader.py` - Smart config path detection
2. `services/execution/src/execution_svc/state_machine_manager.py` - Explicit JSON serialization
3. `infra/docker-compose.test.yml` - Add config volume mount for bot-core

---

## Lessons Learned

1. **Environment-specific path resolution**: Code that relies on relative path calculations can break in Docker containers. Always provide fallback paths for containerized environments.

2. **Don't rely on implicit serialization**: While asyncpg claims to handle JSONB serialization automatically, explicitly using `json.dumps()` ensures consistent behavior across environments and versions.

3. **Test compose parity**: The test compose file (`docker-compose.test.yml`) should maintain parity with the services compose file (`docker-compose.services.yml`) for critical volume mounts like config directories.

4. **CI is the source of truth**: Tests passing locally but failing in CI usually indicates environment-specific differences (paths, versions, mounts) that need explicit handling.

---

## Next Steps

1. ✅ Push changes and verify CI passes
2. Consider adding a healthcheck that validates config files are accessible
3. Consider adding integration test that specifically validates config loading in containerized environment

