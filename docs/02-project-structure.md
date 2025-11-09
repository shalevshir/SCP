# Project Structure

## Directory Layout

```
SCP/
├── data_layer/          # Data connectors and loaders (stubs)
├── feature_engine/      # Indicator and feature computations (stubs)
├── rule_engine/         # SOP rule evaluation and scoring (stubs)
├── backtester/          # Backtesting shell and integration (stubs)
├── common/              # Shared utilities, types, constants
├── config/              # Configuration files
│   └── core.yaml        # Main configuration file
├── src/                 # Source code (legacy structure)
│   └── scp/             # Main package
│       └── __init__.py  # Package initialization
├── tests/               # Test suite
│   ├── unit/            # Unit tests
│   │   └── test_version.py
│   └── test_imports.py  # Skeleton integrity tests
├── data/                # Runtime data storage (git-kept)
├── logs/                # Runtime logs (git-kept)
├── docs/                # Documentation
├── pyproject.toml       # Poetry configuration and tool settings
├── README.md            # Project overview
└── .gitignore           # Git ignore rules
```

## Module Descriptions

### `/data_layer/`

**Purpose:** Data connectors and loaders for market data ingestion.

**Status:** Stub only (Phase 1)

**Current Implementation:**
- `clients.py` - Data client stubs (CMEGCClient for Gold Futures, DXYIndexClient for Dollar Index)

**Future Responsibilities:**
- Real API clients for GC (Gold) and DXY (Dollar Index) data
- CSV file loaders for historical data
- Data normalization and schema validation
- Time-series alignment

**Files:**
- `__init__.py` - Package exports
- `clients.py` - Data client stubs (CMEGCClient, DXYIndexClient)

### `/feature_engine/`

**Purpose:** Technical indicator and feature computation.

**Status:** Stub only (Phase 1)

**Future Responsibilities:**
- VWAP calculations
- RSI computation
- EMA calculations
- DXY correlation analysis
- Structure detection

**Files:**
- `__init__.py` - Package marker

### `/rule_engine/`

**Purpose:** SOP rule evaluation and trade scoring.

**Status:** Stub only (Phase 1)

**Future Responsibilities:**
- Structure-first validation
- Setup scoring (0-10 scale)
- Trade qualification logic (≥8/10 threshold)
- Risk parameter enforcement

**Files:**
- `__init__.py` - Package marker

### `/backtester/`

**Purpose:** Historical simulation and backtesting framework.

**Status:** Stub only (Phase 1)

**Future Responsibilities:**
- Historical data iteration
- Trade simulation
- PnL calculation
- Performance metrics
- Integration with rule engine

**Files:**
- `__init__.py` - Package marker

### `/common/`

**Purpose:** Shared utilities, types, and constants.

**Status:** Partially implemented (Phase 1)

**Current Implementation:**
- `config.py` - Configuration loading system with YAML/JSON support
- `logger.py` - Centralized logging wrapper with rotating file handlers
- `exceptions.py` - Exception hierarchy with domain-specific error types
- `types.py` - Core data models (Candle schema)

**Future Responsibilities:**
- Additional type definitions (Trade, Signal, etc.)
- Constants (symbols, timeframes)
- Utility functions

**Files:**
- `__init__.py` - Package exports
- `config.py` - Configuration system
- `logger.py` - Logging wrapper
- `exceptions.py` - Exception hierarchy (AppError, ConfigError, DataSourceError, NormalizationError)
- `types.py` - Data models (Candle)

### `/config/`

**Purpose:** Static configuration files.

**Files:**
- `core.yaml` - Main configuration with system, assets, risk, governance, and backtest parameters

See [Configuration](./04-configuration.md) for detailed parameter documentation.

### `/tests/`

**Purpose:** Test suite following TDD principles.

**Structure:**
- `unit/` - Unit tests for individual components
- `test_imports.py` - Skeleton integrity test (validates all packages import)

**Test Framework:**
- pytest with pytest-xdist for parallel execution
- Type checking via mypy (excluded from tests directory)

See [Testing](./06-testing.md) for testing conventions.

## Package Organization

All code modules are organized as top-level Python packages with `__init__.py` markers. This structure allows for:

- Clear separation of concerns
- Easy module discovery
- Straightforward import paths
- Scalable architecture

## Data Flow (Future)

```
Market Data (GC/DXY)
    ↓
Data Layer (ingestion & normalization)
    ↓
Feature Engine (indicator computation)
    ↓
Rule Engine (SOP evaluation & scoring)
    ↓
Backtester (simulation & validation)
    ↓
Results & Logs
```

## Git Tracking

Empty directories are tracked via `.gitkeep` files:
- `data/.gitkeep`
- `logs/.gitkeep`
- Each module directory contains `.gitkeep` for structure visibility

