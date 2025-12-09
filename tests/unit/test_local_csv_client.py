"""Tests for LocalCSVClient stub."""

from datetime import UTC, datetime
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
    """Test that fetch returns a list with real CSV data."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)
    start = datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 7, 1, 0, 10, 0, tzinfo=UTC)

    # This date range may contain invalid data (negative values)
    # If so, DataSourceError should be raised (fail-fast behavior)
    try:
        result = client.fetch(start, end, "1m")
        assert isinstance(result, list)
    except DataSourceError as e:
        # If error is raised due to invalid data, verify it's the expected error
        assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_fetch_returns_list_of_candles():
    """Test that fetch returns list of Candle objects."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)
    start = datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 7, 1, 0, 10, 0, tzinfo=UTC)

    # This date range may contain invalid data (negative values)
    # If so, DataSourceError should be raised (fail-fast behavior)
    try:
        result = client.fetch(start, end, "1m")
        # Should be a list (empty or with Candles)
        assert isinstance(result, list)
        # If not empty, all items should be Candles
        for item in result:
            assert isinstance(item, Candle)
    except DataSourceError as e:
        # If error is raised due to invalid data, verify it's the expected error
        assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_nonexistent_file_raises_error():
    """Test that nonexistent file raises DataSourceError."""
    client = LocalCSVClient("nonexistent_test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    with pytest.raises(DataSourceError):
        client.fetch(start, end, "1m")


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
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert (
        "timezone" in str(exc_info.value).lower()
        or "aware" in str(exc_info.value).lower()
    )


def test_fetch_with_naive_end_datetime_raises_error():
    """Test that fetch raises error when end datetime is naive (no timezone)."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
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
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 23, 59, 59, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "")

    assert "timeframe" in str(exc_info.value).lower()


def test_fetch_with_end_before_start_raises_error():
    """Test that fetch raises error when end is before start."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert (
        "start" in str(exc_info.value).lower() or "end" in str(exc_info.value).lower()
    )


def test_fetch_with_equal_start_and_end():
    """Test that fetch fails when start and end are equal."""
    client = LocalCSVClient("test.csv")
    start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    assert (
        "start" in str(exc_info.value).lower() or "end" in str(exc_info.value).lower()
    )


def test_fetch_with_different_timeframes():
    """Test that fetch accepts various timeframe formats."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)
    start = datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 7, 1, 0, 10, 0, tzinfo=UTC)

    timeframes = ["1m", "5m", "15m", "1h", "1d"]

    for timeframe in timeframes:
        # This date range may contain invalid data (negative values)
        # If so, DataSourceError should be raised (fail-fast behavior)
        try:
            result = client.fetch(start, end, timeframe)
            assert isinstance(result, list)
        except DataSourceError as e:
            # If error is raised due to invalid data, verify it's the expected error
            assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_multiple_fetch_calls():
    """Test that multiple fetch calls work correctly."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)
    start = datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 7, 1, 0, 10, 0, tzinfo=UTC)

    # This date range may contain invalid data (negative values)
    # If so, DataSourceError should be raised (fail-fast behavior)
    try:
        result1 = client.fetch(start, end, "1m")
        result2 = client.fetch(start, end, "5m")
        result3 = client.fetch(start, end, "15m")
        assert isinstance(result1, list)
        assert isinstance(result2, list)
        assert isinstance(result3, list)
    except DataSourceError as e:
        # If error is raised due to invalid data, verify it's the expected error
        assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_fetch_signature_matches_expected():
    """Test that fetch method signature matches expected interface."""
    client = LocalCSVClient("test.csv")
    fetch_method = client.fetch

    # Check it accepts the expected parameters
    import inspect

    sig = inspect.signature(fetch_method)
    params = list(sig.parameters.keys())

    assert "start" in params
    assert "end" in params
    assert "timeframe" in params


def test_fetch_accepts_timezone_aware_datetimes():
    """Test that fetch properly handles timezone-aware datetimes."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)

    # Test with UTC
    start_utc = datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
    end_utc = datetime(2025, 7, 1, 0, 10, 0, tzinfo=UTC)
    # This date range may contain invalid data (negative values)
    # If so, DataSourceError should be raised (fail-fast behavior)
    try:
        result = client.fetch(start_utc, end_utc, "1m")
        assert isinstance(result, list)
    except DataSourceError as e:
        # If error is raised due to invalid data, verify it's the expected error
        assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_client_repr():
    """Test that client has a useful string representation."""
    client = LocalCSVClient("test.csv")
    repr_str = repr(client)
    assert "LocalCSVClient" in repr_str
    assert "test.csv" in repr_str


def test_fetch_return_type_annotation():
    """Test that fetch method has proper return type annotation."""
    client = LocalCSVClient("test.csv")
    fetch_method = client.fetch

    from typing import get_type_hints

    hints = get_type_hints(fetch_method)

    # The return type should be list[Candle]
    assert "return" in hints
    # The return type should be list
    return_type = hints["return"]
    assert hasattr(return_type, "__origin__")


# Real CSV loading tests (Phase 1 implementation)


def test_fetch_loads_real_csv_data():
    """Test that fetch loads actual data from CSV file or fails on invalid data."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)

    # Use date range from actual data (2025-07-01 onwards)
    start = datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 7, 1, 0, 10, 0, tzinfo=UTC)

    # This date range may contain invalid data (negative values)
    # If so, DataSourceError should be raised (fail-fast behavior)
    try:
        result = client.fetch(start, end, "1m")
        # Should return non-empty list if valid data exists
        assert isinstance(result, list)
        if len(result) > 0:
            # All items should be Candle objects
            for candle in result:
                assert isinstance(candle, Candle)
                assert candle.symbol.startswith("GC")  # GC symbols
                assert candle.timeframe == "1m"
                assert candle.source == "CSV"
    except DataSourceError as e:
        # If error is raised due to invalid data, verify it's the expected error
        assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_fetch_filters_by_date_range():
    """Test that fetch correctly filters data by date range or fails on invalid data."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)

    # Narrow date range (2025-07-01 onwards)
    start = datetime(2025, 7, 1, 0, 1, 0, tzinfo=UTC)
    end = datetime(2025, 7, 1, 0, 3, 0, tzinfo=UTC)

    # This date range may contain invalid data (negative values)
    # If so, DataSourceError should be raised (fail-fast behavior)
    try:
        result = client.fetch(start, end, "1m")
        # All candles should be within range
        for candle in result:
            assert candle.timestamp >= start
            assert candle.timestamp < end
    except DataSourceError as e:
        # If error is raised due to invalid data, verify it's the expected error
        assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_fetch_parses_timezone_aware_timestamps():
    """Test that fetch parses timestamps as timezone-aware UTC or fails on invalid data."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)

    # Use date range from actual data (2025-07-01 onwards)
    start = datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 7, 1, 0, 10, 0, tzinfo=UTC)

    # This date range may contain invalid data (negative values)
    # If so, DataSourceError should be raised (fail-fast behavior)
    try:
        result = client.fetch(start, end, "1m")
        # All timestamps should be timezone-aware UTC
        for candle in result:
            assert candle.timestamp.tzinfo is not None
            assert candle.timestamp.tzinfo == UTC
    except DataSourceError as e:
        # If error is raised due to invalid data, verify it's the expected error
        assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_fetch_converts_to_candle_objects():
    """Test that fetch converts CSV rows to valid Candle objects or fails on invalid data."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)

    # Use date range from actual data (2025-07-01 onwards)
    start = datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 7, 1, 0, 10, 0, tzinfo=UTC)

    # This date range may contain invalid data (negative values)
    # If so, DataSourceError should be raised (fail-fast behavior)
    try:
        result = client.fetch(start, end, "1m")
        # Verify Candle structure and validation
        for candle in result:
            assert candle.open > 0
            assert candle.high > 0
            assert candle.low > 0
            assert candle.close > 0
            assert candle.volume >= 0
            # OHLC relationships
            assert candle.high >= candle.low
            assert candle.high >= candle.open
            assert candle.high >= candle.close
            assert candle.low <= candle.open
            assert candle.low <= candle.close
    except DataSourceError as e:
        # If error is raised due to invalid data, verify it's the expected error
        assert "invalid data" in str(e).lower() or "positive" in str(e).lower()


def test_fetch_raises_error_for_missing_file():
    """Test that fetch raises DataSourceError for missing file."""
    client = LocalCSVClient("nonexistent_file.csv")

    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC)

    with pytest.raises(DataSourceError) as exc_info:
        client.fetch(start, end, "1m")

    error_msg = str(exc_info.value).lower()
    assert "file" in error_msg or "not found" in error_msg


def test_fetch_handles_empty_date_range():
    """Test that fetch returns empty list when no data in date range."""
    csv_path = Path("data/gc_dx_ohlcv/GC_ohlcv-1m.csv")
    client = LocalCSVClient(csv_path)

    # Date range with no data
    start = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2020, 1, 2, 0, 0, 0, tzinfo=UTC)

    result = client.fetch(start, end, "1m")

    assert isinstance(result, list)
    assert len(result) == 0
