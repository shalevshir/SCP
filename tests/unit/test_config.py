"""Tests for configuration loading system."""

import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from common.config import Config, load_config


def test_load_config_from_yaml():
    """Test loading configuration from YAML file."""
    config_path = Path(__file__).parent.parent.parent / "config" / "core.yaml"
    config = load_config(config_path)
    
    assert isinstance(config, Config)
    assert config.system.data_path == "./data/"
    assert config.system.timezone == "UTC"
    assert "1m" in config.system.timeframes
    assert "GC" in config.assets.symbols
    assert config.risk.rr_target == 3.0


def test_config_env_override():
    """Test environment variable overrides configuration."""
    config_path = Path(__file__).parent.parent.parent / "config" / "core.yaml"
    
    # Set environment variable
    os.environ["SCP_SYSTEM__DATA_PATH"] = "/custom/data/path"
    os.environ["SCP_SYSTEM__TIMEZONE"] = "America/New_York"
    
    try:
        config = load_config(config_path)
        assert config.system.data_path == "/custom/data/path"
        assert config.system.timezone == "America/New_York"
    finally:
        # Cleanup
        os.environ.pop("SCP_SYSTEM__DATA_PATH", None)
        os.environ.pop("SCP_SYSTEM__TIMEZONE", None)


def test_load_config_from_json():
    """Test loading configuration from JSON file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json_content = """{
            "system": {
                "data_path": "./test_data/",
                "log_path": "./test_logs/",
                "db_path": "sqlite:///test.db",
                "timezone": "UTC",
                "timeframes": ["1m", "5m"]
            },
            "assets": {
                "symbols": ["GC"],
                "broker": "TEST",
                "start_date": "2023-01-01",
                "end_date": "2024-12-31"
            },
            "risk": {
                "phases": ["Startup"],
                "startup_risk_per_trade": 100,
                "growth_risk_per_trade": 200,
                "daily_drawdown_limit": 300,
                "rr_target": 2.0
            },
            "governance": {
                "tiers": [
                    {
                        "name": "Conservative",
                        "max_contracts": 1,
                        "max_trades_per_day": 2,
                        "mode": "Baseline"
                    }
                ]
            },
            "backtest": {
                "initial_balance": 50000,
                "commission_per_trade": 2,
                "slippage_points": 0.1,
                "mock_strategy": true
            }
        }"""
        f.write(json_content)
        json_path = Path(f.name)
    
    try:
        config = load_config(json_path)
        assert config.system.data_path == "./test_data/"
        assert config.assets.symbols == ["GC"]
        assert config.risk.rr_target == 2.0
    finally:
        json_path.unlink()


def test_config_validation():
    """Test that invalid configuration raises validation error."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml_content = """
system:
  data_path: "./data/"
  log_path: "./logs/"
  db_path: "sqlite:///db/core.db"
  timezone: "UTC"
  timeframes: ["1m"]
assets:
  symbols: []
  broker: "SIMULATION"
  start_date: "2022-01-01"
  end_date: "2025-12-31"
risk:
  phases: []
  startup_risk_per_trade: -100
  growth_risk_per_trade: 600
  daily_drawdown_limit: 600
  rr_target: 3.0
governance:
  tiers: []
backtest:
  initial_balance: 100000
  commission_per_trade: 5
  slippage_points: 0.5
  mock_strategy: true
"""
        f.write(yaml_content)
        yaml_path = Path(f.name)
    
    try:
        with pytest.raises(ValidationError):  # Should raise validation error
            load_config(yaml_path)
    finally:
        yaml_path.unlink()


def test_config_type_safety():
    """Test that config provides type-safe access."""
    config_path = Path(__file__).parent.parent.parent / "config" / "core.yaml"
    config = load_config(config_path)
    
    # Type-safe access
    assert isinstance(config.system.data_path, str)
    assert isinstance(config.system.timeframes, list)
    assert isinstance(config.risk.rr_target, float)
    assert isinstance(config.backtest.initial_balance, (int, float))  # Can be int or float

