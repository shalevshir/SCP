# Documentation Index

This directory contains documentation for the Shir Capital Partners Trading Bot project.

## Documents

- [Project Overview](./01-project-overview.md) - High-level project vision and architecture
- [Project Structure](./02-project-structure.md) - Directory layout and module organization
- [Setup Guide](./03-setup-guide.md) - Installation and development environment setup
- [Configuration](./04-configuration.md) - Configuration files and parameters
- [Development Workflow](./05-development-workflow.md) - TDD practices and coding standards
- [Testing](./06-testing.md) - Test framework and conventions
- [Running Tests](./07-running-tests.md) - Test execution and CI/CD
- [Logging Guide](./08-logging.md) - Logging system setup and best practices
- [Error Handling Guide](./09-error-handling.md) - Exception hierarchy and error handling patterns
- [Data Layer Guide](./10-data-layer.md) - Candle data model and client stubs
- [**Feature Engine**](./feature-engine/README.md) - Technical indicators and features
  - [VWAP](./feature-engine/vwap.md) - Volume-Weighted Average Price
  - [RSI](./feature-engine/rsi.md) - Relative Strength Index
  - [EMA](./feature-engine/ema.md) - Exponential Moving Average

## Phase 1 Status

**Current Phase:** Feature Engine & Rule Engine (Phase 2)  
**Status:** In Progress  
**Last Updated:** 2025-11-16

### Completed
- ✅ Repository structure and tooling
- ✅ Configuration system (YAML/JSON with env overrides)
- ✅ Logging wrapper with rotating file handlers
- ✅ Exception hierarchy with domain-specific errors
- ✅ Test framework (pytest with coverage, Makefile automation)
- ✅ Unified Candle data model with validation
- ✅ Data client stubs (CMEGCClient, DXYIndexClient, LocalCSVClient)
- ✅ TimeAligner stub for data stream synchronization
- ✅ CI/CD pipeline with GitHub Actions (tests, linting, formatting)
- ✅ PR automation: coverage reports and test results posted as comments
- ✅ **VWAP Implementation** - First production feature (Phase 2)

### In Progress
- Additional data layer components (DataNormalizer)
- Feature engine: RSI, EMA, DXY correlation indicators
- Rule engine stubs

Phase 1 focuses on establishing the foundational structure without any trading logic or external I/O. All components are placeholders/stubs that will be implemented in subsequent phases.

