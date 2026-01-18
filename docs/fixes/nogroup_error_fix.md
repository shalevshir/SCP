# NOGROUP Error Fix

## Issue

Services were crashing with this error:

```
redis.exceptions.ResponseError: NOGROUP No such key 'candles.1m.dxy' or consumer group 'htf-bias' in XREADGROUP with GROUP option
```

## Root Cause

The replay script (`scripts/replay_historical.py`) deletes all Redis streams before starting a replay to ensure clean state. This also deletes consumer groups associated with those streams.

When services (feature-engine, htf-bias, bot-core, execution) try to read from these streams, the consumer groups don't exist anymore. The existing error handling tried to recreate the group and retry once, but if that retry also failed with NOGROUP, it would crash the service.

The issue was that the `@with_retry` decorator only retries on connection errors (ConnectionError, TimeoutError), NOT on ResponseError (which NOGROUP is). So the retry logic wasn't being applied properly.

## Fix

Updated `services/shared/src/scp_shared/messaging/redis_streams.py` to add a dedicated retry loop for NOGROUP errors:

1. **Added explicit NOGROUP retry logic**: Instead of relying on the `@with_retry` decorator (which doesn't retry ResponseError), we added a manual retry loop inside the `_read()` function.

2. **Exponential backoff**: The retry logic uses exponential backoff (0.1s, 0.2s, 0.4s) to avoid hammering Redis.

3. **Maximum retries**: Fails after 3 attempts if the consumer group still can't be created.

## Changes

### `redis_streams.py`

```python
# Before (simplified)
async def _read():
    try:
        results = await self.redis.xreadgroup(...)
        return results
    except redis.ResponseError as e:
        if "NOGROUP" in str(e):
            self._initialized = False
            await self.ensure_group()
            # Retry once - if this fails, exception is raised
            results = await self.redis.xreadgroup(...)
            return results
        raise

# After (simplified)
async def _read():
    max_nogroup_retries = 3
    for nogroup_attempt in range(max_nogroup_retries):
        try:
            results = await self.redis.xreadgroup(...)
            return results
        except redis.ResponseError as e:
            if "NOGROUP" in str(e):
                self._initialized = False
                await self.ensure_group()
                
                if nogroup_attempt >= max_nogroup_retries - 1:
                    raise
                
                delay = 0.1 * (2 ** nogroup_attempt)
                await asyncio.sleep(delay)
                continue  # Retry
            raise
```

## Testing

Added comprehensive unit tests in `tests/unit/test_redis_nogroup_retry.py`:

1. **`test_nogroup_error_retry`**: Verifies that NOGROUP errors trigger consumer group recreation and retry
2. **`test_nogroup_error_max_retries`**: Verifies that after max retries, the exception is raised
3. **`test_nogroup_error_with_backoff`**: Verifies exponential backoff delays

All tests pass:

```bash
$ poetry run pytest tests/unit/test_redis_nogroup_retry.py -v
============================= test session starts ==============================
tests/unit/test_redis_nogroup_retry.py ...                               [100%]
======================== 3 passed, 5 warnings in 0.47s =========================
```

## Services Rebuilt

The following services were rebuilt with the fix:

- ✅ `feature-engine`
- ✅ `htf-bias`
- ✅ `bot-core`
- ✅ `execution`

## What to Do Next

1. **Restart the affected services** (if running):

```bash
cd /Users/shalev/Code/SCP
docker-compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml restart feature-engine htf-bias bot-core execution
```

2. **Run the integration tests** to verify the fix:

```bash
./scripts/run_integration_tests.sh
```

3. **Monitor the logs** during replay to ensure no more NOGROUP errors appear:

```bash
docker-compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml logs -f feature-engine htf-bias
```

## Expected Behavior

After the fix:

- Services will automatically recreate consumer groups when they're deleted (e.g., during replay script startup)
- Services will retry up to 3 times with exponential backoff if group creation initially fails
- Services will continue processing without crashes when streams are cleaned up and recreated

## Related Files

- **Core Fix**: `services/shared/src/scp_shared/messaging/redis_streams.py`
- **Tests**: `tests/unit/test_redis_nogroup_retry.py`
- **Documentation**: `docs/fixes/nogroup_error_fix.md` (this file)
