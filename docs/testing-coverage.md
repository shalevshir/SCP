# Test Coverage Documentation

This document describes the test coverage infrastructure for the SCP microservices architecture.

## Overview

The project includes comprehensive test coverage tracking for all microservices with:

- Individual service coverage reports
- Combined coverage report across all services
- CI/CD integration with automated coverage tracking
- Coverage thresholds and quality gates

## Quick Start

### Test a Single Service

```bash
# Using the script directly
./scripts/test_coverage_service.sh execution

# Or using Make
make service-test-coverage SERVICE=execution
```

### Test All Services

```bash
# Using the script directly
./scripts/test_coverage_all.sh

# Or using Make
make service-test-coverage-all
```

## Services

The following services have test coverage tracking:

| Service | Description | Test Location |
|---------|-------------|---------------|
| **shared** | Shared utilities library | `services/shared/tests/` |
| **bot-core** | Signal generation and guardrails | `services/bot-core/tests/` |
| **data-adapter** | Live data ingestion | `services/data-adapter/tests/` |
| **execution** | Trade lifecycle management | `services/execution/tests/` |
| **feature-engine** | Indicator computation | `services/feature-engine/tests/` |
| **htf-bias** | Higher-timeframe analysis | `services/htf-bias/tests/` |

## Coverage Scripts

### `test_coverage_service.sh`

Runs tests with coverage for a single service.

**Usage:**
```bash
./scripts/test_coverage_service.sh <service-name>
```

**Available services:**
- `shared`
- `bot-core`
- `data-adapter`
- `execution`
- `feature-engine`
- `htf-bias`

**Output Files:**
```
services/<service-name>/
  ├── coverage_html/       # Interactive HTML report
  │   └── index.html
  ├── coverage.xml         # XML format (for CI/CD)
  ├── coverage.json        # JSON format (for analysis)
  └── pytest-results.xml   # JUnit test results
```

**Features:**
- Installs dependencies automatically using Poetry
- Runs all tests with coverage tracking
- Generates multiple report formats (HTML, XML, JSON)
- Shows coverage summary with missing lines
- Generates JUnit XML for test results

### `test_coverage_all.sh`

Runs tests with coverage for all services and generates a combined report.

**Usage:**
```bash
./scripts/test_coverage_all.sh
```

**Output:**
```
coverage_reports/
  ├── shared-coverage.xml
  ├── bot-core-coverage.xml
  ├── data-adapter-coverage.xml
  ├── execution-coverage.xml
  ├── feature-engine-coverage.xml
  ├── htf-bias-coverage.xml
  ├── coverage_summary.json       # Combined data in JSON
  └── coverage_report.md          # Human-readable report
```

**Features:**
- Tests all services sequentially
- Tracks which services pass/fail
- Combines coverage data from all services
- Generates JSON summary and Markdown report
- Provides visual status indicators
- Returns non-zero exit code if any service fails

## Coverage Reports

### Individual Service Reports

Each service generates the following reports:

**HTML Report** (`coverage_html/index.html`):
- Interactive web interface
- Browse by file/module
- See covered/uncovered lines with color coding
- View missing lines and branches
- Open with: `open services/execution/coverage_html/index.html`

**XML Report** (`coverage.xml`):
- Standard Cobertura XML format
- Used by CI/CD tools
- Compatible with coverage aggregation tools

**JSON Report** (`coverage.json`):
- Machine-readable format
- Detailed per-file coverage data
- Used for programmatic analysis

**Terminal Output**:
```
Name                                 Stmts   Miss  Cover   Missing
------------------------------------------------------------------
execution_svc/__init__.py                0      0   100%
execution_svc/broker/__init__.py         2      0   100%
execution_svc/broker/base.py            45      3    93%   102-104
execution_svc/broker/paper.py          128      8    94%   145, 189-195
execution_svc/config.py                 15      0   100%
execution_svc/daily_state.py            67      4    94%   78-81
execution_svc/main.py                  120     12    90%   156-167
------------------------------------------------------------------
TOTAL                                  520     42    92%
```

### Combined Coverage Report

The combined report aggregates coverage across all services:

**Markdown Report** (`coverage_reports/coverage_report.md`):

```markdown
# Test Coverage Report

## Service Coverage

| Service | Statements | Covered | Coverage |
|---------|------------|---------|----------|
| shared | 450 | 405 | 90.0% |
| bot-core | 280 | 245 | 87.5% |
| data-adapter | 190 | 165 | 86.8% |
| execution | 520 | 442 | 85.0% |
| feature-engine | 310 | 263 | 84.8% |
| htf-bias | 220 | 187 | 85.0% |
| **TOTAL** | **1970** | **1707** | **86.6%** |

**Overall Status:** 🟢 Excellent

- ✅ Coverage >= 80%: Excellent
- ⚠️  Coverage >= 60%: Good
- ❌ Coverage < 60%: Needs Improvement
```

**JSON Summary** (`coverage_reports/coverage_summary.json`):
```json
{
  "services": {
    "shared": {
      "statements": 450,
      "covered": 405,
      "percent": 90.0
    },
    "execution": {
      "statements": 520,
      "covered": 442,
      "percent": 85.0
    }
  },
  "total": {
    "statements": 1970,
    "covered": 1707,
    "percent": 86.6
  }
}
```

## Coverage Thresholds

The project uses the following coverage thresholds:

| Threshold | Coverage | Status | Indicator |
|-----------|----------|--------|-----------|
| Excellent | ≥ 80% | High quality, well-tested | 🟢 |
| Good | ≥ 60% | Acceptable, room for improvement | 🟡 |
| Needs Improvement | < 60% | Insufficient testing | 🔴 |

## CI/CD Integration

### GitHub Actions Workflow

The CI pipeline includes comprehensive coverage tracking:

**Service Tests Job:**
- Runs tests for all services in parallel using a matrix strategy
- Each service generates its own coverage report
- Uploads coverage.xml as artifacts

**Combined Coverage Job:**
- Runs after all service tests complete
- Downloads all coverage artifacts
- Combines coverage data into a unified report
- Posts coverage report as PR comment
- Uploads combined report as artifact

**Workflow Structure:**
```yaml
jobs:
  service-tests:
    strategy:
      matrix:
        service: [shared, bot-core, data-adapter, execution, feature-engine, htf-bias]
    steps:
      - Run tests with coverage
      - Upload coverage.xml
  
  combined-coverage:
    needs: service-tests
    steps:
      - Download all coverage reports
      - Combine coverage data
      - Generate markdown report
      - Comment on PR
      - Upload combined report
```

### CI Coverage Reports

On every pull request, the CI will:

1. **Run tests for all services** (in parallel)
2. **Generate individual coverage reports**
3. **Combine coverage data**
4. **Post coverage report as PR comment**
5. **Upload artifacts:**
   - Individual service coverage reports
   - Combined coverage report
   - Test results (JUnit XML)

### Viewing CI Coverage Reports

**On Pull Requests:**
- Coverage report is automatically commented on the PR
- View detailed coverage in the "Checks" tab
- Download artifacts from the workflow run

**On GitHub:**
1. Go to Actions tab
2. Select the workflow run
3. Scroll to "Artifacts" section
4. Download:
   - `coverage-<service-name>` - Individual service reports
   - `combined-coverage-report` - Combined report

## Make Targets

The Makefile includes convenient targets for coverage testing:

```bash
# Test root project with coverage (legacy)
make test-coverage

# Test a single service with coverage
make service-test-coverage SERVICE=execution

# Test all services with combined coverage report
make service-test-coverage-all
```

## Development Workflow

### Adding Tests

When adding new code, follow this workflow:

1. **Write tests first** (TDD approach)
2. **Run coverage locally:**
   ```bash
   make service-test-coverage SERVICE=<your-service>
   ```
3. **Check coverage report:**
   - Open `services/<your-service>/coverage_html/index.html`
   - Identify uncovered lines
4. **Add tests for uncovered code**
5. **Verify coverage improves:**
   ```bash
   make service-test-coverage SERVICE=<your-service>
   ```

### Pre-Commit Checklist

Before committing code:

- [ ] All tests pass locally
- [ ] Coverage is maintained or improved
- [ ] Coverage >= 80% for new code
- [ ] No critical uncovered paths

### Coverage Best Practices

1. **Aim for 80%+ coverage** for all services
2. **Focus on critical paths:**
   - Core business logic
   - Error handling
   - State transitions
3. **Don't chase 100% coverage blindly:**
   - Some code is not worth testing (e.g., simple getters)
   - Focus on meaningful tests, not coverage metrics
4. **Test behavior, not implementation:**
   - Test what the code does, not how it does it
   - Make tests resilient to refactoring

## Troubleshooting

### Poetry Not Found

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -
```

### Service Dependencies Not Installed

```bash
# Install shared library first
cd services/shared
poetry install

# Then install service
cd services/<service-name>
poetry install
```

### Tests Failing in CI but Passing Locally

1. **Check Python version:** CI uses Python 3.11
2. **Check dependencies:** Ensure poetry.lock is committed
3. **Check environment variables:** CI may need additional config
4. **Check test isolation:** Tests should not depend on execution order

### Coverage Not Updating

```bash
# Clear coverage cache
cd services/<service-name>
rm -rf .coverage coverage.xml coverage.json coverage_html/

# Re-run coverage
poetry run pytest tests/ --cov=src --cov-report=html
```

## Related Documentation

- [Development Guidelines](.cursor/rules/development_guidlines.mdc) - TDD practices
- [Microservices Architecture](.cursor/rules/microservices_architecture.mdc) - Service architecture
- [Scripts README](scripts/README.md) - All available scripts
- [Services README](services/README.md) - Service development workflow

## Future Enhancements

Planned improvements to coverage tracking:

- [ ] Coverage badges in README
- [ ] Coverage trend tracking over time
- [ ] Coverage diff on PRs (show coverage change)
- [ ] Integration test coverage
- [ ] E2E test coverage
- [ ] Coverage gates (block PRs below threshold)
- [ ] Per-module coverage requirements
