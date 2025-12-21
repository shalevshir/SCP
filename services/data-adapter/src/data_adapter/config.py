"""Configuration for Data Adapter service."""

from pydantic import Field

from scp_shared.config import BaseServiceConfig


class DataAdapterConfig(BaseServiceConfig):
    """Data Adapter service configuration."""

    service_name: str = Field(default="data-adapter")
    service_version: str = Field(default="0.1.0")

    # Databento configuration
    databento_api_key: str = Field(
        ...,
        description="Databento API key for live data",
    )

    databento_ws_url: str = Field(
        default="wss://live.databento.com/v1",
        description="Databento WebSocket URL",
    )

    # Symbols to subscribe to
    symbols: list[str] = Field(
        default=["GC", "DXY"],
        description="Symbols to subscribe to",
    )

