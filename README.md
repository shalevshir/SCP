# Shir Capital Partners — Trading Bot (Phase 1: Infrastructure)

Structure before signal. This repository initializes the Python skeleton for Phase 1:

- src/ layout with typed modules
- Tests via pytest
- Tooling: black, isort, ruff, mypy (strict), Poetry
- Config under `config/`

## Quickstart

```bash
# (Optional) using uv or poetry; choose your preferred toolchain
# poetry install --no-root
# or with uv
# uv sync

# run tests
pytest -q
```

## Layout

- `src/scp/` — package code
- `tests/` — unit tests
- `config/core.yaml` — default configuration (Phase 1)
- `data/`, `logs/` — runtime folders (git-kept via .gitkeep)

## Module map (skeleton)

- `/data-layer/`: Data connectors/loaders (stubs only in Phase 1)
- `/feature-engine/`: Indicator and feature computations (stubs)
- `/rule-engine/`: SOP rule evaluation and scoring (stubs)
- `/backtester/`: Backtesting shell and integration (stubs)
- `/common/`: Shared utilities, types, constants
- `/config/`: Static configuration files (e.g., `core.yaml`)

## Documentation

Comprehensive documentation is available in the [`docs/`](./docs/) directory:

- [Project Overview](./docs/01-project-overview.md) - Vision, architecture, and current status
- [Project Structure](./docs/02-project-structure.md) - Directory layout and module organization
- [Setup Guide](./docs/03-setup-guide.md) - Installation and development environment
- [Configuration](./docs/04-configuration.md) - Configuration files and parameters
- [Development Workflow](./docs/05-development-workflow.md) - TDD practices and coding standards
- [Testing](./docs/06-testing.md) - Test framework and conventions

## Notes

- Python 3.11+
- No external I/O or trading logic in Phase 1
- All behavior added via TDD

