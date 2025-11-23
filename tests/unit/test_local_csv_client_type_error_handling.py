"""Test that the overly broad except TypeError: pass has been removed.

This test verifies the fix for the bug where:
- The `except TypeError: pass` block caught TypeErrors from the entire validation
  logic (lines 382-452), not just from comparison operations
- If a TypeError occurred during exception creation, data validation checks, or
  any other operation in this block, it would be silently ignored
- This allowed invalid data to pass through validation undetected

The fix:
- Remove the overly broad try-except block entirely
- pd.to_numeric(..., errors='coerce') already handles mixed types gracefully
- Any TypeError in the validation block is a real bug that should surface

Red-Green-Refactor:
1. Red: Verify validation still works correctly for negative/invalid values
2. Green: Remove try-except block
3. Refactor: Tests pass and validation is explicit
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from common.exceptions import DataSourceError
from data_layer.clients import LocalCSVClient


def test_validation_detects_negative_values_correctly():
    """Test that negative price validation works correctly.
    
    This test verifies that after removing the try-except block,
    validation still correctly detects negative values.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # Negative open price should be caught
        f.write("2025-01-01T12:00:00+00:00,-100.0,105.0,95.0,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        # Should raise DataSourceError about negative value
        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "positive" in error_msg or "open" in error_msg
        
    finally:
        Path(csv_path).unlink()


def test_validation_detects_zero_values_correctly():
    """Test that zero price validation works correctly."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # Zero close price should be caught
        f.write("2025-01-01T12:00:00+00:00,100.0,105.0,95.0,0.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        # Should raise DataSourceError about zero value
        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "positive" in error_msg or "close" in error_msg
        
    finally:
        Path(csv_path).unlink()


def test_numeric_conversion_handles_mixed_types_gracefully():
    """Test that pd.to_numeric with errors='coerce' handles mixed types correctly.
    
    This verifies that we don't need a try-except for mixed types since
    pd.to_numeric(..., errors='coerce') already handles them gracefully.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # Mixed type data - pandas will read this but conversion should detect it
        f.write("2025-01-01T12:00:00+00:00,100.0,105.0,not_a_number,102.0,1000.0,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        # Should raise DataSourceError about non-numeric value, not TypeError
        with pytest.raises(DataSourceError) as exc_info:
            client.fetch(start, end, "1m")

        error_msg = str(exc_info.value).lower()
        assert "non-numeric" in error_msg or "invalid" in error_msg
        
    finally:
        Path(csv_path).unlink()


def test_validation_with_all_valid_numeric_types():
    """Test that validation works correctly with various valid numeric representations."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("ts_event,open,high,low,close,volume,symbol\n")
        # Various numeric representations that should all be valid
        f.write("2025-01-01T12:00:00+00:00,100,105.5,95.25,102.75,1000,GC\n")
        f.write("2025-01-01T12:01:00+00:00,102.75,107,96,103,1500,GC\n")
        csv_path = f.name

    try:
        client = LocalCSVClient(csv_path)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

        # Should succeed without any errors
        candles = client.fetch(start, end, "1m")
        assert len(candles) == 2
        assert candles[0].open == 100.0
        assert candles[1].high == 107.0
        
    finally:
        Path(csv_path).unlink()

