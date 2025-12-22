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
        description="PostgreSQL connection URL"
    )
    
    # Session configuration
    session_config_path: str = Field(
        default="./config/validation.yaml",
        description="Path to validation config file"
    )
    
    # Bias cache configuration
    bias_cache_ttl_seconds: int = Field(
        default=300,
        description="TTL for HTF bias cache in seconds (default: 300 = 5 minutes)"
    )
    
    # State persistence
    state_persist_interval: int = Field(
        default=5,
        description="Persist state every N trades (default: 5)"
    )
    
    # Enforcer tier
    enforcer_tier: str = Field(
        default="Conservative",
        description="Active enforcer tier (Conservative, Early Mild, Mild, Offensive)"
    )
