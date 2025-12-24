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
    
    Connects to Redis on port specified by REDIS_PORT env var:
    - Local development (default): 6379 (same as services via launch.json)
    - CI/Docker: 6380 (test Redis via docker-compose.test.yml)
    
    Yields:
        Redis client for integration tests
    """
    import os
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    
    client = redis.Redis(
        host="localhost",
        port=redis_port,
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
    
    Connects to PostgreSQL using DATABASE_URL env var or defaults:
    - Local development (default): port 5432 with scp/scp_dev_password
    - CI/Docker: port 5433 with scp_test/scp_test_password
    
    Yields:
        Database pool for integration tests
    """
    import os
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://scp:scp_dev_password@localhost:5432/scp"  # Match launch.json
    )
    pool = DatabasePool(database_url)
    
    try:
        await pool.connect()
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture(scope="function")
async def clean_streams(redis_client: redis.Redis) -> None:
    """Clean Redis streams before each test.
    
    Uses XTRIM to clear messages while preserving consumer groups.
    This is critical because messages published BEFORE a consumer group
    is created are NOT delivered to that group.
    
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
            # Use XTRIM to remove all messages but keep consumer groups intact
            # MAXLEN 0 removes all entries
            await redis_client.xtrim(stream, maxlen=0)
        except Exception:
            # Stream might not exist, that's ok
            pass
    
    # Also acknowledge any pending messages in consumer groups
    # to prevent them from being redelivered
    # Include both service consumer groups and test consumer groups
    consumer_groups = [
        # Service consumer groups
        ("signals.pending", "execution"),
        ("candles.1m.gc", "execution"),
        ("features.1m", "execution"),
        ("candles.1m.gc", "feature-engine"),
        ("candles.1m.dxy", "feature-engine"),
        ("features.1m", "htf-bias"),
        # Test consumer groups (various tests use different group names)
        ("trades.opened", "integration-test-trades"),
        ("trades.opened", "integration-test-sl"),
        ("trades.opened", "integration-test-tp"),
        ("trades.opened", "integration-test-invalid-opened"),
        ("trades.opened", "integration-test-pipeline"),
        ("trades.closed", "integration-test-sl-closed"),
        ("trades.closed", "integration-test-tp-closed"),
        ("trades.closed", "integration-test-invalid"),
        ("trades.closed", "integration-test-pipeline-closed"),
        ("htf.bias", "integration-test-bias"),
        ("htf.bias", "integration-test-structure"),
        ("htf.bias", "integration-test-chop"),
        ("htf.bias", "integration-test-timestamp"),
        ("features.1m", "integration-test"),
        ("features.1m", "integration-test-corr"),
        ("features.1m", "integration-test-ts"),
    ]
    
    for stream, group in consumer_groups:
        try:
            # Get pending messages and acknowledge them
            # xpending returns dict with 'pending' count or similar structure
            pending = await redis_client.xpending(stream, group)
            # Handle various response formats
            pending_count = 0
            if isinstance(pending, dict):
                pending_count = pending.get("pending", 0)
            elif isinstance(pending, (list, tuple)) and len(pending) > 0:
                # Some versions return [count, first_id, last_id, consumers]
                pending_count = pending[0] if isinstance(pending[0], int) else 0
            
            if pending_count > 0:
                # Read and ack all pending
                messages = await redis_client.xreadgroup(
                    groupname=group,
                    consumername="cleanup",
                    streams={stream: "0"},
                    count=1000,
                )
                if messages:
                    for _, stream_messages in messages:
                        for msg_id, _ in stream_messages:
                            await redis_client.xack(stream, group, msg_id)
        except Exception:
            # Group might not exist, that's ok
            pass
    
    # Wait briefly for services to complete any in-flight reads
    # This ensures services are in a clean state before test proceeds
    await asyncio.sleep(0.5)


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

