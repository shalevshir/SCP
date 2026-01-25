"""Interactive Brokers Gateway client for live market data.

This module provides an IB Gateway data client using ib_insync for async streaming.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from scp_shared.common import get_logger

from data_adapter.databento_client import DataClientBase, Tick

logger = get_logger(__name__)

# Check if ib_insync is available
try:
    from ib_insync import IB, Contract, Ticker

    IB_INSYNC_AVAILABLE = True
except ImportError:
    IB_INSYNC_AVAILABLE = False
    # Create dummy classes for type checking when ib_insync is not available
    IB = None  # type: ignore
    Contract = None  # type: ignore
    Ticker = None  # type: ignore


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
        market_data_type: int = 3,
    ) -> None:
        """Initialize IB data client.

        Args:
            host: IB Gateway/TWS host
            port: IB port (4002=Gateway paper, 7497=TWS paper)
            client_id: Unique client ID (differ from execution client)
            gc_symbol: IB symbol for Gold futures (default: "GC")
            dxy_symbol: IB symbol for Dollar Index (default: "DX")
            market_data_type: Market data type (1=Live, 2=Frozen, 3=Delayed, 4=Delayed Frozen, default: 3)

        Raises:
            ImportError: If ib_insync is not installed
        """
        if not IB_INSYNC_AVAILABLE:
            raise ImportError(
                "ib_insync is not installed. Install it with: pip install ib-insync"
            )

        self.host = host
        self.port = port
        self.client_id = client_id
        self.gc_symbol = gc_symbol
        self.dxy_symbol = dxy_symbol
        self.market_data_type = market_data_type

        self._ib: IB | None = None
        self._connected = False

        # Queue for tick events (bounded to prevent unbounded growth)
        # Max size of 10000 ticks (~10 seconds at 1000 ticks/sec) prevents memory issues
        # while allowing reasonable buffering during processing spikes
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=10000)

        # Track tick counts for logging first data receipt
        self._tick_counts: dict[str, int] = {"GC": 0, "DXY": 0}

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
        # Get price - prefer last trade, fall back to bid/ask midpoint
        # Delayed data often only provides bid/ask, not trade ticks
        price: float | None = None
        volume: float = 0.0

        if ticker.last is not None and ticker.last > 0:
            price = float(ticker.last)
            volume = float(ticker.lastSize) if ticker.lastSize else 0.0
        elif ticker.bid is not None and ticker.ask is not None:
            # Use bid/ask midpoint for delayed data
            if ticker.bid > 0 and ticker.ask > 0:
                price = (float(ticker.bid) + float(ticker.ask)) / 2
                volume = 1.0  # Synthetic volume for quote updates

        if price is None or price <= 0:
            # Log occasionally for debugging (every ~100 updates with no price)
            logger.debug(
                f"No valid price for {internal_symbol}: "
                f"last={ticker.last}, bid={ticker.bid}, ask={ticker.ask}"
            )
            return  # No valid price data

        # Get timestamp
        # For futures, IB doesn't provide tick type 45 (Last Timestamp)
        # Use ticker.time which is when data was received by the client
        # For delayed data, this is typically close to the actual trade time
        # (within seconds for delayed data feeds)
        if hasattr(ticker, "time") and ticker.time is not None:
            tick_timestamp = ticker.time
            # Ensure timezone-aware and convert to UTC
            if tick_timestamp.tzinfo is None:
                # Naive datetime - assume UTC (common for IB delayed data)
                tick_timestamp = tick_timestamp.replace(tzinfo=UTC)
            else:
                # Timezone-aware - convert to UTC
                tick_timestamp = tick_timestamp.astimezone(UTC)
        elif hasattr(ticker, "lastTimestamp") and ticker.lastTimestamp is not None:
            # Fallback: if lastTimestamp somehow available (e.g., for stocks), use it
            tick_timestamp = datetime.fromtimestamp(ticker.lastTimestamp, tz=UTC)
        else:
            # Final fallback to current time
            tick_timestamp = datetime.now(UTC)

        tick = Tick(
            timestamp=tick_timestamp,
            price=price,
            volume=volume,
            symbol=internal_symbol,
        )

        # Log first tick received for each symbol
        self._tick_counts[internal_symbol] += 1
        if self._tick_counts[internal_symbol] == 1:
            logger.info(
                f"First tick received for {internal_symbol}: "
                f"price={price:.2f}, timestamp={tick_timestamp}"
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

            # Request market data type (configurable via IB_MARKET_DATA_TYPE env var)
            # MarketDataType: 1=Live, 2=Frozen, 3=Delayed, 4=Delayed Frozen
            self._ib.reqMarketDataType(self.market_data_type)
            data_type_names = {
                1: "Live",
                2: "Frozen",
                3: "Delayed",
                4: "Delayed Frozen",
            }
            data_type_name = data_type_names.get(
                self.market_data_type, f"Unknown({self.market_data_type})"
            )
            logger.info(
                f"Requested market data type: {data_type_name} ({self.market_data_type})"
            )

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
        """Disconnect from IB Gateway and clear tick queue."""
        if self._ib and self._ib.isConnected():
            logger.info("Closing IB Gateway connection")
            self._ib.disconnect()
            self._connected = False
            self._ib = None

        # CRITICAL: Clear tick queue to prevent stale data on reconnection
        # Drain all pending ticks from the previous session
        drained_count = 0
        while not self._tick_queue.empty():
            try:
                self._tick_queue.get_nowait()
                drained_count += 1
            except asyncio.QueueEmpty:
                break

        if drained_count > 0:
            logger.info(f"Cleared {drained_count} stale ticks from queue on disconnect")


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
                    self.max_delay,
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
                    self.max_delay,
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
