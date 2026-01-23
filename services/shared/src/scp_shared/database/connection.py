"""Database connection pool management."""

from typing import Any

import asyncpg


class DatabasePool:
    """Async PostgreSQL connection pool wrapper.

    Example:
        >>> db_pool = DatabasePool("postgresql://user:pass@localhost/db")
        >>> await db_pool.connect()
        >>> async with db_pool.acquire() as conn:
        ...     result = await conn.fetchrow("SELECT 1")
        >>> await db_pool.close()
    """

    def __init__(self, dsn: str, min_size: int = 5, max_size: int = 20) -> None:
        """Initialize database pool.

        Args:
            dsn: Database connection string
            min_size: Minimum pool connections
            max_size: Maximum pool connections
        """
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=self.min_size,
                max_size=self.max_size,
            )

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    def acquire(self) -> Any:
        """Acquire a connection from the pool.

        Returns:
            Async context manager for connection

        Raises:
            RuntimeError: If pool not connected
        """
        if not self._pool:
            raise RuntimeError("Database pool not connected. Call connect() first.")
        return self._pool.acquire()

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a query and return status.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Query execution status string
        """
        if not self._pool:
            raise RuntimeError("Database pool not connected. Call connect() first.")
        return await self._pool.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Fetch all rows from a query.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            List of records
        """
        if not self._pool:
            raise RuntimeError("Database pool not connected. Call connect() first.")
        return await self._pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """Fetch a single row from a query.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single record or None
        """
        if not self._pool:
            raise RuntimeError("Database pool not connected. Call connect() first.")
        return await self._pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Fetch a single value from a query.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single value
        """
        if not self._pool:
            raise RuntimeError("Database pool not connected. Call connect() first.")
        return await self._pool.fetchval(query, *args)


# Global pool instance (optional, for simple use cases)
_global_pool: DatabasePool | None = None


async def get_db_pool(dsn: str) -> DatabasePool:
    """Get or create global database pool.

    Args:
        dsn: Database connection string

    Returns:
        Connected database pool
    """
    global _global_pool
    if _global_pool is None:
        _global_pool = DatabasePool(dsn)
        await _global_pool.connect()
    return _global_pool
