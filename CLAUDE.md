# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/claude-code) when working with this codebase.

## Project Overview

**Shir Capital Partners (SCP) Trading Bot** - A systematic, institutional-grade automated trading bot for Gold (GC) and US Dollar Index (DXY) futures with strict risk management and structured technical analysis.

**Philosophy:** "Structure before signal. Discipline before profit. Legacy above all."

**Status:** Phase 7/10 - Integration Testing. Core services (data-adapter, feature-engine, htf-bias, bot-core, execution) are operational and tested.

## Tech Stack

- **Language:** Python 3.11+ with strict typing (mypy strict mode)
- **Data:** Databento (real-time), pandas, NumPy
- **Messaging:** Redis Streams (pub/sub between services)
- **Database:** PostgreSQL + TimescaleDB
- **API:** FastAPI, Uvicorn
- **Testing:** pytest, pytest-asyncio, pytest-xdist, pytest-cov
- **Quality:** ruff, black, isort, mypy, pyright
- **Package Manager:** Poetry

## Project Structure

```
services/                    # Microservices architecture
├── shared/                  # Shared library (scp_shared) - indicators, messaging, database
├── data-adapter/            # Port 8001 - Market data ingestion
├── feature-engine/          # Port 8002 - Indicator computation
├── htf-bias/                # Port 8003 - Higher-timeframe analysis
├── bot-core/                # Port 8004 - Signal generation
└── execution/               # Port 8005 - Trade lifecycle
common/                      # Legacy Phase 1 utilities
data_layer/                  # Data normalization layer
config/                      # YAML configuration files
infra/                       # Docker, migrations, monitoring
docs/                        # Technical documentation
tests/                       # Integrated test suite (unit, integration, e2e)
```

## Common Commands

### Setup
```bash
poetry install               # Install dependencies
make shared-install          # Install shared library (editable mode)
```

### Testing
```bash
make test                    # Run all tests
make test-unit               # Unit tests only
make test-parallel           # Parallel execution
make test-coverage           # Coverage report
make shared-test             # Test shared library only
```

### Linting & Formatting
```bash
make lint                    # Run ruff + mypy
make format                  # Run black + isort
make check                   # lint + test combined
```

### Infrastructure
```bash
make infra-up                # Start Redis + PostgreSQL
make infra-down              # Stop infrastructure
make db-migrate              # Apply database migrations
```

### Services
```bash
make services-build          # Build all service images
make services-up             # Start all services
make services-down           # Stop all services
```

## Code Conventions

### Naming
- **Modules:** snake_case (`signal_engine.py`)
- **Classes:** PascalCase (`StreamingFeatureProcessor`)
- **Functions:** snake_case (`calculate_vwap()`)
- **Constants:** UPPER_SNAKE_CASE
- **Service packages:** snake_case with `_svc` suffix (`bot_core_svc`)

### Type Hints (Mandatory)
- Use `|` for unions: `str | None` not `Optional[str]`
- Use modern syntax: `list[Type]` not `List[Type]`
- All functions require full type annotations

### Docstrings
- Google-style docstrings for public functions/classes
- Sections: Args, Returns, Raises, Example, Notes

### Data Models
- Frozen dataclasses for immutable domain objects (e.g., `Candle`)
- Pydantic v2 schemas for message types

## Architecture Patterns

### Microservices Flow
```
Data Adapter → candles.1m.{gc,dxy}
    ↓
Feature Engine → features.1m/15m/1h
    ↓
HTF Bias + Bot Core → signals.pending (A+ only, 8+/10 score)
    ↓
Execution → trades.{opened,closed}
```

### Key Abstractions

**Indicators (`scp_shared/indicators/`):**
- `calculate_vwap()` - Volume-weighted average price with session reset
- `calculate_rsi()` - RSI with Wilder's smoothing
- `calculate_ema()` - Exponential Moving Average
- `StructureContextTracker` - HH/HL/LH/LL labels, BOS, CHoCH detection
- `StreamingFeatureProcessor` - Real-time incremental computation

**Rule Engine (`scp_shared/rule_engine/`):**
- `score_signal()` - Scores trades (A+ threshold: 8+/10)
- Setup types: `VWAP_RECLAIM`, `VWAP_FADE`, `DXY_CONTINUATION`

**Execution (`scp_shared/execution/`):**
- `VWAPReclaimStateMachine` - Trade lifecycle states
- `InvalidationChecker` - PDLL, structure break detection

## Testing Guidelines

- TDD-first approach: all features start with failing tests
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- Use `fakeredis` for mocked Redis in tests
- Coverage targets: aim for 70%+ on shared library

## Commit Style

Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `style:`

## Important Notes

- VWAP resets at 08:20 AM ET (RTH open for Gold futures)
- Signal scoring requires minimum 8/10 confidence (A+ threshold)
- Per-trade risk: $350-$1.2K+ depending on capital phase
- Target R:R: 3:1
