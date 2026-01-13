#!/bin/bash
# Test Databento historical replay integration
#
# This script:
# 1. Ensures infrastructure is running
# 2. Cleans Redis and database
# 3. Runs a short Databento replay (1 day)
# 4. Verifies data flowed through the pipeline
#
# Usage:
#   export DATABENTO_API_KEY="db-your-key"
#   ./scripts/test_databento_replay.sh

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Databento Historical Replay Test"
echo "=========================================="

# Check for API key
if [ -z "$DATABENTO_API_KEY" ]; then
    echo -e "${RED}ERROR: DATABENTO_API_KEY not set${NC}"
    echo "Export your Databento API key:"
    echo "  export DATABENTO_API_KEY='db-your-key'"
    exit 1
fi

echo -e "${GREEN}✓${NC} Databento API key configured"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Docker is not running${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Docker is running"

# Start infrastructure
echo ""
echo "Starting infrastructure..."
cd infra
docker-compose up -d redis postgres

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 5

# Check Redis
if ! docker exec scp-redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Redis not responding${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Redis ready"

# Check PostgreSQL
if ! docker exec scp-postgres pg_isready -U scp > /dev/null 2>&1; then
    echo -e "${RED}ERROR: PostgreSQL not responding${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} PostgreSQL ready"

cd ..

# Clean Redis streams
echo ""
echo "Cleaning Redis streams..."
docker exec scp-redis redis-cli FLUSHDB > /dev/null
echo -e "${GREEN}✓${NC} Redis cleaned"

# Clean database
echo "Cleaning database..."
docker exec scp-postgres psql -U scp -d scp -c "TRUNCATE TABLE trades, candles, features CASCADE" > /dev/null 2>&1 || true
echo -e "${GREEN}✓${NC} Database cleaned"

# Run replay
echo ""
echo "Running Databento historical replay (1 day sample)..."
echo "Date range: 2024-11-05 to 2024-11-06"
echo "Speed: 0x (turbo mode)"
echo ""

poetry run python scripts/replay_databento_historical.py \
    --start 2024-11-05 \
    --end 2024-11-06 \
    --api-key "$DATABENTO_API_KEY" \
    --speed 0 \
    --processing-delay 10.0

# Verify data in Redis
echo ""
echo "Verifying data flow..."

GC_COUNT=$(docker exec scp-redis redis-cli XLEN candles.1m.gc)
DXY_COUNT=$(docker exec scp-redis redis-cli XLEN candles.1m.dxy)

echo "Redis stream lengths:"
echo "  candles.1m.gc: $GC_COUNT"
echo "  candles.1m.dxy: $DXY_COUNT"

if [ "$GC_COUNT" -eq 0 ]; then
    echo -e "${RED}ERROR: No GC candles in Redis${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Candles successfully published to Redis"

# Verify data in database (if services are running)
CANDLE_DB_COUNT=$(docker exec scp-postgres psql -U scp -d scp -t -c "SELECT COUNT(*) FROM candles" 2>/dev/null | xargs)

if [ -n "$CANDLE_DB_COUNT" ] && [ "$CANDLE_DB_COUNT" != "0" ]; then
    echo "  candles table: $CANDLE_DB_COUNT rows"
    echo -e "${GREEN}✓${NC} Data persisted to database"
else
    echo -e "${YELLOW}⚠${NC}  No data in database (services may not be running)"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}Databento Replay Test PASSED${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Start microservices: make services-up"
echo "  2. Run full replay: poetry run python scripts/replay_databento_historical.py --start 2024-11-05 --end 2024-11-12 --api-key \$DATABENTO_API_KEY --speed 0"
echo "  3. Check trades: docker exec scp-postgres psql -U scp -d scp -c 'SELECT * FROM trades'"
