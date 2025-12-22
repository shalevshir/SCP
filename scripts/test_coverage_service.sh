#!/bin/bash
# Test coverage for a single service
# Usage: ./test_coverage_service.sh <service-name>

set -e

SERVICE_NAME=$1

if [ -z "$SERVICE_NAME" ]; then
    echo "Usage: $0 <service-name>"
    echo "Available services: shared, bot-core, data-adapter, execution, feature-engine, htf-bias"
    exit 1
fi

SERVICE_DIR="services/${SERVICE_NAME}"

if [ ! -d "$SERVICE_DIR" ]; then
    echo "Error: Service directory '$SERVICE_DIR' does not exist"
    exit 1
fi

echo "========================================="
echo "Running tests with coverage for: $SERVICE_NAME"
echo "========================================="

cd "$SERVICE_DIR"

# Check if poetry is available
if ! command -v poetry &> /dev/null; then
    echo "Error: poetry is not installed. Please install poetry first."
    exit 1
fi

# Install dependencies if needed
echo "Installing dependencies..."
poetry install --no-interaction --no-ansi

# Run tests with coverage
echo "Running tests..."
poetry run pytest tests/ -v \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=html:coverage_html \
    --cov-report=xml:coverage.xml \
    --cov-report=json:coverage.json \
    --junitxml=pytest-results.xml

# Display coverage summary
echo ""
echo "========================================="
echo "Coverage report for $SERVICE_NAME:"
echo "========================================="
poetry run coverage report --skip-covered

echo ""
echo "Coverage reports generated:"
echo "  - HTML: $SERVICE_DIR/coverage_html/index.html"
echo "  - XML:  $SERVICE_DIR/coverage.xml"
echo "  - JSON: $SERVICE_DIR/coverage.json"
echo ""
