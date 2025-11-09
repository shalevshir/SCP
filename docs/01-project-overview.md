# Project Overview

## Shir Capital Partners Trading Bot

**Version:** 0.1.0  
**Phase:** 1 - Infrastructure  
**Python Version:** 3.11+

## Mission

Build a disciplined, rule-based trading system that enforces Shir Capital's Standard Operating Procedures (SOP) through three intelligent layers:

1. **Rule-Based Core (Engine)** - Encodes SOP with structure-first logic
2. **LLM Enforcer (Cognitive Layer)** - Validates logic and enforces discipline
3. **ML Optimization Layer (Adaptive Intelligence)** - Learns from results to optimize

## Core Principles

- **Structure First:** No trade without confirmation
- **Transparency:** Every decision logged and auditable
- **Discipline Automation:** SOP enforcement before profit pursuit
- **Scalability:** Modular APIs for seamless upgrades

## Current Status (Phase 1)

Phase 1 establishes the technical backbone without any live indicators or trade logic:

- ✅ Repository structure initialized
- ✅ Module skeleton created (data_layer, feature_engine, rule_engine, backtester, common)
- ✅ Configuration system in place (YAML/JSON with env overrides)
- ✅ Logging wrapper with rotating file handlers
- ✅ Exception hierarchy with domain-specific errors
- ✅ Test framework configured (pytest, pytest-xdist, pytest-cov, Makefile)
- ✅ Development tooling set up (linting, type checking, formatting)
- ✅ Unified Candle data model with comprehensive validation
- ✅ Data client stubs (CMEGCClient for Gold Futures, DXYIndexClient for Dollar Index)
- ✅ TimeAligner stub for synchronizing GC and DXY data streams
- ✅ CI/CD pipeline with GitHub Actions (automated tests, linting, formatting checks)

**What's NOT included in Phase 1:**
- No external API calls
- No trading logic
- No live data ingestion
- No indicator calculations (stubs only)

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Core Language** | Python 3.11+ | Data + logic foundation |
| **Package Management** | Poetry | Dependency management |
| **Testing** | pytest | Test framework |
| **Linting** | ruff | Fast Python linter |
| **Formatting** | black, isort | Code style enforcement |
| **Type Checking** | mypy (strict) | Static type analysis |
| **Configuration** | YAML + pydantic | Parameter management |
| **Storage** | SQLite (planned) | Trade & result database |

## Development Philosophy

- **Test-Driven Development (TDD):** Red-Green-Refactor cycle
- **Type Safety:** Strict typing with mypy
- **Code Quality:** Automated linting and formatting
- **Documentation:** Executable specs and clear intent

## Next Steps

See [Project Structure](./02-project-structure.md) for detailed module organization and [Setup Guide](./03-setup-guide.md) to get started.

