"""Interactive Brokers API client wrapper.

Wraps the synchronous ibapi library with async interface.
Runs the IB client in a background thread and provides async methods.
"""

import asyncio
import threading
from datetime import datetime
from typing import Literal
from uuid import uuid4

from scp_shared.common.logger import get_logger

from execution_svc.broker.base import OrderResult

logger = get_logger(__name__)

# Lazy import of ibapi - only import when actually needed
# This allows the module to be imported even if ibapi is not installed
# (e.g., when using paper mode)
try:
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.order import Order
    from ibapi.wrapper import EWrapper

    IBAPI_AVAILABLE = True
except ImportError:
    IBAPI_AVAILABLE = False

    # Create separate dummy classes for type hints when ibapi is not available
    # Must be separate classes to avoid "duplicate base class" error
    class _DummyEClient:  # type: ignore[no-redef]
        pass

    class _DummyEWrapper:  # type: ignore[no-redef]
        pass

    class _DummyContract:  # type: ignore[no-redef]
        pass

    class _DummyOrder:  # type: ignore[no-redef]
        pass

    EClient = _DummyEClient  # type: ignore[assignment,misc]
    EWrapper = _DummyEWrapper  # type: ignore[assignment,misc]
    Contract = _DummyContract  # type: ignore[assignment,misc]
    Order = _DummyOrder  # type: ignore[assignment,misc]


class IBClient(EWrapper, EClient):
    """Interactive Brokers API client wrapper.

    Combines EWrapper (callbacks) and EClient (requests) with async interface.
    Runs the IB message loop in a background thread.

    Example:
        >>> client = IBClient("127.0.0.1", 7497, 1)
        >>> await client.connect_async()
        >>> order_result = await client.place_order_async("GC", "long", 1, 2650.0)
        >>> await client.disconnect_async()
    """

    def __init__(self, host: str, port: int, client_id: int) -> None:
        """Initialize IB client.

        Args:
            host: IB Gateway/TWS host
            port: IB port (7497=TWS paper, 4002=Gateway paper)
            client_id: Unique client ID

        Raises:
            ImportError: If ibapi is not installed
        """
        if not IBAPI_AVAILABLE:
            raise ImportError(
                "ibapi is not installed. Install it with: poetry add ibapi\n"
                "Or use BROKER_MODE=paper for in-memory simulation."
            )

        EClient.__init__(self, self)

        self.host = host
        self.port = port
        self.client_id = client_id

        # Connection state
        self.connected = False
        self.next_order_id = 0

        # Order tracking: order_id -> (event, OrderResult)
        # Using threading.Event for thread-safe signaling from IB callback thread
        self._pending_orders: dict[int, tuple[threading.Event, OrderResult]] = {}

        # Thread for message loop
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def _set_event_threadsafe(self, event: threading.Event) -> None:
        """Set a threading event from the IB background thread.

        threading.Event is inherently thread-safe, so we just call set() directly.
        """
        event.set()

    def nextValidId(self, orderId: int) -> None:
        """Callback: Receive next valid order ID.

        This is the first callback after successful connection.
        """
        self.next_order_id = orderId
        self.connected = True
        logger.info(f"Connected to IB. Next order ID: {orderId}")

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        """Callback: Error message from IB.

        Args:
            reqId: Request/order ID (-1 for connection errors)
            errorCode: Error code
            errorString: Error message
            advancedOrderRejectJson: Advanced order reject info
        """
        # Informational/warning codes - NOT actual errors
        # 2100-2110: Connectivity status messages
        # 2104, 2106, 2158: Data farm connection OK
        # 399: Order message (informational)
        # 10147: Order held until conditions met
        informational_codes = {
            *range(2100, 2111),  # 2100-2110
            2104,
            2106,
            2158,  # Data farm OK
            399,  # Order message
            10147,  # Order held
            10167,  # Requested market data not subscribed
        }

        if errorCode in informational_codes:
            logger.info(f"IB info [{errorCode}]: {errorString}")
            return

        # Order rejection error codes - these actually reject orders
        order_rejection_codes = {
            201,  # Order rejected
            202,  # Order cancelled
            103,  # Duplicate order ID
            104,  # Can't modify filled order
            105,  # Order being modified doesn't exist
            106,  # Can't transmit order
            107,  # Can't transmit order - no account
            109,  # Price is out of range
            110,  # Price exceeds limit
            161,  # Cancel attempted when order not in cancellable state
        }

        if errorCode in order_rejection_codes:
            logger.error(f"IB order error [{errorCode}]: {errorString}")
            if reqId in self._pending_orders:
                event, order_result = self._pending_orders[reqId]
                order_result.status = "rejected"
                self._set_event_threadsafe(event)
        else:
            # Log as warning but don't reject order
            logger.warning(
                f"IB warning [reqId={reqId}, code={errorCode}]: {errorString}"
            )

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ) -> None:
        """Callback: Order status update.

        Args:
            orderId: Order ID
            status: Order status ("Filled", "Submitted", "Cancelled", etc.)
            filled: Filled quantity
            remaining: Remaining quantity
            avgFillPrice: Average fill price
            ... (other IB params)
        """
        logger.info(
            f"Order status: orderId={orderId}, status={status}, "
            f"filled={filled}, avgFillPrice={avgFillPrice}"
        )

        if orderId not in self._pending_orders:
            return

        event, order_result = self._pending_orders[orderId]

        # Handle different order statuses
        if status == "Filled":
            order_result.status = "filled"
            order_result.filled_price = avgFillPrice
            order_result.filled_at = datetime.utcnow()
            self._set_event_threadsafe(event)
        elif status == "Submitted" or status == "PreSubmitted":
            # Order accepted by IB, waiting for fill
            # Market orders should fill very quickly, so we just log and wait
            logger.info(f"Order {orderId} submitted to exchange, waiting for fill...")
        elif status in ("Cancelled", "ApiCancelled"):
            order_result.status = "rejected"
            self._set_event_threadsafe(event)

    def execDetails(self, reqId: int, contract: Contract, execution) -> None:
        """Callback: Execution details.

        Called when an order executes. We primarily use orderStatus(),
        but this provides additional execution details if needed.
        """
        logger.debug(
            f"Execution: orderId={execution.orderId}, "
            f"execId={execution.execId}, price={execution.price}, "
            f"shares={execution.shares}"
        )

    async def connect_async(self) -> None:
        """Connect to IB Gateway/TWS asynchronously.

        Starts the message loop in a background thread.

        Raises:
            ConnectionError: If connection fails
        """
        # Connect to IB
        self.connect(self.host, self.port, self.client_id)

        # Start message loop in background thread
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # Wait for connection confirmation (nextValidId callback)
        timeout = 10.0
        start = asyncio.get_event_loop().time()
        while not self.connected:
            if asyncio.get_event_loop().time() - start > timeout:
                raise ConnectionError(
                    f"Failed to connect to IB at {self.host}:{self.port} "
                    f"(timeout after {timeout}s)"
                )
            await asyncio.sleep(0.1)

        logger.info(f"Connected to IB at {self.host}:{self.port}")

    async def disconnect_async(self) -> None:
        """Disconnect from IB Gateway/TWS asynchronously."""
        self._stop_event.set()
        self.disconnect()

        if self._thread:
            self._thread.join(timeout=2.0)

        self.connected = False
        logger.info("Disconnected from IB")

    def _run_loop(self) -> None:
        """Run the IB message loop in background thread."""
        while not self._stop_event.is_set():
            self.run()

    async def place_order_async(
        self,
        symbol: str,
        side: Literal["long", "short"],
        quantity: int,
        price: float | None = None,
    ) -> OrderResult:
        """Place an order asynchronously.

        Args:
            symbol: Asset symbol (e.g., "GC")
            side: Order side ("long" or "short")
            quantity: Number of contracts
            price: Limit price (None for market order)

        Returns:
            OrderResult when order fills or rejects

        Raises:
            ValueError: If not connected or invalid parameters
        """
        if not self.connected:
            raise ValueError("Not connected to IB")

        # Create contract
        contract = self._create_contract(symbol)

        # Create order
        order_id = self.next_order_id
        self.next_order_id += 1

        order = Order()
        order.action = "BUY" if side == "long" else "SELL"
        order.totalQuantity = quantity
        order.orderType = "MKT"
        if price:
            order.lmtPrice = price

        # Disable unsupported order attributes for futures
        order.eTradeOnly = False
        order.firmQuoteOnly = False

        # Create OrderResult for tracking
        order_result = OrderResult(
            order_id=str(order_id),
            symbol=symbol,
            side=side,
            quantity=quantity,
            status="pending",
            limit_price=price,  # Track limit price for submitted orders
        )

        # Create threading event for thread-safe signaling from IB callback
        event = threading.Event()
        self._pending_orders[order_id] = (event, order_result)

        # Place order with IB
        self.placeOrder(order_id, contract, order)
        logger.info(
            f"Placed MKT order with IB: {side} {quantity} {symbol} (orderId={order_id})"
        )

        # Wait for fill or rejection (with timeout)
        # Poll the threading.Event from asyncio to avoid blocking the event loop
        timeout = 30.0
        poll_interval = 0.05  # 50ms
        elapsed = 0.0

        try:
            while not event.is_set() and elapsed < timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            if not event.is_set():
                logger.error(f"Order {order_id} timed out waiting for fill")
                order_result.status = "rejected"
        finally:
            # Clean up
            self._pending_orders.pop(order_id, None)

        return order_result

    def _create_contract(self, symbol: str) -> Contract:
        """Create IB contract for a symbol.

        Currently only supports GC (Gold Futures) on COMEX.

        Args:
            symbol: Asset symbol

        Returns:
            IB Contract object

        Raises:
            ValueError: If symbol is not supported
        """
        if symbol != "GC":
            raise ValueError(f"Unsupported symbol: {symbol}. Only GC is supported.")

        contract = Contract()
        contract.symbol = "GC"
        contract.secType = "FUT"
        contract.exchange = "COMEX"
        contract.currency = "USD"

        # Get current front month for GC futures
        # GC trades: Feb(G), Apr(J), Jun(M), Aug(Q), Oct(V), Dec(Z)
        contract.lastTradeDateOrContractMonth = self._get_gc_front_month()

        return contract

    def _get_gc_front_month(self) -> str:
        """Get the current front month contract for GC futures.

        GC futures trade in even months: Feb, Apr, Jun, Aug, Oct, Dec.
        Returns the next valid contract month.

        Returns:
            Contract month string (e.g., "202602" for Feb 2026)
        """
        from datetime import datetime

        now = datetime.utcnow()
        year = now.year
        month = now.month

        # GC valid months: 2, 4, 6, 8, 10, 12
        valid_months = [2, 4, 6, 8, 10, 12]

        # Find next valid month (current month + 1 to allow for rollover)
        # We add 1 because if we're in the expiry month, we want the next contract
        target_month = month + 1

        for vm in valid_months:
            if vm >= target_month:
                return f"{year}{vm:02d}"

        # If no valid month this year, use first month next year
        return f"{year + 1}02"
