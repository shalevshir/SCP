"""Configuration loading system with YAML/JSON support and environment variable overrides."""

import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class SystemConfig(BaseModel):
    """System configuration settings."""

    data_path: str = Field(default="./data/", description="Base folder for market data")
    log_path: str = Field(default="./logs/", description="Location for runtime logs")
    db_path: str = Field(
        default="sqlite:///db/core.db", description="Database connection string"
    )
    timezone: str = Field(default="UTC", description="Default timezone")
    timeframes: list[str] = Field(
        default=["1m", "5m", "15m"], description="Active time resolutions"
    )


class AssetsConfig(BaseModel):
    """Assets and market data configuration."""

    symbols: list[str] = Field(
        default=["GC", "DXY"], description="Tracked instruments"
    )
    broker: str = Field(default="SIMULATION", description="Broker/API source")
    start_date: str = Field(default="2022-01-01", description="Back-test start date")
    end_date: str = Field(default="2025-12-31", description="Back-test end date")


class GovernanceTier(BaseModel):
    """Governance tier configuration."""

    name: str
    max_contracts: int = Field(ge=1, description="Maximum contracts per trade")
    max_trades_per_day: int = Field(ge=1, description="Maximum trades per day")
    mode: str


class GovernanceConfig(BaseModel):
    """Governance and enforcer tier configuration."""

    tiers: list[GovernanceTier]


class RiskConfig(BaseModel):
    """Risk management configuration."""

    phases: list[str] = Field(
        default=["Startup", "Growth", "Scaling", "Institutional"],
        description="Risk phases",
    )
    startup_risk_per_trade: float = Field(
        default=350.0, ge=0, description="Startup phase risk per trade (USD)"
    )
    growth_risk_per_trade: float = Field(
        default=600.0, ge=0, description="Growth phase risk per trade (USD)"
    )
    daily_drawdown_limit: float = Field(
        default=600.0, ge=0, description="Daily drawdown limit (USD)"
    )
    rr_target: float = Field(
        default=3.0, ge=0, description="Target Risk:Reward ratio"
    )


class BacktestConfig(BaseModel):
    """Backtesting configuration."""

    initial_balance: float = Field(
        default=100000.0, ge=0, description="Starting equity for simulation"
    )
    commission_per_trade: float = Field(
        default=5.0, ge=0, description="Commission per trade (USD)"
    )
    slippage_points: float = Field(
        default=0.5, ge=0, description="Slippage in price points"
    )
    mock_strategy: bool = Field(
        default=True, description="Use mock strategy (Phase 1)"
    )


class Config(BaseModel):
    """Main configuration model."""

    system: SystemConfig = Field(default_factory=SystemConfig)
    assets: AssetsConfig = Field(default_factory=AssetsConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)

    @field_validator("assets")
    @classmethod
    def validate_symbols_not_empty(cls, v: AssetsConfig) -> AssetsConfig:
        """Ensure at least one symbol is configured."""
        if not v.symbols:
            raise ValueError("At least one symbol must be configured")
        return v

    @field_validator("governance")
    @classmethod
    def validate_tiers_not_empty(cls, v: GovernanceConfig) -> GovernanceConfig:
        """Ensure at least one governance tier is configured."""
        if not v.tiers:
            raise ValueError("At least one governance tier must be configured")
        return v


def _load_file(path: Path) -> dict[str, Any]:
    """Load configuration from YAML or JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open() as f:
        if path.suffix in (".yaml", ".yml"):
            return yaml.safe_load(f) or {}
        elif path.suffix == ".json":
            return json.load(f)
        else:
            raise ValueError(
                f"Unsupported configuration file format: {path.suffix}. "
                "Use .yaml, .yml, or .json"
            )


def _apply_env_overrides(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to configuration.

    Environment variables should be prefixed with 'SCP_' and use double
    underscores to represent nested keys. For example:
    - SCP_SYSTEM__DATA_PATH overrides config['system']['data_path']
    - SCP_RISK__RR_TARGET overrides config['risk']['rr_target']
    """
    prefix = "SCP_"
    result = config_dict.copy()

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        # Remove prefix and split by double underscore
        config_key = key[len(prefix) :].lower()
        parts = config_key.split("__")

        # Navigate/create nested structure
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Set the value (convert string to appropriate type)
        final_key = parts[-1]
        current[final_key] = _parse_env_value(value)

    return result


def _parse_env_value(value: str) -> Any:
    """Parse environment variable string to appropriate Python type."""
    # Try boolean
    if value.lower() in ("true", "1", "yes", "on"):
        return True
    if value.lower() in ("false", "0", "no", "off"):
        return False

    # Try integer
    try:
        if "." not in value:
            return int(value)
    except ValueError:
        pass

    # Try float
    try:
        return float(value)
    except ValueError:
        pass

    # Try JSON list
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

    # Return as string
    return value


def load_config(config_path: Path | str) -> Config:
    """Load configuration from file with environment variable overrides.

    Args:
        config_path: Path to YAML or JSON configuration file

    Returns:
        Validated Config object

    Raises:
        FileNotFoundError: If configuration file doesn't exist
        ValueError: If configuration is invalid
        pydantic.ValidationError: If configuration doesn't match schema
    """
    path = Path(config_path)

    # Load base configuration
    config_dict = _load_file(path)

    # Apply environment variable overrides
    config_dict = _apply_env_overrides(config_dict)

    # Validate and return
    return Config.model_validate(config_dict)

