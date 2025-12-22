"""Abstract broker interface for order execution."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class OrderResult:
    """Result of an order placement.
    
    Attributes:
        order_id: Unique order identifier
        symbol: Asset symbol
        side: Order side ("long" or "short")
        quantity: Number of contracts
        filled_price: Execution price
        filled_at: Execution timestamp
        status: Order status ("filled", "rejected", "pending")
    """
    
    order_id: str
    symbol: str
    side: Literal["long", "short"]
    quantity: int
    filled_price: float | None = None
    filled_at: datetime | None = None
    status: Literal["filled", "rejected", "pending"] = "pending"


@dataclass
class Position:
    """Current position state.
    
    Attributes:
        symbol: Asset symbol
        side: Position side ("long" or "short")
        quantity: Number of contracts
        entry_price: Average entry price
        unrealized_pnl: Unrealized P&L in points
    """
    
    symbol: str
    side: Literal["long", "short"]
    quantity: int
    entry_price: float
    unrealized_pnl: float = 0.0


class BaseBroker(ABC):
    """Abstract broker interface for order execution.
    
    Defines the contract that all broker implementations must follow,
    whether paper trading or live execution.
    
    Example:
        >>> broker = PaperBroker()
        >>> result = await broker.place_order("GC", "long", 1)
        >>> position = await broker.get_position("GC")
    """
    
    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: Literal["long", "short"],
        quantity: int,
        price: float | None = None,
    ) -> OrderResult:
        """Place an order.
        
        Args:
            symbol: Asset symbol (e.g., "GC")
            side: Order side ("long" or "short")
            quantity: Number of contracts
            price: Limit price (None for market order)
            
        Returns:
            OrderResult with execution details
            
        Raises:
            ValueError: If order parameters are invalid
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order.
        
        Args:
            order_id: Order identifier
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Position | None:
        """Get current position for a symbol.
        
        Args:
            symbol: Asset symbol
            
        Returns:
            Position if exists, None otherwise
        """
        pass
    
    @abstractmethod
    async def close_position(
        self,
        symbol: str,
        price: float | None = None,
    ) -> OrderResult:
        """Close an existing position.
        
        Args:
            symbol: Asset symbol
            price: Limit price (None for market order)
            
        Returns:
            OrderResult with execution details
            
        Raises:
            ValueError: If no position exists
        """
        pass


