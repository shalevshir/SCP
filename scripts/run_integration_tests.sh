#!/bin/bash
# Integration test runner for SCP microservices
# Ensures infrastructure is running before executing tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== SCP Integration Test Runner ===${NC}\n"

# Check if we're in the project root
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: Must run from project root${NC}"
    exit 1
fi

# Function to check if a service is running
check_service() {
    local service=$1
    local port=$2
    local name=$3
    
    if ! nc -z localhost "$port" 2>/dev/null; then
        echo -e "${RED}✗${NC} $name not running on port $port"
        return 1
    else
        echo -e "${GREEN}✓${NC} $name running on port $port"
        return 0
    fi
}

# Check infrastructure
echo "Checking infrastructure..."
echo ""

REDIS_OK=false
POSTGRES_OK=false

if check_service "redis" 6379 "Redis"; then
    REDIS_OK=true
fi

if check_service "postgres" 5432 "PostgreSQL"; then
    POSTGRES_OK=true
fi

echo ""

# Exit if infrastructure not running
if [ "$REDIS_OK" = false ] || [ "$POSTGRES_OK" = false ]; then
    echo -e "${YELLOW}Infrastructure not running. Starting with docker-compose...${NC}"
    echo ""
    
    cd infra
    docker-compose up -d redis postgres
    cd ..
    
    echo "Waiting for services to be ready..."
    sleep 5
    
    # Re-check
    if ! check_service "redis" 6379 "Redis" || ! check_service "postgres" 5432 "PostgreSQL"; then
        echo -e "${RED}Failed to start infrastructure. Please check docker-compose logs.${NC}"
        exit 1
    fi
fi

# Check database migrations
echo ""
echo "Checking database schema..."

if ! docker-compose -f infra/docker-compose.infra.yml exec -T postgres psql -U scp -d scp -c "\dt candles" &>/dev/null; then
    echo -e "${YELLOW}Database schema not initialized. Applying migrations...${NC}"
    # Migrations are applied automatically via docker-entrypoint-initdb.d
    echo "Restarting PostgreSQL to apply migrations..."
    docker-compose -f infra/docker-compose.infra.yml restart postgres
    sleep 5
fi

echo -e "${GREEN}✓${NC} Database schema ready"
echo ""

# Set environment variables
export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
export DATABASE_URL="${DATABASE_URL:-postgresql://scp:scp_dev_password@localhost:5432/scp}"

echo "Environment:"
echo "  REDIS_URL=$REDIS_URL"
echo "  DATABASE_URL=postgresql://scp:***@localhost:5432/scp"
echo ""

# Parse arguments
RUN_SLOW=true
VERBOSE=false
COVERAGE=false
SPECIFIC_TEST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --slow)
            RUN_SLOW=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        --test)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="poetry run pytest tests/integration/"

if [ -n "$SPECIFIC_TEST" ]; then
    PYTEST_CMD="poetry run pytest $SPECIFIC_TEST"
fi

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=services --cov-report=term-missing --cov-report=html"
fi

if [ "$RUN_SLOW" = false ]; then
    PYTEST_CMD="$PYTEST_CMD -m 'infrastructure and not slow'"
else
    PYTEST_CMD="$PYTEST_CMD -m 'infrastructure'"
fi

# Add asyncio mode
PYTEST_CMD="$PYTEST_CMD --asyncio-mode=auto"

# Run tests
echo -e "${GREEN}Running integration tests...${NC}"
echo "Command: $PYTEST_CMD"
echo ""

eval "$PYTEST_CMD"

# Capture exit code
TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}=== All tests passed! ===${NC}"
else
    echo -e "${RED}=== Some tests failed ===${NC}"
fi

# Show coverage report location if generated
if [ "$COVERAGE" = true ]; then
    echo ""
    echo -e "${GREEN}Coverage report:${NC} htmlcov/index.html"
fi

exit $TEST_EXIT_CODE
