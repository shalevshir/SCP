"""Unit tests for consumer group management utilities."""

import pytest
from unittest.mock import AsyncMock, MagicMock
import redis.asyncio as redis

from scp_shared.messaging.consumer_group import (
    create_consumer_group,
    delete_consumer_group,
    get_consumer_group_info,
    get_stream_length,
)


class TestCreateConsumerGroup:
    """Tests for create_consumer_group function."""

    @pytest.mark.asyncio
    async def test_creates_group_successfully(self) -> None:
        """Successfully creates a consumer group."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xgroup_create = AsyncMock(return_value=True)
        
        result = await create_consumer_group(
            redis_client=mock_client,
            stream="test-stream",
            group="test-group",
        )
        
        assert result is True
        mock_client.xgroup_create.assert_called_once_with(
            "test-stream",
            "test-group",
            id="0",
            mkstream=True,
        )

    @pytest.mark.asyncio
    async def test_creates_group_with_custom_start_id(self) -> None:
        """Creates group with custom start ID."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xgroup_create = AsyncMock(return_value=True)
        
        result = await create_consumer_group(
            redis_client=mock_client,
            stream="test-stream",
            group="test-group",
            start_id="$",
        )
        
        assert result is True
        mock_client.xgroup_create.assert_called_once_with(
            "test-stream",
            "test-group",
            id="$",
            mkstream=True,
        )

    @pytest.mark.asyncio
    async def test_returns_false_when_group_exists(self) -> None:
        """Returns False when group already exists."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xgroup_create = AsyncMock(
            side_effect=redis.ResponseError("BUSYGROUP Consumer group name already exists")
        )
        
        result = await create_consumer_group(
            redis_client=mock_client,
            stream="test-stream",
            group="test-group",
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_other_errors(self) -> None:
        """Raises exception for non-BUSYGROUP errors."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xgroup_create = AsyncMock(
            side_effect=redis.ResponseError("WRONGTYPE Operation against a key holding wrong kind of value")
        )
        
        with pytest.raises(redis.ResponseError, match="WRONGTYPE"):
            await create_consumer_group(
                redis_client=mock_client,
                stream="test-stream",
                group="test-group",
            )


class TestDeleteConsumerGroup:
    """Tests for delete_consumer_group function."""

    @pytest.mark.asyncio
    async def test_deletes_group_successfully(self) -> None:
        """Successfully deletes a consumer group."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xgroup_destroy = AsyncMock(return_value=1)
        
        result = await delete_consumer_group(
            redis_client=mock_client,
            stream="test-stream",
            group="test-group",
        )
        
        assert result is True
        mock_client.xgroup_destroy.assert_called_once_with("test-stream", "test-group")

    @pytest.mark.asyncio
    async def test_returns_false_when_group_not_found(self) -> None:
        """Returns False when group doesn't exist."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xgroup_destroy = AsyncMock(return_value=0)
        
        result = await delete_consumer_group(
            redis_client=mock_client,
            stream="test-stream",
            group="test-group",
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self) -> None:
        """Returns False on Redis error."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xgroup_destroy = AsyncMock(
            side_effect=redis.ResponseError("Some error")
        )
        
        result = await delete_consumer_group(
            redis_client=mock_client,
            stream="test-stream",
            group="test-group",
        )
        
        assert result is False


class TestGetConsumerGroupInfo:
    """Tests for get_consumer_group_info function."""

    @pytest.mark.asyncio
    async def test_returns_group_info(self) -> None:
        """Returns consumer group information."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_info = [
            {"name": "group1", "consumers": 2, "pending": 10},
            {"name": "group2", "consumers": 1, "pending": 5},
        ]
        mock_client.xinfo_groups = AsyncMock(return_value=mock_info)
        
        result = await get_consumer_group_info(
            redis_client=mock_client,
            stream="test-stream",
        )
        
        assert result == mock_info
        mock_client.xinfo_groups.assert_called_once_with("test-stream")

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_stream_not_found(self) -> None:
        """Returns empty list when stream doesn't exist."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xinfo_groups = AsyncMock(
            side_effect=redis.ResponseError("ERR no such key")
        )
        
        result = await get_consumer_group_info(
            redis_client=mock_client,
            stream="test-stream",
        )
        
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_error(self) -> None:
        """Returns empty list on any Redis error."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xinfo_groups = AsyncMock(
            side_effect=redis.ResponseError("Some other error")
        )
        
        result = await get_consumer_group_info(
            redis_client=mock_client,
            stream="test-stream",
        )
        
        assert result == []


class TestGetStreamLength:
    """Tests for get_stream_length function."""

    @pytest.mark.asyncio
    async def test_returns_stream_length(self) -> None:
        """Returns the number of messages in stream."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xlen = AsyncMock(return_value=42)
        
        result = await get_stream_length(
            redis_client=mock_client,
            stream="test-stream",
        )
        
        assert result == 42
        mock_client.xlen.assert_called_once_with("test-stream")

    @pytest.mark.asyncio
    async def test_returns_zero_when_stream_empty(self) -> None:
        """Returns 0 when stream is empty."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xlen = AsyncMock(return_value=0)
        
        result = await get_stream_length(
            redis_client=mock_client,
            stream="test-stream",
        )
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_stream_not_found(self) -> None:
        """Returns 0 when stream doesn't exist (xlen returns None)."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.xlen = AsyncMock(return_value=None)
        
        result = await get_stream_length(
            redis_client=mock_client,
            stream="test-stream",
        )
        
        assert result == 0
