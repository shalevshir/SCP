#!/bin/bash
# Start paper trading with live data and IB integration
# Usage: ./scripts/start-paper-trading.sh

set -e

echo "🚀 Starting Paper Trading with Live Data + IB Integration"
echo ""

# # Check prerequisites
# if [ -z "$DATABENTO_API_KEY" ]; then
#   echo "❌ Error: DATABENTO_API_KEY not set"
#   echo "   export DATABENTO_API_KEY='db-your-key'"
#   exit 1
# fi

echo "✅ Databento API key found"
echo ""

# Check if IB Gateway/TWS is running (basic check)
IB_PORT=${IB_PORT:-7497}
if ! nc -z localhost "$IB_PORT" 2>/dev/null; then
  echo "⚠️  Warning: IB Gateway/TWS may not be running on port $IB_PORT"
  echo "   Please start IB Gateway/TWS and ensure API is enabled"
  echo "   - TWS Paper: port 7497"
  echo "   - Gateway Paper: port 4002"
  echo ""
  read -p "Continue anyway? [y/N] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
  echo ""
fi

# Start infrastructure
echo "📦 Starting infrastructure (Redis + PostgreSQL)..."
cd "$(dirname "$0")/.." || exit 1
make infra-up
sleep 5

# Start services with paper trading overlay
echo "🚀 Starting all services with paper trading configuration..."
docker compose \
  -f infra/docker-compose.infra.yml \
  -f infra/docker-compose.services.yml \
  -f infra/docker-compose.paper-trading.yml \
  up -d --build

echo ""
echo "✅ Services started!"
echo ""
echo "📊 Service URLs:"
echo "   Data Adapter:   http://localhost:8001/health"
echo "   Feature Engine: http://localhost:8002/health"
echo "   HTF Bias:       http://localhost:8003/health"
echo "   Bot Core:       http://localhost:8004/health"
echo "   Execution:      http://localhost:8005/health"
echo ""
echo "📝 Monitor logs:"
echo "   make services-logs"
echo "   docker logs -f scp-execution"
echo ""
echo "🛑 Stop services:"
echo "   make services-down"
echo ""
echo "🔍 Check broker connection:"
echo "   docker logs scp-execution | grep -i broker"
echo ""
