# Setup Guide

## Prerequisites

- **Python:** 3.11 or 3.12 (3.13 not yet supported)
- **Package Manager:** Poetry (recommended) or uv
- **Git:** For version control

## Installation

### Option 1: Poetry (Recommended)

1. **Install Poetry** (if not already installed):
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   # or
   pip install poetry
   ```

2. **Install dependencies:**
   ```bash
   poetry install
   ```
   
   This will install all dependencies from `pyproject.toml` and use `poetry.lock` to ensure reproducible builds.

3. **Activate virtual environment (optional):**
   ```bash
   poetry shell
   ```
   
   Or run commands directly with `poetry run <command>` without activating the shell.

### Option 2: uv

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Activate virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

## Verify Installation

Run the test suite to verify everything is set up correctly:

```bash
# Using Poetry
poetry run pytest -q

# Or if you activated the shell (poetry shell)
pytest -q
```

Expected output:
```
..                                                                  [100%]
2 passed in X.XXs
```

## Development Tools

The project includes the following development tools configured in `pyproject.toml`:

### Code Formatting

```bash
# Format code with black
poetry run black .

# Sort imports with isort
poetry run isort .
```

### Linting

```bash
# Run ruff linter
poetry run ruff check .

# Auto-fix issues
poetry run ruff check --fix .
```

### Type Checking

```bash
# Run mypy (strict mode)
poetry run mypy src/
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run specific test file
poetry run pytest tests/test_imports.py

# Run in parallel (faster)
poetry run pytest -n auto

# Run with coverage
poetry run pytest --cov=feature_engine --cov=common
```

## Pre-commit Setup (Optional)

To run checks before commits, you can set up pre-commit hooks:

1. **Install pre-commit:**
   ```bash
   poetry add --group dev pre-commit
   ```

2. **Create `.pre-commit-config.yaml`:**
   ```yaml
   repos:
     - repo: https://github.com/psf/black
       rev: 24.8.0
       hooks:
         - id: black
     - repo: https://github.com/pycqa/isort
       rev: 5.13.2
       hooks:
         - id: isort
     - repo: https://github.com/astral-sh/ruff-pre-commit
       rev: 0.6.9
       hooks:
         - id: ruff
           args: [--fix]
   ```

3. **Install hooks:**
   ```bash
   pre-commit install
   ```

## IDE Configuration

### VS Code

Recommended extensions:
- Python
- Pylance
- Ruff
- Black Formatter

Settings (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "ms-python.black-formatter",
  "[python]": {
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  },
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true
}
```

### PyCharm

1. Configure Python interpreter to use Poetry/uv virtual environment
2. Enable type checking with mypy
3. Configure code style to match black (line length: 88)

## Troubleshooting

### Import Errors

If you encounter import errors, ensure:
- Virtual environment is activated
- Dependencies are installed (`poetry install` or `uv sync`)
- Python path includes project root

### Type Checking Errors

mypy runs in strict mode. If you need to temporarily ignore errors:
```python
# type: ignore[error-code]
```

But prefer fixing the underlying issue.

### Test Failures

If tests fail:
1. Check Python version: `python --version` (should be 3.11+)
2. Verify dependencies: `poetry show` or `uv pip list`
3. Check test output: `pytest -v` for detailed errors

## Next Steps

- Review [Configuration](./04-configuration.md) to understand system parameters
- Read [Development Workflow](./05-development-workflow.md) for TDD practices
- Check [Testing](./06-testing.md) for test conventions

