"""Configuration for HTF Bias service."""

from pydantic import Field

from scp_shared.config import BaseServiceConfig


class HTFBiasConfig(BaseServiceConfig):
    """HTF Bias service configuration."""

    service_name: str = Field(default="htf-bias")
    service_version: str = Field(default="0.1.0")
    
    # Database configuration
    database_url: str = Field(
        default="postgresql://scp:scp@localhost:5432/scp",
        description="PostgreSQL connection URL"
    )
    
    # Warmup configuration
    enable_warmup: bool = Field(
        default=True,
        description="Enable warmup by loading recent candles from database"
    )
    warmup_candles: int = Field(
        default=1440,
        description="Number of 1m candles to load for warmup (1440 = 24 hours, needed for 1H structure detection)"
    )

