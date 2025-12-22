"""Minimal types for streaming execution."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TradeRecord:
    """Minimal trade record for invalidation checking.
    
    This is a lightweight version of the full Trade dataclass from backtester,
    containing only fields needed for invalidation logic in streaming mode.
    """
    
    trade_id: str
    signal_id: str  # Source signal ID for correlation
    symbol: str
    direction: str  # "long" | "short"
    setup_type: str  # "VWAP_RECLAIM" | "VWAP_FADE" | "DXY_CONTINUATION"
    entry_price: float
    sl_price: float
    tp_price: float
    risk_amount: float
    reward_amount: float
    entry_timestamp: datetime
    exit_timestamp: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    pnl: float | None = None
    
    # State fields for service restart recovery
    entry_bar_idx: int | None = None  # Bar index when trade was entered
    reached_1r: bool = False  # Whether trade achieved +1R protection


