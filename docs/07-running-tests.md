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

## Next Steps

- See [Testing Guide](./06-testing.md) for test conventions and best practices
- See [Development Workflow](./05-development-workflow.md) for TDD practices
- See [Setup Guide](./03-setup-guide.md) for full environment setup

