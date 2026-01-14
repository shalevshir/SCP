"""Interactive Brokers Gateway client for live market data.

This module provides an IB Gateway data client using ib_insync for async streaming.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from scp_shared.common import get_logger

from data_adapter.databento_client import DataClientBase, Tick

logger = get_logger(__name__)

# Lazy import of ib_insync - only import when actually needed
try:
    from ib_insync import IB, Contract, Ticker
    IB_INSYNC_AVAILABLE = True
except ImportError:
    IB_INSYNC_AVAILABLE = False
    IB = None  # type: ignore[assignment,misc]
    Contract = None  # type: ignore[assignment,misc]
    Ticker = None  # type: ignore[assignment,misc]


class IBDataClient(DataClientBase):
    """Interactive Brokers Gateway client for live market data.
    
    Uses ib_insync for async-native streaming of real-time tick data.
    Subscribes to both GC (Gold) and DXY (Dollar Index) futures.
    
    Example:
        >>> client = IBDataClient("127.0.0.1", 4002, 10)
        >>> async for tick in client.stream_ticks():
        ...     print(f"{tick.symbol}: {tick.price}")
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        gc_symbol: str = "GC",
        dxy_symbol: str = "DX",
    ) -> None:
        """Initialize IB data client.
        
        Args:
            host: IB Gateway/TWS host
            port: IB port (4002=Gateway paper, 7497=TWS paper)
            client_id: Unique client ID (differ from execution client)
            gc_symbol: IB symbol for Gold futures (default: "GC")
            dxy_symbol: IB symbol for Dollar Index (default: "DX")
            
        Raises:
            ImportError: If ib_insync is not installed
        """
        if not IB_INSYNC_AVAILABLE:
            raise ImportError(
                "ib_insync is not installed. Install it with: poetry add ib-insync\n"
                "Or use DATA_PROVIDER=databento or DATA_PROVIDER=mock"
            )
        
        self.host = host
        self.port = port
        self.client_id = client_id
        self.gc_symbol = gc_symbol
        self.dxy_symbol = dxy_symbol
        
        self._ib: IB | None = None
        self._connected = False
        
        # Queue for tick events
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue()
    
    def _get_front_month(self, symbol: str) -> str:
        """Get the current front month contract for futures.
        
        Args:
            symbol: Futures symbol (GC or DX)
            
        Returns:
            Contract month string (e.g., "202602" for Feb 2026)
        """
        now = datetime.now(UTC)
        year = now.year
        month = now.month
        
        if symbol == "GC":
            # GC trades in even months: Feb, Apr, Jun, Aug, Oct, Dec
            valid_months = [2, 4, 6, 8, 10, 12]
        elif symbol == "DX":
            # DX trades in Mar, Jun, Sep, Dec (quarterly)
            valid_months = [3, 6, 9, 12]
        else:
            raise ValueError(f"Unsupported symbol: {symbol}")
        
        # Find next valid month (current month + 1 to allow for rollover)
        target_month = month + 1
        
        for vm in valid_months:
            if vm >= target_month:
                return f"{year}{vm:02d}"
        
        # If no valid month this year, use first month next year
        return f"{year + 1}{valid_months[0]:02d}"
    
    def _create_contract(self, symbol: str) -> Contract:
        """Create IB contract for a symbol.
        
        Args:
            symbol: Internal symbol (GC or DX)
            
        Returns:
            ib_insync Contract object
            
        Raises:
            ValueError: If symbol is not supported
        """
        if symbol == "GC":
            contract = Contract()
            contract.symbol = "GC"
            contract.secType = "FUT"
            contract.exchange = "COMEX"
            contract.currency = "USD"
            contract.lastTradeDateOrContractMonth = self._get_front_month("GC")
            return contract
        elif symbol == "DX":
            contract = Contract()
            contract.symbol = "DX"
            contract.secType = "FUT"
            contract.exchange = "NYBOT"
            contract.currency = "USD"
            contract.lastTradeDateOrContractMonth = self._get_front_month("DX")
            return contract
        else:
            raise ValueError(f"Unsupported symbol: {symbol}. Use GC or DX.")
    
    def _on_tick(self, ticker: Ticker, internal_symbol: str) -> None:
        """Callback for tick updates from IB.
        
        Args:
            ticker: ib_insync Ticker object
            internal_symbol: Internal symbol name (GC or DXY)
        """
        # Get last trade price and size
        if ticker.last is not None and ticker.last > 0:
            tick = Tick(
                timestamp=datetime.now(UTC),
                price=float(ticker.last),
                volume=float(ticker.lastSize) if ticker.lastSize else 0.0,
                symbol=internal_symbol,
            )
            
            # Put tick in queue (non-blocking)
            try:
                self._tick_queue.put_nowait(tick)
            except asyncio.QueueFull:
                logger.warning(f"Tick queue full, dropping tick for {internal_symbol}")
    
    async def stream_ticks(self) -> AsyncIterator[Tick]:
        """Stream real-time ticks from IB Gateway.
        
        Subscribes to tick-by-tick trade data for GC and DX futures.
        
        Yields:
            Tick objects as they arrive from IB
            
        Raises:
            Exception: On connection or subscription errors
        """
        try:
            # Connect to IB Gateway
            logger.info(
                f"Connecting to IB Gateway at {self.host}:{self.port} "
                f"(client_id={self.client_id})"
            )
            self._ib = IB()
            await self._ib.connectAsync(self.host, self.port, clientId=self.client_id)
            self._connected = True
            logger.info("Connected to IB Gateway successfully")
            
            # Create contracts for GC and DX
            gc_contract = self._create_contract(self.gc_symbol)
            dx_contract = self._create_contract(self.dxy_symbol)
            
            gc_month = gc_contract.lastTradeDateOrContractMonth
            dx_month = dx_contract.lastTradeDateOrContractMonth
            logger.info(
                f"Subscribing to market data: "
                f"{gc_contract.symbol} ({gc_month}), {dx_contract.symbol} ({dx_month})"
            )
            
            # Request market data
            gc_ticker = self._ib.reqMktData(
                gc_contract, genericTickList="", snapshot=False
            )
            dx_ticker = self._ib.reqMktData(
                dx_contract, genericTickList="", snapshot=False
            )
            
            # Set up tick callbacks
            gc_ticker.updateEvent += lambda ticker: self._on_tick(ticker, "GC")
            dx_ticker.updateEvent += lambda ticker: self._on_tick(ticker, "DXY")
            
            logger.info("Market data subscription successful, streaming ticks...")
            
            # Stream ticks from queue
            while self._connected:
                try:
                    # Wait for tick with timeout to allow checking connection state
                    tick = await asyncio.wait_for(self._tick_queue.get(), timeout=1.0)
                    yield tick
                except TimeoutError:
                    # No tick in last second - check if still connected
                    if not self._ib.isConnected():
                        logger.warning("IB Gateway disconnected")
                        break
                    continue
        
        except Exception as e:
            logger.error(f"Error in IB data stream: {e}", exc_info=True)
            raise
        finally:
            await self.close()
    
    async def close(self) -> None:
        """Disconnect from IB Gateway."""
        if self._ib and self._ib.isConnected():
            logger.info("Closing IB Gateway connection")
            self._ib.disconnect()
            self._connected = False
            self._ib = None


class ResilientIBDataClient(DataClientBase):
    """Wraps IBDataClient with automatic reconnection and circuit breaker.
    
    Provides exponential backoff reconnection on connection failures,
    making the client production-ready for 24/7 operation.
    """
    
    def __init__(
        self,
        inner: IBDataClient,
        max_retries: int = 10,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> None:
        """Initialize resilient IB client wrapper.
        
        Args:
            inner: Underlying IBDataClient to wrap
            max_retries: Maximum consecutive failures before giving up (0 = infinite)
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay between reconnection attempts
        """
        self.inner = inner
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._state = "disconnected"  # disconnected, connecting, connected
        self._consecutive_failures = 0
        self._last_disconnect: datetime | None = None
    
    @property
    def connection_state(self) -> str:
        """Get current connection state."""
        return self._state
    
    async def stream_ticks(self) -> AsyncIterator[Tick]:
        """Stream ticks with automatic reconnection on failure.
        
        Yields:
            Tick objects from the underlying client
            
        Raises:
            Exception: If max_retries is exceeded
        """
        while True:
            try:
                self._state = "connecting"
                failures = self._consecutive_failures
                logger.info(f"Attempting IB Gateway connection (failures: {failures})")
                
                async for tick in self.inner.stream_ticks():
                    # Successfully receiving data
                    if self._state != "connected":
                        self._state = "connected"
                        self._consecutive_failures = 0
                        logger.info("IB Gateway connection established successfully")
                    
                    yield tick
                
                # Stream ended normally - server closed connection cleanly
                # (gateway restart, maintenance, or graceful shutdown)
                self._state = "disconnected"
                self._last_disconnect = datetime.now(UTC)
                
                # For normal disconnection, apply backoff to avoid tight loops
                # Cap at 3 for normal disconnects
                delay = min(
                    self.base_delay * (2 ** min(self._consecutive_failures, 3)),
                    self.max_delay
                )
                
                logger.info(
                    f"IB Gateway stream ended normally (connection closed). "
                    f"Reconnecting in {delay:.1f}s"
                )
                
                # Wait before reconnecting to avoid overwhelming the gateway
                await asyncio.sleep(delay)
                
                # Close and reset inner client for clean reconnection
                try:
                    await self.inner.close()
                except Exception:
                    pass  # Ignore close errors
            
            except Exception as e:
                self._state = "disconnected"
                self._last_disconnect = datetime.now(UTC)
                self._consecutive_failures += 1
                
                # Check if max retries exceeded
                max_exceeded = (
                    self.max_retries > 0
                    and self._consecutive_failures >= self.max_retries
                )
                if max_exceeded:
                    logger.error(
                        f"Max retries ({self.max_retries}) exceeded. Giving up."
                    )
                    raise
                
                # Calculate exponential backoff delay
                delay = min(
                    self.base_delay * (2 ** (self._consecutive_failures - 1)),
                    self.max_delay
                )
                
                attempt = self._consecutive_failures
                logger.warning(
                    f"IB Gateway connection lost: {e}. "
                    f"Reconnecting in {delay:.1f}s (attempt {attempt})"
                )
                
                # Wait before reconnecting
                await asyncio.sleep(delay)
                
                # Close and reset inner client for clean reconnection
                try:
                    await self.inner.close()
                except Exception:
                    pass  # Ignore close errors
    
    async def close(self) -> None:
        """Close the underlying client."""
        await self.inner.close()
