"""Tests for LocalCSVClient stub."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from common.exceptions import DataSourceError
from common.types import Candle
from data_layer.clients import LocalCSVClient


def test_client_instantiation():
    """Test that LocalCSVClient can be instantiated."""
    client = LocalCSVClient("test.csv")
    assert client is not None
    assert isinstance(client, LocalCSVClient)


def test_client_stores_file_path():
    """Test that client stores the file path."""
    file_path = "data/gold_futures.csv"
    client = LocalCSVClient(file_path)
    assert client.file_path == file_path


def test_client_accepts_path_object():
    """Test that client accepts Path objects."""
    file_path = Path("data/gold_futures.csv")
    client = LocalCSVClient(file_path)
    assert client.file_path == str(file_path)


def test_client_has_fetch_method():
    """Test that client has fetch method."""
    client = LocalCSVClient("test.csv")
    assert hasattr(client, "fetch")
    assert callable(client.fetch)


def test_fetch_returns_list():
    """Test that fetch returns a list."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    result = client.fetch(start, end, "1m")

    assert isinstance(result, list)


def test_fetch_returns_list_of_candles():
    """Test that fetch returns list of Candle objects."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    result = client.fetch(start, end, "1m")

    # Should be a list (empty or with Candles)
    assert isinstance(result, list)
    # If not empty, all items should be Candles
    for item in result:
        assert isinstance(item, Candle)


def test_stub_returns_empty_list():
    """Test that stub implementation returns empty list.

    This verifies Phase 1 behavior where the stub returns an empty list
    instead of actually reading from CSV files.
    """
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    result = client.fetch(start, end, "1m")

    assert result == []


def test_fetch_with_invalid_file_path_type():
    """Test that client raises error for invalid file_path type."""
    with pytest.raises(DataSourceError) as exc_info:
        LocalCSVClient(123)  # type: ignore

    assert "file_path" in str(exc_info.value).lower()


def test_fetch_with_empty_file_path():
    """Test that client raises error for empty file path."""
    with pytest.raises(DataSourceError) as exc_info:
        LocalCSVClient("")

    assert "file_path" in str(exc_info.value).lower()


def test_fetch_with_naive_start_datetime_raises_error():
    """Test that fetch raises error when start datetime is naive (no timezone)."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0)  # No timezone
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert (
        "timezone" in str(exc_info.value).lower()
        or "aware" in str(exc_info.value).lower()
    )


def test_fetch_with_naive_end_datetime_raises_error():
    """Test that fetch raises error when end datetime is naive (no timezone)."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59)  # No timezone

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert (
        "timezone" in str(exc_info.value).lower()
        or "aware" in str(exc_info.value).lower()
    )


def test_fetch_with_empty_timeframe_raises_error():
    """Test that fetch raises error for empty timeframe."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "")

    assert "timeframe" in str(exc_info.value).lower()


def test_fetch_with_end_before_start_raises_error():
    """Test that fetch raises error when end is before start."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert "start" in str(exc_info.value).lower() or "end" in str(
        exc_info.value
    ).lower()


def test_fetch_with_equal_start_and_end():
    """Test that fetch handles equal start and end datetimes."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Should not raise error, but return empty list (stub behavior)
    result = client.fetch(start, end, "1m")
    assert isinstance(result, list)


def test_fetch_with_different_timeframes():
    """Test that fetch accepts various timeframe formats."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    timeframes = ["1m", "5m", "15m", "1h", "1d"]

    for timeframe in timeframes:
        result = client.fetch(start, end, timeframe)
        assert isinstance(result, list)


def test_multiple_fetch_calls():
    """Test that multiple fetch calls work correctly."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)

    result1 = client.fetch(start, end, "1m")
    result2 = client.fetch(start, end, "5m")
    result3 = client.fetch(start, end, "15m")

    assert isinstance(result1, list)
    assert isinstance(result2, list)
    assert isinstance(result3, list)


def test_fetch_signature_matches_expected():
    """Test that fetch method signature matches expected interface."""
    client = LocalCSVClient("test.csv")
    fetch_method = getattr(client, "fetch")

    # Check it accepts the expected parameters
    import inspect

    sig = inspect.signature(fetch_method)
    params = list(sig.parameters.keys())

    assert "start" in params
    assert "end" in params
    assert "timeframe" in params


def test_fetch_accepts_timezone_aware_datetimes():
    """Test that fetch properly handles timezone-aware datetimes."""
    client = LocalCSVClient("test.csv")

    # Test with UTC
    start_utc = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(2025, 1, 1, 23, 59, 59, tzinfo=timezone.utc)
    result = client.fetch(start_utc, end_utc, "1m")
    assert isinstance(result, list)


def test_client_repr():
    """Test that client has a useful string representation."""
    client = LocalCSVClient("test.csv")
    repr_str = repr(client)
    assert "LocalCSVClient" in repr_str
    assert "test.csv" in repr_str


def test_fetch_return_type_annotation():
    """Test that fetch method has proper return type annotation."""
    client = LocalCSVClient("test.csv")
    fetch_method = getattr(client, "fetch")

    import inspect
    from typing import get_type_hints

    hints = get_type_hints(fetch_method)

    # The return type should be list[Candle]
    assert "return" in hints
    # The return type should be list
    return_type = hints["return"]
    assert hasattr(return_type, "__origin__")

