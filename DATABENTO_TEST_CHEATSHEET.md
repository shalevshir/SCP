# Databento Testing - Cheat Sheet

## One-Time Setup

```bash
# Get API key from databento.com
export DATABENTO_API_KEY="db-your-key-here"

# Start infrastructure
make infra-up
```

---

## Quick Tests

```bash
# Test 1: Quick replay (1 day)
make test-databento-replay

# Test 2: Full week replay
make replay-databento START=2024-11-05 END=2024-11-12 SPEED=0

# Test 3: Full validation
make validate-databento START=2024-11-05 END=2024-11-12
```

---

## Monitor Results

```bash
# Check Redis streams
docker exec scp-redis redis-cli XLEN candles.1m.gc

# Check database
docker exec scp-postgres psql -U scp -d scp -c "SELECT COUNT(*) FROM candles"

# Watch logs
docker logs -f scp-data-adapter
```

---

## Common Commands

| Action | Command |
|--------|---------|
| Start infra | `make infra-up` |
| Stop infra | `make infra-down` |
| Clean data | `make replay-clean` |
| Test replay | `make test-databento-replay` |
| Full replay | `make replay-databento START=... END=... SPEED=0` |
| Validate | `make validate-databento START=... END=...` |
| Live stream | `export DATA_PROVIDER=databento && make services-up` |
| View logs | `docker logs -f scp-data-adapter` |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No API key | `export DATABENTO_API_KEY="db-..."` |
| Redis refused | `make infra-up` |
| No data fetched | Check API key & date range |
| Connection lost | Wait for auto-reconnect |

---

## Success Signs

✅ `make test-databento-replay` shows "PASSED"  
✅ `XLEN candles.1m.gc` shows 1440+ for 1 day  
✅ No ERROR in logs  
✅ Validation shows >90% match rate  

---

## Full Guide

See: `DATABENTO_LOCAL_TEST_GUIDE.md`
