"""Tests for LocalCSVClient negative value handling.

These tests verify that LocalCSVClient fails fast when encountering
invalid data (e.g., negative OHLC values) instead of silently skipping rows.
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from common.exceptions import DataSourceError, NormalizationError
from data_layer.clients import LocalCSVClient


def test_fetch_raises_error_on_negative_open():
    """Test that fetch raises DataSourceError when encountering negative open price."""
    # Create temporary CSV with negative open value
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,-100.0,105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "invalid data" in error_msg or "negative" in error_msg
        assert "open" in error_msg or "positive" in error_msg
        assert csv_path in str(exc_info.value) or "file" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_raises_error_on_negative_high():
    """Test that fetch raises DataSourceError when encountering negative high price."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,100.0,-105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "invalid data" in error_msg or "negative" in error_msg
        assert "high" in error_msg or "positive" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_raises_error_on_negative_low():
    """Test that fetch raises DataSourceError when encountering negative low price."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,100.0,105.0,-95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "invalid data" in error_msg or "negative" in error_msg
        assert "low" in error_msg or "positive" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_raises_error_on_negative_close():
    """Test that fetch raises DataSourceError when encountering negative close price."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,100.0,105.0,95.0,-102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "invalid data" in error_msg or "negative" in error_msg
        assert "close" in error_msg or "positive" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_raises_error_on_zero_price():
    """Test that fetch raises DataSourceError when encountering zero price."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,0.0,105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "invalid data" in error_msg or "positive" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_raises_error_on_invalid_ohlc_relationship():
    """Test that fetch raises DataSourceError when OHLC relationships are invalid."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # High < Low (invalid relationship)
        f.write("2025-01-01T12:00:00+00:00,100.0,95.0,105.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "invalid data" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_error_includes_row_information():
    """Test that DataSourceError includes detailed row information."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,-100.0,105.0,95.0,102.0,1000.0,DXY\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error = exc_info.value
        # Check that error includes row details
        error_str = str(error).lower()
        assert "dxy" in error_str or "symbol" in error_str
        assert "-100.0" in str(error) or "open" in error_str
        # Check that error has file_path attribute
        assert hasattr(error, "file_path")
        assert error.file_path == csv_path
    finally:
        Path(csv_path).unlink()


def test_fetch_error_chained_from_normalization_error():
    """Test that DataSourceError is properly chained from NormalizationError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,-100.0,105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        # Check that the exception is chained from NormalizationError
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, NormalizationError)
    finally:
        Path(csv_path).unlink()


def test_fetch_raises_error_on_missing_column():
    """Test that fetch raises DataSourceError when CSV is missing required columns."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume\n")  # Missing 'symbol' column
        f.write("2025-01-01T12:00:00+00:00,100.0,105.0,95.0,102.0,1000.0\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "failed to parse" in error_msg or "parse" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_raises_error_on_invalid_numeric_value():
    """Test that fetch raises DataSourceError when numeric values cannot be converted."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,invalid,105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "failed to parse" in error_msg or "parse" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_fails_on_first_invalid_row():
    """Test that fetch fails immediately on the first invalid row, not after processing all rows."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        f.write("2025-01-01T12:00:00+00:00,100.0,105.0,95.0,102.0,1000.0,GC\n")
        f.write("2025-01-01T12:01:00+00:00,-100.0,105.0,95.0,102.0,1000.0,GC\n")  # Invalid
        f.write("2025-01-01T12:02:00+00:00,100.0,105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        # Should fail on the second row (index 1), not process the third row
        error_msg = str(exc_info.value)
        # The error should reference row index 1 (second row)
        assert "row" in error_msg.lower()
    finally:
        Path(csv_path).unlink()


def test_fetch_validates_converted_numeric_values_not_strings():
    """Test that negative/zero validation uses converted numeric values, not original strings.
    
    This test verifies the fix for the bug where:
    - Line 384 converts column to numeric: numeric_col = pd.to_numeric(df[col], errors='coerce')
    - Line 406 incorrectly checked original column: df[df[col] <= 0]
    
    The bug meant that numeric string comparisons could fail silently.
    The fix ensures we validate numeric_col instead of df[col].
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # Write a negative value as a numeric string - should be caught after conversion
        f.write("2025-01-01T12:00:00+00:00,-50.0,105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        # This should raise DataSourceError because -50.0 is negative
        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        # Should detect negative value and mention open price or positive requirement
        assert ("open" in error_msg or "positive" in error_msg) and ("invalid" in error_msg or "negative" in error_msg)
    finally:
        Path(csv_path).unlink()


def test_fetch_validates_zero_after_numeric_conversion():
    """Test that zero validation works on converted numeric values."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # Zero value should be caught after numeric conversion
        f.write("2025-01-01T12:00:00+00:00,100.0,0.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        # This should raise DataSourceError because 0.0 is not positive
        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "positive" in error_msg or "high" in error_msg
    finally:
        Path(csv_path).unlink()


def test_fetch_rejects_nan_values_in_csv():
    """Test that NaN values already present in CSV are detected and rejected.
    
    This test verifies the fix for the bug where:
    - NaN values already in the CSV (not from failed conversion) were not caught
    - The check at line 387 only catches: numeric_col.isna() & df[col].notna()
      (values that became NaN during conversion, where original was not NaN)
    - The check at line 406: invalid_mask = numeric_col <= 0
      doesn't catch NaN because in pandas, NaN <= 0 evaluates to False
    
    The fix adds an explicit check for any NaN values in numeric_col.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # Write a row with NaN already in the data (pandas will read empty/NaN as NaN)
        # Use pandas NaN representation that will be read as NaN
        f.write("2025-01-01T12:00:00+00:00,100.0,105.0,,102.0,1000.0,GC\n")  # Empty low field
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        # This should raise DataSourceError because low is NaN/missing
        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        # Should detect missing/NaN value and mention the column
        assert ("nan" in error_msg or "missing" in error_msg or "invalid" in error_msg)
    finally:
        Path(csv_path).unlink()


def test_fetch_rejects_explicit_nan_string_in_csv():
    """Test that explicit 'NaN' string values in CSV are detected and rejected."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # Write explicit 'NaN' string - pandas will convert this to NaN
        f.write("2025-01-01T12:00:00+00:00,NaN,105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        # This should raise DataSourceError because open is NaN
        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert ("nan" in error_msg or "missing" in error_msg or "invalid" in error_msg)
    finally:
        Path(csv_path).unlink()

