# Force use of bash for all recipes (required for db-reset and other advanced shell features)
SHELL := /bin/bash

.PHONY: test test-unit test-verbose test-parallel test-coverage test-fast lint format check clean help install data-clean data-fetch data-resample data-resample-5m data-resample-1h infra-up infra-down infra-logs infra-ps db-migrate db-reset db-shell shared-install shared-test

help:
	@echo "SCP Trading Bot - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install           Install all dependencies (including dev)"
	@echo "  make shared-install    Install shared library in editable mode"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make infra-up          Start Redis + PostgreSQL/TimescaleDB"
	@echo "  make infra-down        Stop infrastructure containers"
	@echo "  make infra-logs        View infrastructure logs"
	@echo "  make infra-ps          Show running containers"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate        Apply database migrations"
	@echo "  make db-reset          Drop and recreate database"
	@echo "  make db-shell          Open PostgreSQL shell"
	@echo ""
	@echo "Testing:"
	@echo "  make test              Run all tests"
	@echo "  make test-unit         Run unit tests only"
	@echo "  make test-verbose      Run tests with verbose output"
	@echo "  make test-parallel     Run tests in parallel"
	@echo "  make test-coverage     Run tests with coverage report"
	@echo "  make test-fast         Run tests in parallel with minimal output"
	@echo "  make shared-test       Run shared library tests"
	@echo ""
	@echo "Data Management:"
	@echo "  make data-clean        Clean and deduplicate CSV data (remove spreads, select highest volume)"
	@echo "  make data-fetch        Fetch historical data from Databento (requires API key)"
	@echo "  make data-resample     Resample 1m data to 15m bars"
	@echo "  make data-resample-5m  Resample 1m data to 5m bars"
	@echo "  make data-resample-1h  Resample 1m data to 1h bars"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint              Run linters (ruff, mypy)"
	@echo "  make format            Run code formatters (black, isort)"
	@echo "  make check             Run all checks (lint + test)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean             Remove test artifacts and caches"

install:
	poetry install

test:
	poetry run pytest

test-unit:
	poetry run pytest tests/unit/

test-verbose:
	poetry run pytest -vv

test-parallel:
	poetry run pytest -n auto

test-coverage:
	poetry run pytest --cov=common --cov=data_layer --cov=src --cov=feature_engine --cov=backtester --cov=rule_engine --cov=validation --cov-report=html --cov-report=term

test-fast:
	poetry run pytest -n auto -q

lint:
	@echo "Running ruff..."
	poetry run ruff check .
	@echo "Running mypy..."
	poetry run mypy src/

format:
	@echo "Running black..."
	poetry run black .
	@echo "Running isort..."
	poetry run isort .

check: lint test

clean:
	@echo "Cleaning test artifacts..."
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."

data-clean:
	@echo "Cleaning and deduplicating CSV data..."
	./scripts/clean_all_csv_data.sh
	@echo "Data cleaning complete."

data-fetch:
	@echo "Fetching historical data from Databento..."
	@if [ -z "$$DATABENTO_API_KEY" ]; then \
		echo "Error: DATABENTO_API_KEY not set. Please export your API key."; \
		exit 1; \
	fi
	poetry run python scripts/fetch_gc_dx_ohlcv_to_csv.py
	@echo "Data fetch complete."

data-resample:
	@echo "Resampling 1m data to 15m bars..."
	poetry run python scripts/resample_ohlcv_to_15m.py
	@echo "Resampling complete."

data-resample-5m:
	@echo "Resampling 1m data to 5m bars..."
	poetry run python scripts/resample_ohlcv_to_5m.py
	@echo "Resampling complete."

data-resample-1h:
	@echo "Resampling 1m data to 1h bars..."
	poetry run python scripts/resample_ohlcv_to_1h.py
	@echo "Resampling complete."

backtest:
	@echo "Running backtest..."
	poetry run python scripts/run_backtest_and_view.py \
		--start $(START) --end $(END) \
		--buffer-phase $(PHASE) --tier-active $(TIER) \
		--view

backtest-view:
	@echo "Loading backtest results..."
	poetry run python scripts/run_backtest_and_view.py \
		--load $(RESULTS_FILE) --view

# ============================================================================
# Infrastructure Commands
# ============================================================================

infra-up:
	@echo "Starting infrastructure (Redis + PostgreSQL/TimescaleDB)..."
	docker compose -f infra/docker-compose.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 3
	@echo "✓ Infrastructure is running"
	@echo "  Redis: localhost:6379"
	@echo "  PostgreSQL: localhost:5432"

infra-down:
	@echo "Stopping infrastructure..."
	docker compose -f infra/docker-compose.yml down
	@echo "✓ Infrastructure stopped"

infra-logs:
	@echo "Tailing infrastructure logs (Ctrl+C to stop)..."
	docker compose -f infra/docker-compose.yml logs -f

infra-ps:
	@echo "Running infrastructure containers:"
	docker compose -f infra/docker-compose.yml ps

# ============================================================================
# Database Commands
# ============================================================================

db-migrate:
	@echo "Applying database migrations..."
	@if ! docker ps | grep -q scp-postgres; then \
		echo "Error: PostgreSQL container not running. Run 'make infra-up' first."; \
		exit 1; \
	fi
	@echo "Migrations are auto-applied on first startup via docker-entrypoint-initdb.d"
	@echo "For manual migration, use:"
	@echo "  psql -h localhost -U scp -d scp -f infra/migrations/001_initial_schema.sql"
	@echo "  psql -h localhost -U scp -d scp -f infra/migrations/002_indexes.sql"

db-reset:
	@echo "Resetting database..."
	@echo "Warning: This will destroy all data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose -f infra/docker-compose.yml down -v; \
		docker compose -f infra/docker-compose.yml up -d; \
		echo "✓ Database reset complete"; \
	else \
		echo "Cancelled"; \
	fi

db-shell:
	@echo "Opening PostgreSQL shell..."
	@docker exec -it scp-postgres psql -U scp -d scp

# ============================================================================
# Shared Library Commands
# ============================================================================

shared-install:
	@echo "Installing shared library..."
	cd services/shared && poetry install
	@echo "✓ Shared library installed"

shared-test:
	@echo "Running shared library tests..."
	cd services/shared && poetry run pytest -v
	@echo "✓ Shared library tests passed"
