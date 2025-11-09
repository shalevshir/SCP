# Testing

## Test Framework

**Framework:** pytest  
**Parallel Execution:** pytest-xdist  
**Coverage:** pytest-cov

## Test Structure

```
tests/
├── conftest.py        # Shared fixtures and configuration
├── unit/              # Unit tests for individual components
│   └── test_version.py
├── integration/       # Integration tests (future)
└── test_imports.py    # Skeleton integrity tests
```

## Test Conventions

### Naming

- Test files: `test_*.py` or `*_test.py`
- Test functions: `test_*`
- Test classes: `Test*`

### Organization

- **Unit tests:** Test individual functions/classes in isolation
- **Integration tests:** Test component interactions
- **E2E tests:** Test full workflows (future)

## Example Tests

### Unit Test

```python
# tests/unit/test_feature_engine.py
def test_calculate_vwap():
    prices = [100.0, 101.0, 102.0]
    volumes = [10.0, 20.0, 30.0]
    
    result = calculate_vwap(prices, volumes)
    
    expected = (100*10 + 101*20 + 102*30) / (10 + 20 + 30)
    assert result == pytest.approx(expected, rel=1e-6)
```

### Shared Fixtures

The project provides shared fixtures in `tests/conftest.py`:

```python
def test_with_temp_directory(temp_dir):
    """Use temporary directory fixture."""
    test_file = temp_dir / "data.txt"
    test_file.write_text("content")
    assert test_file.exists()

def test_with_sample_config(sample_config_dict):
    """Use sample configuration dictionary."""
    assert sample_config_dict["system"]["log_level"] == "INFO"

def test_with_config_file(sample_config_path):
    """Use temporary config file."""
    config = load_config(sample_config_path)
    assert config.system.data_path == "./data/"
```

**Available fixtures:**
- `temp_dir` - Temporary directory for tests
- `sample_config_dict` - Sample configuration dictionary
- `sample_config_path` - Path to temporary config file
- `mock_logger` - Mock logger for testing

### Test with Fixtures

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_candle_data():
    return {
        "timestamp": "2025-01-01T00:00:00Z",
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 1000.0
    }

# tests/unit/test_data_layer.py
def test_normalize_candle(sample_candle_data):
    result = normalize_candle(sample_candle_data)
    assert result.symbol == "GC"
    assert result.close == 101.0
```

### Test with Parametrization

```python
@pytest.mark.parametrize("input,expected", [
    ([100, 102, 101], 101.0),
    ([50, 60, 55], 55.0),
    ([], None),
])
def test_calculate_average(input, expected):
    result = calculate_average(input)
    assert result == expected
```

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_version.py

# Run specific test
pytest tests/unit/test_version.py::test_version_exposed

# Run tests matching pattern
pytest -k "version"
```

### Parallel Execution

```bash
# Auto-detect CPU count
pytest -n auto

# Use specific number of workers
pytest -n 4
```

### Coverage (Future)

```bash
# Run with coverage
pytest --cov=src --cov-report=html

# View coverage report
open htmlcov/index.html
```

## Test Categories

### Skeleton Integrity Tests

**File:** `tests/test_imports.py`

**Purpose:** Validate that all package modules can be imported without errors.

**Example:**
```python
def test_packages_import():
    # Validates skeleton packages import without side effects
    root = pathlib.Path(__file__).resolve().parents[1]
    _import_package_from(root / "data_layer", "data_layer")
    _import_package_from(root / "feature_engine", "feature_engine")
    # ... etc
```

### Unit Tests

**Location:** `tests/unit/`

**Purpose:** Test individual functions and classes in isolation.

**Characteristics:**
- Fast execution
- No external dependencies (mocked if needed)
- Test one behavior per test
- Clear, descriptive names

### Integration Tests (Future)

**Location:** `tests/integration/`

**Purpose:** Test component interactions.

**Characteristics:**
- May use test databases/files
- Test workflows across modules
- Slower than unit tests

## Test Best Practices

### 1. Test Behavior, Not Implementation

```python
# Good: Tests behavior
def test_calculates_correct_vwap():
    result = calculate_vwap([100, 101], [10, 20])
    assert result == pytest.approx(100.67, rel=1e-2)

# Bad: Tests implementation details
def test_uses_pandas():
    assert "pandas" in str(calculate_vwap.__code__.co_names)
```

### 2. Use Descriptive Names

```python
# Good
def test_returns_none_when_insufficient_data():
    result = calculate_vwap([100], [10])
    assert result is None

# Bad
def test_vwap_1():
    assert calculate_vwap([100], [10]) is None
```

### 3. One Assertion Per Behavior

```python
# Good: One behavior
def test_validates_input_lengths():
    with pytest.raises(ValueError):
        calculate_vwap([100, 101], [10])  # Mismatched lengths

# Good: Related assertions for one behavior
def test_calculates_vwap_correctly():
    result = calculate_vwap([100, 101, 102], [10, 20, 30])
    assert result is not None
    assert result > 100
    assert result < 102
```

### 4. Use Fixtures for Setup

```python
# Good: Reusable fixture
@pytest.fixture
def sample_data():
    return load_test_data("fixtures/sample.csv")

def test_processes_data(sample_data):
    result = process(sample_data)
    assert result is not None
```

### 5. Test Edge Cases

```python
def test_handles_empty_input():
    result = calculate_vwap([], [])
    assert result is None

def test_handles_single_value():
    result = calculate_vwap([100], [10])
    assert result == 100.0

def test_handles_negative_values():
    with pytest.raises(ValueError):
        calculate_vwap([-100], [10])
```

## Mocking and Faking

### Principles

- **Prefer fakes over mocks:** Use realistic test doubles
- **Mock external boundaries:** I/O, network, time
- **Avoid deep mocking:** Keep tests simple

### Example: Mocking Time

```python
from unittest.mock import patch
from datetime import datetime

@patch('scp.common.utils.get_current_time')
def test_logs_with_timestamp(mock_time):
    mock_time.return_value = datetime(2025, 1, 1, 12, 0, 0)
    
    log_entry = create_log_entry("test message")
    
    assert log_entry.timestamp == datetime(2025, 1, 1, 12, 0, 0)
```

## Test Data

### Fixtures Directory (Future)

```
tests/
├── fixtures/
│   ├── sample_gc_data.csv
│   ├── sample_dxy_data.csv
│   └── config_test.yaml
```

### Generating Test Data

```python
import pytest

@pytest.fixture
def generate_candles():
    def _generate(count: int) -> List[Candle]:
        return [
            Candle(
                timestamp=datetime.now() + timedelta(minutes=i),
                open=100.0 + i,
                high=102.0 + i,
                low=99.0 + i,
                close=101.0 + i,
                volume=1000.0
            )
            for i in range(count)
        ]
    return _generate
```

## Continuous Integration

The CI pipeline is active and runs on every PR and push to `main`:

1. ✅ Runs full test suite with coverage
2. ✅ Checks linting (ruff) and type checking (mypy)
3. ✅ Validates code formatting (black, isort)
4. ✅ Generates coverage reports
5. ✅ Blocks merges if tests fail
6. ✅ Posts coverage and test results as PR comments

See [Running Tests - Continuous Integration](./07-running-tests.md#continuous-integration) for complete CI documentation.

## Test Checklist

Before committing:
- [ ] All tests pass locally
- [ ] New features have tests
- [ ] Bug fixes have regression tests
- [ ] Tests are fast (< 1s for unit tests)
- [ ] Tests are deterministic (no flakiness)
- [ ] Test names clearly describe behavior

## Next Steps

- Add property-based testing with hypothesis (future)
- Set up coverage reporting
- Create integration test framework
- Add performance/benchmark tests for critical paths

