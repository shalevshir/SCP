"""Configuration for Bot Core service."""

from pydantic import Field

from scp_shared.config import BaseServiceConfig


class BotCoreConfig(BaseServiceConfig):
    """Bot Core service configuration."""

    service_name: str = Field(default="bot-core")
    service_version: str = Field(default="0.1.0")

    # Database configuration
    database_url: str = Field(
        default="postgresql://scp:scp@localhost:5432/scp",
        description="PostgreSQL connection URL",
    )

    # Session configuration
    session_config_path: str = Field(
        default="./config/validation.yaml", description="Path to validation config file"
    )

    # Bias cache configuration
    # HTF bias updates every 15 minutes at boundaries (e.g., 06:14, 06:29, 06:44, 06:59)
    # TTL must be >= 15 minutes (900s) so features between updates have valid bias
    # Using 1800s (30 min) to handle gaps and ensure coverage
    bias_cache_ttl_seconds: int = Field(
        default=1800,
        description="TTL for HTF bias cache in seconds (default: 1800 = 30 minutes)",
    )

    # State persistence
    state_persist_interval: int = Field(
        default=5, description="Persist state every N trades (default: 5)"
    )

    # Enforcer tier
    enforcer_tier: str = Field(
        default="Conservative",
        description="Active enforcer tier (Conservative, Early Mild, Mild, Offensive)",
    )

    # Warmup period
    warmup_bars: int = Field(
        default=60,
        description="Number of bars to skip before generating signals (warmup period)",
    )

    # Contract type for SL/TP scaling
    contract_type: str = Field(
        default="GC",
        description="Contract type: 'GC' (standard, $100/pt) or 'MGC' (micro, $10/pt, 10x wider SL/TP)",
    )
