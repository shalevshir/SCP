"""Tests for DXYIndexClient stub."""

from datetime import UTC, datetime

import pytest
from common.exceptions import DataSourceError
from common.types import Candle
from data_layer.clients import DXYIndexClient


def test_client_instantiation():
    """Test that DXYIndexClient can be instantiated."""
    client = DXYIndexClient()
    assert client is not None
    assert isinstance(client, DXYIndexClient)


def test_client_has_fetch_method():
    """Test that client has fetch method."""
    client = DXYIndexClient()
    assert hasattr(client, "fetch")
    assert callable(client.fetch)


def test_fetch_returns_list():
    """Test that fetch returns a list."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    result = client.fetch(start, end, "1m")

    assert isinstance(result, list)


def test_fetch_returns_list_of_candles():
    """Test that fetch returns list of Candle objects."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    result = client.fetch(start, end, "1m")

    # Should be a list (empty or with Candles)
    assert isinstance(result, list)
    # If not empty, all items should be Candles
    for item in result:
        assert isinstance(item, Candle)


def test_stub_returns_empty_list():
    """Test that stub implementation returns empty list."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    result = client.fetch(start, end, "1m")

    # Stub should return empty list in Phase 1
    assert result == []


def test_fetch_with_naive_start_datetime_raises_error():
    """Test that fetch raises DataSourceError for naive start datetime."""
    client = DXYIndexClient()
    # Naive datetime (no timezone)
    start = datetime(2025, 1, 1, 0, 0, 0)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert "timezone-aware" in str(exc_info.value).lower()
    assert hasattr(exc_info.value, "symbol")
    assert exc_info.value.symbol == "DXY"


def test_fetch_with_naive_end_datetime_raises_error():
    """Test that fetch raises DataSourceError for naive end datetime."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    # Naive datetime (no timezone)
    end = datetime(2025, 1, 1, 23, 59, 59)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert "timezone-aware" in str(exc_info.value).lower()
    assert hasattr(exc_info.value, "symbol")
    assert exc_info.value.symbol == "DXY"


def test_fetch_with_start_after_end_raises_error():
    """Test that fetch raises DataSourceError when start >= end."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert "before" in str(exc_info.value).lower()
    assert hasattr(exc_info.value, "symbol")
    assert exc_info.value.symbol == "DXY"


def test_fetch_with_start_equal_to_end_raises_error():
    """Test that fetch raises DataSourceError when start == end."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert "before" in str(exc_info.value).lower()


def test_fetch_with_empty_timeframe_raises_error():
    """Test that fetch raises DataSourceError for empty timeframe."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "")

    assert "timeframe" in str(exc_info.value).lower()
    assert "empty" in str(exc_info.value).lower()
    assert hasattr(exc_info.value, "symbol")
    assert exc_info.value.symbol == "DXY"


def test_fetch_with_whitespace_timeframe_raises_error():
    """Test that fetch raises DataSourceError for whitespace-only timeframe."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "   ")

    assert "timeframe" in str(exc_info.value).lower()
    assert "empty" in str(exc_info.value).lower()


def test_fetch_with_different_timeframes():
    """Test that fetch works with various valid timeframes."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    timeframes = ["1m", "5m", "15m", "1h", "1d"]

    for timeframe in timeframes:
        result = client.fetch(start, end, timeframe)
        assert isinstance(result, list)
        # Stub returns empty list
        assert result == []


def test_multiple_fetch_calls():
    """Test that multiple fetch calls work correctly."""
    client = DXYIndexClient()
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    # First call
    result1 = client.fetch(start, end, "1m")
    assert result1 == []

    # Second call
    result2 = client.fetch(start, end, "5m")
    assert result2 == []

    # Results should be independent
    assert result1 == result2 == []


def test_fetch_signature_matches_expected():
    """Test that fetch method has the expected signature."""
    client = DXYIndexClient()

    # Get the fetch method
    fetch_method = client.fetch

    # Check it accepts the expected parameters
    import inspect

    sig = inspect.signature(fetch_method)
    params = list(sig.parameters.keys())

    assert "start" in params
    assert "end" in params
    assert "timeframe" in params
