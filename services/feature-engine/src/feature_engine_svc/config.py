"""Configuration for Feature Engine service."""

from pydantic import Field

from scp_shared.config import BaseServiceConfig


class FeatureEngineConfig(BaseServiceConfig):
    """Feature Engine service configuration."""

    service_name: str = Field(default="feature-engine")
    service_version: str = Field(default="0.1.0")

    # Warmup settings
    warmup_candles: int = Field(
        default=60, description="Number of candles to load for warmup"
    )
    enable_warmup: bool = Field(default=True, description="Enable warmup from database")

    # Redis stream warmup settings
    warmup_use_redis_streams: bool = Field(
        default=True,
        description="Use Redis warmup streams if available (fallback to database)",
    )

    warmup_stream_timeout_seconds: int = Field(
        default=10,
        description="Timeout waiting for warmup streams before database fallback",
    )
