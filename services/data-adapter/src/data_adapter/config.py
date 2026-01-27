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
        description="Data provider: 'ib', 'databento', or 'mock' (default: mock)",
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

    # IB Gateway configuration
    ib_host: str = Field(
        default="127.0.0.1",
        description="IB Gateway/TWS host",
    )

    ib_port: int = Field(
        default=4002,
        description="IB Gateway port (4002=Gateway paper, 7497=TWS paper)",
    )

    ib_client_id: int = Field(
        default=10,
        description="IB client ID for data streaming (different from execution)",
    )

    ib_gc_symbol: str = Field(
        default="GC",
        description="IB symbol for Gold futures",
    )

    ib_dxy_symbol: str = Field(
        default="DX",
        description="IB symbol for Dollar Index futures",
    )

    ib_market_data_type: int = Field(
        default=3,
        description="IB market data type: 1=Live, 2=Frozen, 3=Delayed, 4=Delayed Frozen (default: 3=Delayed)",
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

    # Warmup configuration
    warmup_enabled: bool = Field(
        default=False,
        description="Enable warmup stream publishing from IB Gateway on startup",
    )

    warmup_lookback_hours: int = Field(
        default=24,
        description="Hours of historical data to fetch for warmup (24 = 1440 1m candles)",
    )

    warmup_stream_ttl_seconds: int = Field(
        default=600,
        description="TTL for warmup streams (auto-expire after consumption, default: 10 minutes)",
    )
