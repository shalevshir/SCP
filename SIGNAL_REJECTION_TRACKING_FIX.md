# Signal Rejection Tracking Fix

**Date:** January 16, 2026  
**Status:** ✅ Complete (Pending Service Rebuild)

## Problem Statement

When `SignalEngine.generate()` returned `None`, the Bot Core service **always** recorded the rejection as `"confidence_filter"`. However, `generate()` can return `None` for three distinct reasons:

1. **HTF validity failure**: HTF conflict or DXY chop detected
2. **Confidence filter**: Signal confidence is not "A+"
3. **Neutral direction**: Signal direction is "neutral" (rare edge case)

This caused HTF validity rejections and neutral direction rejections to be incorrectly counted as confidence filter rejections, making the `signals_rejected_total` metric's `reason` label unreliable for monitoring and debugging.

## Root Cause

**Location:** `services/bot-core/src/bot_core_svc/main.py:268-271`

```python
# OLD CODE (INCORRECT)
if signal_msg is not None:
    await signal_publisher.publish(signal_msg)
    core_metrics.signals_generated_total.labels(...).inc()
else:
    # Signal didn't meet A+ criteria
    core_metrics.record_signal_rejection("confidence_filter", mode, service)  # ❌ WRONG
```

The problem: `SignalEngine.generate()` returned `None` without indicating **why** it rejected the signal.

## Solution

### 1. Updated Rejection Reasons (metrics.py)

Added new rejection reason types:

```python
REJECTION_REASONS = {
    "risk_limit",
    "session_filter",
    "confidence_filter",  # Existing
    "htf_validity",       # ✅ NEW - HTF conflict or DXY chop
    "neutral_direction",  # ✅ NEW - Neutral direction edge case
    "cooldown",
    "invalid_context",
    "warmup",
    "kill_switch",
    "active_trade",
}
```

### 2. Modified SignalEngine.generate() Return Type (signal_engine.py)

Changed the return type from `SignalMessage | None` to `tuple[SignalMessage | None, str | None]`:

```python
def generate(
    self,
    features: FeaturesMessage,
    htf_bias: HTFBiasMessage,
    context: dict,
) -> tuple[SignalMessage | None, str | None]:
    """Generate signal from features and bias.
    
    Returns:
        Tuple of (SignalMessage, rejection_reason):
            - SignalMessage if A+ signal generated, None otherwise
            - rejection_reason if signal rejected, None if signal generated
    """
```

### 3. Updated Rejection Logic (signal_engine.py)

Each rejection path now returns the specific reason:

```python
# HTF validity check
if not htf_valid:
    logger.debug(...)
    return None, "htf_validity"  # ✅ Specific reason

# Confidence filter
if signal.confidence != "A+":
    logger.debug(...)
    return None, "confidence_filter"  # ✅ Specific reason

# Neutral direction filter
if signal.direction == "neutral":
    logger.warning(...)
    return None, "neutral_direction"  # ✅ Specific reason

# Success case
return signal_msg, None  # ✅ No rejection
```

### 4. Updated Bot Core Main Logic (main.py)

Now unpacks the tuple and records the correct rejection reason:

```python
# NEW CODE (CORRECT)
signal_msg, rejection_reason = signal_engine.generate(features, bias, context)

if signal_msg is not None:
    await signal_publisher.publish(signal_msg)
    core_metrics.signals_generated_total.labels(...).inc()
else:
    # Signal was rejected - record the specific reason
    if rejection_reason:
        core_metrics.record_signal_rejection(rejection_reason, mode, service)  # ✅ CORRECT
```

### 5. Updated Tests (test_signal_engine.py)

All existing tests were updated to handle the new tuple return type:

```python
# OLD TEST CODE
result = engine.generate(features, htf_bias, context)
assert result is None

# NEW TEST CODE
result, rejection_reason = engine.generate(features, htf_bias, context)
assert result is None
assert rejection_reason == "confidence_filter"  # ✅ Verify correct reason
```

Added new test case for HTF validity rejection:

```python
def test_generate_returns_none_for_htf_validity_failure(self, mock_score_signal: Mock) -> None:
    """Generate returns None with htf_validity reason when conflict or chop detected."""
    # ... setup with conflict_detected=True ...
    
    result, rejection_reason = engine.generate(features, htf_bias, {"session_ok": True})
    
    assert result is None
    assert rejection_reason == "htf_validity"  # ✅ Correct rejection reason
```

## Files Modified

1. **services/bot-core/src/bot_core_svc/metrics.py**
   - Added `"htf_validity"` and `"neutral_direction"` to `REJECTION_REASONS`

2. **services/bot-core/src/bot_core_svc/signal_engine.py**
   - Changed `generate()` return type to tuple
   - Updated all return statements to include rejection reason

3. **services/bot-core/src/bot_core_svc/main.py**
   - Updated to unpack tuple from `generate()`
   - Removed hardcoded `"confidence_filter"` label
   - Now records actual rejection reason

4. **services/bot-core/tests/unit/test_signal_engine.py**
   - Updated all test cases to unpack tuple
   - Added assertions for rejection reasons
   - Added new test for HTF validity rejection

## Impact

### Before Fix

```
scp_signals_rejected_total{reason="confidence_filter"} = 150
# ^^ Includes ALL rejections (HTF validity, confidence, neutral)
```

### After Fix

```
scp_signals_rejected_total{reason="confidence_filter"} = 120
scp_signals_rejected_total{reason="htf_validity"} = 28
scp_signals_rejected_total{reason="neutral_direction"} = 2
```

Now operators can:
- Identify if HTF conflicts are blocking good signals
- Distinguish between scoring issues (confidence) vs. structural issues (HTF validity)
- Debug DXY chop detection impact on signal flow
- Track rare neutral direction edge cases

## Deployment Status

✅ **Code Changes**: Complete  
⏳ **Service Rebuild**: Required (bot-core service needs rebuild)  
⏳ **Testing**: Unit tests updated, awaiting service restart  

## Next Steps

1. Rebuild and restart bot-core service:
   ```bash
   docker compose -f infra/docker-compose.infra.yml \
                  -f infra/docker-compose.services.yml \
                  -f infra/docker-compose.paper.yml \
                  up --build -d bot-core
   ```

2. Verify metrics are being recorded with correct reasons:
   ```bash
   curl http://localhost:8004/metrics | grep scp_signals_rejected_total
   ```

3. Monitor Grafana dashboard "Signal Rejection Reasons" panel to see breakdown

## Grafana Integration

The existing Grafana panel "3.2 Signal Rejection Reasons" will automatically show the new breakdowns once the service is rebuilt:

```promql
sum by (reason) (rate(scp_signals_rejected_total{mode="$mode"}[5m]))
```

Expected output:
- `confidence_filter`: Signals below A+ threshold
- `htf_validity`: HTF conflicts or DXY chop blocking signals
- `neutral_direction`: Rare edge case (close == vwap exactly)
- `session_filter`: Outside trading hours
- `risk_limit`: PDLL or loss streak active
- ... (other rejection reasons)

## Verification Checklist

- [x] Updated rejection reason enum
- [x] Modified SignalEngine.generate() return type
- [x] Updated all return statements with reasons
- [x] Updated main.py to use rejection reasons
- [x] Updated unit tests
- [x] Added test for HTF validity rejection
- [ ] Rebuild bot-core service
- [ ] Verify metrics in Prometheus
- [ ] Check Grafana dashboard shows new breakdowns
- [ ] Monitor production for 24 hours

## Related Documentation

- **Metrics Reference**: `services/bot-core/src/bot_core_svc/metrics.py`
- **Signal Engine**: `services/bot-core/src/bot_core_svc/signal_engine.py`
- **Grafana Dashboard**: `infra/grafana/dashboards/operations.json`
- **Test Suite**: `services/bot-core/tests/unit/test_signal_engine.py`
