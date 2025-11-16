# Shir Capital Partners — Trading Bot

**Structure before signal. Discipline before profit.**

A systematic trading bot built with Python, following strict TDD practices and institutional-grade architecture.

**Current Phase:** Phase 2 - Feature Engine & Rule Engine  
**Status:** Feature Engine Complete ✅ (VWAP, RSI, EMA, DXY Correlation, Aggregator)

## Key Features

- ✅ **Feature Engine** - Complete SOP indicator suite (VWAP, RSI, EMA, DXY correlation, unified aggregator)
- 🏗️ Rule Engine - Next phase (SOP scoring and signal generation)
- 📊 Clean architecture with typed modules
- ✅ Comprehensive test coverage (220+ tests, all passing)
- 🔧 Full development tooling: black, isort, ruff, mypy (strict)
- 📝 Extensive documentation

## Quickstart

```bash
# Install dependencies (choose one)
poetry install --no-root  # Using Poetry
# or
uv sync                   # Using uv

# Run tests
make test

# Run tests with coverage
make test-coverage

# Run all checks (lint + test)
make check

# See all available commands
make help
```

## Layout

- `src/scp/` — package code
- `tests/` — unit tests
- `config/core.yaml` — default configuration (Phase 1)
- `data/`, `logs/` — runtime folders (git-kept via .gitkeep)

## Module Map

- `/data_layer/`: Data connectors and normalization (Candle model, client stubs, TimeAligner)
- `/feature_engine/`: ✅ **VWAP, RSI, EMA, DXY Correlation, Aggregator** (all complete)
- `/rule_engine/`: SOP rule evaluation and scoring (stubs)
- `/backtester/`: Backtesting shell and integration (stubs)
- `/common/`: Shared utilities, types, logging, config, exceptions
- `/config/`: Configuration files (`core.yaml`, `dev.local.json`)
- `/data/`: Market data storage (GC/DXY OHLCV)
- `/tests/`: Comprehensive test suite (unit, integration, e2e)

## Quick Example: Feature Engine

```python
from feature_engine import aggregate_features
import pandas as pd

# Load OHLCV data
gc_df = pd.read_csv('data/gc_dx_ohlcv/GC_ohlcv-1m.csv', parse_dates=['ts_event'])
dxy_df = pd.read_csv('data/gc_dx_ohlcv/DX_ohlcv-1m.csv', parse_dates=['ts_event'])

# Aggregate all SOP indicators with one call
features = aggregate_features(gc_df, dxy_df, timeframe="1m")

# Output includes: vwap, rsi, ema_9, ema_20, ema_50, dxy_corr
print(features.columns)
# Index(['ts_event', 'open', 'high', 'low', 'close', 'volume',
#        'vwap', 'rsi', 'ema_9', 'ema_20', 'ema_50', 'dxy_corr'])

# SOP-aligned long setup (8+/10 score)
long_setup = (
    (features['close'] > features['vwap']) &              # Structure ✓
    (features['close'] > features['ema_20']) &            # Trend ✓
    (features['ema_9'] > features['ema_20']) &            # Trend ✓
    (features['rsi'] > 30) & (features['rsi'] < 70) &     # Momentum ✓
    (features['dxy_corr'] < -0.6)                         # Environment ✓
)

high_quality_signals = features[long_setup]
print(f"Found {len(high_quality_signals)} high-quality setups (8+/10)")
```

**Modular Configuration:**

```python
# Skip DXY, use custom RSI period
indicators = {
    "vwap": True,
    "rsi": {"period": 21},
    "ema": True,
    "dxy_correlation": False
}
features = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)
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
  - [Aggregator](./docs/feature-engine/aggregator.md) - Unified interface for all indicators
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

