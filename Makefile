# Force use of bash for all recipes (required for db-reset and other advanced shell features)
SHELL := /bin/bash

.PHONY: test test-unit test-verbose test-parallel test-coverage test-fast lint format check clean system-clean system-clean-yes system-clean-db system-clean-redis help install data-clean data-fetch data-resample data-resample-5m data-resample-1h infra-up infra-down infra-logs infra-ps db-migrate db-reset db-shell shared-install shared-test service-test-coverage service-test-coverage-all services-up services-down services-build services-logs services-ps paper-trading-up paper-trading-down paper-trading-logs live-trading-up live-trading-down live-trading-logs replay replay-validate compare-results validate-replay replay-clean eda-vwap

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
	@echo "  make services-up        Start all microservices (development mode)"
	@echo "  make services-down      Stop all microservices"
	@echo "  make services-build     Build all microservice images"
	@echo "  make services-logs      View microservice logs"
	@echo "  make services-ps        Show running microservices"
	@echo ""
	@echo "Paper Trading (IB Paper):"
	@echo "  make paper-trading-up   Start paper trading with IB Gateway"
	@echo "  make paper-trading-down Stop paper trading services"
	@echo "  make paper-trading-logs View paper trading logs"
	@echo "  (Requires: IB Gateway on port 4002)"
	@echo ""
	@echo "Live Trading (⚠️  REAL MONEY ⚠️):"
	@echo "  make live-trading-up    Start LIVE trading with real money"
	@echo "  make live-trading-down  Stop live trading services"
	@echo "  make live-trading-logs  View live trading logs"
	@echo "  (Requires: IB_ACCOUNT, POSTGRES_PASSWORD, IB Gateway on port 4001)"
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
	@echo "  make replay START=... END=... [SPEED=0]    Run replay from CSV (SPEED=0 is turbo, default)"
	@echo "  make replay-validate START=... END=...     Full validation (backtest + replay + compare)"
	@echo "  make replay-databento START=... END=...    Run replay from Databento (requires API key)"
	@echo "  make validate-databento START=... END=...  Full validation with Databento data"
	@echo "  make test-databento-replay                 Test Databento replay (1 day sample)"
	@echo "  make compare-results BACKTEST=...          Compare backtest vs microservices"
	@echo "  make validate-replay START=... END=...     Alias for replay-validate (deprecated)"
	@echo "  make replay-clean                          Clean replay artifacts"
	@echo ""
	@echo "Analysis & Reporting:"
	@echo "  make eda-vwap START=... END=...            Generate VWAP feature EDA report"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean             Remove test artifacts and caches"
	@echo "  make system-clean      Clean database and Redis (interactive)"
	@echo "  make system-clean-yes  Clean database and Redis (auto-confirm)"
	@echo "  make system-clean-db   Clean only database tables"
	@echo "  make system-clean-redis Clean only Redis streams"

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

# ============================================================================
# System Cleanup Commands (Database + Redis)
# ============================================================================

system-clean:
	@echo "🧹 Running system cleanup (database + Redis)..."
	poetry run python scripts/cleanup_system.py

system-clean-yes:
	@echo "🧹 Running system cleanup (auto-confirm)..."
	poetry run python scripts/cleanup_system.py --confirm

system-clean-db:
	@echo "🧹 Cleaning database only..."
	poetry run python scripts/cleanup_system.py --postgres-only

system-clean-redis:
	@echo "🧹 Cleaning Redis streams only..."
	poetry run python scripts/cleanup_system.py --redis-only

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
	docker compose -f infra/docker-compose.infra.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 3
	@echo "✓ Infrastructure is running"
	@echo "  Redis: localhost:6379"
	@echo "  PostgreSQL: localhost:5432"

infra-down:
	@echo "Stopping infrastructure..."
	docker compose -f infra/docker-compose.infra.yml down
	@echo "✓ Infrastructure stopped"

infra-logs:
	@echo "Tailing infrastructure logs (Ctrl+C to stop)..."
	docker compose -f infra/docker-compose.infra.yml logs -f

infra-ps:
	@echo "Running infrastructure containers:"
	docker compose -f infra/docker-compose.infra.yml ps

# ============================================================================
# Database Commands
# ============================================================================

db-migrate:
	@echo "Applying database migrations..."
	@if ! docker ps | grep -q scp-postgres; then \
		echo "Error: PostgreSQL container not running. Run 'make infra-up' first."; \
		exit 1; \
	fi
	@for f in infra/migrations/*.sql; do \
		echo "Applying $$f..."; \
		docker exec -i scp-postgres psql -U scp -d scp -f /docker-entrypoint-initdb.d/$$(basename $$f) 2>/dev/null || \
		docker exec -i scp-postgres psql -U scp -d scp < $$f; \
	done
	@echo "✓ Migrations complete"

db-reset:
	@echo "Resetting database..."
	@echo "Warning: This will destroy all data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose -f infra/docker-compose.infra.yml down -v; \
		docker compose -f infra/docker-compose.infra.yml up -d; \
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
	@echo "Starting all microservices (development mode)..."
	docker compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.dev.yml up -d --build
	@echo "✓ All services are running"
	@echo "  Data Adapter:    http://localhost:8001/health"
	@echo "  Feature Engine:  http://localhost:8002/health"
	@echo "  HTF Bias:        http://localhost:8003/health"
	@echo "  Bot Core:        http://localhost:8004/health"
	@echo "  Execution:       http://localhost:8005/health"

services-down:
	@echo "Stopping all microservices..."
	docker compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.dev.yml down
	@echo "✓ All services stopped"

services-build:
	@echo "Building all microservice images..."
	docker compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.dev.yml build
	@echo "✓ All images built"

services-logs:
	@echo "Tailing microservice logs (Ctrl+C to stop)..."
	docker compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.dev.yml logs -f

services-ps:
	@echo "Running services:"
	docker compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.dev.yml ps

# ============================================================================
# Paper Trading Commands
# ============================================================================

paper-trading-up:
	@echo "Starting paper trading with IB Gateway integration..."
	@echo "Ensure IB Gateway is running in paper trading mode on port 4002"
	@echo ""
	@echo "🚀 Starting paper trading services..."
	docker compose \
		-f infra/docker-compose.infra.yml \
		-f infra/docker-compose.services.yml \
		-f infra/docker-compose.paper.yml \
		up -d --build
	@echo ""
	@echo "✅ Paper trading services started!"
	@echo "   Data Adapter:   http://localhost:8001/health"
	@echo "   Feature Engine: http://localhost:8002/health"
	@echo "   HTF Bias:       http://localhost:8003/health"
	@echo "   Bot Core:       http://localhost:8004/health"
	@echo "   Execution:      http://localhost:8005/health"
	@echo ""
	@echo "📝 Monitor: make paper-trading-logs"
	@echo "🛑 Stop: make paper-trading-down"

paper-trading-down:
	@echo "Stopping paper trading services..."
	docker compose \
		-f infra/docker-compose.infra.yml \
		-f infra/docker-compose.services.yml \
		-f infra/docker-compose.paper.yml \
		down
	@echo "✅ Paper trading services stopped"

paper-trading-logs:
	@echo "Tailing paper trading logs (Ctrl+C to stop)..."
	docker compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.paper.yml logs -f

# ============================================================================
# Live Trading Commands (⚠️  REAL MONEY ⚠️)
# ============================================================================

live-trading-up:
	@echo "⚠️  WARNING: STARTING LIVE TRADING WITH REAL MONEY ⚠️"
	@echo ""
	@if [ -z "$$IB_ACCOUNT" ]; then \
		echo "❌ Error: IB_ACCOUNT not set"; \
		echo "   export IB_ACCOUNT='your-account-id'"; \
		exit 1; \
	fi
	@if [ -z "$$POSTGRES_PASSWORD" ]; then \
		echo "❌ Error: POSTGRES_PASSWORD not set"; \
		echo "   export POSTGRES_PASSWORD='strong-password'"; \
		exit 1; \
	fi
	@echo "✅ Required environment variables found"
	@echo ""
	@echo "⚠️  Final confirmation required!"
	@echo "   This will place REAL TRADES with REAL MONEY"
	@echo "   Ensure IB Gateway is running in LIVE mode on port 4001"
	@read -p "Are you absolutely sure? Type 'YES' to continue: " confirm; \
	if [ "$$confirm" != "YES" ]; then \
		echo "Cancelled"; \
		exit 1; \
	fi
	@echo ""
	@echo "🚀 Starting LIVE trading services..."
	docker compose \
		-f infra/docker-compose.infra.yml \
		-f infra/docker-compose.services.yml \
		-f infra/docker-compose.live.yml \
		up -d --build
	@echo ""
	@echo "✅ LIVE trading services started!"
	@echo "   ⚠️  REAL MONEY AT RISK ⚠️"
	@echo ""
	@echo "   Data Adapter:   http://localhost:8001/health"
	@echo "   Feature Engine: http://localhost:8002/health"
	@echo "   HTF Bias:       http://localhost:8003/health"
	@echo "   Bot Core:       http://localhost:8004/health"
	@echo "   Execution:      http://localhost:8005/health"
	@echo ""
	@echo "📝 Monitor: make live-trading-logs"
	@echo "🛑 Stop: make live-trading-down"

live-trading-down:
	@echo "Stopping LIVE trading services..."
	docker compose \
		-f infra/docker-compose.infra.yml \
		-f infra/docker-compose.services.yml \
		-f infra/docker-compose.live.yml \
		down
	@echo "✅ LIVE trading services stopped"

live-trading-logs:
	@echo "Tailing LIVE trading logs (Ctrl+C to stop)..."
	docker compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.live.yml logs -f

# ============================================================================
# Replay Mode & Validation Commands (Phase 8)
# ============================================================================

# Simple replay - just run historical data through the pipeline
replay:
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: START and END required."; \
		echo "Usage: make replay START=2024-11-01 END=2024-11-30 [SPEED=0] [DATA_DIR=...] [REDIS_URL=...] [NO_WARMUP=1]"; \
		echo ""; \
		echo "Options:"; \
		echo "  SPEED=0        Turbo mode (no delays, default)"; \
		echo "  SPEED=100      100x faster than real-time"; \
		echo "  SPEED=1        Real-time replay"; \
		echo "  DATA_DIR=...   Custom data directory (default: data/gc_dx_ohlcv)"; \
		echo "  REDIS_URL=...  Redis URL (default: redis://localhost:6379)"; \
		echo "  DELAY=...      Processing delay in seconds (default: 5.0)"; \
		echo "  NO_WARMUP=1    Skip warmup phase (cold start)"; \
		exit 1; \
	fi
	@echo "Running historical data replay..."
	@echo "  Date range: $(START) to $(END)"
	@if [ -z "$(SPEED)" ]; then \
		echo "  Speed: TURBO (no delays, maximum speed)"; \
	elif [ "$(SPEED)" = "0" ]; then \
		echo "  Speed: TURBO (no delays, maximum speed)"; \
	else \
		echo "  Speed: $(SPEED)x"; \
	fi
	@if [ -n "$(DATA_DIR)" ]; then \
		echo "  Data directory: $(DATA_DIR)"; \
	fi
	@echo ""
	@echo "Replaying through microservices pipeline..."
	@poetry run python scripts/replay_historical.py \
		--start $(START) --end $(END) \
		--speed $(if $(SPEED),$(SPEED),0) \
		$(if $(DATA_DIR),--data-dir $(DATA_DIR),) \
		$(if $(REDIS_URL),--redis-url $(REDIS_URL),) \
		--processing-delay $(if $(DELAY),$(DELAY),5.0) \
		$(if $(NO_WARMUP),--no-warmup,)
	@echo ""
	@echo "✓ Replay complete!"

# Full validation - run backtest + replay + comparison
replay-validate:
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: START and END required."; \
		echo "Usage: make replay-validate START=2024-11-01 END=2024-11-30 [SPEED=0]"; \
		exit 1; \
	fi
	@echo "Running full validation workflow (backtest + replay + compare)..."
	@echo "  Date range: $(START) to $(END)"
	@if [ -z "$(SPEED)" ]; then \
		echo "  Speed: TURBO (no delays, maximum speed)"; \
	elif [ "$(SPEED)" = "0" ]; then \
		echo "  Speed: TURBO (no delays, maximum speed)"; \
	else \
		echo "  Speed: $(SPEED)x"; \
	fi
	@echo ""
	@echo "Step 1/3: Running backtester..."
	@poetry run python scripts/run_backtest_and_view.py \
		--start $(START) --end $(END) --no-view \
		--output-file output/backtest_validation_$(START)_$(END).json
	@echo ""
	@echo "Step 2/3: Replaying historical data through microservices..."
	@$(MAKE) replay START=$(START) END=$(END) SPEED=$(if $(SPEED),$(SPEED),0)
	@echo ""
	@echo "Step 3/3: Comparing results..."
	@$(MAKE) compare-results BACKTEST=output/backtest_validation_$(START)_$(END).json
	@echo ""
	@echo "✓ Full validation complete!"

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

# Backwards compatibility alias
validate-replay:
	@echo "⚠️  Note: 'make validate-replay' is deprecated. Use 'make replay-validate' instead."
	@echo ""
	@$(MAKE) replay-validate START=$(START) END=$(END) SPEED=$(SPEED)

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
		docker compose -f infra/docker-compose.infra.yml -f infra/docker-compose.services.yml -f infra/docker-compose.dev.yml down; \
		echo "Starting infrastructure..."; \
		docker compose -f infra/docker-compose.infra.yml up -d; \
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

# =============================================================================
# VWAP_RECLAIM Diagnostics
# =============================================================================

diagnose-vwap-reclaim:
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Usage: make diagnose-vwap-reclaim START=2024-11-01 END=2024-11-05"; \
		exit 1; \
	fi
	@echo "Running VWAP_RECLAIM constraint failure analysis..."
	@echo "Period: $(START) to $(END)"
	@poetry run python scripts/diagnose_vwap_reclaim.py \
		--start "$(START)" \
		--end "$(END)" \
		--db-dsn "postgresql://scp:scp_dev_password@localhost:5432/scp"

# =============================================================================
# EDA: Exploratory Data Analysis
# =============================================================================

eda-vwap:
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: START and END required."; \
		echo "Usage: make eda-vwap START=2025-11-05 END=2025-11-10"; \
		exit 1; \
	fi
	@echo "Generating VWAP feature EDA report..."
	@mkdir -p reports
	@poetry run python scripts/eda/eda_vwap_features.py \
		--start $(START) \
		--end $(END) \
		--output reports/vwap_eda_$(START)_$(END).html \
		--detect-anomalies \
		--db-url "postgresql://scp:scp_dev_password@localhost:5432/scp"
	@echo "Report saved to: reports/vwap_eda_$(START)_$(END).html"
