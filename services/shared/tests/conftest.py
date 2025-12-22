"""Pytest fixtures for shared library tests."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import redis.asyncio as redis
from fakeredis import aioredis as fakeredis


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Provide fake Redis client for testing."""
    client = fakeredis.FakeRedis(decode_responses=False)
    yield client
    await client.flushall()
    await client.aclose()

