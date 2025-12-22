"""Unit tests for Databento clients."""

import asyncio
from datetime import UTC, datetime

import pytest
from scp_shared.messaging.schemas import CandleMessage

from data_adapter.databento_client import (
    MockDatabentoClient,
    ReplayDatabentoClient,
    Tick,
)


class TestMockDatabentoClient:
    """Test MockDatabentoClient."""
    
    @pytest.mark.asyncio
    async def test_mock_client_streams_provided_ticks(self) -> None:
        """Custom tick list iteration."""
        ticks = [
            Tick(
                timestamp=datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC),
                price=2050.0,
                volume=10.0,
                symbol="GC",
            ),
            Tick(
                timestamp=datetime(2024, 3, 15, 10, 0, 30, tzinfo=UTC),
                price=2051.0,
                volume=20.0,
                symbol="GC",
            ),
        ]
        
        client = MockDatabentoClient(ticks=ticks, delay_ms=0)
        
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        
        assert len(received_ticks) == 2
        assert received_ticks[0].price == 2050.0
        assert received_ticks[1].price == 2051.0
    
    @pytest.mark.asyncio
    async def test_mock_client_generates_sample_ticks(self) -> None:
        """Default sample data generation."""
        client = MockDatabentoClient(delay_ms=0)
        
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        
        # Should generate 3 sample ticks
        assert len(received_ticks) == 3
        assert all(tick.symbol == "GC" for tick in received_ticks)
        assert all(tick.price > 0 for tick in received_ticks)
    
    @pytest.mark.asyncio
    async def test_mock_client_applies_delay(self) -> None:
        """delay_ms parameter timing."""
        ticks = [
            Tick(
                timestamp=datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC),
                price=2050.0,
                volume=10.0,
                symbol="GC",
            ),
            Tick(
                timestamp=datetime(2024, 3, 15, 10, 0, 1, tzinfo=UTC),
                price=2051.0,
                volume=10.0,
                symbol="GC",
            ),
        ]
        
        # Use 100ms delay
        client = MockDatabentoClient(ticks=ticks, delay_ms=100)
        
        start = asyncio.get_event_loop().time()
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        elapsed = asyncio.get_event_loop().time() - start
        
        # Should have taken at least 100ms (2 ticks, delay before each)
        assert len(received_ticks) == 2
        assert elapsed >= 0.1  # At least 100ms
    
    @pytest.mark.asyncio
    async def test_mock_client_close_is_noop(self) -> None:
        """Graceful close (no-op)."""
        client = MockDatabentoClient(delay_ms=0)
        
        # Close should not raise
        await client.close()
        
        # Should still be able to stream after close (since it's a no-op)
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        
        assert len(received_ticks) > 0
    
    @pytest.mark.asyncio
    async def test_mock_client_async_context_manager(self) -> None:
        """__aenter__/__aexit__ work."""
        ticks = [
            Tick(
                timestamp=datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC),
                price=2050.0,
                volume=10.0,
                symbol="GC",
            ),
        ]
        
        async with MockDatabentoClient(ticks=ticks, delay_ms=0) as client:
            received_ticks = []
            async for tick in client.stream_ticks():
                received_ticks.append(tick)
            
            assert len(received_ticks) == 1
            assert received_ticks[0].price == 2050.0


class TestReplayDatabentoClient:
    """Test ReplayDatabentoClient."""
    
    @pytest.mark.asyncio
    async def test_replay_generates_ohlc_ticks(self) -> None:
        """4 ticks per candle (O, H, L, C)."""
        candles = [
            CandleMessage(
                timestamp=datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                open=2050.0,
                high=2052.0,
                low=2049.0,
                close=2051.0,
                volume=1000.0,
            ),
        ]
        
        client = ReplayDatabentoClient(candles=candles, speed_multiplier=1000.0)
        
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        
        # Should generate 4 ticks (O, H, L, C)
        assert len(received_ticks) == 4
        assert received_ticks[0].price == 2050.0  # Open
        assert received_ticks[1].price == 2052.0  # High
        assert received_ticks[2].price == 2049.0  # Low
        assert received_ticks[3].price == 2051.0  # Close
        
        # Volume split across 4 ticks
        assert all(tick.volume == 250.0 for tick in received_ticks)
    
    @pytest.mark.asyncio
    async def test_replay_applies_speed_multiplier(self) -> None:
        """Timing adjustment with multiplier."""
        candles = [
            CandleMessage(
                timestamp=datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                open=2050.0,
                high=2052.0,
                low=2049.0,
                close=2051.0,
                volume=1000.0,
            ),
            CandleMessage(
                timestamp=datetime(2024, 3, 15, 10, 1, 0, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                open=2051.0,
                high=2053.0,
                low=2050.0,
                close=2052.0,
                volume=1000.0,
            ),
        ]
        
        # Use 100x speed multiplier (60 seconds / 100 = 0.6 seconds)
        client = ReplayDatabentoClient(candles=candles, speed_multiplier=100.0)
        
        start = asyncio.get_event_loop().time()
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        elapsed = asyncio.get_event_loop().time() - start
        
        # Should have 8 ticks (4 per candle)
        assert len(received_ticks) == 8
        
        # Should take approximately 0.6 seconds (60s / 100)
        assert 0.5 <= elapsed <= 1.0
    
    @pytest.mark.asyncio
    async def test_replay_handles_empty_candles_list(self) -> None:
        """Edge case: empty input."""
        client = ReplayDatabentoClient(candles=[], speed_multiplier=1.0)
        
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        
        # Should not yield any ticks
        assert len(received_ticks) == 0
    
    # Edge cases (adapted from test_replay_loop_edge_cases.py patterns)
    
    @pytest.mark.asyncio
    async def test_replay_handles_single_candle(self) -> None:
        """Minimal data edge case."""
        candles = [
            CandleMessage(
                timestamp=datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                open=2050.0,
                high=2050.0,
                low=2050.0,
                close=2050.0,
                volume=100.0,
            ),
        ]
        
        client = ReplayDatabentoClient(candles=candles, speed_multiplier=1000.0)
        
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        
        # Should still generate 4 ticks even if OHLC are the same
        assert len(received_ticks) == 4
        assert all(tick.price == 2050.0 for tick in received_ticks)
    
    @pytest.mark.asyncio
    async def test_replay_handles_zero_volume_candles(self) -> None:
        """DXY often has zero volume."""
        candles = [
            CandleMessage(
                timestamp=datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC),
                symbol="DXY",
                timeframe="1m",
                open=104.5,
                high=104.6,
                low=104.4,
                close=104.5,
                volume=0.0,  # Zero volume
            ),
        ]
        
        client = ReplayDatabentoClient(candles=candles, speed_multiplier=1000.0)
        
        received_ticks = []
        async for tick in client.stream_ticks():
            received_ticks.append(tick)
        
        # Should generate ticks with zero volume
        assert len(received_ticks) == 4
        assert all(tick.volume == 0.0 for tick in received_ticks)
        assert all(tick.symbol == "DXY" for tick in received_ticks)
