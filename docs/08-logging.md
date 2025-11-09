# Logging Guide

## Overview

The SCP project uses a centralized logging system built on Python's standard `logging` module. The system provides structured logging with rotating file handlers and console output, configured through the existing config system.

## Quick Start

### Initialize Logging

At application startup, initialize the logging system:

```python
from pathlib import Path
from common import load_config
from common.logger import setup_logging

# Load configuration
config = load_config(Path("config/core.yaml"))

# Initialize logging
setup_logging(config.system)
```

### Get Logger in Your Module

```python
from common import get_logger

logger = get_logger(__name__)

def my_function():
    logger.info("Function started")
    logger.debug("Detailed debug information")
    logger.warning("Something unusual happened")
    logger.error("An error occurred", exc_info=True)
```

## Features

### Dual Output
- **File logs:** Written to `{log_path}/dev/app.log`
- **Console logs:** Real-time output to stdout

### Log Rotation
- Maximum file size: 10MB
- Backup count: 5 files (app.log, app.log.1, app.log.2, etc.)
- Automatic rotation when size limit reached

### Configurable Log Levels
- DEBUG - Detailed diagnostic information
- INFO - General informational messages
- WARNING - Warning messages for unusual situations
- ERROR - Error messages for failures
- CRITICAL - Critical issues requiring immediate attention

### Structured Format
```
YYYY-MM-DD HH:MM:SS,mmm - module.name - LEVEL - message
```

Example:
```
2025-11-09 14:15:30,123 - data_layer.loader - INFO - Loading data from CSV
2025-11-09 14:15:30,456 - rule_engine.scorer - DEBUG - Evaluating setup score
2025-11-09 14:15:31,789 - backtester.engine - ERROR - Trade execution failed
```

## Configuration

### Via Configuration File

In `config/core.yaml`:

```yaml
system:
  log_path: "./logs/"
  log_level: "INFO"
```

Valid log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

### Via Environment Variable

Override the config file setting:

```bash
export SCP_LOG_LEVEL=DEBUG
python your_script.py
```

Environment variable takes precedence over config file.

## Best Practices

### 1. Use Appropriate Log Levels

```python
from common import get_logger

logger = get_logger(__name__)

# DEBUG - Detailed diagnostic info (disabled in production)
logger.debug(f"Processing {len(data)} records with params {params}")

# INFO - General progress and state changes
logger.info("Data loading completed successfully")

# WARNING - Unexpected but recoverable situations
logger.warning("Using fallback configuration due to missing file")

# ERROR - Failures requiring attention
logger.error("Failed to connect to database", exc_info=True)

# CRITICAL - Severe errors causing program termination
logger.critical("Configuration file corrupted, cannot continue")
```

### 2. Log at Boundaries

Log at module/function entry/exit points and external interactions:

```python
def load_market_data(symbol: str, start_date: str) -> pd.DataFrame:
    logger.info(f"Loading market data for {symbol} from {start_date}")
    
    try:
        data = fetch_data(symbol, start_date)
        logger.info(f"Loaded {len(data)} records for {symbol}")
        return data
    except Exception as e:
        logger.error(f"Failed to load data for {symbol}: {e}", exc_info=True)
        raise
```

### 3. Include Context

Provide actionable information in log messages:

```python
# Good - includes context
logger.error(f"Failed to parse config file {path}: {error}")

# Bad - too vague
logger.error("Parsing failed")
```

### 4. Avoid Logging in Hot Paths

Don't log inside tight loops or high-frequency operations:

```python
# Bad - logs in hot loop
for i in range(1000000):
    logger.debug(f"Processing iteration {i}")
    process(i)

# Good - log summary
logger.debug(f"Starting batch processing of {len(items)} items")
for item in items:
    process(item)
logger.debug("Batch processing completed")
```

### 5. Use exc_info for Exceptions

Always include traceback for errors:

```python
try:
    risky_operation()
except Exception as e:
    # Good - includes full traceback
    logger.error(f"Operation failed: {e}", exc_info=True)
    raise
```

### 6. Never Use print() in Library Code

```python
# Bad
def calculate_vwap(prices):
    print("Calculating VWAP")  # Don't do this
    return vwap

# Good
def calculate_vwap(prices):
    logger.debug("Calculating VWAP")
    return vwap
```

## Module-Specific Loggers

Each module should use its own logger:

```python
# data_layer/loader.py
from common import get_logger
logger = get_logger(__name__)  # Creates 'data_layer.loader' logger

# rule_engine/scorer.py
from common import get_logger
logger = get_logger(__name__)  # Creates 'rule_engine.scorer' logger
```

This creates a hierarchy that can be filtered:
```
root
├── data_layer
│   ├── loader
│   └── validator
├── rule_engine
│   ├── scorer
│   └── evaluator
└── backtester
    └── engine
```

## Testing with Logging

### Capture Logs in Tests

```python
import logging
from common import get_logger
from common.logger import setup_logging
from common.config import SystemConfig

def test_function_logs_error(caplog):
    """Test that function logs error on failure."""
    with caplog.at_level(logging.ERROR):
        my_function_that_fails()
    
    assert "Expected error message" in caplog.text
```

### Use Temporary Log Directory

```python
import tempfile
from pathlib import Path
from common.config import SystemConfig
from common.logger import setup_logging

def test_with_logging():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = SystemConfig(log_path=str(Path(tmpdir) / "logs"))
        setup_logging(config)
        
        # Your test code here
        
        # Verify log file
        log_file = Path(tmpdir) / "logs" / "dev" / "app.log"
        assert log_file.exists()
```

## Log File Management

### Location
- Development: `./logs/dev/app.log`
- Logs directory is created automatically if it doesn't exist

### Rotation
Files rotate automatically:
```
logs/dev/
├── app.log        # Current log (up to 10MB)
├── app.log.1      # Previous log
├── app.log.2      # Older log
├── app.log.3
├── app.log.4
└── app.log.5      # Oldest (deleted when new rotation occurs)
```

### Cleanup
Old logs are automatically removed when exceeding backup count (5 files).

## Troubleshooting

### Logs Not Appearing

**Problem:** Logger doesn't output anything

**Solution:** Ensure `setup_logging()` is called before using loggers:

```python
from common import load_config
from common.logger import setup_logging, get_logger

config = load_config("config/core.yaml")
setup_logging(config.system)  # Must call this first!

logger = get_logger(__name__)
logger.info("Now this will work")
```

### Wrong Log Level

**Problem:** DEBUG logs not showing

**Solution:** Check log level configuration:

```bash
# Via environment variable
export SCP_LOG_LEVEL=DEBUG

# Or update config/core.yaml
system:
  log_level: "DEBUG"
```

### Permission Errors

**Problem:** Cannot write to log directory

**Solution:** Ensure log directory is writable:

```bash
mkdir -p logs/dev
chmod 755 logs/dev
```

### Duplicate Log Messages

**Problem:** Each message appears twice

**Solution:** Don't call `setup_logging()` multiple times. Call it once at application startup.

## API Reference

### setup_logging(config: SystemConfig) -> None

Initialize the logging system with file and console handlers.

**Parameters:**
- `config`: SystemConfig instance containing `log_path` and `log_level`

**Effects:**
- Creates log directory if it doesn't exist
- Configures root logger with specified level
- Adds RotatingFileHandler and StreamHandler
- Sets up log formatting

**Example:**
```python
from common.config import SystemConfig
from common.logger import setup_logging

config = SystemConfig(log_path="./logs/", log_level="INFO")
setup_logging(config)
```

### get_logger(name: str) -> logging.Logger

Get or create a logger instance for the given module.

**Parameters:**
- `name`: Logger name (typically `__name__` of the calling module)

**Returns:**
- `logging.Logger`: Logger instance that inherits from configured root logger

**Example:**
```python
from common import get_logger

logger = get_logger(__name__)
logger.info("Message from this module")
```

## Integration with Other Systems

### With Configuration System

```python
from pathlib import Path
from common import load_config
from common.logger import setup_logging, get_logger

# Load config
config = load_config(Path("config/core.yaml"))

# Setup logging using config
setup_logging(config.system)

# Use logger
logger = get_logger(__name__)
logger.info(f"Config loaded from {config.system.data_path}")
```

### With Error Handling

```python
from common import get_logger

logger = get_logger(__name__)

def process_data(data):
    try:
        logger.info("Starting data processing")
        result = complex_operation(data)
        logger.info(f"Processing completed: {len(result)} records")
        return result
    except ValueError as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.critical(f"Unexpected error: {e}", exc_info=True)
        raise
```

## Next Steps

- Review [Development Workflow](./05-development-workflow.md) for coding standards
- Check [Configuration](./04-configuration.md) for system settings
- See [Testing](./06-testing.md) for test conventions with logging

