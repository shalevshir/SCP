"""Shared fixtures for integration tests.

This module provides fixtures for multi-service integration testing including:
- Docker container management (Redis, PostgreSQL)
- Service lifecycle management
- Test data generators
- Database initialization and cleanup
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock

import asyncpg
import pytest
import redis.asyncio as aioredis
from scp_shared.common.types import Candle
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage, HTFBiasMessage


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for async tests."""
    return asyncio.get_event_loop_policy()


@pytest.fixture(scope="session")
def redis_url() -> str:
    """Provide Redis connection URL.
    
    Uses environment variable or defaults to localhost.
    Assumes Redis is running (via docker-compose or locally).
    """
    return os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Provide PostgreSQL connection URL.
    
    Uses environment variable or defaults to localhost.
    Assumes PostgreSQL is running with migrations applied.
    """
    return os.getenv(
        "DATABASE_URL",
        "postgresql://scp:scp_dev_password@localhost:5432/scp"
    )


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncGenerator[aioredis.Redis, None]:
    """Provide Redis client with automatic cleanup.
    
    Yields:
        Connected Redis client
        
    Cleans up all test streams after test completes.
    """
    client = aioredis.from_url(redis_url, decode_responses=True)
    
    try:
        await client.ping()
        yield client
    finally:
        # Cleanup: delete all test streams
        test_streams = [
            "candles.1m.gc",
            "candles.1m.dxy",
            "features.1m",
            "features.15m",
            "features.1h",
            "htf.bias",
            "signals.pending",
            "trades.opened",
            "trades.closed",
        ]
        for stream in test_streams:
            try:
                await client.delete(stream)
            except Exception:
                pass
        
        await client.aclose()


@pytest.fixture
async def db_pool(postgres_url: str) -> AsyncGenerator[asyncpg.Pool, None]:
    """Provide PostgreSQL connection pool with automatic cleanup.
    
    Yields:
        Connection pool
        
    Cleans up test data after test completes.
    """
    pool = await asyncpg.create_pool(postgres_url, min_size=2, max_size=10)
    
    try:
        yield pool
    finally:
        # Cleanup: truncate all tables (preserve schema)
        async with pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE trades CASCADE")
            await conn.execute("TRUNCATE TABLE state_machine_snapshots CASCADE")
            await conn.execute("TRUNCATE TABLE daily_state CASCADE")
            await conn.execute("TRUNCATE TABLE htf_bias_history CASCADE")
            await conn.execute("TRUNCATE TABLE features CASCADE")
            await conn.execute("TRUNCATE TABLE candles CASCADE")
        
        await pool.close()


@pytest.fixture
def sample_candle_gc() -> Candle:
    """Generate sample GC candle for testing.
    
    Returns:
        Candle with realistic GC price data
    """
    return Candle(
        timestamp=datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        open=2050.0,
        high=2052.0,
        low=2049.0,
        close=2051.0,
        volume=1000.0,
    )


@pytest.fixture
def sample_candle_dxy() -> Candle:
    """Generate sample DXY candle for testing.
    
    Returns:
        Candle with realistic DXY price data
    """
    return Candle(
        timestamp=datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        open=103.50,
        high=103.60,
        low=103.45,
        close=103.55,
        volume=500.0,
    )


@pytest.fixture
def candle_message_factory():
    """Factory for creating CandleMessage instances.
    
    Returns:
        Callable that generates CandleMessage with custom parameters
    """
    def _create(
        timestamp: datetime | None = None,
        symbol: str = "GC",
        timeframe: str = "1m",
        open: float = 2050.0,
        high: float = 2052.0,
        low: float = 2049.0,
        close: float = 2051.0,
        volume: float = 1000.0,
    ) -> CandleMessage:
        if timestamp is None:
            timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        return CandleMessage(
            timestamp=timestamp,
            symbol=symbol,
            timeframe=timeframe,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
    
    return _create


@pytest.fixture
def features_message_factory():
    """Factory for creating FeaturesMessage instances.
    
    Returns:
        Callable that generates FeaturesMessage with custom parameters
    """
    def _create(
        timestamp: datetime | None = None,
        symbol: str = "GC",
        timeframe: str = "1m",
        close: float = 2051.0,
        vwap: float = 2050.5,
        rsi: float = 55.0,
        ema_9: float = 2050.0,
        ema_20: float = 2049.0,
        ema_50: float = 2048.0,
        dxy_correlation: float = -0.75,
        structure_label: str = "HH",
        **kwargs: Any,
    ) -> FeaturesMessage:
        if timestamp is None:
            timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        return FeaturesMessage(
            timestamp=timestamp,
            symbol=symbol,
            timeframe=timeframe,
            close=close,
            open=kwargs.get("open", close - 1.0),
            high=kwargs.get("high", close + 1.0),
            low=kwargs.get("low", close - 2.0),
            volume=kwargs.get("volume", 1000.0),
            vwap=vwap,
            vwap_slope=kwargs.get("vwap_slope", 0.5),
            vwap_deviation=kwargs.get("vwap_deviation", 0.5),
            rsi=rsi,
            ema_9=ema_9,
            ema_20=ema_20,
            ema_50=ema_50,
            dxy_correlation=dxy_correlation,
            dxy_corr=dxy_correlation,
            dxy_structure=kwargs.get("dxy_structure", "HH"),
            structure_label=structure_label,
            htf_structure_label=kwargs.get("htf_structure_label"),
            bos_direction=kwargs.get("bos_direction"),
            bos_recent=kwargs.get("bos_recent", False),
            bos_age=kwargs.get("bos_age", 0),
            choch_detected=kwargs.get("choch_detected", False),
            choch_direction=kwargs.get("choch_direction"),
            structure_clarity=kwargs.get("structure_clarity", 8.0),
            liquidity_sweep=kwargs.get("liquidity_sweep", False),
            sweep_age=kwargs.get("sweep_age", 0),
            expansion_detected=kwargs.get("expansion_detected", False),
            expansion_reasons=kwargs.get("expansion_reasons", []),
            second_confirmation_long=kwargs.get("second_confirmation_long", False),
            second_confirmation_short=kwargs.get("second_confirmation_short", False),
        )
    
    return _create


@pytest.fixture
def htf_bias_message_factory():
    """Factory for creating HTFBiasMessage instances.
    
    Returns:
        Callable that generates HTFBiasMessage with custom parameters
    """
    def _create(
        timestamp: datetime | None = None,
        bias: str = "bullish",
        score: float = 8.5,
        confidence: str = "A+",
        structure_15m: str = "HH",
        structure_1h: str = "HH",
        dxy_aligned: bool = True,
        chop_detected: bool = False,
        **kwargs: Any,
    ) -> HTFBiasMessage:
        if timestamp is None:
            timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        return HTFBiasMessage(
            timestamp=timestamp,
            bias=bias,
            score=score,
            confidence=confidence,
            structure_15m=structure_15m,
            structure_1h=structure_1h,
            dxy_aligned=dxy_aligned,
            chop_detected=chop_detected,
            seasonality_adjustment=kwargs.get("seasonality_adjustment", 0.0),
            seasonality_period=kwargs.get("seasonality_period"),
            vwap_trend_confirmed=kwargs.get("vwap_trend_confirmed", True),
        )
    
    return _create


@pytest.fixture
async def publish_to_stream(redis_client: aioredis.Redis):
    """Helper to publish messages to Redis streams.
    
    Args:
        redis_client: Connected Redis client
        
    Returns:
        Async function to publish messages
    """
    async def _publish(stream: str, message: dict[str, Any]) -> str:
        """Publish message to stream and return message ID."""
        # Convert datetime objects to ISO format strings
        serialized = {}
        for key, value in message.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, (list, dict)):
                import json
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = str(value)
        
        msg_id = await redis_client.xadd(stream, serialized)
        return msg_id
    
    return _publish


@pytest.fixture
async def read_from_stream(redis_client: aioredis.Redis):
    """Helper to read messages from Redis streams.
    
    Args:
        redis_client: Connected Redis client
        
    Returns:
        Async function to read messages
    """
    async def _read(
        stream: str,
        count: int = 10,
        block_ms: int = 1000,
    ) -> list[dict[str, Any]]:
        """Read messages from stream."""
        results = await redis_client.xread({stream: "0"}, count=count, block=block_ms)
        
        if not results:
            return []
        
        messages = []
        for _, msg_list in results:
            for msg_id, data in msg_list:
                messages.append({"id": msg_id, "data": data})
        
        return messages
    
    return _read


@pytest.fixture
def mock_broker():
    """Provide mock broker for testing execution without real orders.
    
    Returns:
        AsyncMock configured as a broker
    """
    broker = AsyncMock()
    broker.connect = AsyncMock(return_value=True)
    broker.disconnect = AsyncMock(return_value=True)
    broker.place_order = AsyncMock(return_value={"order_id": "test_order_123", "status": "filled"})
    broker.close_position = AsyncMock(return_value={"status": "closed"})
    broker.get_position = AsyncMock(return_value=None)
    broker.get_all_positions = AsyncMock(return_value=[])
    
    return broker


@pytest.fixture
async def cleanup_consumer_groups(redis_client: aioredis.Redis):
    """Cleanup consumer groups after tests.
    
    Yields control back to test, then cleans up consumer groups.
    """
    yield
    
    # Cleanup consumer groups
    test_streams = [
        "candles.1m.gc",
        "candles.1m.dxy",
        "features.1m",
        "htf.bias",
        "signals.pending",
    ]
    
    for stream in test_streams:
        try:
            # Try to destroy consumer groups (ignore if they don't exist)
            groups = await redis_client.xinfo_groups(stream)
            for group_info in groups:
                group_name = group_info["name"]
                await redis_client.xgroup_destroy(stream, group_name)
        except Exception:
            # Stream or group doesn't exist - that's fine
            pass


# ============================================================================
# Compatibility fixtures for existing integration tests
# ============================================================================


@pytest.fixture
async def redis_publisher(redis_client: aioredis.Redis):
    """Provide RedisStreamPublisher for existing tests.
    
    This is a compatibility fixture for tests written before the
    publish_to_stream helper was introduced.
    """
    from scp_shared.messaging import RedisStreamPublisher
    
    publisher = RedisStreamPublisher(redis_client)
    return publisher


@pytest.fixture
async def clean_streams(redis_client: aioredis.Redis):
    """Cleanup Redis streams before test (compatibility fixture).
    
    Yields control to test, streams are cleaned up by redis_client fixture.
    """
    # Cleanup happens in redis_client fixture
    yield


@pytest.fixture
async def ensure_services_healthy():
    """Placeholder fixture for service health checks.
    
    In a full integration test environment, this would verify that
    all required services (data-adapter, feature-engine, etc.) are
    running and healthy before executing tests.
    
    For now, tests run against infrastructure only (Redis, PostgreSQL).
    """
    # TODO: Add actual health checks when running full service stack
    yield


@pytest.fixture
async def reset_execution_state():
    """Reset Execution service state before each test.
    
    Calls the /admin/reset endpoint to clear active trades, pending signals,
    and other runtime state. This prevents test interference when running
    multiple tests in sequence.
    """
    import httpx
    
    # Reset state before test
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://localhost:8005/admin/reset", timeout=5.0)
            if response.status_code == 200:
                pass  # Success
    except Exception:
        pass  # Service might not be running or endpoint might not exist
    
    yield
    
    # Reset state after test (cleanup)
    try:
        async with httpx.AsyncClient() as client:
            await client.post("http://localhost:8005/admin/reset", timeout=5.0)
    except Exception:
        pass


# ============================================================================
# Pytest configuration
# ============================================================================


def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "integration: All integration tests")
    config.addinivalue_line(
        "markers",
        "infrastructure: Infrastructure-only tests (no services required)"
    )
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end tests (require full service stack)"
    )
    config.addinivalue_line("markers", "slow: Slow running tests")
