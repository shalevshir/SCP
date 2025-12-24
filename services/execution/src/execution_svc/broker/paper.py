"""Paper trading broker implementation."""

from datetime import datetime
from typing import Literal, cast
from uuid import uuid4

from scp_shared.common.logger import get_logger

from execution_svc.broker.base import BaseBroker, OrderResult, Position

logger = get_logger(__name__)


class PaperBroker(BaseBroker):
    """Paper trading broker with simulated order execution.
    
    Simulates order execution at market prices with immediate fills.
    Tracks positions and provides realistic order flow without real capital.
    
    Features:
    - Immediate market order fills
    - Position tracking
    - Order history
    
    Simplifications (for Phase 6):
    - No slippage simulation
    - No partial fills
    - No order rejection
    - Immediate execution (no latency)
    
    Example:
        >>> broker = PaperBroker()
        >>> result = await broker.place_order("GC", "long", 1, price=2650.0)
        >>> position = await broker.get_position("GC")
        >>> print(f"Position: {position.quantity} @ {position.entry_price}")
    """
    
    def __init__(self) -> None:
        """Initialize paper broker with empty state."""
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderResult] = {}
    
    async def place_order(
        self,
        symbol: str,
        side: Literal["long", "short"],
        quantity: int,
        price: float | None = None,
    ) -> OrderResult:
        """Place an order (simulated execution).
        
        Args:
            symbol: Asset symbol (e.g., "GC")
            side: Order side ("long" or "short")
            quantity: Number of contracts
            price: Execution price (required for paper trading)
            
        Returns:
            OrderResult with immediate fill
            
        Raises:
            ValueError: If price is None or quantity <= 0
        """
        # Validate inputs
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")
        
        if price is None:
            raise ValueError("Paper broker requires explicit price for order execution")
        
        if price <= 0:
            raise ValueError(f"Price must be positive, got {price}")
        
        # Check for existing position (paper broker allows only one position per symbol)
        if symbol in self._positions:
            # In test environments, the database might be cleaned but broker state persists
            # Auto-close orphaned position to allow new trades
            existing = self._positions[symbol]
            logger.warning(
                f"Auto-closing orphaned position for {symbol}: {existing.side} "
                f"{existing.quantity} @ {existing.entry_price:.2f} (likely from previous test)"
            )
            # Force close at current price (simulating market close)
            await self.close_position(symbol, price=price)
        
        # Create order result
        order_id = str(uuid4())
        result = OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            filled_price=price,
            filled_at=datetime.utcnow(),
            status="filled",
        )
        
        # Store order
        self._orders[order_id] = result
        
        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=price,
            unrealized_pnl=0.0,
        )
        self._positions[symbol] = position
        
        logger.info(
            f"Paper order filled: {side} {quantity} {symbol} @ {price:.2f} "
            f"(order_id={order_id})"
        )
        
        return result
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order (not applicable for paper broker).
        
        Paper broker executes orders immediately, so cancellation is not supported.
        
        Args:
            order_id: Order identifier
            
        Returns:
            False (orders are filled immediately)
        """
        logger.warning(
            f"Cancel order called for {order_id}, but paper broker "
            "executes immediately (no pending orders)"
        )
        return False
    
    async def get_position(self, symbol: str) -> Position | None:
        """Get current position for a symbol.
        
        Args:
            symbol: Asset symbol
            
        Returns:
            Position if exists, None otherwise
        """
        return self._positions.get(symbol)
    
    async def close_position(
        self,
        symbol: str,
        price: float | None = None,
    ) -> OrderResult:
        """Close an existing position.
        
        Args:
            symbol: Asset symbol
            price: Exit price (required for paper trading)
            
        Returns:
            OrderResult with execution details
            
        Raises:
            ValueError: If no position exists or price is None
        """
        # Check position exists
        position = self._positions.get(symbol)
        if position is None:
            raise ValueError(f"No position exists for {symbol}")
        
        if price is None:
            raise ValueError("Paper broker requires explicit price for position close")
        
        if price <= 0:
            raise ValueError(f"Price must be positive, got {price}")
        
        # Create closing order (opposite side)
        closing_side: Literal["long", "short"] = "short" if position.side == "long" else "long"
        
        order_id = str(uuid4())
        result = OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=closing_side,
            quantity=position.quantity,
            filled_price=price,
            filled_at=datetime.utcnow(),
            status="filled",
        )
        
        # Store order
        self._orders[order_id] = result
        
        # Calculate P&L
        if position.side == "long":
            pnl = price - position.entry_price
        else:  # short
            pnl = position.entry_price - price
        
        pnl_total = pnl * position.quantity
        
        # Remove position
        del self._positions[symbol]
        
        logger.info(
            f"Paper position closed: {position.side} {position.quantity} {symbol} "
            f"@ {price:.2f} (entry={position.entry_price:.2f}, pnl={pnl_total:.2f} points, "
            f"order_id={order_id})"
        )
        
        return result
    
    def get_all_positions(self) -> list[Position]:
        """Get all current positions.
        
        Returns:
            List of all positions
        """
        return list(self._positions.values())
    
    def get_order_history(self) -> list[OrderResult]:
        """Get order history.
        
        Returns:
            List of all orders
        """
        return list(self._orders.values())
    
    async def reconcile_positions(
        self,
        trades: list[tuple[str, str, float, int]],
    ) -> None:
        """Reconcile broker positions with restored trades on startup.
        
        This method restores broker position state from trade records,
        ensuring broker state matches the database after a restart.
        
        Args:
            trades: List of (symbol, side, entry_price, quantity) tuples
        """
        for symbol, side, entry_price, quantity in trades:
            # Only restore if position doesn't already exist
            if symbol not in self._positions:
                position = Position(
                    symbol=symbol,
                    side=cast(Literal["long", "short"], side),
                    quantity=quantity,
                    entry_price=entry_price,
                    unrealized_pnl=0.0,
                )
                self._positions[symbol] = position
                logger.info(
                    f"Reconciled broker position: {side} {quantity} {symbol} @ {entry_price:.2f}"
                )
            else:
                logger.warning(
                    f"Position already exists for {symbol}, skipping reconciliation"
                )
    
    def reset_state(self) -> None:
        """Reset broker state (for testing purposes).
        
        Clears all positions and order history. This is useful in integration
        tests where the service persists across tests but the database is cleaned.
        
        Warning: This should only be used in test environments!
        """
        self._positions.clear()
        self._orders.clear()
        logger.info("Paper broker state reset (all positions and orders cleared)")

