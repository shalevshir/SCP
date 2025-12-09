.PHONY: test test-unit test-verbose test-parallel test-coverage test-fast lint format check clean help install data-clean data-fetch data-resample data-resample-1h

help:
	@echo "SCP Trading Bot - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install           Install all dependencies (including dev)"
	@echo ""
	@echo "Testing:"
	@echo "  make test              Run all tests"
	@echo "  make test-unit         Run unit tests only"
	@echo "  make test-verbose      Run tests with verbose output"
	@echo "  make test-parallel     Run tests in parallel"
	@echo "  make test-coverage     Run tests with coverage report"
	@echo "  make test-fast         Run tests in parallel with minimal output"
	@echo ""
	@echo "Data Management:"
	@echo "  make data-clean        Clean and deduplicate CSV data (remove spreads, select highest volume)"
	@echo "  make data-fetch        Fetch historical data from Databento (requires API key)"
	@echo "  make data-resample     Resample 1m data to 15m bars"
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
