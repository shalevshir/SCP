# Shir Capital Partners — Trading Bot

**Structure before signal. Discipline before profit.**

A systematic trading bot built with Python, following strict TDD practices and institutional-grade architecture.

**Current Phase:** Phase 2 - Feature Engine & Rule Engine  
**Status:** VWAP Implementation Complete ✅

## Key Features

- ✅ **VWAP Calculator** - Production-ready volume-weighted average price with session resets
- 🏗️ Technical Indicators (RSI, EMA, DXY correlation) - In Progress
- 📊 Clean architecture with typed modules
- ✅ Comprehensive test coverage (145+ tests)
- 🔧 Full development tooling: black, isort, ruff, mypy (strict)
- 📝 Extensive documentation

## Quickstart

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd SCP

# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -
# or
pip install poetry

# Install all dependencies (including dev dependencies)
poetry install

# Verify installation
poetry run pytest --version

# Note: poetry.lock is committed to ensure reproducible builds
# This file should be kept in version control
```

### Development Workflow

```bash
# Run tests
poetry run pytest
# or
make test

# Run tests with coverage
poetry run pytest --cov=feature_engine --cov=common
# or
make test-coverage

# Run linting
poetry run ruff check .
poetry run mypy .

# Run all checks (lint + test)
make check

# Format code
poetry run black .
poetry run isort .

# See all available commands
make help
```

### Using Poetry Commands

```bash
# Add a new dependency
poetry add package-name

# Add a dev dependency
poetry add --group dev package-name

# Update dependencies
poetry update

# Show installed packages
poetry show

# Run any command in Poetry's environment
poetry run <command>
```

## Layout

- `src/scp/` — package code
- `tests/` — unit tests
- `config/core.yaml` — default configuration (Phase 1)
- `data/`, `logs/` — runtime folders (git-kept via .gitkeep)

## Module Map

- `/data_layer/`: Data connectors and normalization (Candle model, client stubs, TimeAligner)
- `/feature_engine/`: ✅ **VWAP** implemented | RSI, EMA, DXY correlation (planned)
- `/rule_engine/`: SOP rule evaluation and scoring (stubs)
- `/backtester/`: Backtesting shell and integration (stubs)
- `/common/`: Shared utilities, types, logging, config, exceptions
- `/config/`: Configuration files (`core.yaml`, `dev.local.json`)
- `/data/`: Market data storage (GC/DXY OHLCV)
- `/tests/`: Comprehensive test suite (unit, integration, e2e)

## Quick Example: Feature Engine

```python
from feature_engine import calculate_vwap, calculate_rsi, calculate_ema, calculate_dxy_correlation
import pandas as pd

# Load OHLCV data
df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])

# Calculate SOP indicators
df['vwap'] = calculate_vwap(df, session_reset=True)   # Structure
df['rsi'] = calculate_rsi(df, period=14)              # Momentum
df['ema_20'] = calculate_ema(df, period=20)           # Trend
df['dxy_correlation'] = calculate_dxy_correlation(gc_df, dxy_df, window=50)  # Environment

# SOP-aligned signal: Structure + Trend + Momentum + Environment
df['long_setup'] = (
    (df['close'] > df['vwap']) &      # Above VWAP (structure)
    (df['close'] > df['ema_20']) &    # Above EMA (trend)
    (df['rsi'] > 30) & (df['rsi'] < 70) &  # RSI healthy (momentum)
    (df['dxy_correlation'] < -0.6)    # Strong negative correlation (environment)
)
```

See [Feature Engine Guide](./docs/feature-engine/README.md) for complete API documentation and examples.

## Documentation

Comprehensive documentation is available in the [`docs/`](./docs/) directory:

- [Project Overview](./docs/01-project-overview.md) - Vision, architecture, and current status
- [Project Structure](./docs/02-project-structure.md) - Directory layout and module organization
- [Setup Guide](./docs/03-setup-guide.md) - Installation and development environment
- [Configuration](./docs/04-configuration.md) - Configuration files and parameters
- [Development Workflow](./docs/05-development-workflow.md) - TDD practices and coding standards
- [Testing](./docs/06-testing.md) - Test framework and conventions
- [Data Layer Guide](./docs/10-data-layer.md) - OHLCV data structures and clients
- [**Feature Engine**](./docs/feature-engine/README.md) - **Technical indicators** ⭐
  - [VWAP](./docs/feature-engine/vwap.md) - Volume-Weighted Average Price
  - [RSI](./docs/feature-engine/rsi.md) - Relative Strength Index
  - [EMA](./docs/feature-engine/ema.md) - Exponential Moving Average
  - [DXY Correlation](./docs/feature-engine/dxy-correlation.md) - Gold-Dollar correlation

## Development Principles

- **TDD First:** All features start with failing tests
- **Structure Before Signal:** Architecture before trading logic
- **100% Typed:** mypy strict mode enforced
- **Validated:** ≥99% correlation with industry benchmarks
- **Documented:** Every feature has comprehensive docs and examples

## Requirements

- Python 3.11+
- pandas, numpy
- pytest for testing
- Development tools: ruff, black, isort, mypy

## Phase Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Infrastructure, config, logging, data models |
| **Phase 2** | 🏗️ In Progress | Feature engine (VWAP ✅, RSI, EMA) & rule engine |
| **Phase 3** | 📋 Planned | Validation dashboard & indicator verification |
| **Phase 4** | 📋 Planned | LLM enforcer layer & SOP compliance |
| **Phase 5** | 📋 Planned | ML optimization & adaptive scoring |
| **Phase 6** | 📋 Planned | Production deployment & monitoring |

