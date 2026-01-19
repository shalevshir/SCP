"""Unit tests for cleanup_system.py resource management."""

from unittest.mock import AsyncMock, patch

import pytest


class TestGetDataCountsResourceManagement:
    """Test resource cleanup in get_data_counts function."""
    
    @pytest.mark.asyncio
    async def test_postgres_connection_closed_when_redis_fails(self):
        """Verify postgres connection is closed even if redis connection fails."""
        # Mock postgres connection
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=0)
        mock_conn.close = AsyncMock()
        
        # Mock successful postgres connect but failing redis connect
        with patch('asyncpg.connect', return_value=mock_conn) as mock_pg_connect:
            redis_error = ConnectionError("Redis connection failed")
            with patch('redis.asyncio.from_url', side_effect=redis_error):
                # Import after patching to get mocked version
                from scripts.cleanup_system import get_data_counts
                
                # Should raise the redis connection error
                with pytest.raises(ConnectionError, match="Redis connection failed"):
                    await get_data_counts()
                
                # Verify postgres connection was created
                mock_pg_connect.assert_called_once()
                
                # CRITICAL: Verify postgres connection was closed despite redis failure
                mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_both_connections_closed_on_success(self):
        """Verify both connections are closed on successful execution."""
        # Mock postgres connection
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=42)
        mock_conn.close = AsyncMock()
        
        # Mock redis client
        mock_redis = AsyncMock()
        mock_redis.xlen = AsyncMock(return_value=10)
        mock_redis.close = AsyncMock()
        
        # Create async mock for redis.from_url
        async def mock_redis_from_url(*args, **kwargs):
            return mock_redis
        
        with patch('asyncpg.connect', return_value=mock_conn):
            with patch('redis.asyncio.from_url', side_effect=mock_redis_from_url):
                from scripts.cleanup_system import get_data_counts
                
                result = await get_data_counts()
                
                # Verify both connections were closed
                mock_conn.close.assert_called_once()
                mock_redis.close.assert_called_once()
                
                # Verify data was collected
                assert "postgres" in result
                assert "redis" in result
    
    @pytest.mark.asyncio
    async def test_postgres_connection_closed_on_query_error(self):
        """Verify postgres connection is closed even if queries fail."""
        # Mock postgres connection with failing query
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(side_effect=Exception("Query failed"))
        mock_conn.close = AsyncMock()
        
        # Mock redis client
        mock_redis = AsyncMock()
        mock_redis.xlen = AsyncMock(return_value=0)
        mock_redis.close = AsyncMock()
        
        # Create async mock for redis.from_url
        async def mock_redis_from_url(*args, **kwargs):
            return mock_redis
        
        with patch('asyncpg.connect', return_value=mock_conn):
            with patch('redis.asyncio.from_url', side_effect=mock_redis_from_url):
                from scripts.cleanup_system import get_data_counts
                
                # Should succeed (exceptions caught internally)
                result = await get_data_counts()
                
                # Verify both connections were closed
                mock_conn.close.assert_called_once()
                mock_redis.close.assert_called_once()
                
                # Verify error was handled gracefully
                assert all(
                    count == "N/A" 
                    for count in result["postgres"].values()
                )
    
    @pytest.mark.asyncio
    async def test_redis_connection_closed_on_stream_error(self):
        """Verify redis connection is closed even if stream queries fail."""
        # Mock postgres connection
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=5)
        mock_conn.close = AsyncMock()
        
        # Mock redis client with failing xlen
        mock_redis = AsyncMock()
        mock_redis.xlen = AsyncMock(side_effect=Exception("Stream error"))
        mock_redis.close = AsyncMock()
        
        # Create async mock for redis.from_url
        async def mock_redis_from_url(*args, **kwargs):
            return mock_redis
        
        with patch('asyncpg.connect', return_value=mock_conn):
            with patch('redis.asyncio.from_url', side_effect=mock_redis_from_url):
                from scripts.cleanup_system import get_data_counts
                
                # Should succeed (exceptions caught internally)
                result = await get_data_counts()
                
                # Verify both connections were closed
                mock_conn.close.assert_called_once()
                mock_redis.close.assert_called_once()
                
                # Verify error was handled gracefully (defaulted to 0)
                assert all(
                    count == 0 
                    for count in result["redis"].values()
                )
