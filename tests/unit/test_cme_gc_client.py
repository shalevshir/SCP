"""Tests for CMEGCClient stub."""

from datetime import datetime, timezone

import pytest

from common.exceptions import DataSourceError
from common.types import Candle
from data_layer.clients import CMEGCClient


def test_client_instantiation():
    """Test that CMEGCClient can be instantiated."""
    client = CMEGCClient()
    assert client is not None
    assert isinstance(client, CMEGCClient)


def test_client_has_fetch_method():
    """Test that client has fetch method."""
    client = CMEGCClient()
    assert hasattr(client, "fetch")
    assert callable(client.fetch)


def test_fetch_returns_list():
    """Test that fetch returns a list."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    result = client.fetch(start, end, "1m")

    assert isinstance(result, list)


def test_fetch_returns_list_of_candles():
    """Test that fetch returns list of Candle objects."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    result = client.fetch(start, end, "1m")

    # Should be a list (empty or with Candles)
    assert isinstance(result, list)
    # If not empty, all items should be Candles
    for item in result:
        assert isinstance(item, Candle)


def test_fetch_with_different_timeframes():
    """Test fetch with various timeframes."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    for timeframe in ["1m", "5m", "15m"]:
        result = client.fetch(start, end, timeframe)
        assert isinstance(result, list)


def test_fetch_with_valid_date_range():
    """Test fetch with valid date range."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

    result = client.fetch(start, end, "1m")

    assert isinstance(result, list)


def test_fetch_with_start_after_end_raises_error():
    """Test that start >= end raises DataSourceError."""
    client = CMEGCClient()
    start = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert "start" in str(exc_info.value).lower()
    assert "end" in str(exc_info.value).lower()


def test_fetch_with_same_start_and_end_raises_error():
    """Test that start == end raises DataSourceError."""
    client = CMEGCClient()
    timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(timestamp, timestamp, "1m")

    assert "start" in str(exc_info.value).lower()


def test_fetch_with_naive_start_datetime_raises_error():
    """Test that naive start datetime raises DataSourceError."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0)  # No timezone
    end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert (
        "timezone" in str(exc_info.value).lower()
        or "aware" in str(exc_info.value).lower()
    )


def test_fetch_with_naive_end_datetime_raises_error():
    """Test that naive end datetime raises DataSourceError."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, 0, 0, 0)  # No timezone

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert (
        "timezone" in str(exc_info.value).lower()
        or "aware" in str(exc_info.value).lower()
    )


def test_fetch_with_empty_timeframe_raises_error():
    """Test that empty timeframe raises DataSourceError."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "")

    assert "timeframe" in str(exc_info.value).lower()
    assert "empty" in str(exc_info.value).lower()


def test_fetch_with_whitespace_only_timeframe_raises_error():
    """Test that whitespace-only timeframe raises DataSourceError."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "   ")

    assert "timeframe" in str(exc_info.value).lower()


def test_fetch_stub_behavior():
    """Test that stub returns empty list (Phase 1 behavior)."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

    result = client.fetch(start, end, "1m")

    # Stub should return empty list
    assert result == []


def test_fetch_method_signature():
    """Test that fetch has the correct signature."""
    import inspect

    client = CMEGCClient()
    sig = inspect.signature(client.fetch)

    # Should have 3 parameters (plus self)
    params = list(sig.parameters.keys())
    assert "start" in params
    assert "end" in params
    assert "timeframe" in params

    # Check return annotation
    assert sig.return_annotation is not inspect.Signature.empty


def test_multiple_fetch_calls():
    """Test that client can handle multiple fetch calls."""
    client = CMEGCClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

    # Multiple calls should all work
    result1 = client.fetch(start, end, "1m")
    result2 = client.fetch(start, end, "5m")
    result3 = client.fetch(start, end, "15m")

    assert isinstance(result1, list)
    assert isinstance(result2, list)
    assert isinstance(result3, list)
