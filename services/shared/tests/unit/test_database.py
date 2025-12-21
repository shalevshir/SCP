"""Tests for database connection utilities.

Note: These are minimal tests since we'd need a real database for full integration tests.
For now, we test the interface and error handling.
"""

import pytest

from scp_shared.database.connection import DatabasePool


class TestDatabasePool:
    """Test DatabasePool interface."""

    def test_pool_initialization(self) -> None:
        """DatabasePool can be initialized with DSN."""
        pool = DatabasePool("postgresql://user:pass@localhost/db")

        assert pool.dsn == "postgresql://user:pass@localhost/db"
        assert pool.min_size == 5
        assert pool.max_size == 20

    def test_pool_with_custom_sizes(self) -> None:
        """DatabasePool accepts custom pool sizes."""
        pool = DatabasePool(
            "postgresql://user:pass@localhost/db",
            min_size=2,
            max_size=10,
        )

        assert pool.min_size == 2
        assert pool.max_size == 10

    @pytest.mark.asyncio
    async def test_pool_not_connected_raises_error(self) -> None:
        """Attempting to use pool before connect() raises error."""
        pool = DatabasePool("postgresql://user:pass@localhost/db")

        with pytest.raises(RuntimeError, match="not connected"):
            _ = pool.acquire()

    @pytest.mark.asyncio
    async def test_pool_close_without_connect_is_safe(self) -> None:
        """Calling close() without connect() is safe."""
        pool = DatabasePool("postgresql://user:pass@localhost/db")

        # Should not raise
        await pool.close()

