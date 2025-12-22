"""Configuration for Execution service."""

from pydantic import Field
from scp_shared.config import BaseServiceConfig


class ExecutionConfig(BaseServiceConfig):
    """Execution service configuration."""

    service_name: str = Field(default="execution")
    service_version: str = Field(default="0.1.0")
    
    broker_mode: str = Field(
        default="paper",
        description="Broker mode: paper or live",
    )
    
    default_quantity: int = Field(
        default=1,
        description="Default number of contracts per trade",
    )
    
    sl_buffer_ticks: int = Field(
        default=5,
        description="Buffer ticks for stop-loss placement",
    )
    
    max_active_trades: int = Field(
        default=1,
        description="Maximum concurrent trades",
    )
    
    pdll_limit: float = Field(
        default=600.0,
        description="Per day loss limit in points",
    )
    
    max_trades_per_day: int = Field(
        default=2,
        description="Maximum trades per day",
    )

