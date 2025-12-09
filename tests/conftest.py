"""Shared pytest fixtures and configuration for all tests."""

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for tests.

    Args:
        tmp_path: pytest's built-in temporary directory fixture

    Returns:
        Path to temporary directory (cleaned up automatically)

    Example:
        >>> def test_file_creation(temp_dir):
        ...     test_file = temp_dir / "test.txt"
        ...     test_file.write_text("content")
        ...     assert test_file.exists()
    """
    return tmp_path


@pytest.fixture
def sample_config_dict() -> dict[str, Any]:
    """Provide a sample configuration dictionary.

    Returns:
        Dictionary with valid configuration structure

    Example:
        >>> def test_config_loading(sample_config_dict):
        ...     config = Config.model_validate(sample_config_dict)
        ...     assert config.system.log_level == "INFO"
    """
    return {
        "system": {
            "data_path": "./data/",
            "log_path": "./logs/",
            "log_level": "INFO",
            "db_path": "sqlite:///db/test.db",
            "timezone": "UTC",
            "timeframes": ["1m", "5m", "15m"],
        },
        "assets": {
            "symbols": ["GC", "DXY"],
            "broker": "SIMULATION",
            "start_date": "2022-01-01",
            "end_date": "2025-12-31",
        },
        "risk": {
            "phases": ["Startup", "Growth", "Scaling", "Institutional"],
            "startup_risk_per_trade": 350.0,
            "growth_risk_per_trade": 600.0,
            "daily_drawdown_limit": 600.0,
            "rr_target": 3.0,
        },
        "governance": {
            "tiers": [
                {
                    "name": "Conservative",
                    "max_contracts": 1,
                    "max_trades_per_day": 2,
                    "mode": "Baseline",
                }
            ]
        },
        "backtest": {
            "initial_balance": 100000.0,
            "commission_per_trade": 5.0,
            "slippage_points": 0.5,
            "mock_strategy": True,
        },
    }


@pytest.fixture
def sample_config_path(tmp_path: Path, sample_config_dict: dict[str, Any]) -> Path:
    """Provide a path to a temporary config file with sample data.

    Args:
        tmp_path: pytest's built-in temporary directory fixture
        sample_config_dict: Sample configuration dictionary

    Returns:
        Path to temporary YAML config file

    Example:
        >>> def test_load_from_file(sample_config_path):
        ...     config = load_config(sample_config_path)
        ...     assert config.system.data_path == "./data/"
    """
    import yaml

    config_file = tmp_path / "config.yaml"
    with config_file.open("w") as f:
        yaml.dump(sample_config_dict, f)

    return config_file


@pytest.fixture
def mock_logger(monkeypatch: pytest.MonkeyPatch):
    """Provide a mock logger that captures log calls.

    Args:
        monkeypatch: pytest's monkeypatch fixture

    Returns:
        Mock logger object with call tracking

    Example:
        >>> def test_logging(mock_logger):
        ...     logger = get_logger(__name__)
        ...     logger.info("test message")
        ...     # Verify log was called (implementation depends on mock setup)
    """
    from unittest.mock import Mock

    mock = Mock()
    # This is a basic mock - can be enhanced as needed
    return mock


# Configure pytest markers
def pytest_configure(config: pytest.Config) -> None:
    """Configure custom pytest markers.

    Args:
        config: pytest configuration object
    """
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
