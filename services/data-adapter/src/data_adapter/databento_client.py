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
    """
    
    def __init__(
        self,
        api_key: str,
        dataset: str = "GLBX.MDP3",
        symbols: list[str] | None = None,
    ) -> None:
        """Initialize Databento client.
        
        Args:
            api_key: Databento API key
            dataset: Dataset identifier (default: GLBX.MDP3 for CME futures)
            symbols: List of symbols to subscribe to (default: ["GC", "DX"])
        """
        self.api_key = api_key
        self.dataset = dataset
        self.symbols = symbols or ["GC", "DX"]
        self._client: db.Live | None = None
    
    async def stream_ticks(self) -> AsyncIterator[Tick]:
        """Stream ticks from Databento live feed.
        
        Yields:
            Tick objects as they arrive
        """
        # Initialize Databento live client
        self._client = db.Live(key=self.api_key)
        
        # Subscribe to symbols
        await self._client.subscribe(
            dataset=self.dataset,
            schema="trades",
            symbols=self.symbols,
        )
        
        # Stream data
        async for record in self._client:
            # Convert Databento record to Tick
            tick = Tick(
                timestamp=record.ts_event,
                price=float(record.price) / 1e9,  # Databento uses fixed-point
                volume=float(record.size),
                symbol=record.symbol,
            )
            yield tick
    
    async def close(self) -> None:
        """Close Databento connection."""
        if self._client:
            await self._client.close()


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

