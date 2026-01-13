# Databento Quick Start Guide

Quick reference for using Databento with the SCP trading system.

## Setup

### Option 1: Mock (Testing)

For testing without external data:

```bash
export DATA_PROVIDER=mock
make infra-up
```

### Option 2: Databento (Production)

1. **Get API Key**: Sign up at [databento.com](https://databento.com)

2. **Export API Key**:
```bash
export DATA_PROVIDER=databento
export DATABENTO_API_KEY="db-your-actual-key"
```

3. **Start Infrastructure**:
```bash
make infra-up
```

## Quick Tests

### Test 1: Mock Client

Test the pipeline without external data:

```bash
cd services/data-adapter
export DATA_PROVIDER=mock
export REDIS_URL=redis://localhost:6379
poetry run python src/data_adapter/main.py
```

### Test 2: Databento Replay (1 Day)

Test with real Databento data:

```bash
export DATABENTO_API_KEY="db-your-key"
make test-databento-replay
```

### Test 3: Full Week Replay

```bash
make replay-databento START=2024-11-05 END=2024-11-12 SPEED=0
```

### Test 4: Full Validation

```bash
make validate-databento START=2024-11-05 END=2024-11-12
```

## Live Data Usage

Start all services with live Databento feed:

```bash
# 1. Start services
export DATA_PROVIDER=databento
export DATABENTO_API_KEY="db-your-key"
make services-up

# 2. Watch logs
docker logs -f scp-data-adapter

# 3. Monitor data flow
docker exec scp-redis redis-cli XLEN candles.1m.gc
```

## Monitor Data Flow

### Check Redis Streams

```bash
# Watch candles
docker exec -it scp-redis redis-cli XREAD COUNT 10 STREAMS candles.1m.gc 0

# Check stream lengths
docker exec scp-redis redis-cli XLEN candles.1m.gc
docker exec scp-redis redis-cli XLEN candles.1m.dxy

# Watch session events
docker exec -it scp-redis redis-cli XREAD BLOCK 0 STREAMS session.events 0
```

### Check Database

```bash
# Check candles persisted
docker exec scp-postgres psql -U scp -d scp -c "SELECT COUNT(*) FROM candles"

# Check recent candles
docker exec scp-postgres psql -U scp -d scp -c "
SELECT timestamp, symbol, close, volume 
FROM candles 
ORDER BY timestamp DESC 
LIMIT 20"

# Check trades
docker exec scp-postgres psql -U scp -d scp -c "SELECT * FROM trades"
```

## Common Commands

```bash
# Historical replay
make replay-databento START=2024-11-05 END=2024-11-12 SPEED=0

# Full validation
make validate-databento START=2024-11-05 END=2024-11-12

# Quick test
make test-databento-replay

# Clean environment
make replay-clean

# Live streaming
export DATA_PROVIDER=databento
make services-up
```

## Key Files

| File | Purpose |
|------|---------|
| `services/data-adapter/DATABENTO_INTEGRATION.md` | Complete guide |
| `services/data-adapter/src/data_adapter/databento_client.py` | Client implementation |
| `scripts/replay_databento_historical.py` | Historical replay |
| `scripts/validate_databento_replay.py` | Validation workflow |

## Next Steps

1. ✅ Test replay: `make replay-databento START=2024-11-05 END=2024-11-06 SPEED=0`
2. ⏳ Validate parity: `make validate-databento START=2024-11-05 END=2024-11-12`
3. ⏳ Paper trading: 2-4 weeks monitoring
4. ⏳ Go live: After validation passes

## Support

See full documentation: `services/data-adapter/DATABENTO_INTEGRATION.md`
