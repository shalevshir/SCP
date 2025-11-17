.PHONY: test test-unit test-verbose test-parallel test-coverage test-fast lint format check clean help

help:
	@echo "SCP Trading Bot - Development Commands"
	@echo ""
	@echo "Testing:"
	@echo "  make test              Run all tests"
	@echo "  make test-unit         Run unit tests only"
	@echo "  make test-verbose      Run tests with verbose output"
	@echo "  make test-parallel     Run tests in parallel"
	@echo "  make test-coverage     Run tests with coverage report"
	@echo "  make test-fast         Run tests in parallel with minimal output"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint              Run linters (ruff, mypy)"
	@echo "  make format            Run code formatters (black, isort)"
	@echo "  make check             Run all checks (lint + test)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean             Remove test artifacts and caches"

test:
	pytest

test-unit:
	pytest tests/unit/

test-verbose:
	pytest -vv

test-parallel:
	pytest -n auto

test-coverage:
	pytest --cov=common --cov=data_layer --cov=src --cov=feature_engine --cov=backtester --cov=rule_engine --cov=validation --cov-report=html --cov-report=term

test-fast:
	pytest -n auto -q

lint:
	@echo "Running ruff..."
	ruff check .
	@echo "Running mypy..."
	mypy src/

format:
	@echo "Running black..."
	black .
	@echo "Running isort..."
	isort .

check: lint test

clean:
	@echo "Cleaning test artifacts..."
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."

