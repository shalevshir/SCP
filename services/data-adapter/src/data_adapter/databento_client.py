"""Databento WebSocket client for live data ingestion.

This module provides both a real Databento WebSocket client and a mock
implementation for testing/replay scenarios.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import databento as db
from scp_shared.common import get_logger

logger = get_logger(__name__)


@dataclass
class Tick:
    """Tick data structure."""
    
    timestamp: datetime
    price: float
    volume: float
    symbol: str


class DatabentoClientBase(ABC):
    """Base class for Databento clients."""
    
    @abstractmethod
    async def stream_ticks(self) -> AsyncIterator[Tick]:
        """Stream ticks from Databento.
        
        Yields:
            Tick objects as they arrive
        """
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close connection and cleanup resources."""
        ...
    
    async def __aenter__(self) -> "DatabentoClientBase":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Async context manager exit."""
        await self.close()


class DatabentoClient(DatabentoClientBase):
    """Real Databento WebSocket client for live data.
    
    Connects to Databento live WebSocket feed and streams tick data.
    Handles proper symbol mapping between Databento and internal symbols.
    """
    
    def __init__(
        self,
        api_key: str,
        dataset: str = "GLBX.MDP3",
        gc_symbol: str = "GC.FUT",
        dxy_symbol: str = "DX.FUT",
    ) -> None:
        """Initialize Databento client.
        
        Args:
            api_key: Databento API key
            dataset: Dataset identifier (default: GLBX.MDP3 for CME futures)
            gc_symbol: Databento symbol for Gold (default: GC.FUT for continuous)
            dxy_symbol: Databento symbol for DXY (default: DX.FUT for continuous)
        """
        self.api_key = api_key
        self.dataset = dataset
        self.databento_symbols = [gc_symbol, dxy_symbol]
        
        # Map Databento symbols to internal symbols
        # Databento may return GC.FUT, GCZ4, etc. - normalize to GC/DXY
        self.symbol_map: dict[str, str] = {}
        for db_sym in self.databento_symbols:
            if "GC" in db_sym or "gc" in db_sym.lower():
                self.symbol_map[db_sym] = "GC"
            elif "DX" in db_sym or "dx" in db_sym.lower():
                self.symbol_map[db_sym] = "DXY"
        
        self._client: db.Live | None = None
    
    def _normalize_symbol(self, databento_symbol: str) -> str:
        """Normalize Databento symbol to internal format.
        
        Args:
            databento_symbol: Symbol from Databento (e.g., GC.FUT, GCZ4, DX.FUT)
            
        Returns:
            Normalized symbol (GC or DXY)
        """
        # Check exact match first
        if databento_symbol in self.symbol_map:
            return self.symbol_map[databento_symbol]
        
        # Fallback: check if symbol starts with our known prefixes
        symbol_upper = databento_symbol.upper()
        if symbol_upper.startswith("GC"):
            return "GC"
        elif symbol_upper.startswith("DX"):
            return "DXY"
        
        # Unknown symbol - log warning and return as-is
        logger.warning(f"Unknown Databento symbol: {databento_symbol}")
        return databento_symbol
    
    async def stream_ticks(self) -> AsyncIterator[Tick]:
        """Stream ticks from Databento live feed.
        
        Yields:
            Tick objects as they arrive
            
        Raises:
            Exception: On connection or subscription errors
        """
        try:
            # Initialize Databento live client
            logger.info(f"Connecting to Databento {self.dataset} with symbols {self.databento_symbols}")
            self._client = db.Live(key=self.api_key)
            
            # Subscribe to symbols
            logger.info(f"Subscribing to trades for symbols: {self.databento_symbols}")
            await self._client.subscribe(
                dataset=self.dataset,
                schema="trades",
                symbols=self.databento_symbols,
            )
            
            logger.info("Databento subscription successful, streaming ticks...")
            
            # Stream data
            async for record in self._client:
                # Convert Databento record to Tick with normalized symbol
                normalized_symbol = self._normalize_symbol(record.symbol)
                
                tick = Tick(
                    timestamp=record.ts_event if hasattr(record, 'ts_event') else datetime.now(UTC),
                    price=float(record.price) / 1e9,  # Databento uses fixed-point (nanoseconds)
                    volume=float(record.size) if hasattr(record, 'size') else 0.0,
                    symbol=normalized_symbol,
                )
                yield tick
        
        except Exception as e:
            logger.error(f"Error in Databento stream: {e}", exc_info=True)
            raise
    
    async def close(self) -> None:
        """Close Databento connection."""
        if self._client:
            logger.info("Closing Databento connection")
            try:
                # Databento Live client doesn't have async close, use stop()
                if hasattr(self._client, 'stop'):
                    self._client.stop()
                elif hasattr(self._client, 'close'):
                    await self._client.close()
            except Exception as e:
                logger.warning(f"Error closing Databento client: {e}")
            finally:
                self._client = None


class MockDatabentoClient(DatabentoClientBase):
    """Mock Databento client for testing and replay.
    
    Streams pre-defined tick data for testing purposes.
    """
    
    def __init__(
        self,
        ticks: list[Tick] | None = None,
        delay_ms: int = 0,
    ) -> None:
        """Initialize mock client.
        
        Args:
            ticks: List of ticks to stream (default: generates sample data)
            delay_ms: Delay between ticks in milliseconds (default: 0)
        """
        self.ticks = ticks or self._generate_sample_ticks()
        self.delay_ms = delay_ms
    
    async def stream_ticks(self) -> AsyncIterator[Tick]:
        """Stream mock ticks.
        
        Yields:
            Tick objects from pre-defined list
        """
        for tick in self.ticks:
            if self.delay_ms > 0:
                await asyncio.sleep(self.delay_ms / 1000.0)
            yield tick
    
    async def close(self) -> None:
        """Close mock client (no-op)."""
        pass
    
    @staticmethod
    def _generate_sample_ticks() -> list[Tick]:
        """Generate sample ticks for testing."""
        
        base_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        
        return [
            Tick(
                timestamp=base_time,
                price=2650.0,
                volume=10.0,
                symbol="GC",
            ),
            Tick(
                timestamp=base_time.replace(second=30),
                price=2651.0,
                volume=20.0,
                symbol="GC",
            ),
            Tick(
                timestamp=base_time.replace(minute=1),
                price=2652.0,
                volume=15.0,
                symbol="GC",
            ),
        ]


class ResilientDatabentoClient(DatabentoClientBase):
    """Wraps DatabentoClient with automatic reconnection and circuit breaker.
    
    Provides exponential backoff reconnection on connection failures,
    making the client production-ready for 24/7 operation.
    """
    
    def __init__(
        self,
        inner: DatabentoClient,
        max_retries: int = 10,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> None:
        """Initialize resilient client wrapper.
        
        Args:
            inner: Underlying DatabentoClient to wrap
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
                logger.info(f"Attempting to connect to Databento (failures: {self._consecutive_failures})")
                
                async for tick in self.inner.stream_ticks():
                    # Successfully receiving data
                    if self._state != "connected":
                        self._state = "connected"
                        self._consecutive_failures = 0
                        logger.info("Databento connection established successfully")
                    
                    yield tick
                
                # Stream ended normally (no exception) - server closed connection cleanly
                # This can happen during rate limiting, maintenance, or graceful shutdown
                self._state = "disconnected"
                self._last_disconnect = datetime.now(UTC)
                
                # For normal disconnection, we still apply backoff to avoid tight reconnection loops
                # but we don't increment failure counter (it's not an error)
                # Use a smaller base delay for normal disconnections
                delay = min(
                    self.base_delay * (2 ** min(self._consecutive_failures, 3)),  # Cap at 3 for normal disconnects
                    self.max_delay
                )
                
                logger.info(
                    f"Databento stream ended normally (server closed connection). "
                    f"Reconnecting in {delay:.1f}s"
                )
                
                # Wait before reconnecting to avoid overwhelming the API
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
                if self.max_retries > 0 and self._consecutive_failures >= self.max_retries:
                    logger.error(
                        f"Max retries ({self.max_retries}) exceeded. Giving up."
                    )
                    raise
                
                # Calculate exponential backoff delay
                delay = min(
                    self.base_delay * (2 ** (self._consecutive_failures - 1)),
                    self.max_delay
                )
                
                logger.warning(
                    f"Databento connection lost: {e}. "
                    f"Reconnecting in {delay:.1f}s (attempt {self._consecutive_failures})"
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


class DatabentoHistoricalFetcher:
    """Fetches historical candles from Databento for gap backfill.
    
    Uses Databento Historical API to fetch missing data when gaps are detected
    in the live stream.
    """
    
    def __init__(
        self,
        api_key: str,
        dataset: str = "GLBX.MDP3",
    ) -> None:
        """Initialize historical fetcher.
        
        Args:
            api_key: Databento API key
            dataset: Dataset identifier
        """
        self.api_key = api_key
        self.dataset = dataset
    
    def _map_symbol(self, internal_symbol: str) -> str:
        """Map internal symbol to Databento symbol format.
        
        Args:
            internal_symbol: Internal symbol (GC or DXY)
            
        Returns:
            Databento symbol format
        """
        if internal_symbol == "GC":
            return "GC.FUT"
        elif internal_symbol == "DXY":
            return "DX.FUT"
        return internal_symbol
    
    def _to_candle_message(self, record, symbol: str):  # type: ignore[no-untyped-def]
        """Convert Databento OHLCV record to CandleMessage.
        
        Args:
            record: Databento OHLCV record
            symbol: Internal symbol (GC or DXY)
            
        Returns:
            CandleMessage instance
        """
        from scp_shared.messaging.schemas import CandleMessage
        
        return CandleMessage(
            timestamp=record.ts_event if hasattr(record, 'ts_event') else datetime.now(UTC),
            symbol=symbol,
            timeframe="1m",
            open=float(record.open) / 1e9,
            high=float(record.high) / 1e9,
            low=float(record.low) / 1e9,
            close=float(record.close) / 1e9,
            volume=float(record.volume) if hasattr(record, 'volume') else 0.0,
        )
    
    async def fetch_candles(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1m",
    ) -> list:  # Returns list[CandleMessage]
        """Fetch historical candles for gap backfill.
        
        Args:
            symbol: Internal symbol (GC or DXY)
            start: Start datetime (inclusive)
            end: End datetime (exclusive)
            timeframe: Timeframe (currently only 1m supported)
            
        Returns:
            List of CandleMessage objects
        """
        try:
            logger.info(
                f"Fetching historical data for {symbol} "
                f"from {start.isoformat()} to {end.isoformat()}"
            )
            
            # Map symbol to Databento format
            db_symbol = self._map_symbol(symbol)
            
            # Create historical client
            client = db.Historical(key=self.api_key)
            
            # Fetch OHLCV data
            data = await asyncio.to_thread(
                client.timeseries.get_range,
                dataset=self.dataset,
                symbols=[db_symbol],
                schema="ohlcv-1m",
                start=start.isoformat(),
                end=end.isoformat(),
            )
            
            # Convert to CandleMessage objects
            candles = [self._to_candle_message(record, symbol) for record in data]
            
            logger.info(f"Fetched {len(candles)} historical candles for {symbol}")
            return candles
        
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}", exc_info=True)
            return []


class ReplayDatabentoClient(DatabentoClientBase):
    """Replay client that streams historical candles as ticks.
    
    Useful for testing with historical data at accelerated speed.
    """
    
    def __init__(
        self,
        candles: list,  # List of CandleMessage
        speed_multiplier: float = 1.0,
    ) -> None:
        """Initialize replay client.
        
        Args:
            candles: List of CandleMessage objects to replay
            speed_multiplier: Speed multiplier (1.0 = real-time, 10.0 = 10x faster)
        """
        self.candles = candles
        self.speed_multiplier = speed_multiplier
    
    async def stream_ticks(self) -> AsyncIterator[Tick]:
        """Stream candles as synthetic ticks.
        
        For each candle, generates 4 ticks (OHLC).
        
        Yields:
            Tick objects synthesized from candles
        """
        prev_timestamp = None
        
        for candle in self.candles:
            # Simulate time delay
            if prev_timestamp is not None:
                delay_seconds = (candle.timestamp - prev_timestamp).total_seconds()
                await asyncio.sleep(delay_seconds / self.speed_multiplier)
            
            # Generate 4 ticks per candle (O, H, L, C)
            ticks = [
                Tick(candle.timestamp, candle.open, candle.volume / 4, candle.symbol),
                Tick(candle.timestamp, candle.high, candle.volume / 4, candle.symbol),
                Tick(candle.timestamp, candle.low, candle.volume / 4, candle.symbol),
                Tick(candle.timestamp, candle.close, candle.volume / 4, candle.symbol),
            ]
            
            for tick in ticks:
                yield tick
            
            prev_timestamp = candle.timestamp
    
    async def close(self) -> None:
        """Close replay client (no-op)."""
        pass

