"""Configuration for Data Adapter service."""

from pydantic import Field
from scp_shared.config import BaseServiceConfig


class DataAdapterConfig(BaseServiceConfig):
    """Data Adapter service configuration."""

    service_name: str = Field(default="data-adapter")
    service_version: str = Field(default="0.1.0")

    # Data provider selection
    data_provider: str = Field(
        default="mock",
        description="Data provider: 'databento' or 'mock' (default: mock)",
    )

    # Databento configuration
    databento_api_key: str = Field(
        default="",
        description="Databento API key for live data",
    )

    databento_dataset: str = Field(
        default="GLBX.MDP3",
        description="Databento dataset identifier (CME futures)",
    )

    databento_gc_symbol: str = Field(
        default="GC.FUT",
        description="Databento symbol for Gold futures (continuous contract)",
    )

    databento_dxy_symbol: str = Field(
        default="DX.FUT",
        description="Databento symbol for Dollar Index (continuous contract)",
    )

    # Session filter configuration
    session_filter_enabled: bool = Field(
        default=True,
        description="Enable session hour filtering",
    )

    # Reconnection configuration
    reconnect_max_retries: int = Field(
        default=10,
        description="Maximum reconnection attempts (0 = infinite)",
    )

    reconnect_base_delay: float = Field(
        default=1.0,
        description="Base delay in seconds for exponential backoff",
    )

    reconnect_max_delay: float = Field(
        default=60.0,
        description="Maximum delay between reconnection attempts",
    )

    # Gap detection configuration
    gap_backfill_enabled: bool = Field(
        default=True,
        description="Enable automatic gap backfill from historical data",
    )

