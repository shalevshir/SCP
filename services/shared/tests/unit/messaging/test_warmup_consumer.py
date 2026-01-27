"""Unit tests for warmup consumer utilities."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from scp_shared.messaging.warmup_consumer import check_warmup_available


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_warmup_available_returns_false_when_hash_missing() -> None:
    """Returns available=False when warmup:status hash doesn't exist."""
    mock_redis = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={})

    result = await check_warmup_available(mock_redis)

    assert result["available"] is False
    assert result["gc_ready"] is False
    assert result["dxy_ready"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_warmup_available_returns_true_when_complete() -> None:
    """Returns available=True when both GC and DXY marked complete."""
    mock_redis = AsyncMock()
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"gc": b"complete",
            b"dxy": b"complete",
            b"gc_count": b"1440",
            b"dxy_count": b"1440",
            b"timestamp": b"2025-01-27T10:00:00+00:00",
        }
    )

    result = await check_warmup_available(mock_redis)

    assert result["available"] is True
    assert result["gc_ready"] is True
    assert result["dxy_ready"] is True
    assert result["gc_count"] == 1440
    assert result["dxy_count"] == 1440


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_warmup_available_rejects_status_with_error_field() -> None:
    """Rejects warmup as unavailable when error field present.

    Regression test for bug where _set_error_status would leave gc/dxy
    completion markers from previous successful runs. The defensive check
    ensures consumers reject status with error field even if old success
    markers are present.
    """
    mock_redis = AsyncMock()

    # Simulate stale success markers + error field
    # (This scenario should never happen after fix, but we defend against it)
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"gc": b"complete",  # Stale from previous run
            b"dxy": b"complete",  # Stale from previous run
            b"gc_count": b"1440",  # Stale from previous run
            b"dxy_count": b"1440",  # Stale from previous run
            b"error": b"No GC candles fetched",  # Current run failed
            b"timestamp": b"2025-01-27T10:00:00+00:00",
        }
    )

    result = await check_warmup_available(mock_redis)

    # Should reject as unavailable due to error field
    assert result["available"] is False
    assert result["gc_ready"] is False
    assert result["dxy_ready"] is False
    assert result["gc_count"] == 0
    assert result["dxy_count"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_warmup_available_partial_completion() -> None:
    """Returns available=False when only one symbol completed."""
    mock_redis = AsyncMock()
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"gc": b"complete",
            b"dxy": b"pending",  # Not complete
            b"gc_count": b"1440",
            b"dxy_count": b"0",
        }
    )

    result = await check_warmup_available(mock_redis)

    assert result["available"] is False
    assert result["gc_ready"] is True
    assert result["dxy_ready"] is False
    assert result["gc_count"] == 1440
    assert result["dxy_count"] == 0
