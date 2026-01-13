# Testing Databento Provider Locally - Step-by-Step Guide

Complete guide to test the Databento integration on your local machine.

---

## Prerequisites

### 1. Get Databento API Key

1. Go to [databento.com](https://databento.com)
2. Sign up for an account
3. Navigate to API Keys section
4. Generate a new API key
5. Copy the key (starts with `db-`)

### 2. Verify Docker is Running

```bash
docker info
# Should show Docker info without errors
```

---

## Step-by-Step Test Guide

### Step 1: Start Infrastructure

```bash
# Navigate to project root
cd /Users/shalev/Code/SCP

# Start Redis and PostgreSQL
make infra-up

# Verify they're running
docker ps | grep scp
# Should show: scp-redis and scp-postgres
```

**Verify connectivity:**
```bash
# Test Redis
docker exec scp-redis redis-cli ping
# Should output: PONG

# Test PostgreSQL
docker exec scp-postgres pg_isready -U scp
# Should output: accepting connections
```

---

### Step 2: Set Environment Variables

```bash
# Set your Databento API key
export DATABENTO_API_KEY="db-your-actual-key-here"

# Optional: Set other config (defaults work fine)
export DATABENTO_DATASET="GLBX.MDP3"
export DATABENTO_GC_SYMBOL="GC.FUT"
export DATABENTO_DXY_SYMBOL="DX.FUT"
export DATA_PROVIDER="databento"
```

**Verify it's set:**
```bash
echo $DATABENTO_API_KEY
# Should show: db-...
```

---

### Step 3: Test Historical Replay (Quick 1-Day Test)

This tests fetching historical data from Databento and replaying it through the pipeline:

```bash
# Run quick 1-day test
make test-databento-replay
```

**What this does:**
1. Starts infrastructure (Redis, PostgreSQL)
2. Fetches 1 day of data (Nov 5, 2024) from Databento
3. Replays it through the pipeline (turbo mode)
4. Verifies candles appear in Redis
5. Reports success/failure

**Expected output:**
```
==========================================
Databento Historical Replay Test
==========================================
✓ Databento API key configured
✓ Docker is running
✓ Redis ready
✓ PostgreSQL ready
Fetching GC data from Databento: 2024-11-05...
Fetched 1440 candles for GC
Fetched 1440 candles for DXY
Starting replay...
Published 2880 candles
✓ Candles successfully published to Redis
==========================================
Databento Replay Test PASSED
==========================================
```

---

### Step 4: Test Full Week Replay

Once the quick test passes, try a full week:

```bash
make replay-databento START=2024-11-05 END=2024-11-12 SPEED=0
```

**What this does:**
- Fetches 7 days of historical data from Databento
- Replays at turbo speed (SPEED=0)
- Publishes to Redis streams
- Waits 10 seconds for processing

**Monitor progress:**

In another terminal:
```bash
# Watch Redis stream grow
watch -n 1 'docker exec scp-redis redis-cli XLEN candles.1m.gc'

# Watch candles being published
docker exec -it scp-redis redis-cli XREAD COUNT 5 STREAMS candles.1m.gc 0
```

**Expected:**
- ~10,080 GC candles (7 days × 24 hours × 60 minutes)
- ~10,080 DXY candles
- Total: ~20,000 candles

---

### Step 5: Test with Microservices Running

Now test the full pipeline:

```bash
# 1. Start all microservices
make services-up

# Wait for services to be healthy (30 seconds)
sleep 30

# 2. Clean environment
make replay-clean  # Type 'y' when prompted

# 3. Run replay
make replay-databento START=2024-11-05 END=2024-11-12 SPEED=0
```

**Monitor the pipeline:**

Open 6 terminals:

**Terminal 1 - Data Adapter:**
```bash
docker logs -f scp-data-adapter
```

**Terminal 2 - Feature Engine:**
```bash
docker logs -f scp-feature-engine
```

**Terminal 3 - Bot Core:**
```bash
docker logs -f scp-bot-core
```

**Terminal 4 - Execution:**
```bash
docker logs -f scp-execution
```

**Terminal 5 - Redis Monitoring:**
```bash
# Watch streams
watch -n 2 'docker exec scp-redis redis-cli <<EOF
XLEN candles.1m.gc
XLEN features.1m
XLEN htf.bias
XLEN signals.pending
XLEN trades.opened
EOF'
```

**Terminal 6 - Database Monitoring:**
```bash
# Watch trades
watch -n 5 'docker exec scp-postgres psql -U scp -d scp -c "SELECT COUNT(*) AS total_trades, direction, exit_reason FROM trades GROUP BY direction, exit_reason ORDER BY total_trades DESC"'
```

**Expected flow:**
```
candles.1m.gc → features.1m → htf.bias → signals.pending → trades.opened → trades.closed
```

---

### Step 6: Validate Against Backtester

Compare microservices output with backtester:

```bash
make validate-databento START=2024-11-05 END=2024-11-12
```

**What this does:**
1. Runs backtester on date range
2. Replays same data through microservices (via Databento)
3. Collects trades from both systems
4. Compares trade-by-trade
5. Generates comparison report

**Expected output:**
```
==========================================
Validation Complete
==========================================
Backtester trades: 42
Microservices trades: 40
Match rate: 95.2%
Missing in microservices: 2
Extra in microservices: 0

✓ Validation PASSED (>90% match rate)
```

**Report location:** `output/databento_validation/comparison_report_*.json`

---

### Step 7: Test Live Connection (Optional)

Test actual live Databento streaming (uses live market data):

```bash
# 1. Stop replay scripts
# Ctrl+C any running replay

# 2. Start data-adapter with live Databento
cd services/data-adapter

export DATA_PROVIDER=databento
export DATABENTO_API_KEY="db-your-key"
export REDIS_URL=redis://localhost:6379
export SESSION_FILTER_ENABLED=true
export GAP_BACKFILL_ENABLED=true

poetry run python src/data_adapter/main.py
```

**Watch the logs:**
```
INFO: Creating ResilientDatabentoClient for live data
INFO: Connecting to Databento GLBX.MDP3 with symbols ['GC.FUT', 'DX.FUT']
INFO: Databento subscription successful, streaming ticks...
INFO: Databento connection established successfully
DEBUG: Candle closed: GC 2026-01-12T15:23:00+00:00 O=2650.0...
```

**Monitor candles:**
```bash
# In another terminal
docker exec -it scp-redis redis-cli XREAD COUNT 10 STREAMS candles.1m.gc 0
```

**Stop the service:**
```bash
# Press Ctrl+C in the data-adapter terminal
```

---

## Troubleshooting

### Issue 1: "Databento API key required"

**Problem:** No API key set
```
ValueError: DATABENTO_API_KEY required for databento provider
```

**Solution:**
```bash
export DATABENTO_API_KEY="db-your-actual-key"
```

---

### Issue 2: "Redis connection refused"

**Problem:** Redis not running

**Solution:**
```bash
make infra-up
# Wait 5 seconds
docker ps | grep scp-redis
```

---

### Issue 3: "No GC data fetched"

**Possible causes:**
1. Invalid API key
2. API key doesn't have historical data access
3. Date range has no data
4. Rate limiting

**Debug:**
```bash
# Check API key format
echo $DATABENTO_API_KEY | grep "^db-"

# Try different date range
make replay-databento START=2024-12-01 END=2024-12-02 SPEED=0

# Check Databento dashboard for quota/limits
```

---

### Issue 4: "Connection lost" loops

**Problem:** Network issues or API limits

**Check logs for:**
```
WARNING: Databento connection lost: ... Reconnecting in 2.0s (attempt 2)
```

**Solutions:**
- Wait for reconnection (automatic)
- Check network connectivity
- Verify API key is valid
- Check Databento status page

---

### Issue 5: Services not processing data

**Problem:** Services not running or not consuming streams

**Verify services:**
```bash
# Check all services are healthy
curl http://localhost:8001/health  # Data Adapter
curl http://localhost:8002/health  # Feature Engine
curl http://localhost:8003/health  # HTF Bias
curl http://localhost:8004/health  # Bot Core
curl http://localhost:8005/health  # Execution

# All should return: {"status":"healthy",...}
```

**Check consumer groups:**
```bash
docker exec scp-redis redis-cli XINFO GROUPS candles.1m.gc
# Should show: feature-engine, htf-bias, execution
```

---

## Verification Checklist

After running tests, verify:

### ✅ Data Flow Check

```bash
# Check Redis streams have data
docker exec scp-redis redis-cli XLEN candles.1m.gc
docker exec scp-redis redis-cli XLEN candles.1m.dxy
docker exec scp-redis redis-cli XLEN features.1m
docker exec scp-redis redis-cli XLEN htf.bias
docker exec scp-redis redis-cli XLEN signals.pending
docker exec scp-redis redis-cli XLEN trades.opened
```

Expected: All show numbers > 0

### ✅ Database Check

```bash
# Check tables have data
docker exec scp-postgres psql -U scp -d scp -c "
SELECT 
  (SELECT COUNT(*) FROM candles) as candles,
  (SELECT COUNT(*) FROM features) as features,
  (SELECT COUNT(*) FROM htf_bias_history) as htf_bias,
  (SELECT COUNT(*) FROM trades) as trades
"
```

Expected: All counts > 0 (trades may be 0 if no signals generated)

### ✅ Logs Check

```bash
# Check for errors in logs
docker logs scp-data-adapter 2>&1 | grep ERROR
docker logs scp-feature-engine 2>&1 | grep ERROR
docker logs scp-bot-core 2>&1 | grep ERROR
docker logs scp-execution 2>&1 | grep ERROR
```

Expected: No ERROR lines (or only minor warnings)

---

## Performance Expectations

### Historical Replay (Turbo Mode)

| Data Range | Candles | Time to Fetch | Time to Replay | Total |
|------------|---------|---------------|----------------|-------|
| 1 day | ~2,900 | 5-10s | 5s | ~15s |
| 1 week | ~20,000 | 30-60s | 30s | ~90s |
| 1 month | ~86,000 | 2-5min | 2min | ~7min |

### Live Streaming

| Metric | Expected |
|--------|----------|
| Connection time | 2-5 seconds |
| First tick latency | <1 second |
| Reconnection | 1-60 seconds (exponential) |
| Candle publish rate | 2/minute (GC + DXY) |

---

## Success Criteria

After testing, you should see:

✅ **Quick test passes**
```bash
make test-databento-replay
# ✓ Databento Replay Test PASSED
```

✅ **Candles in Redis**
```bash
docker exec scp-redis redis-cli XLEN candles.1m.gc
# Shows: 1440 (for 1 day test)
```

✅ **No errors in logs**
```bash
docker logs scp-data-adapter 2>&1 | grep -c ERROR
# Shows: 0
```

✅ **Validation passes**
```bash
make validate-databento START=2024-11-05 END=2024-11-12
# Match rate: >90%
```

---

## Next Steps After Successful Testing

1. ✅ **Local tests pass** (you are here)
2. ⏳ **Validate parity** - Run `make validate-databento` 
3. ⏳ **Paper trading** - Run with live data for 2-4 weeks
4. ⏳ **Go live** - Switch to real broker

---

## Quick Test Script

Save this as `test_databento_quick.sh`:

```bash
#!/bin/bash
set -e

echo "Testing Databento Integration..."

# Check prerequisites
if [ -z "$DATABENTO_API_KEY" ]; then
    echo "ERROR: DATABENTO_API_KEY not set"
    echo "Run: export DATABENTO_API_KEY='db-your-key'"
    exit 1
fi

# Start infrastructure
echo "Starting infrastructure..."
cd /Users/shalev/Code/SCP
make infra-up
sleep 5

# Run quick test
echo "Running 1-day replay test..."
make replay-databento START=2024-11-05 END=2024-11-06 SPEED=0

# Verify results
echo "Verifying results..."
GC_COUNT=$(docker exec scp-redis redis-cli XLEN candles.1m.gc)
echo "GC candles: $GC_COUNT"

if [ "$GC_COUNT" -gt 1000 ]; then
    echo "✓ TEST PASSED - Got $GC_COUNT candles"
    exit 0
else
    echo "✗ TEST FAILED - Only got $GC_COUNT candles"
    exit 1
fi
```

Run it:
```bash
chmod +x test_databento_quick.sh
export DATABENTO_API_KEY="db-your-key"
./test_databento_quick.sh
```

---

## Common Test Scenarios

### Scenario 1: First-Time Setup

```bash
# 1. Infrastructure
make infra-up

# 2. Set API key
export DATABENTO_API_KEY="db-your-key"

# 3. Quick test
make test-databento-replay

# Expected: PASSED
```

### Scenario 2: Full Validation

```bash
# 1. Clean environment
make replay-clean  # Type 'y'

# 2. Run full validation
make validate-databento START=2024-11-05 END=2024-11-12

# Expected: >90% match rate
```

### Scenario 3: Live Connection Test

```bash
# 1. Start data-adapter only
cd services/data-adapter
export DATA_PROVIDER=databento
export DATABENTO_API_KEY="db-your-key"
export REDIS_URL=redis://localhost:6379

poetry run python src/data_adapter/main.py

# 2. Watch logs for live data
# Should see: "Databento connection established successfully"
# Should see: Tick data streaming

# 3. Press Ctrl+C to stop
```

### Scenario 4: Test Reconnection

```bash
# 1. Start data-adapter
cd services/data-adapter
poetry run python src/data_adapter/main.py &
PID=$!

# 2. Kill after 10 seconds
sleep 10
kill $PID

# 3. Check logs show graceful shutdown
# Should see: "Closing Databento connection"
# No error stack traces
```

---

## Data Verification

### Verify Candle Data Quality

```bash
# Check a few candles
docker exec scp-redis redis-cli XREAD COUNT 3 STREAMS candles.1m.gc 0

# Should show candles with:
# - timestamp
# - symbol: GC
# - timeframe: 1m
# - OHLCV values (all positive numbers)
```

### Verify Database Persistence

```bash
# Check candles table
docker exec scp-postgres psql -U scp -d scp -c "
SELECT timestamp, symbol, close, volume 
FROM candles 
WHERE symbol = 'GC'
ORDER BY timestamp DESC 
LIMIT 5
"

# Should show recent GC candles
```

### Verify Session Events

```bash
# Check for session events
docker exec scp-redis redis-cli XREAD BLOCK 1000 STREAMS session.events 0

# Should show events like:
# - event_type: session.opened / session.closed
# - timestamp
# - session_date
```

---

## Performance Benchmarks

Test your system's performance:

```bash
# Benchmark 1: Fetch speed
time make replay-databento START=2024-11-05 END=2024-11-06 SPEED=0
# Expected: 15-30 seconds for 1 day

# Benchmark 2: Replay speed
time make replay-databento START=2024-11-05 END=2024-11-12 SPEED=0
# Expected: 60-120 seconds for 1 week
```

---

## Debug Mode

For detailed debugging:

```bash
cd services/data-adapter

export DATA_PROVIDER=databento
export DATABENTO_API_KEY="db-your-key"
export REDIS_URL=redis://localhost:6379
export LOG_LEVEL=DEBUG  # Enable debug logs

poetry run python src/data_adapter/main.py
```

**Debug logs show:**
- Each tick received
- Each candle aggregated
- Gap detection events
- Session filter decisions
- Every publish to Redis

---

## What Success Looks Like

### ✅ Successful Test Output

```
INFO: Starting Data Adapter Service v0.1.0
INFO: Connected to Redis at redis://localhost:6379
INFO: Creating ResilientDatabentoClient for live data
INFO: Historical backfill enabled (databento)
INFO: Connecting to Databento GLBX.MDP3 with symbols ['GC.FUT', 'DX.FUT']
INFO: Databento subscription successful, streaming ticks...
INFO: Databento connection established successfully
DEBUG: Candle closed: GC 2024-11-05T10:00:00 O=2650.0 H=2652.0 L=2649.0 C=2651.0 V=1000
DEBUG: Published candle GC 2024-11-05T10:00:00: 1730804400000-0
INFO: Session OPENED at 2024-11-05T23:00:00
```

### ❌ Failed Test Signs

```
ERROR: Databento API key required
# Solution: Set DATABENTO_API_KEY

ERROR: Connection refused (Redis)
# Solution: make infra-up

WARNING: Databento connection lost: 401 Unauthorized
# Solution: Check API key validity

ERROR: No GC data fetched
# Solution: Verify date range and API access
```

---

## Final Checklist

Before proceeding to paper trading:

- [ ] `make test-databento-replay` passes
- [ ] `make replay-databento START=2024-11-05 END=2024-11-12 SPEED=0` completes
- [ ] Redis streams show candles (XLEN > 0)
- [ ] Database shows candles in `candles` table
- [ ] No ERROR logs in data-adapter
- [ ] `make validate-databento` shows >90% match rate
- [ ] Session events published correctly
- [ ] Gap detection and backfill working

---

## Getting Help

If tests fail:

1. **Check logs:**
```bash
docker logs scp-data-adapter 2>&1 | tail -50
```

2. **Verify API key:**
```bash
echo $DATABENTO_API_KEY | grep "^db-"
```

3. **Test API access:**
```bash
python -c "import databento as db; client = db.Historical(key='$DATABENTO_API_KEY'); print('✓ API key valid')"
```

4. **Check documentation:**
- `services/data-adapter/DATABENTO_INTEGRATION.md`
- `DATABENTO_QUICK_START.md`

---

## You're Ready When...

✅ Quick test passes  
✅ Full week replay completes  
✅ Validation shows >90% match  
✅ No errors in logs  
✅ Candles flowing to Redis  
✅ Data persisted to database  

**Then proceed to Epic 6: Paper Trading Validation!** 🚀
