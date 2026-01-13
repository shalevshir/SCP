# Databento Integration Guide

This guide covers how to use the Data Adapter service with Databento for live and historical data.

## Features

- **Live Data Streaming**: Real-time tick data from Databento WebSocket
- **Automatic Reconnection**: Exponential backoff on connection failures
- **Gap Detection & Backfill**: Automatic historical data fetch for missing candles
- **Market Hours Filtering**: Gold futures trading hours (Sun 6 PM - Fri 5 PM ET)
- **Session Events**: Publishes session open/close events to downstream services

## Configuration

### Environment Variables

```bash
# Databento API Configuration
DATABENTO_API_KEY=db-your-actual-key-here
DATABENTO_DATASET=GLBX.MDP3           # CME futures dataset
DATABENTO_GC_SYMBOL=GC.FUT            # Gold continuous contract
DATABENTO_DXY_SYMBOL=DX.FUT           # Dollar Index continuous

# Session Filtering
SESSION_FILTER_ENABLED=true           # Enable Gold futures market hours

# Connection Resilience
RECONNECT_MAX_RETRIES=10              # Max reconnection attempts (0=infinite)
RECONNECT_BASE_DELAY=1.0              # Base delay in seconds
RECONNECT_MAX_DELAY=60.0              # Max delay between retries

# Gap Detection
GAP_BACKFILL_ENABLED=true             # Enable automatic backfill
```

### Symbol Mapping

The Data Adapter automatically maps Databento symbols to internal format:

| Databento Symbol | Internal Symbol | Description |
|------------------|-----------------|-------------|
| `GC.FUT` | `GC` | Gold Futures (continuous) |
| `GCZ4`, `GCF5`, etc. | `GC` | Gold Futures (specific expiry) |
| `DX.FUT` | `DXY` | Dollar Index (continuous) |
| `DXU4`, `DXZ4`, etc. | `DXY` | Dollar Index (specific expiry) |

## Usage

### 1. Live Data Streaming

Start the Data Adapter with your Databento API key:

```bash
cd services/data-adapter

export DATABENTO_API_KEY="db-your-key"
export SESSION_FILTER_ENABLED=true
export GAP_BACKFILL_ENABLED=true

poetry run python src/data_adapter/main.py
```

**What happens:**
- Connects to Databento WebSocket
- Subscribes to GC and DX futures
- Aggregates ticks into 1-minute candles
- Filters by Gold futures market hours
- Publishes to `candles.1m.gc` and `candles.1m.dxy` Redis streams
- Emits `session.opened`/`session.closed` events

**Logs to watch for:**
```
Using ResilientDatabentoClient for live data
Connecting to Databento GLBX.MDP3 with symbols ['GC.FUT', 'DX.FUT']
Databento subscription successful, streaming ticks...
Databento connection established successfully
```

### 2. Historical Data Replay

Replay historical data from Databento through the pipeline:

```bash
export DATABENTO_API_KEY="db-your-key"

# Quick test (1 day)
make test-databento-replay

# Full week replay
make replay-databento START=2024-11-05 END=2024-11-12 SPEED=10

# Turbo mode (no delays)
make replay-databento START=2024-11-05 END=2024-11-12 SPEED=0
```

Or run directly:

```bash
poetry run python scripts/replay_databento_historical.py \
    --start 2024-11-05 \
    --end 2024-11-12 \
    --api-key "$DATABENTO_API_KEY" \
    --speed 10.0 \
    --processing-delay 10.0
```

**Arguments:**
- `--start`, `--end`: Date range (YYYY-MM-DD or ISO 8601)
- `--api-key`: Your Databento API key
- `--speed`: Replay speed (1.0=realtime, 10.0=10x faster, 0=turbo)
- `--dataset`: Databento dataset (default: GLBX.MDP3)
- `--gc-symbol`: Gold symbol (default: GC.FUT)
- `--dxy-symbol`: DXY symbol (default: DX.FUT)
- `--redis-url`: Redis URL (default: redis://localhost:6379)
- `--processing-delay`: Wait time after replay (default: 5.0s)

### 3. Full Validation (Backtester vs Databento)

Validate that microservices match backtester output using Databento data:

```bash
export DATABENTO_API_KEY="db-your-key"

poetry run python scripts/validate_databento_replay.py \
    --start 2024-11-05 \
    --end 2024-11-12 \
    --api-key "$DATABENTO_API_KEY" \
    --speed 0
```

**Output:**
- Backtester results JSON
- Comparison report with match rate
- Lists missing/extra trades
- Pass/fail status

**Expected match rate:** ≥90%

## Connection Resilience

The `ResilientDatabentoClient` handles connection issues automatically:

### Reconnection Behavior

1. **Connection lost**: Logs warning, enters "disconnected" state
2. **Exponential backoff**: Waits 1s, 2s, 4s, 8s, ... (up to max_delay)
3. **Retry**: Attempts to reconnect
4. **Success**: Resumes streaming, resets failure counter
5. **Max retries exceeded**: Logs error and exits (if max_retries > 0)

### Connection States

- `disconnected`: No active connection
- `connecting`: Attempting to establish connection
- `connected`: Successfully streaming data

### Logs Example

```
INFO: Connecting to Databento GLBX.MDP3 with symbols ['GC.FUT', 'DX.FUT']
INFO: Databento subscription successful, streaming ticks...
INFO: Databento connection established successfully

# ... some time later, connection drops ...

WARNING: Databento connection lost: ConnectionError. Reconnecting in 1.0s (attempt 1)
INFO: Attempting to connect to Databento (failures: 1)
INFO: Databento connection established successfully
```

## Gap Detection & Backfill

When gaps are detected (missing candles > 1 minute):

1. **Detection**: `GapDetector` identifies missing timestamps
2. **Backfill**: `DatabentoHistoricalFetcher` fetches missing data
3. **Publish**: Backfilled candles published to Redis in order
4. **Reset**: Gap state cleared

### Logs Example

```
WARNING: Gap detected for GC: 2024-11-05T10:05:00Z to 2024-11-05T10:08:00Z
INFO: Fetching historical data for GC from 2024-11-05T10:05:00Z to 2024-11-05T10:08:00Z
INFO: Fetched 3 historical candles for GC
INFO: Backfilled 3 candles for GC
```

### Configuration

```bash
# Enable backfill
export GAP_BACKFILL_ENABLED=true

# Disable backfill (gaps will only be logged)
export GAP_BACKFILL_ENABLED=false
```

## Market Hours (Gold Futures)

The `GoldFuturesSessionFilter` implements proper CME Gold futures hours:

### Trading Hours (Eastern Time)
- **Open**: Sunday 6:00 PM ET
- **Close**: Friday 5:00 PM ET
- **Daily maintenance**: 5:00 PM - 6:00 PM ET (Monday-Thursday)
- **Weekend**: Fully closed Saturday, closed Sunday before 6 PM

### Session Events

The Data Adapter publishes session boundary events to `session.events` stream:

```json
{
  "event_type": "session.opened",
  "timestamp": "2024-11-03T23:00:00Z",
  "session_date": "2024-11-03",
  "timezone": "America/New_York"
}
```

Downstream services can consume these events for:
- Daily state resets
- Trade limits refresh
- Risk parameter updates

## Testing

### Unit Tests

```bash
cd services/data-adapter

# Test resilient client
poetry run pytest tests/unit/test_resilient_client.py -v

# Test session filter
poetry run pytest tests/unit/test_session_filter.py -v

# All tests
poetry run pytest tests/unit/ -v
```

### Integration Test (Mock Client)

```bash
# Start infrastructure
make infra-up

# Run data-adapter with mock client (no API key)
cd services/data-adapter
export REDIS_URL=redis://localhost:6379
export SESSION_FILTER_ENABLED=true
export DATABENTO_API_KEY=""  # Empty = uses MockDatabentoClient

poetry run python src/data_adapter/main.py
```

### Integration Test (Real Databento)

```bash
export DATABENTO_API_KEY="db-your-key"

# Quick test (automated)
make test-databento-replay

# Manual test
poetry run python scripts/replay_databento_historical.py \
    --start 2024-11-05 --end 2024-11-06 \
    --api-key "$DATABENTO_API_KEY" --speed 0
```

## Troubleshooting

### "No GC data fetched"

- Check API key has historical data access
- Verify date range has data (check Databento dashboard)
- Check symbol format (GC.FUT vs GCZ4)

### "Connection lost" loops

- Check network connectivity
- Verify API key is valid
- Check rate limits (Databento may throttle)
- Increase `RECONNECT_MAX_DELAY` if needed

### "Gap detected" but no backfill

- Ensure `GAP_BACKFILL_ENABLED=true`
- Verify API key has historical data access
- Check logs for "Backfill failed" errors

### Session filter rejecting all candles

- Check timezone configuration (should be America/New_York)
- Verify timestamps are in correct timezone
- Test with `SESSION_FILTER_ENABLED=false` to bypass

## Production Checklist

Before going live with Databento:

- [ ] Valid Databento API key with live + historical access
- [ ] Tested connection resilience (simulate disconnects)
- [ ] Validated gap backfill works correctly
- [ ] Session filter tested for all edge cases (weekends, maintenance)
- [ ] Monitoring/alerting for connection state
- [ ] Verified symbol mapping for specific contract months
- [ ] Tested with paper broker for at least 1 week

## API Key Management

**Never commit your API key!**

Use environment variables or secret management:

```bash
# Development
export DATABENTO_API_KEY="db-dev-key"

# Production (Docker)
docker run -e DATABENTO_API_KEY="$DATABENTO_API_KEY" ...

# Production (Kubernetes)
kubectl create secret generic databento-api-key --from-literal=key=db-prod-key
```

## Cost Considerations

Databento charges for:
- Live data streaming (per connection)
- Historical data fetches (per request)
- Data volume (varies by plan)

**Optimization tips:**
- Use continuous contracts (GC.FUT) to avoid symbol rollovers
- Minimize historical fetches (cache in database)
- Use session filtering to reduce unnecessary data
- Monitor API usage via Databento dashboard
