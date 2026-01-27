# Warmup Status Stale Success Markers Fix

**Date:** 2025-01-27  
**Status:** ✅ Fixed  
**Severity:** High (Data Consistency Bug)

## Problem

The warmup system had a race condition bug where downstream services could incorrectly detect warmup data as available when it was actually stale or missing.

### Root Cause

When `_set_error_status` was called after a failed warmup attempt, it only set `error` and `timestamp` fields in the Redis `warmup:status` hash:

```python
# BEFORE (buggy code)
await self.redis.hset(
    "warmup:status",
    mapping={
        "error": error_message,
        "timestamp": datetime.now(UTC).isoformat(),
    },
)
```

This left **stale success markers** (`gc=complete`, `dxy=complete`, `gc_count`, `dxy_count`) from a previous successful warmup run intact in the hash.

### Vulnerable Scenario

1. **First run succeeds** (t=0):
   - Hash: `{gc: "complete", dxy: "complete", gc_count: "1440", dxy_count: "1440"}`
   - Warmup streams published to Redis
   - TTL set to 10 minutes

2. **Service restarts** (t=5 minutes, within TTL):
   - Hash still exists with success markers

3. **Second run fails** (t=5 minutes):
   - IB Gateway unavailable or no candles fetched
   - `_set_error_status` called
   - Hash now: `{gc: "complete", dxy: "complete", gc_count: "1440", dxy_count: "1440", error: "No GC candles fetched"}`
   - **Stale success markers NOT cleared**

4. **Downstream service checks warmup** (t=5 minutes):
   - `check_warmup_available()` checks: `status.get("gc") == "complete"` ✅
   - `check_warmup_available()` checks: `status.get("dxy") == "complete"` ✅
   - **Does NOT check for `error` field**
   - Returns `available=True` ❌ WRONG!

5. **Downstream service tries to consume warmup streams**:
   - Streams may be expired, empty, or contain stale data
   - Service may fail to warmup correctly or use stale data

### Impact

- **Data Consistency**: Services could use stale warmup data from previous runs
- **Silent Failures**: Services might incorrectly report successful warmup when it failed
- **Replay Correctness**: Historical replay could use wrong initial state

## Solution

### Two-Layer Defense

#### Layer 1: Publisher Clears Status Hash (Primary Fix)

Modified `_set_error_status` to **delete the entire status hash** before setting error status:

```python
# AFTER (fixed code)
async def _set_error_status(self, error_message: str) -> None:
    """Set error status in Redis for downstream services.

    Deletes any existing warmup status hash to prevent stale success
    markers from previous runs from being visible to consumers.
    """
    try:
        # Delete entire status hash to clear any stale success markers
        await self.redis.delete("warmup:status")

        # Set fresh error status
        await self.redis.hset(
            "warmup:status",
            mapping={
                "error": error_message,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await self.redis.expire("warmup:status", self.ttl_seconds)
    except Exception as e:
        logger.error(f"Failed to set error status in Redis: {e}", exc_info=True)
```

#### Layer 2: Consumer Rejects Error Status (Defense in Depth)

Added defensive check in `check_warmup_available` to reject status with `error` field:

```python
# Defensive check in consumer
if "error" in status_decoded:
    error_msg = status_decoded.get("error", "unknown error")
    logger.info(f"Warmup status indicates error: {error_msg}")
    return {
        "available": False,
        "gc_ready": False,
        "dxy_ready": False,
        "gc_count": 0,
        "dxy_count": 0,
    }
```

This ensures that even if the publisher bug reoccurs, consumers will still reject the status.

## Test Coverage

### Publisher Tests

**File:** `services/data-adapter/tests/unit/test_warmup_publisher.py`

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_status_clears_stale_success_markers() -> None:
    """Error status deletes entire hash to prevent stale success markers."""
    # Simulates fetch failure and verifies:
    # 1. warmup:status hash is deleted
    # 2. Fresh error status is set
    # 3. Delete happens BEFORE hset
```

### Consumer Tests

**File:** `services/shared/tests/unit/messaging/test_warmup_consumer.py`

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_warmup_available_rejects_status_with_error_field() -> None:
    """Rejects warmup as unavailable when error field present."""
    # Simulates stale success markers + error field
    # Verifies consumer rejects as unavailable
```

All tests pass ✅

## Verification

To verify the fix manually:

```bash
# 1. Start Redis
docker compose -f infra/docker-compose.infra.yml up -d redis

# 2. Simulate successful warmup (set success markers)
redis-cli HSET warmup:status gc complete dxy complete gc_count 1440 dxy_count 1440

# 3. Check status (should show available)
redis-cli HGETALL warmup:status

# 4. Simulate failed warmup (trigger error path)
# Start data-adapter with invalid IB config or no data

# 5. Check status again
redis-cli HGETALL warmup:status
# Should ONLY show: error, timestamp (no stale gc/dxy fields)

# 6. Downstream service should correctly detect unavailable
# Run feature-engine or htf-bias and check logs:
# "Warmup streams not available - will use database fallback"
```

## Related Files

- **Publisher:** `services/data-adapter/src/data_adapter/warmup_publisher.py`
- **Consumer:** `services/shared/src/scp_shared/messaging/warmup_consumer.py`
- **Tests:** 
  - `services/data-adapter/tests/unit/test_warmup_publisher.py`
  - `services/shared/tests/unit/messaging/test_warmup_consumer.py`

## Lessons Learned

1. **State Pollution**: When updating shared state (Redis hash), always clear or replace entire structure to avoid partial updates
2. **Defense in Depth**: Implement validation at both producer and consumer layers
3. **TTL Windows**: Be aware of state persistence within TTL windows during service restarts
4. **Test Race Conditions**: Write tests that simulate the exact timing scenario (previous state + current failure)

## Future Improvements

Consider these enhancements for production robustness:

1. **Atomic Operations**: Use Redis transactions (MULTI/EXEC) to ensure atomic hash updates
2. **Versioning**: Add version field to status hash to detect stale data
3. **Timestamps**: Consumer could check timestamp freshness (reject if > TTL/2 old)
4. **Stream Metadata**: Store stream lengths in status hash and verify before consumption
