# Data Layer Guide

This guide covers the data layer components for market data ingestion, including the unified Candle data model and client stubs for retrieving market data.

## Overview

The data layer is responsible for:
- Defining a unified data model for market candles (OHLCV data)
- Providing client interfaces for data retrieval
- Validating and normalizing incoming data
- Supporting multiple data sources (CME, ICE, CSV files, etc.)

**Current Status:** 
- **LocalCSVClient:** Fully implemented with real CSV loading using pandas
- **HistoricalDataLoader:** Fully implemented for backtesting workflows
- **CMEGCClient, DXYIndexClient:** Stub implementations (return empty lists)
- **TimeAligner, DataNormalizer:** Stub implementations

## Table of Contents

- [Candle Data Model](#candle-data-model)
- [Data Client Stubs](#data-client-stubs)
- [Historical Data Loader](#historical-data-loader)
- [Usage Examples](#usage-examples)
- [Validation and Error Handling](#validation-and-error-handling)
- [Testing](#testing)
- [Future Implementation](#future-implementation)

---

## Candle Data Model

The `Candle` dataclass is the unified data structure for all market data (OHLCV - Open, High, Low, Close, Volume).

### Definition

**Location:** `common/types.py`

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Candle:
    """Represents a single market candle (OHLCV data).
    
    This is a frozen dataclass, meaning instances are immutable after creation.
    """
    timestamp: datetime      # Start time of the candle (UTC, timezone-aware)
    open: float             # Opening price
    high: float             # Highest price
    low: float              # Lowest price
    close: float            # Closing price
    volume: float           # Trading volume
    symbol: str             # Instrument symbol (e.g., "GC", "DXY")
    timeframe: str          # Aggregation period (e.g., "1m", "5m", "1h")
    source: str             # Data source (e.g., "CME", "ICE", "LocalCSV")
```

### Key Properties

1. **Immutable:** Frozen dataclass ensures data integrity throughout the pipeline
2. **Timezone-Aware:** All timestamps must be in UTC with timezone information
3. **Validated:** Comprehensive validation in `__post_init__` ensures data quality
4. **Type-Safe:** Full type hints for mypy compliance

### Validation Rules

The Candle dataclass enforces the following rules:

#### Timestamp Validation
- Must be a `datetime` object
- Must be timezone-aware (tzinfo not None)
- Automatically converts to UTC if in a different timezone

```python
# ✅ Valid
candle = Candle(
    timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    # ... other fields
)

# ❌ Invalid - raises NormalizationError
candle = Candle(
    timestamp=datetime(2025, 1, 1, 12, 0),  # No timezone
    # ... other fields
)
```

#### OHLC Relationship Validation
- High must be >= max(open, close, low)
- Low must be <= min(open, close, high)
- All OHLC prices must be non-negative (>= 0)

```python
# ✅ Valid
Candle(open=100.0, high=105.0, low=99.0, close=103.0, ...)

# ❌ Invalid - high < close
Candle(open=100.0, high=102.0, low=99.0, close=105.0, ...)

# ❌ Invalid - negative price
Candle(open=-100.0, high=105.0, low=99.0, close=103.0, ...)
```

#### Volume Validation
- Must be non-negative (>= 0)
- Zero volume is allowed (represents no trading activity)

```python
# ✅ Valid
Candle(volume=1000.0, ...)  # Normal trading
Candle(volume=0.0, ...)     # No trading

# ❌ Invalid
Candle(volume=-100.0, ...)  # Negative volume
```

#### String Field Validation
- `symbol`, `timeframe`, and `source` cannot be empty strings
- Must be non-None strings

```python
# ✅ Valid
Candle(symbol="GC", timeframe="5m", source="CME", ...)

# ❌ Invalid - empty strings
Candle(symbol="", timeframe="5m", source="CME", ...)
```

### Error Handling

All validation failures raise `NormalizationError` with descriptive messages:

```python
from common.exceptions import NormalizationError
from common.types import Candle

try:
    candle = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0),  # Naive datetime
        open=100.0, high=105.0, low=99.0, close=103.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME"
    )
except NormalizationError as e:
    print(e)  # "Timestamp must be timezone-aware (UTC)."
```

### Usage Example

```python
from datetime import datetime, timezone
from common.types import Candle

# Create a candle
candle = Candle(
    timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    open=2050.5,
    high=2055.0,
    low=2048.0,
    close=2052.0,
    volume=1500.0,
    symbol="GC",
    timeframe="5m",
    source="CME"
)

# Access fields
print(f"Gold at {candle.timestamp}: ${candle.close}")
print(f"Range: ${candle.low} - ${candle.high}")

# Candles are immutable
# candle.close = 2060.0  # ❌ Raises FrozenInstanceError

# Candles are hashable (can be used in sets/dicts)
candles_set = {candle}
```

---

## Data Client Stubs

Data clients provide a unified interface for retrieving market data from various sources.

### CMEGCClient

**Purpose:** Client for CME Gold Futures (GC) data

**Location:** `data_layer/clients.py`

**Exchange:** CME Group / COMEX (Chicago Mercantile Exchange)

#### Interface

```python
class CMEGCClient:
    def __init__(self) -> None:
        """Initialize the CME GC client stub."""
        
    def fetch(
        self,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[Candle]:
        """Fetch CME Gold Futures (GC) candle data.
        
        Args:
            start: Start datetime (must be timezone-aware UTC)
            end: End datetime (must be timezone-aware UTC, must be after start)
            timeframe: Candle timeframe (e.g., "1m", "5m", "15m")
            
        Returns:
            List of Candle objects. Currently returns empty list (stub).
            
        Raises:
            DataSourceError: If validation fails
        """
```

#### Validation

The `fetch` method validates:
1. Start datetime is timezone-aware
2. End datetime is timezone-aware
3. Start is before end
4. Timeframe is not empty or whitespace-only

All validation failures raise `DataSourceError` with `symbol="GC"`.

#### Usage

```python
from datetime import datetime, timezone
from data_layer.clients import CMEGCClient

# Create client
client = CMEGCClient()

# Fetch data
start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
end = datetime(2025, 1, 1, 17, 0, tzinfo=timezone.utc)
candles = client.fetch(start, end, "5m")

# Phase 1: Returns empty list
assert candles == []
```

### DXYIndexClient

**Purpose:** Client for U.S. Dollar Index (DXY) data

**Location:** `data_layer/clients.py`

**Exchange:** ICE (Intercontinental Exchange)

#### Interface

```python
class DXYIndexClient:
    def __init__(self) -> None:
        """Initialize the DXY Index client stub."""
        
    def fetch(
        self,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[Candle]:
        """Fetch U.S. Dollar Index (DXY) candle data.
        
        Args:
            start: Start datetime (must be timezone-aware UTC)
            end: End datetime (must be timezone-aware UTC, must be after start)
            timeframe: Candle timeframe (e.g., "1m", "5m", "15m")
            
        Returns:
            List of Candle objects. Currently returns empty list (stub).
            
        Raises:
            DataSourceError: If validation fails
        """
```

#### Validation

Identical to CMEGCClient, but uses `symbol="DXY"` in error messages.

#### Usage

```python
from datetime import datetime, timezone
from data_layer.clients import DXYIndexClient

# Create client
client = DXYIndexClient()

# Fetch data
start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
end = datetime(2025, 1, 1, 17, 0, tzinfo=timezone.utc)
candles = client.fetch(start, end, "1m")

# Phase 1: Returns empty list
assert candles == []
```

### LocalCSVClient

**Purpose:** Client for reading market data from local CSV files

**Location:** `data_layer/clients.py`

**Data Source:** Local file system (CSV files)

#### Interface

```python
class LocalCSVClient:
    def __init__(self, file_path: str | os.PathLike[str]) -> None:
        """Initialize the Local CSV client stub.
        
        Args:
            file_path: Path to CSV file (string or Path object)
            
        Raises:
            DataSourceError: If file_path is invalid or empty
        """
        
    def fetch(
        self,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[Candle]:
        """Fetch candle data from local CSV file.
        
        Args:
            start: Start datetime (must be timezone-aware UTC)
            end: End datetime (must be timezone-aware UTC)
            timeframe: Candle timeframe (e.g., "1m", "5m", "15m")
            
        Returns:
            List of Candle objects. Currently returns empty list (stub).
            
        Raises:
            DataSourceError: If validation fails
        """
```

#### Validation

The `__init__` method validates:
1. `file_path` is a string or Path object
2. `file_path` is not empty or whitespace-only

The `fetch` method validates:
1. Start datetime is timezone-aware
2. End datetime is timezone-aware
3. Start is before or equal to end
4. Timeframe is not empty or whitespace-only

All validation failures raise `DataSourceError` with `file_path` context.

#### Usage

```python
from datetime import datetime, timezone
from pathlib import Path
from data_layer.clients import LocalCSVClient

# Create client with string path
client = LocalCSVClient("data/gold_futures_2025.csv")

# Or with Path object
client = LocalCSVClient(Path("data/gold_futures_2025.csv"))

# Fetch data
start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
end = datetime(2025, 1, 1, 17, 0, tzinfo=timezone.utc)
candles = client.fetch(start, end, "5m")

# Phase 1: Returns empty list
assert candles == []
```

#### Future Implementation

In future phases, LocalCSVClient will:
- Read and parse CSV files with OHLCV data
- Support various CSV formats (standard, custom, vendor-specific)
- Filter data by date range
- Handle missing data and validate data quality
- Support chunked reading for large files

**Expected CSV Format (Future):**
```csv
timestamp,open,high,low,close,volume,symbol
2025-01-01T09:00:00Z,2050.0,2055.0,2048.0,2052.0,1000,GC
2025-01-01T09:05:00Z,2052.0,2057.0,2050.0,2055.0,1200,GC
```

### TimeAligner

**Purpose:** Align two candle data streams by timestamp for comparative analysis

**Location:** `data_layer/aligner.py`

**Use Case:** Synchronize Gold (GC) and Dollar Index (DXY) data on the same timeline

#### Interface

```python
class TimeAligner:
    def __init__(self) -> None:
        """Initialize the TimeAligner stub."""
        
    def align(
        self,
        gc_candles: list[Candle],
        dxy_candles: list[Candle],
        timeframe: str,
    ) -> list[tuple[Candle | None, Candle | None]]:
        """Align two candle streams by timestamp.
        
        Args:
            gc_candles: List of Gold (GC) candles to align
            dxy_candles: List of DXY index candles to align
            timeframe: Target timeframe for alignment (e.g., "5m")
            
        Returns:
            List of tuples (gc_candle, dxy_candle) aligned by timestamp.
            Missing data is represented as None.
            Currently returns empty list (stub).
            
        Raises:
            DataSourceError: If validation fails
        """
```

#### Validation

The `align` method validates:
1. Timeframe is not empty or whitespace-only

Validation failures raise `DataSourceError`.

#### Return Format

Returns `list[tuple[Candle | None, Candle | None]]` where:
- Each tuple contains (gc_candle, dxy_candle)
- `None` represents missing data for that timestamp
- Tuples are ordered by timestamp

For example:
```python
[
    (gc_candle_1, dxy_candle_1),  # Both have data at timestamp 1
    (gc_candle_2, None),           # Only GC has data at timestamp 2
    (None, dxy_candle_3)           # Only DXY has data at timestamp 3
]
```

#### Usage

```python
from datetime import datetime, timezone
from data_layer.aligner import TimeAligner
from data_layer.clients import CMEGCClient, DXYIndexClient

# Fetch data from both sources
gc_client = CMEGCClient()
dxy_client = DXYIndexClient()

start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
end = datetime(2025, 1, 1, 17, 0, tzinfo=timezone.utc)

gc_candles = gc_client.fetch(start, end, "5m")
dxy_candles = dxy_client.fetch(start, end, "5m")

# Align the data streams
aligner = TimeAligner()
aligned = aligner.align(gc_candles, dxy_candles, "5m")

# Phase 1: Returns empty list
assert aligned == []

# Future: Process aligned pairs
for gc, dxy in aligned:
    if gc and dxy:
        # Both have data - analyze correlation
        print(f"GC: ${gc.close}, DXY: {dxy.close}")
    elif gc:
        # Only GC data available
        print(f"GC: ${gc.close}, DXY: missing")
    elif dxy:
        # Only DXY data available
        print(f"GC: missing, DXY: {dxy.close}")
```

#### Future Implementation

Phase 2+ will include:

**Full Timestamp Alignment:**
- Merge timestamps from both streams
- Create union of all unique timestamps
- Pair candles with matching timestamps
- Fill gaps with `None` for missing data

**Gap Filling Strategies:**
- Forward-fill: Use last known value
- Interpolation: Estimate missing values
- Configurable strategy per use case

**Resampling:**
- Convert data to different timeframes
- Aggregate higher-frequency to lower-frequency
- Interpolate lower-frequency to higher-frequency

**Multi-Stream Alignment:**
- Support more than 2 data sources
- Return tuples of N candles
- Handle complex alignment scenarios

**Example Future Usage:**
```python
# Future: Full alignment with gap filling
aligner = TimeAligner(fill_method="forward")
aligned = aligner.align(gc_candles, dxy_candles, "5m")

for gc, dxy in aligned:
    # All timestamps present, gaps filled
    assert gc is not None or dxy is not None
```

---

## Historical Data Loader

**Location:** `data_layer/loader.py`

The `HistoricalDataLoader` provides a high-level interface for loading GC (Gold Futures) and DXY (Dollar Index) historical data from CSV files into pandas DataFrames for backtesting and analysis.

### Key Features

- **Symbol-to-filename mapping:** Automatically maps "DXY" to "DX_ohlcv" files
- **DataFrame output:** Returns data as pandas DataFrames with timestamp index
- **Data validation:** Ensures sorted, unique timestamps
- **Multi-symbol loading:** Load GC and DXY data in a single call
- **Logging:** Tracks loading statistics for audit trail

### API

```python
class HistoricalDataLoader:
    def __init__(self, data_dir: str | Path):
        """Initialize loader with data directory path."""
        
    def load(
        self,
        symbols: list[str],      # e.g., ["GC", "DXY"]
        timeframe: str,           # e.g., "1m", "15m", "1h"
        start: datetime,          # timezone-aware UTC
        end: datetime,            # timezone-aware UTC
    ) -> dict[str, pd.DataFrame]:
        """Load historical data for multiple symbols.
        
        Returns dict keyed by symbol with DataFrames as values.
        Each DataFrame has:
        - Index: timestamp (DatetimeIndex, UTC, sorted, unique)
        - Columns: open, high, low, close, volume, symbol
        """
```

### DataFrame Schema

Each returned DataFrame has the following structure:

**Index:**
- `timestamp`: DatetimeIndex (UTC, timezone-aware, sorted, unique)

**Columns:**
- `open`: float - Opening price
- `high`: float - Highest price
- `low`: float - Lowest price
- `close`: float - Closing price
- `volume`: float - Trading volume
- `symbol`: str - Instrument symbol (e.g., "GCZ5", "DX  FMZ0025!")

### Usage Example

```python
from datetime import datetime, timezone
from pathlib import Path
from data_layer import HistoricalDataLoader

# Initialize loader
loader = HistoricalDataLoader(Path("data/gc_dx_ohlcv"))

# Define date range
start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=timezone.utc)
end = datetime(2025, 9, 30, 5, 0, 0, tzinfo=timezone.utc)

# Load GC and DXY data
data = loader.load(["GC", "DXY"], "1m", start, end)

# Access DataFrames
gc_df = data["GC"]
dxy_df = data["DXY"]

# DataFrame operations
print(f"GC: {len(gc_df)} rows")
print(f"DXY: {len(dxy_df)} rows")
print(gc_df.head())

# Compute indicators on DataFrame
gc_df["sma_20"] = gc_df["close"].rolling(20).mean()
gc_df["returns"] = gc_df["close"].pct_change()
```

### Symbol Mapping

The loader automatically maps symbols to CSV filenames:

| Symbol | CSV Filename Pattern |
|--------|---------------------|
| GC     | `GC_ohlcv-{timeframe}.csv` |
| DXY    | `DX_ohlcv-{timeframe}.csv` |

**Note:** DXY maps to "DX" because the CSV files use the "DX" prefix.

### Supported Timeframes

The loader supports the following timeframes (must match available CSV files):

- `1s` - 1 second
- `1m` - 1 minute
- `15m` - 15 minutes
- `1h` - 1 hour

### Error Handling

The loader raises `DataSourceError` in the following cases:

- **Missing file:** CSV file not found for symbol/timeframe
- **Invalid data:** CSV parsing errors or malformed data
- **Invalid parameters:** Missing or invalid datetime/timeframe parameters

```python
from common.exceptions import DataSourceError

try:
    data = loader.load(["INVALID"], "1m", start, end)
except DataSourceError as e:
    print(f"Failed to load data: {e}")
```

### Integration with Backtesting

The HistoricalDataLoader is designed for seamless integration with backtesting workflows:

```python
from data_layer import HistoricalDataLoader
from feature_engine import compute_vwap, compute_rsi
from data_layer import TimeAligner

# Load data
loader = HistoricalDataLoader("data/gc_dx_ohlcv")
data = loader.load(["GC", "DXY"], "1m", start, end)

# Compute features
gc_df = data["GC"]
gc_df["vwap"] = compute_vwap(gc_df)
gc_df["rsi"] = compute_rsi(gc_df["close"])

# Align GC and DXY for correlation analysis
aligner = TimeAligner()
aligned_gc, aligned_dxy = aligner.align(
    data["GC"], 
    data["DXY"], 
    "timestamp"
)

# Run backtest
# ... (backtesting logic)
```

### Logging

The loader logs loading statistics for each symbol:

```
INFO - Loaded 45 rows for GC (1m) from 2025-09-30T04:20:00+00:00 to 2025-09-30T05:00:00+00:00
INFO - Loaded 42 rows for DXY (1m) from 2025-09-30T04:20:00+00:00 to 2025-09-30T05:00:00+00:00
```

### Performance Considerations

- **Memory efficient:** Uses pandas for columnar storage
- **Lazy loading:** Data is loaded only when `load()` is called
- **Vectorized operations:** DataFrames enable fast vectorized calculations
- **Caching:** Consider caching DataFrames for repeated access

### Testing

The HistoricalDataLoader has comprehensive test coverage:

```bash
pytest tests/unit/test_historical_data_loader.py -v
```

**Test coverage:**
- Single and multi-symbol loading
- Date range filtering
- Empty result handling
- Missing file error handling
- DataFrame schema validation
- Index sorting and uniqueness
- Symbol-to-filename mapping (DXY → DX)

---

## Usage Examples

### Basic Workflow

```python
from datetime import datetime, timezone, timedelta
from data_layer.clients import CMEGCClient, DXYIndexClient, LocalCSVClient
from common.types import Candle

# Setup time range
end = datetime.now(timezone.utc)
start = end - timedelta(hours=1)

# Fetch gold data from CME API
gc_client = CMEGCClient()
gc_candles = gc_client.fetch(start, end, "5m")

# Fetch dollar index data from ICE
dxy_client = DXYIndexClient()
dxy_candles = dxy_client.fetch(start, end, "5m")

# Or fetch from local CSV file
csv_client = LocalCSVClient("data/historical_gold_2025.csv")
csv_candles = csv_client.fetch(start, end, "5m")

# Process candles (when clients return real data)
for candle in gc_candles:
    print(f"{candle.symbol} @ {candle.timestamp}: "
          f"O={candle.open} H={candle.high} "
          f"L={candle.low} C={candle.close} V={candle.volume}")
```

### Multiple Timeframes

```python
from data_layer.clients import CMEGCClient

client = CMEGCClient()
start = datetime(2025, 1, 1, tzinfo=timezone.utc)
end = datetime(2025, 1, 2, tzinfo=timezone.utc)

# Fetch different timeframes
candles_1m = client.fetch(start, end, "1m")
candles_5m = client.fetch(start, end, "5m")
candles_1h = client.fetch(start, end, "1h")
```

### Creating Candles Manually

```python
from datetime import datetime, timezone
from common.types import Candle

# Create a candle from raw data
candle = Candle(
    timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    open=2050.5,
    high=2055.0,
    low=2048.0,
    close=2052.0,
    volume=1500.0,
    symbol="GC",
    timeframe="5m",
    source="CME"
)
```

---

## Validation and Error Handling

### Client Validation Errors

All clients validate input and raise `DataSourceError` for invalid arguments:

```python
from datetime import datetime, timezone
from data_layer.clients import CMEGCClient
from common.exceptions import DataSourceError

client = CMEGCClient()

# ❌ Naive datetime (no timezone)
try:
    client.fetch(
        datetime(2025, 1, 1),  # No tzinfo
        datetime(2025, 1, 2, tzinfo=timezone.utc),
        "5m"
    )
except DataSourceError as e:
    print(e.message)  # "Start datetime must be timezone-aware"
    print(e.symbol)   # "GC"

# ❌ Start after end
try:
    client.fetch(
        datetime(2025, 1, 2, tzinfo=timezone.utc),
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        "5m"
    )
except DataSourceError as e:
    print(e.message)  # "Start time must be before end time"

# ❌ Empty timeframe
try:
    client.fetch(
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
        ""
    )
except DataSourceError as e:
    print(e.message)  # "Timeframe cannot be empty"
```

### Candle Validation Errors

Creating invalid candles raises `NormalizationError`:

```python
from common.types import Candle
from common.exceptions import NormalizationError

# ❌ OHLC relationship violation
try:
    Candle(
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        open=100.0,
        high=102.0,  # High less than close
        low=99.0,
        close=105.0,  # Close higher than high
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME"
    )
except NormalizationError as e:
    print(e.message)  # "OHLC relationship violated: low <= (open, close) <= high."

# ❌ Negative volume
try:
    Candle(
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        open=100.0, high=105.0, low=99.0, close=103.0,
        volume=-500.0,  # Negative
        symbol="GC",
        timeframe="5m",
        source="CME"
    )
except NormalizationError as e:
    print(e.message)  # "Volume cannot be negative."
```

### Best Practices

1. **Always use timezone-aware datetimes:**
   ```python
   from datetime import datetime, timezone
   
   # ✅ Good
   dt = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
   
   # ❌ Bad
   dt = datetime(2025, 1, 1, 12, 0)
   ```

2. **Catch specific exceptions:**
   ```python
   from common.exceptions import DataSourceError, NormalizationError
   
   try:
       candles = client.fetch(start, end, "5m")
   except DataSourceError as e:
       logger.error(f"Failed to fetch {e.symbol} data: {e.message}")
   ```

3. **Validate timeframes consistently:**
   ```python
   VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
   
   timeframe = "5m"
   if timeframe not in VALID_TIMEFRAMES:
       raise ValueError(f"Invalid timeframe: {timeframe}")
   ```

---

## Testing

### Unit Tests

Both clients have comprehensive test suites:

**CMEGCClient Tests:** `tests/unit/test_cme_gc_client.py` (15 test cases)  
**DXYIndexClient Tests:** `tests/unit/test_dxy_index_client.py` (15 test cases)  
**Candle Tests:** `tests/unit/test_candle.py` (25 test cases)

### Running Tests

```bash
# Run all data layer tests
pytest tests/unit/test_cme_gc_client.py tests/unit/test_dxy_index_client.py tests/unit/test_candle.py -v

# Run with coverage
pytest --cov=data_layer --cov=common tests/unit/test_cme_gc_client.py tests/unit/test_dxy_index_client.py tests/unit/test_candle.py

# Use Makefile
make test
make test-coverage
```

### Writing Tests

Example test for a new client:

```python
from datetime import datetime, timezone
import pytest
from data_layer.clients import MyNewClient
from common.exceptions import DataSourceError

def test_client_fetch_validates_timezone():
    """Test that fetch requires timezone-aware datetimes."""
    client = MyNewClient()
    start = datetime(2025, 1, 1)  # Naive
    end = datetime(2025, 1, 2, tzinfo=timezone.utc)
    
    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "5m")
    
    assert "timezone-aware" in str(exc_info.value).lower()
```

---

## Future Implementation

### Phase 2+: Real Data Integration

The stub clients will be replaced with real implementations:

#### CMEGCClient
- Connect to CME Group API or data providers (Bloomberg, Reuters, etc.)
- Implement authentication and rate limiting
- Handle pagination for large date ranges
- Add caching and retry logic
- Parse and normalize CME-specific data formats

#### DXYIndexClient
- Connect to ICE data feeds or third-party providers
- Handle DXY-specific data formats
- Implement real-time and historical data retrieval

### Additional Planned Components

1. **LocalCSVClient** - Load historical data from CSV files
   - Path: `data_layer/clients.py`
   - Load from `/data/mock/{symbol}/{timeframe}.csv`
   - Convert CSV rows to Candle objects

2. **DataNormalizer** - Normalize raw data to Candle schema
   - Path: `data_layer/normalizer.py`
   - Handle different data source formats
   - Apply data quality checks

3. **TimeAligner** - Align data from multiple sources (IMPLEMENTED IN PHASE 1 AS STUB)
   - Path: `data_layer/aligner.py`
   - Synchronize GC and DXY data by timestamp
   - Handle missing data and gaps
   - Currently returns empty list (stub)

### Extensibility

To add a new data source:

1. **Create a new client class** in `data_layer/clients.py`:
   ```python
   class MyNewClient:
       def __init__(self) -> None:
           pass
       
       def fetch(
           self,
           start: datetime,
           end: datetime,
           timeframe: str,
       ) -> list[Candle]:
           # Implement validation (same as existing clients)
           # Fetch data from your source
           # Convert to Candle objects
           return candles
   ```

2. **Export from `data_layer/__init__.py`**:
   ```python
   from data_layer.clients import CMEGCClient, DXYIndexClient, MyNewClient
   __all__ = ["CMEGCClient", "DXYIndexClient", "MyNewClient"]
   ```

3. **Add comprehensive tests** in `tests/unit/test_mynew_client.py`

4. **Update documentation** to reflect the new client

---

## See Also

- [Project Structure](./02-project-structure.md) - Module organization
- [Configuration](./04-configuration.md) - System configuration
- [Error Handling Guide](./09-error-handling.md) - Exception hierarchy and patterns
- [Testing](./06-testing.md) - Test framework and conventions

