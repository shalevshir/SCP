"""Interactive Brokers paper trading broker implementation."""

from typing import Literal

from scp_shared.common.logger import get_logger

from execution_svc.broker.base import BaseBroker, OrderResult, Position

logger = get_logger(__name__)

# Lazy import - only import IBClient when actually instantiating IBPaperBroker
# This allows the module to be imported even if ibapi is not installed
try:
    from execution_svc.broker.ib_client import IBClient
    IB_CLIENT_AVAILABLE = True
except ImportError:
    IB_CLIENT_AVAILABLE = False
    IBClient = None  # type: ignore[assignment,misc]


class IBPaperBroker(BaseBroker):
    """Interactive Brokers paper trading broker.
    
    Connects to IB TWS/Gateway in paper trading mode.
    Orders are sent to IB for realistic execution with paper money.
    
    Internal tracking (database) remains the source of truth:
    - Trades are saved to PostgreSQL by TradeManager
    - IB provides realistic order flow and fills
    - If IB and internal state disagree, internal wins
    
    Features:
    - Realistic order execution through IB paper account
    - Market orders with real-time fills
    - Position tracking (internal only, not synced from IB)
    
    Example:
        >>> broker = IBPaperBroker("127.0.0.1", 7497, 1)
        >>> await broker.connect()
        >>> result = await broker.place_order("GC", "long", 1, price=2650.0)
        >>> await broker.disconnect()
    """
    
    def __init__(self, host: str, port: int, client_id: int) -> None:
        """Initialize IB paper broker.
        
        Args:
            host: IB Gateway/TWS host
            port: IB port (7497=TWS paper, 4002=Gateway paper)
            client_id: Unique client ID
            
        Raises:
            ImportError: If ibapi is not installed
        """
        if not IB_CLIENT_AVAILABLE or IBClient is None:
            raise ImportError(
                "ibapi is not installed. Install it with: poetry add ibapi\n"
                "Or use BROKER_MODE=paper for in-memory simulation."
            )
        
        self._client = IBClient(host, port, client_id)
        self._positions: dict[str, Position] = {}
        
        # Connection info for logging
        self.host = host
        self.port = port
    
    async def connect(self) -> None:
        """Connect to IB Gateway/TWS.
        
        Raises:
            ConnectionError: If connection fails
        """
        await self._client.connect_async()
        logger.info(f"IBPaperBroker connected to {self.host}:{self.port}")
    
    async def disconnect(self) -> None:
        """Disconnect from IB Gateway/TWS."""
        await self._client.disconnect_async()
        logger.info("IBPaperBroker disconnected")
    
    async def place_order(
        self,
        symbol: str,
        side: Literal["long", "short"],
        quantity: int,
        price: float | None = None,
    ) -> OrderResult:
        """Place an order through IB.
        
        Args:
            symbol: Asset symbol (e.g., "GC")
            side: Order side ("long" or "short")
            quantity: Number of contracts
            price: Limit price (None for market order)
            
        Returns:
            OrderResult with execution details from IB
            
        Raises:
            ValueError: If invalid parameters or not connected
        """
        # Validate inputs
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")
        
        if price is not None and price <= 0:
            raise ValueError(f"Price must be positive, got {price}")
        
        # Check for existing position (paper broker allows only one position per symbol)
        if symbol in self._positions:
            existing = self._positions[symbol]
            logger.warning(
                f"Position already exists for {symbol}: {existing.side} "
                f"{existing.quantity} @ {existing.entry_price:.2f}. "
                "Close existing position first."
            )
            # Auto-close for testing environments
            close_result = await self.close_position(symbol, price=price)
            
            # If close order was rejected, we cannot proceed with new order
            # This prevents state mismatch: internal tracking vs IB positions
            if close_result.status == "rejected":
                logger.error(
                    f"Cannot place new order for {symbol}: close order was rejected. "
                    f"Original position still exists in IB. (orderId={close_result.order_id})"
                )
                raise ValueError(
                    f"Cannot place order for {symbol}: failed to close existing position. "
                    f"Close order was rejected by IB (orderId={close_result.order_id}). "
                    "Internal state and IB positions would be mismatched."
                )
            
            # If close order is pending, we cannot proceed (position still exists)
            if close_result.status == "pending":
                logger.error(
                    f"Cannot place new order for {symbol}: close order is still pending. "
                    f"Original position still exists. (orderId={close_result.order_id})"
                )
                raise ValueError(
                    f"Cannot place order for {symbol}: close order is still pending. "
                    f"Wait for close to complete before placing new order. (orderId={close_result.order_id})"
                )
            
            # Verify position was actually closed (should be removed from _positions on fill)
            # This is a defensive check for bugs in close_position
            if close_result.status == "filled" and symbol in self._positions:
                logger.error(
                    f"Position for {symbol} still exists after successful close order. "
                    "This indicates a bug in close_position."
                )
                raise RuntimeError(
                    f"Position for {symbol} was not closed despite successful close order. "
                    "Internal state is inconsistent."
                )
        
        # Place order through IB
        order_result = await self._client.place_order_async(symbol, side, quantity, price)
        
        # If order filled, track position internally
        if order_result.status == "filled" and order_result.filled_price:
            position = Position(
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=order_result.filled_price,
                unrealized_pnl=0.0,
            )
            self._positions[symbol] = position
            
            logger.info(
                f"IB order filled: {side} {quantity} {symbol} "
                f"@ {order_result.filled_price:.2f} (orderId={order_result.order_id})"
            )
        elif order_result.status == "rejected":
            logger.error(
                f"IB order rejected: {side} {quantity} {symbol} "
                f"(orderId={order_result.order_id})"
            )
        
        return order_result
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order.
        
        Note: IB market orders fill immediately, so cancellation rarely applies.
        
        Args:
            order_id: Order identifier
            
        Returns:
            False (not implemented for IB integration)
        """
        logger.warning(
            f"Cancel order called for {order_id}, but IB paper broker "
            "does not support cancellation (orders fill immediately)"
        )
        return False
    
    async def get_position(self, symbol: str) -> Position | None:
        """Get current position for a symbol.
        
        Returns internal position tracking, not queried from IB.
        
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
        """Close an existing position through IB.
        
        Args:
            symbol: Asset symbol
            price: Exit price (None for market order)
            
        Returns:
            OrderResult with execution details
            
        Raises:
            ValueError: If no position exists or price invalid
        """
        # Check position exists
        position = self._positions.get(symbol)
        if position is None:
            raise ValueError(f"No position exists for {symbol}")
        
        if price is not None and price <= 0:
            raise ValueError(f"Price must be positive, got {price}")
        
        # Create closing order (opposite side)
        closing_side: Literal["long", "short"] = "short" if position.side == "long" else "long"
        
        # Place closing order through IB
        order_result = await self._client.place_order_async(
            symbol, closing_side, position.quantity, price
        )
        
        # If order filled, remove position and calculate P&L
        if order_result.status == "filled" and order_result.filled_price:
            entry_price = float(position.entry_price)
            exit_price = float(order_result.filled_price)
            
            if position.side == "long":
                pnl = exit_price - entry_price
            else:  # short
                pnl = entry_price - exit_price
            
            pnl_total = pnl * position.quantity
            
            # Remove position
            del self._positions[symbol]
            
            logger.info(
                f"IB position closed: {position.side} {position.quantity} {symbol} "
                f"@ {exit_price:.2f} (entry={entry_price:.2f}, "
                f"pnl={pnl_total:.2f} points, orderId={order_result.order_id})"
            )
        
        return order_result
    
    def get_all_positions(self) -> list[Position]:
        """Get all current positions.
        
        Returns internal position tracking.
        
        Returns:
            List of all positions
        """
        return list(self._positions.values())
    
    async def reconcile_positions(
        self,
        trades: list[tuple[str, str, float, int]],
    ) -> None:
        """Reconcile broker positions with restored trades on startup.
        
        For IB paper broker, we restore internal position tracking only.
        We do NOT sync positions from IB (internal tracking is source of truth).
        
        Args:
            trades: List of (symbol, side, entry_price, quantity) tuples
        """
        for symbol, side, entry_price, quantity in trades:
            if symbol not in self._positions:
                position = Position(
                    symbol=symbol,
                    side=side,  # type: ignore[arg-type]
                    quantity=quantity,
                    entry_price=entry_price,
                    unrealized_pnl=0.0,
                )
                self._positions[symbol] = position
                logger.info(
                    f"Reconciled IB paper position: {side} {quantity} {symbol} "
                    f"@ {entry_price:.2f}"
                )
    
    def reset_state(self) -> None:
        """Reset broker state (for testing purposes).
        
        Clears all internal position tracking.
        Does NOT affect IB account state.
        
        Warning: This should only be used in test environments!
        """
        self._positions.clear()
        logger.info("IB paper broker state reset (internal positions cleared)")
