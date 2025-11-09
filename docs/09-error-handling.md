# Error Handling Guide

## Overview

The SCP project uses a consistent exception hierarchy based on a root `AppError` class. This provides unified error handling across all modules while maintaining specific error types for different domains.

## Exception Hierarchy

```
Exception (built-in)
└── AppError (base for all SCP exceptions)
    ├── ConfigError (configuration issues)
    ├── DataSourceError (data loading/connection)
    └── NormalizationError (data validation/quality)
```

### Design Principles

1. **Single Root:** All custom exceptions inherit from `AppError`
2. **Domain-Specific:** Each major module has its own exception type
3. **Context Rich:** Exceptions store additional context as attributes
4. **Chain Preserving:** Original exceptions are preserved via chaining

## Exception Types

### AppError

**Purpose:** Base exception for all SCP application errors

**When to use:** Generally not raised directly; used as base class

**Attributes:**
- `message` - Human-readable error description
- `cause` - Optional original exception that caused this error
- Additional context via `**kwargs`

**Example:**
```python
from common import AppError

raise AppError(
    "Operation failed",
    operation="data_load",
    timestamp="2025-11-09T12:00:00"
)
```

### ConfigError

**Purpose:** Configuration-related errors

**When to use:**
- Invalid YAML/JSON syntax
- Missing required configuration parameters
- Invalid configuration values
- Unsupported configuration formats
- Configuration validation failures

**Example:**
```python
from common import ConfigError

# Simple error
raise ConfigError("Invalid log level: DEBUG2")

# With context
raise ConfigError(
    "Missing required field",
    field="system.log_path",
    config_file="config/core.yaml"
)

# With exception chaining
try:
    data = yaml.safe_load(f)
except yaml.YAMLError as e:
    raise ConfigError(
        f"Failed to parse YAML file: {path}",
        cause=e,
        path=str(path)
    ) from e
```

### DataSourceError

**Purpose:** Data loading and connection errors

**When to use:**
- File access failures
- API connection errors
- Database connection issues
- Data file format problems
- Network timeouts
- Authentication failures

**Example:**
```python
from common import DataSourceError

# File not accessible
raise DataSourceError(
    "Failed to read CSV file",
    path="/data/market.csv",
    reason="Permission denied"
)

# API connection failure
raise DataSourceError(
    "API connection timeout",
    endpoint="https://api.example.com/data",
    timeout_seconds=30,
    retry_count=3
)
```

### NormalizationError

**Purpose:** Data normalization and validation errors

**When to use:**
- Schema mismatches
- Missing required fields
- Invalid data types
- Data quality issues
- Timestamp format errors
- Unit conversion failures

**Example:**
```python
from common import NormalizationError

# Missing column
raise NormalizationError(
    "Required column missing",
    required_column="close_price",
    available_columns=["open", "high", "low", "volume"]
)

# Invalid data type
raise NormalizationError(
    "Invalid data type for timestamp",
    column="timestamp",
    expected_type="datetime",
    actual_type="str",
    sample_value="2025-13-45"  # Invalid date
)
```

## Exception Chaining

### Why Chain Exceptions?

Exception chaining preserves the original error context while providing domain-specific error types. This helps with debugging by maintaining the complete traceback.

### How to Chain Exceptions

Always use `from e` when wrapping exceptions:

```python
from common import ConfigError

try:
    data = yaml.safe_load(file)
except yaml.YAMLError as e:
    # GOOD: Preserves original exception
    raise ConfigError(
        "YAML parsing failed",
        cause=e,
        path=file_path
    ) from e

    # BAD: Loses original context
    # raise ConfigError("YAML parsing failed")
```

### Accessing Chained Exceptions

```python
try:
    load_config("config.yaml")
except ConfigError as e:
    print(f"Error: {e.message}")
    print(f"Caused by: {e.cause}")
    print(f"Original traceback: {e.__cause__}")
```

## Best Practices

### 1. Use Specific Exception Types

```python
# GOOD: Specific exception type
from common import ConfigError
raise ConfigError("Invalid configuration")

# BAD: Generic exception
raise Exception("Invalid configuration")

# BAD: Built-in exception for domain errors
raise ValueError("Invalid configuration")
```

### 2. Provide Context

```python
# GOOD: Rich context
raise DataSourceError(
    "Failed to load market data",
    symbol="GC",
    start_date="2025-01-01",
    source="CSV",
    file_path="/data/gold.csv"
)

# BAD: Vague error
raise DataSourceError("Failed to load data")
```

### 3. Chain Exceptions Properly

```python
# GOOD: Proper chaining
try:
    process_data()
except ValueError as e:
    raise NormalizationError(
        "Data validation failed",
        cause=e
    ) from e

# BAD: Swallowing original exception
try:
    process_data()
except ValueError:
    raise NormalizationError("Data validation failed")
```

### 4. Don't Catch Too Broadly

```python
# GOOD: Specific exception handling
try:
    load_config(path)
except FileNotFoundError:
    logger.error(f"Config not found: {path}")
    use_defaults()
except ConfigError as e:
    logger.error(f"Config invalid: {e}")
    raise

# BAD: Too broad
try:
    load_config(path)
except Exception:  # Catches everything!
    use_defaults()
```

### 5. Log Before Re-raising

```python
from common import get_logger, ConfigError

logger = get_logger(__name__)

try:
    load_config(path)
except ConfigError as e:
    logger.error(f"Configuration error: {e}", exc_info=True)
    raise  # Re-raise for caller to handle
```

## Testing Error Conditions

### Basic Exception Testing

```python
import pytest
from common import ConfigError

def test_invalid_config_raises_error():
    """Test that invalid config raises ConfigError."""
    with pytest.raises(ConfigError) as exc_info:
        load_invalid_config()
    
    assert "Invalid" in str(exc_info.value)
```

### Testing Exception Attributes

```python
def test_error_includes_context():
    """Test that exception includes context attributes."""
    try:
        raise ConfigError(
            "Test error",
            field="log_level",
            value="INVALID"
        )
    except ConfigError as e:
        assert e.message == "Test error"
        assert e.field == "log_level"
        assert e.value == "INVALID"
```

### Testing Exception Chaining

```python
def test_exception_chaining():
    """Test that exception chaining preserves original error."""
    try:
        try:
            raise ValueError("Original error")
        except ValueError as e:
            raise ConfigError("Wrapped error", cause=e) from e
    except ConfigError as config_err:
        assert config_err.message == "Wrapped error"
        assert config_err.cause is not None
        assert isinstance(config_err.cause, ValueError)
        assert config_err.__cause__ is not None
```

## Error Handling Patterns

### Pattern 1: Catch and Re-raise with Context

```python
from common import ConfigError, get_logger

logger = get_logger(__name__)

def load_user_config(path: str) -> dict:
    try:
        return load_config(path)
    except FileNotFoundError as e:
        logger.error(f"Config file not found: {path}")
        raise ConfigError(
            f"Configuration file missing: {path}",
            cause=e,
            path=path
        ) from e
    except ConfigError as e:
        logger.error(f"Config validation failed: {e}")
        raise  # Re-raise as-is
```

### Pattern 2: Convert Built-in to Domain Exception

```python
from common import NormalizationError

def parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as e:
        raise NormalizationError(
            f"Invalid timestamp format: {value}",
            cause=e,
            value=value,
            expected_format="ISO 8601"
        ) from e
```

### Pattern 3: Graceful Degradation

```python
from common import DataSourceError, get_logger

logger = get_logger(__name__)

def load_data_with_fallback(primary_source: str, fallback_source: str):
    try:
        return load_from_source(primary_source)
    except DataSourceError as e:
        logger.warning(f"Primary source failed, using fallback: {e}")
        try:
            return load_from_source(fallback_source)
        except DataSourceError as fallback_error:
            logger.error(f"Both sources failed: {fallback_error}")
            raise DataSourceError(
                "All data sources failed",
                primary_error=str(e),
                fallback_error=str(fallback_error)
            ) from fallback_error
```

### Pattern 4: Validate and Raise Early

```python
from common import NormalizationError

def process_market_data(data: pd.DataFrame) -> pd.DataFrame:
    # Validate early
    required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    missing_cols = set(required_cols) - set(data.columns)
    
    if missing_cols:
        raise NormalizationError(
            "Missing required columns",
            missing=list(missing_cols),
            available=list(data.columns)
        )
    
    # Process data...
    return data
```

## Integration with Logging

Always log exceptions with context:

```python
from common import get_logger, ConfigError

logger = get_logger(__name__)

def initialize_system():
    try:
        config = load_config("config/core.yaml")
        setup_services(config)
    except ConfigError as e:
        logger.error(
            f"Failed to initialize system: {e.message}",
            exc_info=True,
            extra={
                "config_path": getattr(e, 'path', 'unknown'),
                "error_type": type(e).__name__
            }
        )
        raise
```

## Future Exception Types

As the project grows, additional exception types will be added:

- `FeatureEngineError` - Feature computation errors
- `RuleEngineError` - Rule evaluation errors
- `BacktestError` - Backtesting errors
- `ExecutionError` - Trade execution errors
- `RiskError` - Risk management violations

## Common Pitfalls

### Pitfall 1: Catching AppError Too Early

```python
# BAD: Catches all custom exceptions
try:
    load_config()
    load_data()
    process()
except AppError as e:
    # Can't distinguish between config, data, or processing errors
    handle_error(e)

# GOOD: Catch specific types
try:
    load_config()
    load_data()
    process()
except ConfigError as e:
    handle_config_error(e)
except DataSourceError as e:
    handle_data_error(e)
except NormalizationError as e:
    handle_normalization_error(e)
```

### Pitfall 2: Losing Exception Context

```python
# BAD: Loses original exception
try:
    yaml.safe_load(file)
except yaml.YAMLError:
    raise ConfigError("YAML error")  # Lost the details!

# GOOD: Preserves context
try:
    yaml.safe_load(file)
except yaml.YAMLError as e:
    raise ConfigError("YAML parsing failed", cause=e) from e
```

### Pitfall 3: Over-catching

```python
# BAD: Catches system errors you shouldn't handle
try:
    process_data()
except Exception:  # Catches KeyboardInterrupt, SystemExit, etc!
    logger.error("Error occurred")

# GOOD: Catch only what you can handle
try:
    process_data()
except (DataSourceError, NormalizationError) as e:
    logger.error(f"Data processing error: {e}")
    raise
```

## Summary

- Use `AppError` as base for all custom exceptions
- Choose specific exception types (`ConfigError`, `DataSourceError`, `NormalizationError`)
- Always chain exceptions with `from e`
- Provide rich context via keyword arguments
- Log exceptions before re-raising
- Test error conditions thoroughly
- Don't catch exceptions you can't handle meaningfully

## See Also

- [Logging Guide](./08-logging.md) - Logging exceptions
- [Development Workflow](./05-development-workflow.md) - Error handling principles
- [Testing](./06-testing.md) - Testing error conditions
