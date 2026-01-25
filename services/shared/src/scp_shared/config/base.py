"""Base configuration class for all microservices."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceConfig(BaseSettings):
    """Base configuration for all SCP microservices.

    All service-specific configs should inherit from this.

    Example:
        >>> class DataAdapterConfig(BaseServiceConfig):
        ...     databento_api_key: str = Field(...)
        ...
        >>> config = DataAdapterConfig()
        >>> print(config.redis_url)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Redis configuration
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # Database configuration
    database_url: str = Field(
        default="postgresql://scp:scp_dev_password@localhost:5432/scp",
        description="PostgreSQL connection URL",
    )

    # Service metadata
    service_name: str = Field(
        default="scp-service",
        description="Service name for logging/metrics",
    )

    service_version: str = Field(
        default="0.1.0",
        description="Service version",
    )

    service_mode: str = Field(
        default="dev",
        description="Service mode for metrics: dev|test|replay|paper|live",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    # Development flags
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )
