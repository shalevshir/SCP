# Force use of bash for all recipes (required for db-reset and other advanced shell features)
SHELL := /bin/bash

.PHONY: test test-unit test-verbose test-parallel test-coverage test-fast lint format check clean help install data-clean data-fetch data-resample data-resample-5m data-resample-1h infra-up infra-down infra-logs infra-ps db-migrate db-reset db-shell shared-install shared-test service-test-coverage service-test-coverage-all services-up services-down services-build services-logs services-ps replay compare-results validate-replay replay-clean

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
	@echo "Microservices:"
	@echo "  make services-up       Start all microservices (builds if needed)"
	@echo "  make services-down     Stop all microservices"
	@echo "  make services-build    Build all microservice images"
	@echo "  make services-logs     View microservice logs"
	@echo "  make services-ps       Show running microservices"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate        Apply database migrations"
	@echo "  make db-reset          Drop and recreate database"
	@echo "  make db-shell          Open PostgreSQL shell"
	@echo ""
	@echo "Testing:"
	@echo "  make test                          Run all tests"
	@echo "  make test-unit                     Run unit tests only"
	@echo "  make test-verbose                  Run tests with verbose output"
	@echo "  make test-parallel                 Run tests in parallel"
	@echo "  make test-coverage                 Run tests with coverage report"
	@echo "  make test-fast                     Run tests in parallel with minimal output"
	@echo "  make shared-test                   Run shared library tests"
	@echo "  make service-test-coverage         Run coverage for a single service (SERVICE=name)"
	@echo "  make service-test-coverage-all     Run coverage for all services + combined report"
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
	@echo "Replay Mode & Validation:"
	@echo "  make replay START=... END=... [SPEED=120]  Run replay from CSV (default SPEED=120; SPEED=0 is turbo)"
	@echo "  make replay-databento START=... END=...    Run replay from Databento (requires API key)"
	@echo "  make validate-databento START=... END=...  Full validation with Databento data"
	@echo "  make test-databento-replay                 Test Databento replay (1 day sample)"
	@echo "  make compare-results BACKTEST=...          Compare backtest vs microservices"
	@echo "  make validate-replay START=... END=...     Full validation (CSV replay + compare)"
	@echo "  make replay-clean                          Clean replay artifacts"
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

service-test-coverage:
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE not specified."; \
		echo "Usage: make service-test-coverage SERVICE=<service-name>"; \
		echo "Available services: shared, bot-core, data-adapter, execution, feature-engine, htf-bias"; \
		exit 1; \
	fi
	@echo "Running coverage for service: $(SERVICE)"
	./scripts/test_coverage_service.sh $(SERVICE)

service-test-coverage-all:
	@echo "Running coverage for all services..."
	./scripts/test_coverage_all.sh
	@echo "✓ All service tests complete"
	@echo "View combined report at: coverage_reports/coverage_report.md"

# ============================================================================
# Microservices Commands
# ============================================================================

services-up:
	@echo "Starting all microservices..."
	docker compose -f infra/docker-compose.yml -f infra/docker-compose.services.yml up -d --build
	@echo "✓ All services are running"
	@echo "  Data Adapter:    http://localhost:8001/health"
	@echo "  Feature Engine:  http://localhost:8002/health"
	@echo "  HTF Bias:        http://localhost:8003/health"
	@echo "  Bot Core:        http://localhost:8004/health"
	@echo "  Execution:       http://localhost:8005/health"

services-down:
	@echo "Stopping all microservices..."
	docker compose -f infra/docker-compose.yml -f infra/docker-compose.services.yml down
	@echo "✓ All services stopped"

services-build:
	@echo "Building all microservice images..."
	docker compose -f infra/docker-compose.yml -f infra/docker-compose.services.yml build
	@echo "✓ All images built"

services-logs:
	@echo "Tailing microservice logs (Ctrl+C to stop)..."
	docker compose -f infra/docker-compose.yml -f infra/docker-compose.services.yml logs -f

services-ps:
	@echo "Running services:"
	docker compose -f infra/docker-compose.yml -f infra/docker-compose.services.yml ps

# ============================================================================
# Replay Mode & Validation Commands (Phase 8)
# ============================================================================

replay:
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: START and END required."; \
		echo "Usage: make replay START=2024-11-01 END=2024-11-30 [SPEED=120] (SPEED=0 is turbo)"; \
		exit 1; \
	fi
	@echo "Running replay validation..."
	@echo "  Date range: $(START) to $(END)"
	@if [ -z "$(SPEED)" ]; then \
		echo "  Speed: DEFAULT (120x)"; \
	elif [ "$(SPEED)" = "0" ]; then \
		echo "  Speed: TURBO (no delays, maximum speed)"; \
	else \
		echo "  Speed: $(SPEED)x"; \
	fi
	@echo ""
	@echo "Step 1/3: Running backtester..."
	poetry run python scripts/run_backtest_and_view.py \
		--start $(START) --end $(END) --no-view \
		--output-file output/backtest_validation_$(START)_$(END).json
	@echo ""

	@echo "Step 3/3: Replaying historical data..."
	@if [ -z "$(SPEED)" ]; then \
		poetry run python scripts/replay_historical.py \
			--start $(START) --end $(END) \
			--speed 120 \
			--processing-delay 10; \
	else \
		poetry run python scripts/replay_historical.py \
			--start $(START) --end $(END) \
			--speed $(SPEED) \
			--processing-delay 10; \
	fi
	@echo ""
	@echo "✓ Replay complete. Run 'make compare-results' to analyze."

compare-results:
	@if [ -z "$(BACKTEST)" ]; then \
		echo "Error: BACKTEST file required."; \
		echo "Usage: make compare-results BACKTEST=output/backtest_validation.json"; \
		exit 1; \
	fi
	@echo "Comparing results..."
	poetry run python scripts/compare_results.py \
		--backtest $(BACKTEST) \
		--database postgresql://scp:scp_dev_password@localhost:5432/scp \
		--output output/comparison_report_$(shell date +%Y%m%d_%H%M%S).json

validate-replay:
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: START and END required."; \
		echo "Usage: make validate-replay START=2024-11-01 END=2024-11-30"; \
		exit 1; \
	fi
	@echo "Running full validation workflow..."
	@$(MAKE) replay START=$(START) END=$(END) SPEED=0
	@echo ""
	@echo "Comparing results..."
	@$(MAKE) compare-results BACKTEST=output/backtest_validation_$(START)_$(END).json
	@echo ""
	@echo "✓ Validation complete!"

side-by-side:
	@if [ -z "$(DATE)" ] && ([ -z "$(START)" ] || [ -z "$(END)" ]); then \
		echo "Error: Either DATE or both START and END required."; \
		echo "Usage:"; \
		echo "  make side-by-side DATE=2024-11-06"; \
		echo "  make side-by-side START=2024-11-01 END=2024-11-30"; \
		exit 1; \
	fi
	@echo "Running side-by-side parity comparison..."
	@if [ -n "$(DATE)" ]; then \
		poetry run python scripts/side_by_side_replay.py \
			--date $(DATE) \
			$(if $(STOP_ON_FIRST),--stop-on-first,) \
			$(if $(OUTPUT),--output $(OUTPUT),); \
	else \
		poetry run python scripts/side_by_side_replay.py \
			--start $(START) --end $(END) \
			$(if $(STOP_ON_FIRST),--stop-on-first,) \
			$(if $(OUTPUT),--output $(OUTPUT),); \
	fi

replay-databento:
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: START and END required."; \
		echo "Usage: make replay-databento START=2024-11-05 END=2024-11-12 [SPEED=10]"; \
		exit 1; \
	fi
	@if [ -z "$$DATABENTO_API_KEY" ]; then \
		echo "Error: DATABENTO_API_KEY not set. Please export your API key."; \
		echo "  export DATABENTO_API_KEY='db-your-key'"; \
		exit 1; \
	fi
	@echo "Running Databento historical replay..."
	@echo "  Date range: $(START) to $(END)"
	@if [ -z "$(SPEED)" ]; then \
		echo "  Speed: 10x (default)"; \
		poetry run python scripts/replay_databento_historical.py \
			--start $(START) --end $(END) \
			--api-key "$$DATABENTO_API_KEY" \
			--speed 10.0 \
			--processing-delay 10.0; \
	else \
		echo "  Speed: $(SPEED)x"; \
		poetry run python scripts/replay_databento_historical.py \
			--start $(START) --end $(END) \
			--api-key "$$DATABENTO_API_KEY" \
			--speed $(SPEED) \
			--processing-delay 10.0; \
	fi
	@echo "✓ Databento replay complete"

test-databento-replay:
	@if [ -z "$$DATABENTO_API_KEY" ]; then \
		echo "Error: DATABENTO_API_KEY not set. Please export your API key."; \
		echo "  export DATABENTO_API_KEY='db-your-key'"; \
		exit 1; \
	fi
	@echo "Running Databento replay test..."
	./scripts/test_databento_replay.sh

validate-databento:
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: START and END required."; \
		echo "Usage: make validate-databento START=2024-11-05 END=2024-11-12"; \
		exit 1; \
	fi
	@if [ -z "$$DATABENTO_API_KEY" ]; then \
		echo "Error: DATABENTO_API_KEY not set. Please export your API key."; \
		echo "  export DATABENTO_API_KEY='db-your-key'"; \
		exit 1; \
	fi
	@echo "Running full Databento validation..."
	poetry run python scripts/validate_databento_replay.py \
		--start $(START) --end $(END) \
		--api-key "$$DATABENTO_API_KEY" \
		--speed 0

replay-clean:
	@echo "Cleaning replay artifacts..."
	@echo "Warning: This will clear Redis streams and database trades!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "Stopping services..."; \
		docker compose -f infra/docker-compose.yml -f infra/docker-compose.services.yml down; \
		echo "Starting infrastructure..."; \
		docker compose -f infra/docker-compose.yml up -d; \
		sleep 5; \
		echo "Cleaning Redis streams..."; \
		docker exec scp-redis redis-cli FLUSHDB; \
		echo "Cleaning database tables..."; \
		docker exec scp-postgres psql -U scp -d scp -c "TRUNCATE TABLE trades CASCADE"; \
		docker exec scp-postgres psql -U scp -d scp -c "TRUNCATE TABLE state_machine_snapshots CASCADE"; \
		docker exec scp-postgres psql -U scp -d scp -c "TRUNCATE TABLE daily_state CASCADE"; \
		docker exec scp-postgres psql -U scp -d scp -c "TRUNCATE TABLE features CASCADE"; \
		docker exec scp-postgres psql -U scp -d scp -c "TRUNCATE TABLE htf_bias_history CASCADE"; \
		echo "✓ Replay environment cleaned and reset"; \
	else \
		echo "Cancelled"; \
	fi
