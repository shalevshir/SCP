# Running Tests

## Quick Start with Makefile

The easiest way to run tests is using the Makefile:

```bash
# Run all tests
make test

# Run tests with coverage report
make test-coverage

# Run tests in parallel (faster)
make test-parallel

# Run all checks (lint + test)
make check
```

For more Makefile commands, run `make help`.

## Prerequisites

Before running tests, you need to install dependencies. Choose one of the following methods:

### Option 1: Using Poetry (Recommended)

1. **Install Poetry** (if not already installed):
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **Install dependencies:**
   ```bash
   poetry install --no-root
   ```

3. **Activate the virtual environment:**
   ```bash
   poetry shell
   ```

4. **Run tests:**
   ```bash
   poetry run pytest
   ```

### Option 2: Using uv

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Run tests:**
   ```bash
   uv run pytest
   ```

### Option 3: Using pip (Manual)

1. **Create virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

   Or manually:
   ```bash
   pip install pytest pytest-xdist pyyaml pydantic
   ```

3. **Run tests:**
   ```bash
   pytest
   ```

## Running Tests

### Using Makefile (Recommended)

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run tests with verbose output
make test-verbose

# Run tests in parallel (faster)
make test-parallel

# Run tests with coverage report
make test-coverage

# Run tests quickly (parallel + quiet)
make test-fast
```

### Using pytest Directly

```bash
# With Poetry
poetry run pytest

# With uv
uv run pytest

# With activated venv
pytest
```

### Run Specific Test File

```bash
# Run config tests only
pytest tests/unit/test_config.py

# Run version tests only
pytest tests/unit/test_version.py

# Run import tests only
pytest tests/test_imports.py
```

### Run Specific Test Function

```bash
# Run a specific test function
pytest tests/unit/test_config.py::test_load_config_from_yaml

# Run multiple specific tests
pytest tests/unit/test_config.py::test_load_config_from_yaml tests/unit/test_config.py::test_config_env_override
```

### Verbose Output

```bash
# Show detailed output
pytest -v

# Show even more details
pytest -vv
```

### Run Tests in Parallel

```bash
# Auto-detect CPU count
pytest -n auto

# Use specific number of workers
pytest -n 4
```

### Show Print Statements

```bash
# Show print() output (normally captured)
pytest -s
```

### Stop on First Failure

```bash
# Stop after first test failure
pytest -x

# Stop after N failures
pytest --maxfail=3
```

### Run Tests Matching Pattern

```bash
# Run tests matching "config" in name
pytest -k config

# Run tests matching "yaml" or "json"
pytest -k "yaml or json"
```

## Test Configuration

Test configuration is in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-q"              # Quiet mode by default
testpaths = ["tests"]       # Test discovery path
pythonpath = ["src", "."]   # Python path for imports
```

## Expected Output

When tests pass, you should see:

```
tests/unit/test_config.py::test_load_config_from_yaml PASSED
tests/unit/test_config.py::test_config_env_override PASSED
tests/unit/test_config.py::test_load_config_from_json PASSED
tests/unit/test_config.py::test_config_validation PASSED
tests/unit/test_config.py::test_config_type_safety PASSED
tests/unit/test_version.py::test_version_exposed PASSED
tests/test_imports.py::test_packages_import PASSED

7 passed in X.XXs
```

## Troubleshooting

### Import Errors

If you see import errors like `ModuleNotFoundError: No module named 'common'`:

1. **Check Python path:** Ensure `pythonpath = ["src", "."]` in `pyproject.toml`
2. **Verify virtual environment:** Make sure you're in the activated venv
3. **Reinstall:** Try `poetry install` or `uv sync` again

### Missing Dependencies

If you see errors about missing packages:

```bash
# With Poetry
poetry install --no-root

# With uv
uv sync

# With pip
pip install -r requirements.txt  # If you have one
```

### Python Version Issues

The project requires Python 3.11+. Check your version:

```bash
python3 --version
```

If you need to use a different Python version with Poetry:

```bash
poetry env use python3.11
poetry install
```

### Test Discovery Issues

If pytest can't find tests:

```bash
# List discovered tests
pytest --collect-only

# Run with explicit path
pytest tests/
```

## Continuous Integration

For CI/CD pipelines, use:

```bash
# Install and test in one command (Poetry)
poetry install --no-root && poetry run pytest

# Install and test (uv)
uv sync && uv run pytest
```

## Continuous Integration

### GitHub Actions Workflow

The project includes a GitHub Actions CI workflow that automatically runs on every pull request and push to `main`.

**Workflow File:** `.github/workflows/ci.yml`

The CI pipeline runs three parallel jobs:

#### 1. Tests Job
- Runs full test suite with coverage
- Uses Python 3.11 on ubuntu-latest
- Generates coverage reports (XML and terminal) and JUnit test results
- **Automatically comments on PRs with:**
  - Coverage percentage and changes vs base branch
  - List of all failed tests with details
  - Color-coded coverage status (🟢 ≥80%, 🟠 ≥60%, 🔴 <60%)
- Uploads artifacts:
  - Coverage report (`coverage.xml`) - 30 days retention
  - Test results (`pytest-results.xml`) - 30 days retention
  - Test logs (`logs/`) - 7 days retention

#### 2. Lint Job
- Runs `ruff` linter for code quality checks
- Runs `mypy` type checker for type safety
- Type check runs with `continue-on-error` to not block PRs

#### 3. Format Job
- Checks `black` formatting (--check mode)
- Checks `isort` import ordering (--check-only mode)
- Fails if code is not properly formatted

### Viewing CI Results

**On Pull Requests:**
1. Navigate to your PR on GitHub
2. Scroll to the "Checks" section at the bottom
3. Click on a job name to see detailed logs
4. Download artifacts from the job summary page
5. **Check automated comments** - CI bot will post:
   - Coverage report with % change vs base branch
   - Test results summary with failed test details

**Coverage Comment Example:**
```
## Coverage Report
Coverage: 85.5% (+2.3%)

Files changed: 5
- common/types.py: 92% (+5%)
- data_layer/clients.py: 78% (-2%)
```

**Test Report Comment Example:**
```
## Test Results
✅ 45 passed
❌ 2 failed
⏭️ 1 skipped

Failed Tests:
- test_candle.py::test_invalid_timestamp
- test_clients.py::test_fetch_invalid_data
```

**On GitHub Actions Tab:**
1. Go to the "Actions" tab in the repository
2. Select the "CI" workflow
3. Click on a specific run to see results
4. Download artifacts from the run summary

### Downloading Artifacts

Artifacts are available for download after each CI run:

1. Go to the workflow run summary page
2. Scroll to the "Artifacts" section at the bottom
3. Click on an artifact to download it
4. Extract and review (coverage reports, logs, etc.)

**Available Artifacts:**
- **coverage-report** - XML coverage report for analysis (coverage.xml)
- **pytest-results** - JUnit XML test results for detailed test analysis
- **test-logs** - All log files generated during test execution

### Local CI Simulation

Run the same checks locally before pushing:

```bash
# Run all checks (tests + linting)
make check

# Run individual check steps
make test-coverage  # Same as CI test job
make lint           # Same as CI lint job (ruff + mypy)
make format         # Format code (CI uses --check mode)
```

### Pull Request Comments

The CI automatically posts two types of comments on every pull request:

#### Coverage Comment
- Shows overall coverage percentage
- Displays coverage change compared to base branch (+/- %)
- Lists file-by-file coverage changes
- Color codes: 🟢 ≥80% (green), 🟠 ≥60% (orange), 🔴 <60% (red)
- Updates on every new commit to the PR

#### Test Results Comment
- Shows count of passed, failed, and skipped tests
- Lists all failed tests with their names
- Includes test error messages and tracebacks
- Links to full test report in Checks tab
- Only posts if there are test failures (otherwise just shows summary)

**Note:** Comments require `pull-requests: write` permission, which is configured in the workflow.

### CI Requirements

The CI runs three jobs on every PR:

**✅ Required (Blocks Merge):**
- `Run Tests` - All tests must pass with no failures

**📊 Recommended (Non-Blocking):**
- `Run Linters` - Ruff linter should find no issues
- `Check Formatting` - Code should be properly formatted (black + isort)

**ℹ️ Informational:**
- ⚠️ Mypy type errors do not block (for now)
- 📊 Coverage changes are informational only (no minimum threshold enforced yet)

**Branch Protection Setup:**

To require tests before merging PRs:

1. Go to **GitHub Repository Settings** → **Branches**
2. Click **"Add rule"** or **"Add branch protection rule"**
3. Enter branch name pattern: `main`
4. Enable these settings:
   - ☑️ **Require a pull request before merging**
   - ☑️ **Require status checks to pass before merging**
     - ☑️ Require branches to be up to date before merging
     - Search and add: `Run Tests`
   - ☑️ **Include administrators** (recommended)
5. Click **"Create"** or **"Save changes"**

**Note:** Linting and formatting checks will still run and show results, but won't block merging. It's strongly recommended to fix any issues they report.

### Troubleshooting CI Failures

**Test Failures:**
```bash
# Reproduce locally
make test-verbose

# Check specific test
pytest tests/unit/test_specific.py -v
```

**Lint Failures:**
```bash
# Check issues
make lint

# Auto-fix most issues
ruff check --fix .
```

**Format Failures:**
```bash
# Check formatting
black --check .
isort --check-only .

# Auto-format
make format
```

### CI Performance

- **Average CI time:** ~2-3 minutes
- **Jobs run in parallel:** All three jobs
- **Caching:** Python dependencies cached by GitHub Actions
- **Matrix testing:** Currently single Python version (3.11)

### Future CI Enhancements

Planned improvements for Phase 2+:
- Matrix testing (Python 3.11, 3.12)
- Coverage threshold enforcement
- Performance benchmarking
- Docker container builds
- Deployment automation

---

## Next Steps

- See [Testing Guide](./06-testing.md) for test conventions and best practices
- See [Development Workflow](./05-development-workflow.md) for TDD practices
- See [Setup Guide](./03-setup-guide.md) for full environment setup

