#!/bin/bash
# Run tests with coverage for all services and generate combined report
# Usage: ./test_coverage_all.sh

set -e

# Define all services
SERVICES=("shared" "bot-core" "data-adapter" "execution" "feature-engine" "htf-bias")

# Create coverage reports directory
COVERAGE_DIR="coverage_reports"
mkdir -p "$COVERAGE_DIR"

echo "========================================="
echo "Running tests for all services"
echo "========================================="

# Track failures
FAILED_SERVICES=()

# Run tests for each service
for SERVICE in "${SERVICES[@]}"; do
    echo ""
    echo "========================================="
    echo "Testing service: $SERVICE"
    echo "========================================="
    
    if ./scripts/test_coverage_service.sh "$SERVICE"; then
        # Copy coverage reports to central location
        cp "services/${SERVICE}/coverage.xml" "${COVERAGE_DIR}/${SERVICE}-coverage.xml"
        cp "services/${SERVICE}/coverage.json" "${COVERAGE_DIR}/${SERVICE}-coverage.json"
        echo "✓ $SERVICE tests passed"
    else
        FAILED_SERVICES+=("$SERVICE")
        echo "✗ $SERVICE tests failed"
    fi
done

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="

# Display summary
if [ ${#FAILED_SERVICES[@]} -eq 0 ]; then
    echo "✓ All services passed tests!"
else
    echo "✗ Failed services:"
    for SERVICE in "${FAILED_SERVICES[@]}"; do
        echo "  - $SERVICE"
    done
fi

# Generate combined coverage report
echo ""
echo "========================================="
echo "Generating combined coverage report"
echo "========================================="

# Coverage is managed by Poetry, no need to install separately
# Just verify it's available via poetry run
if ! poetry run coverage --version &> /dev/null; then
    echo "Error: coverage tool not available in Poetry environment"
    echo "Run: poetry install"
    exit 1
fi

# Create a script to parse and combine coverage
poetry run python << 'PYTHON_SCRIPT'
import json
import os
from pathlib import Path

coverage_dir = Path("coverage_reports")
services = ["shared", "bot-core", "data-adapter", "execution", "feature-engine", "htf-bias"]

total_lines = 0
covered_lines = 0
service_coverage = {}

for service in services:
    json_file = coverage_dir / f"{service}-coverage.json"
    if not json_file.exists():
        print(f"Warning: Coverage file not found for {service}")
        continue
    
    with open(json_file) as f:
        data = json.load(f)
        
    totals = data.get("totals", {})
    num_statements = totals.get("num_statements", 0)
    covered_statements = totals.get("covered_lines", 0)
    percent = totals.get("percent_covered", 0)
    
    service_coverage[service] = {
        "statements": num_statements,
        "covered": covered_statements,
        "percent": percent
    }
    
    total_lines += num_statements
    covered_lines += covered_statements

overall_percent = (covered_lines / total_lines * 100) if total_lines > 0 else 0

print("\n" + "="*50)
print("Combined Coverage Report")
print("="*50)
print(f"\n{'Service':<20} {'Statements':<12} {'Covered':<10} {'Coverage':<10}")
print("-" * 52)

for service, cov in service_coverage.items():
    print(f"{service:<20} {cov['statements']:<12} {cov['covered']:<10} {cov['percent']:.1f}%")

print("-" * 52)
print(f"{'TOTAL':<20} {total_lines:<12} {covered_lines:<10} {overall_percent:.1f}%")
print("="*50)

# Write summary to file
summary_file = coverage_dir / "coverage_summary.json"
with open(summary_file, 'w') as f:
    json.dump({
        "services": service_coverage,
        "total": {
            "statements": total_lines,
            "covered": covered_lines,
            "percent": overall_percent
        }
    }, f, indent=2)

print(f"\nCombined coverage summary saved to: {summary_file}")

# Create markdown report
md_file = coverage_dir / "coverage_report.md"
with open(md_file, 'w') as f:
    f.write("# Test Coverage Report\n\n")
    f.write("## Service Coverage\n\n")
    f.write("| Service | Statements | Covered | Coverage |\n")
    f.write("|---------|------------|---------|----------|\n")
    for service, cov in service_coverage.items():
        f.write(f"| {service} | {cov['statements']} | {cov['covered']} | {cov['percent']:.1f}% |\n")
    f.write(f"| **TOTAL** | **{total_lines}** | **{covered_lines}** | **{overall_percent:.1f}%** |\n")
    f.write("\n")
    
    # Add coverage status badge
    if overall_percent >= 80:
        status = "🟢 Excellent"
    elif overall_percent >= 60:
        status = "🟡 Good"
    else:
        status = "🔴 Needs Improvement"
    
    f.write(f"\n**Overall Status:** {status}\n\n")
    f.write(f"- ✅ Coverage >= 80%: Excellent\n")
    f.write(f"- ⚠️  Coverage >= 60%: Good\n")
    f.write(f"- ❌ Coverage < 60%: Needs Improvement\n")

print(f"Markdown report saved to: {md_file}")

PYTHON_SCRIPT

echo ""
echo "Coverage reports available in: $COVERAGE_DIR/"
echo "  - coverage_summary.json"
echo "  - coverage_report.md"

# Exit with error if any service failed
if [ ${#FAILED_SERVICES[@]} -ne 0 ]; then
    exit 1
fi
