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
    
    max_consecutive_losses: int = Field(
        default=2,
        ge=1,
        description="Maximum consecutive losses before halt",
    )
    
    # Slippage configuration (disabled by default for production)
    enable_slippage: bool = Field(
        default=False,
        description="Enable slippage simulation for backtest mode",
    )
    slippage_points: float = Field(
        default=0.5,
        description="Slippage in points when enabled",
    )
    
    # Commission configuration (disabled by default for production)
    enable_commission: bool = Field(
        default=False,
        description="Enable commission deduction for backtest mode",
    )
    commission_per_trade: float = Field(
        default=5.0,
        description="Commission per trade in dollars when enabled",
    )
    
    # Position sizing configuration
    sizing_mode: str = Field(
        default="fixed",
        description="Position sizing mode: 'fixed' or 'risk_ladder'",
    )
    fixed_quantity: int = Field(
        default=1,
        description="Fixed quantity when sizing_mode='fixed'",
    )
    risk_per_trade_percent: float = Field(
        default=1.0,
        description="Risk per trade as percent of account when sizing_mode='risk_ladder'",
    )
    
    # Interactive Brokers connection settings
    ib_host: str = Field(
        default="127.0.0.1",
        description="IB Gateway/TWS host",
    )
    ib_port: int = Field(
        default=4002,
        description="IB port (7497=TWS paper, 4002=Gateway paper, 7496=TWS live, 4001=Gateway live)",
    )
    ib_client_id: int = Field(
        default=1,
        description="IB client ID (unique per connection)",
    )
    ib_account: str = Field(
        default="",
        description="IB account ID (leave empty for default account)",
    )

