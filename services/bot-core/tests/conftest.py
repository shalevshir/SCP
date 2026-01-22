"""Pytest configuration and fixtures for bot-core tests."""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from scp_shared.database import DatabasePool


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_pool() -> AsyncGenerator[DatabasePool, None]:
    """Provide database pool connected to test PostgreSQL.
    
    Connects to PostgreSQL using DATABASE_URL env var or defaults to local dev database.
    
    Yields:
        Database pool for unit tests
    """
    import os
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://scp:scp_dev_password@localhost:5432/scp"
    )
    pool = DatabasePool(database_url)
    
    try:
        await pool.connect()
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture(scope="function")
async def clean_database(db_pool: DatabasePool) -> None:
    """Clean signal_history table before each test.
    
    Args:
        db_pool: Database pool fixture
    """
    try:
        await db_pool.execute("TRUNCATE TABLE signal_history CASCADE")
    except Exception:
        # Table might not exist yet (before migration), that's ok
        pass


@pytest.fixture
def sample_context() -> dict:
    """Sample context for signal generation."""
    return {
        "session_ok": True,
        "enforcer_tier": "Conservative",
    }

