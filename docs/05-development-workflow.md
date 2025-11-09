# Development Workflow

## Test-Driven Development (TDD)

This project follows strict TDD principles: **Red-Green-Refactor**.

### TDD Cycle

1. **Red:** Write a failing test that captures the requirement
2. **Green:** Implement minimal code to make the test pass
3. **Refactor:** Improve code quality while keeping tests green

### Principles

- **Start with tests:** Every feature begins with a failing test
- **Small increments:** One behavior per test, minimal changes
- **Executable specs:** Tests describe intent clearly
- **Coverage focus:** Public APIs, invariants, error paths, boundaries
- **Regression prevention:** Every bug fix gets a test

## Workflow Steps

### 1. Write Failing Test

```python
# tests/unit/test_feature.py
def test_new_feature():
    result = my_function()
    assert result == expected_value
```

Run test to confirm it fails:
```bash
pytest tests/unit/test_feature.py -v
```

### 2. Implement Minimal Code

```python
# src/scp/module.py
def my_function():
    return expected_value  # Minimal implementation
```

Run test to confirm it passes:
```bash
pytest tests/unit/test_feature.py -v
```

### 3. Refactor

Improve code quality while keeping tests green:
- Extract functions
- Improve naming
- Add type hints
- Remove duplication

### 4. Commit

```bash
git add .
git commit -m "feat: add new feature

- Implements X behavior
- Test: tests/unit/test_feature.py validates requirement"
```

## Code Quality Checks

Before committing, ensure:

```bash
# Format code
black .
isort .

# Lint
ruff check .

# Type check
mypy src/

# Run tests
pytest
```

## Branching Strategy

- **main:** Always green, production-ready code
- **feature/***: Feature branches for new functionality
- **fix/***: Bug fix branches

### Branch Workflow

1. Create feature branch:
   ```bash
   git checkout -b feature/new-module
   ```

2. Make changes following TDD:
   - Write test
   - Implement
   - Refactor
   - Commit

3. Ensure all checks pass:
   ```bash
   pytest && ruff check . && mypy src/
   ```

4. Push and create PR:
   ```bash
   git push origin feature/new-module
   ```

## Commit Messages

Follow conventional commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `test`: Test additions/changes
- `refactor`: Code refactoring
- `chore`: Maintenance tasks

**Examples:**
```
feat(data-layer): add CSV data loader

Implements LocalCSVClient for loading historical market data.
Test: tests/unit/test_data_layer.py validates file loading.

fix(rule-engine): correct scoring calculation

Fixes off-by-one error in setup scoring logic.
Test: tests/unit/test_rule_engine.py catches regression.
```

## Code Review Checklist

When reviewing PRs, check:

- [ ] Tests are included and pass
- [ ] Test names clearly describe behavior
- [ ] Code follows style guidelines (black, isort, ruff)
- [ ] Type hints are present and correct
- [ ] No secrets or sensitive data
- [ ] Documentation updated if needed
- [ ] Commit messages are clear

## Error Handling

### Principles

- **Don't swallow exceptions:** Handle meaningfully or let them surface
- **Specific exceptions:** Catch specific types, not bare `except`
- **Context on re-raise:** Add context when re-raising exceptions
- **Use domain exceptions:** Use `ConfigError`, `DataSourceError`, `NormalizationError` instead of built-in exceptions
- **Chain exceptions:** Preserve original errors with `from e`

### Exception Hierarchy

All custom exceptions inherit from `AppError`:
- `ConfigError` - Configuration issues
- `DataSourceError` - Data loading/connection errors
- `NormalizationError` - Data validation/quality issues

### Example

```python
from common import get_logger, ConfigError

logger = get_logger(__name__)

# Good
try:
    data = load_config(path)
except FileNotFoundError:
    logger.error(f"Config file not found: {path}")
    raise
except yaml.YAMLError as e:
    logger.error(f"Invalid YAML in {path}: {e}")
    raise ConfigError(
        f"Failed to parse config: {path}",
        cause=e,
        path=str(path)
    ) from e

# Bad
try:
    data = load_config(path)
except:  # Too broad
    pass  # Swallowing exception
```

See [Error Handling Guide](./09-error-handling.md) for comprehensive documentation.

## Logging

### Principles

- Use `logging` module, never `print` in library code
- Log at boundaries and failures with actionable context
- Avoid noisy debug logs in hot paths

### Setup

Initialize logging at application startup:

```python
from common import load_config, get_logger
from pathlib import Path

# Load configuration
config = load_config(Path("config/core.yaml"))

# Initialize logging system
from common.logger import setup_logging
setup_logging(config.system)

# Get logger for your module
logger = get_logger(__name__)
```

### Usage Example

```python
from common import get_logger

logger = get_logger(__name__)

def process_trade(trade: Trade) -> None:
    logger.info(f"Processing trade {trade.id} for {trade.symbol}")
    try:
        result = execute_trade(trade)
        logger.info(f"Trade {trade.id} executed successfully")
    except ExecutionError as e:
        logger.error(f"Trade {trade.id} failed: {e}", exc_info=True)
        raise
```

### Configuration

Log level can be set via:
- Configuration file: `system.log_level` in `config/core.yaml`
- Environment variable: `SCP_LOG_LEVEL=DEBUG`

Logs are written to:
- File: `{log_path}/dev/app.log` (rotating, 10MB max, 5 backups)
- Console: stdout with same format

See [Logging Guide](./08-logging.md) for detailed documentation.

## Type Hints

### Requirements

- Type hints everywhere (PEP 484)
- Use `mypy --strict` equivalent settings
- Avoid `Any` unless necessary

### Example

```python
from typing import List, Optional

def calculate_vwap(
    prices: List[float],
    volumes: List[float],
    period: int = 20
) -> Optional[float]:
    if len(prices) != len(volumes):
        raise ValueError("Prices and volumes must have same length")
    if len(prices) < period:
        return None
    # ... implementation
    return vwap_value
```

## Documentation

### Docstrings

Use Google or NumPy style:

```python
def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate Relative Strength Index.
    
    Args:
        prices: List of closing prices
        period: RSI period (default: 14)
    
    Returns:
        RSI value between 0 and 100
    
    Raises:
        ValueError: If prices list is too short
    
    Example:
        >>> calculate_rsi([100, 102, 101, 103], period=2)
        75.0
    """
    # Implementation
```

### Inline Comments

Only for non-obvious rationale, invariants, or caveats:

```python
# Use vectorized operation for performance (10x faster than loop)
result = prices * volumes / volumes.sum()
```

## Performance Considerations

- Prefer vectorized operations (Pandas/Polars) over Python loops
- Profile before optimizing
- Add performance tests for critical paths when relevant

## Next Steps

- Review [Testing](./06-testing.md) for test conventions
- Check [Project Structure](./02-project-structure.md) for module organization
- See [Configuration](./04-configuration.md) for parameter management

