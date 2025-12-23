"""Pytest fixtures for integration tests."""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
import redis.asyncio as redis
from scp_shared.database import DatabasePool
from scp_shared.messaging import RedisStreamPublisher
from scp_shared.messaging.schemas import CandleMessage


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Provide Redis client connected to test instance.
    
    Connects to test Redis on port 6380 (configured in docker-compose.test.yml).
    
    Yields:
        Redis client for integration tests
    """
    client = redis.Redis(
        host="localhost",
        port=6380,
        decode_responses=False,  # Keep binary for stream handling
    )
    
    try:
        # Verify connection
        await client.ping()
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def db_pool() -> AsyncGenerator[DatabasePool, None]:
    """Provide database pool connected to test PostgreSQL.
    
    Connects to test PostgreSQL on port 5433 (configured in docker-compose.test.yml).
    
    Yields:
        Database pool for integration tests
    """
    pool = DatabasePool(
        "postgresql://scp_test:scp_test_password@localhost:5433/scp_test"
    )
    
    try:
        await pool.connect()
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture(scope="function")
async def clean_streams(redis_client: redis.Redis) -> None:
    """Clean Redis streams before each test.
    
    Deletes all streams used by services to ensure clean test state.
    
    Args:
        redis_client: Redis client fixture
    """
    streams_to_clean = [
        "candles.1m.gc",
        "candles.1m.dxy",
        "candles.15m.gc",
        "candles.1h.gc",
        "features.1m",
        "features.15m",
        "features.1h",
        "htf.bias",
        "signals.pending",
        "trades.opened",
        "trades.closed",
    ]
    
    for stream in streams_to_clean:
        try:
            await redis_client.delete(stream)
        except Exception:
            # Stream might not exist, that's ok
            pass


@pytest_asyncio.fixture(scope="function")
async def clean_database(db_pool: DatabasePool) -> None:
    """Clean database tables before each test.
    
    Truncates all tables used by services to ensure clean test state.
    
    Args:
        db_pool: Database pool fixture
    """
    tables_to_clean = [
        "trades",
        "state_machine_snapshots",
        "daily_state",
        "htf_bias_history",
        "features",
        "candles",
    ]
    
    for table in tables_to_clean:
        try:
            await db_pool.execute(f"TRUNCATE TABLE {table} CASCADE")
        except Exception:
            # Table might not exist, that's ok
            pass


@pytest_asyncio.fixture(scope="function")
async def redis_publisher(redis_client: redis.Redis) -> RedisStreamPublisher:
    """Provide Redis stream publisher for test data injection.
    
    Args:
        redis_client: Redis client fixture
        
    Returns:
        RedisStreamPublisher instance
    """
    return RedisStreamPublisher(redis_client)


def wait_for_service_health(
    service_url: str, max_retries: int = 30, retry_delay: float = 1.0
) -> bool:
    """Wait for a service to become healthy.
    
    Args:
        service_url: URL to health endpoint (e.g., "http://localhost:8001/health")
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        True if service became healthy, False if timed out
    """
    import requests
    
    for i in range(max_retries):
        try:
            response = requests.get(service_url, timeout=2)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        
        if i < max_retries - 1:
            time.sleep(retry_delay)
    
    return False


@pytest.fixture(scope="session")
def docker_services() -> dict[str, str]:
    """Provide service URLs for health checks.
    
    Returns:
        Dictionary mapping service names to health endpoint URLs
    """
    return {
        "data-adapter": "http://localhost:8001/health",
        "feature-engine": "http://localhost:8002/health",
        "htf-bias": "http://localhost:8003/health",
        "bot-core": "http://localhost:8004/health",
        "execution": "http://localhost:8005/health",
    }


@pytest.fixture(scope="function")
def ensure_services_healthy(docker_services: dict[str, str]) -> None:
    """Ensure all services are healthy before running tests.
    
    Args:
        docker_services: Dictionary of service health URLs
        
    Raises:
        RuntimeError: If any service fails to become healthy
    """
    for service_name, health_url in docker_services.items():
        if not wait_for_service_health(health_url):
            raise RuntimeError(
                f"Service {service_name} did not become healthy within timeout. "
                f"Ensure services are running: docker-compose -f infra/docker-compose.yml "
                f"-f infra/docker-compose.services.yml -f infra/docker-compose.test.yml up -d"
            )


def make_candle(
    timestamp: datetime,
    symbol: str = "GC",
    timeframe: str = "1m",
    open_price: float = 2650.0,
    high_price: float = 2652.0,
    low_price: float = 2648.0,
    close_price: float = 2651.0,
    volume: float = 1000.0,
) -> CandleMessage:
    """Helper to create test candles.
    
    Args:
        timestamp: Candle timestamp
        symbol: Asset symbol
        timeframe: Candle timeframe
        open_price: Open price
        high_price: High price
        low_price: Low price
        close_price: Close price
        volume: Volume
        
    Returns:
        CandleMessage instance
    """
    return CandleMessage(
        timestamp=timestamp,
        symbol=symbol,
        timeframe=timeframe,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
    )


@pytest.fixture
def candle_factory():
    """Provide candle factory function for tests.
    
    Returns:
        Function that creates candles with sensible defaults
    """
    return make_candle

