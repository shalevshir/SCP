"""Pytest configuration and fixtures for data-adapter tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from scp_shared.messaging.schemas import CandleMessage

from data_adapter.databento_client import Tick


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create mock Redis client for testing."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sample_candle() -> CandleMessage:
    """Standard CandleMessage fixture."""
    return CandleMessage(
        timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        open=2050.0,
        high=2052.0,
        low=2049.0,
        close=2051.0,
        volume=1500.0,
    )


@pytest.fixture
def sample_tick() -> Tick:
    """Standard Tick fixture."""
    return Tick(
        timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=UTC),
        price=2050.0,
        volume=10.0,
        symbol="GC",
    )


@pytest.fixture
def sample_candle_gc() -> CandleMessage:
    """Gold candle fixture."""
    return CandleMessage(
        timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        open=2050.0,
        high=2052.0,
        low=2049.0,
        close=2051.0,
        volume=1500.0,
    )


@pytest.fixture
def sample_candle_dxy() -> CandleMessage:
    """DXY candle fixture (zero volume)."""
    return CandleMessage(
        timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=UTC),
        symbol="DXY",
        timeframe="1m",
        open=104.5,
        high=104.6,
        low=104.4,
        close=104.5,
        volume=0.0,  # DXY often has zero volume
    )


@pytest.fixture
def sample_ticks() -> list[Tick]:
    """List of sample ticks for testing."""
    base_time = datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC)
    
    return [
        Tick(
            timestamp=base_time,
            price=2050.0,
            volume=10.0,
            symbol="GC",
        ),
        Tick(
            timestamp=base_time.replace(second=30),
            price=2051.0,
            volume=20.0,
            symbol="GC",
        ),
        Tick(
            timestamp=base_time.replace(minute=1),
            price=2052.0,
            volume=15.0,
            symbol="GC",
        ),
    ]


@pytest.fixture
def sample_candles() -> list[CandleMessage]:
    """List of sample candles for testing."""
    return [
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
            volume=1200.0,
        ),
        CandleMessage(
            timestamp=datetime(2024, 3, 15, 10, 2, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2052.0,
            high=2054.0,
            low=2051.0,
            close=2053.0,
            volume=1100.0,
        ),
    ]
