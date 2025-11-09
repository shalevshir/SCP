"""Tests for TimeAligner stub."""

from datetime import datetime, timezone

import pytest

from common.exceptions import DataSourceError
from common.types import Candle
from data_layer.aligner import TimeAligner


def test_aligner_instantiation():
    """Test that TimeAligner can be instantiated."""
    aligner = TimeAligner()
    assert aligner is not None
    assert isinstance(aligner, TimeAligner)


def test_aligner_has_align_method():
    """Test that aligner has align method."""
    aligner = TimeAligner()
    assert hasattr(aligner, "align")
    assert callable(aligner.align)


def test_align_returns_list():
    """Test that align returns a list."""
    aligner = TimeAligner()
    result = aligner.align([], [], "5m")

    assert isinstance(result, list)


def test_align_returns_list_of_tuples():
    """Test that align returns list of tuples."""
    aligner = TimeAligner()
    result = aligner.align([], [], "5m")

    # Should be a list (empty or with tuples)
    assert isinstance(result, list)
    # If not empty, all items should be tuples
    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 2


def test_stub_returns_empty_list():
    """Test that stub implementation returns empty list."""
    aligner = TimeAligner()

    # Empty inputs
    result = aligner.align([], [], "5m")
    assert result == []

    # With candles (stub still returns empty)
    gc_candle = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        open=2050.0,
        high=2055.0,
        low=2048.0,
        close=2052.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    dxy_candle = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        open=105.0,
        high=105.5,
        low=104.8,
        close=105.2,
        volume=500.0,
        symbol="DXY",
        timeframe="5m",
        source="ICE",
    )

    result = aligner.align([gc_candle], [dxy_candle], "5m")
    assert result == []


def test_align_with_empty_gc_candles():
    """Test align with empty GC candles list."""
    aligner = TimeAligner()

    dxy_candle = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        open=105.0,
        high=105.5,
        low=104.8,
        close=105.2,
        volume=500.0,
        symbol="DXY",
        timeframe="5m",
        source="ICE",
    )

    result = aligner.align([], [dxy_candle], "5m")

    # Stub returns empty list
    assert isinstance(result, list)
    assert result == []


def test_align_with_empty_dxy_candles():
    """Test align with empty DXY candles list."""
    aligner = TimeAligner()

    gc_candle = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        open=2050.0,
        high=2055.0,
        low=2048.0,
        close=2052.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )

    result = aligner.align([gc_candle], [], "5m")

    # Stub returns empty list
    assert isinstance(result, list)
    assert result == []


def test_align_with_empty_timeframe_raises_error():
    """Test that align raises DataSourceError for empty timeframe."""
    aligner = TimeAligner()

    with pytest.raises(DataSourceError) as exc_info:
        aligner.align([], [], "")

    assert "timeframe" in str(exc_info.value).lower()
    assert "empty" in str(exc_info.value).lower()


def test_align_with_whitespace_timeframe_raises_error():
    """Test that align raises DataSourceError for whitespace-only timeframe."""
    aligner = TimeAligner()

    with pytest.raises(DataSourceError) as exc_info:
        aligner.align([], [], "   ")

    assert "timeframe" in str(exc_info.value).lower()
    assert "empty" in str(exc_info.value).lower()


def test_align_with_different_timeframes():
    """Test that align works with various valid timeframes."""
    aligner = TimeAligner()

    timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

    for timeframe in timeframes:
        result = aligner.align([], [], timeframe)
        assert isinstance(result, list)
        # Stub returns empty list
        assert result == []


def test_align_with_multiple_candles():
    """Test align with multiple candles from both sources."""
    aligner = TimeAligner()

    # Create multiple GC candles
    gc_candles = [
        Candle(
            timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            open=2050.0,
            high=2055.0,
            low=2048.0,
            close=2052.0,
            volume=1000.0,
            symbol="GC",
            timeframe="5m",
            source="CME",
        ),
        Candle(
            timestamp=datetime(2025, 1, 1, 12, 5, tzinfo=timezone.utc),
            open=2052.0,
            high=2057.0,
            low=2050.0,
            close=2055.0,
            volume=1200.0,
            symbol="GC",
            timeframe="5m",
            source="CME",
        ),
    ]

    # Create multiple DXY candles
    dxy_candles = [
        Candle(
            timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            open=105.0,
            high=105.5,
            low=104.8,
            close=105.2,
            volume=500.0,
            symbol="DXY",
            timeframe="5m",
            source="ICE",
        ),
        Candle(
            timestamp=datetime(2025, 1, 1, 12, 5, tzinfo=timezone.utc),
            open=105.2,
            high=105.7,
            low=105.0,
            close=105.5,
            volume=600.0,
            symbol="DXY",
            timeframe="5m",
            source="ICE",
        ),
    ]

    result = aligner.align(gc_candles, dxy_candles, "5m")

    # Stub returns empty list
    assert isinstance(result, list)
    assert result == []


def test_align_signature_matches_expected():
    """Test that align method has the expected signature."""
    aligner = TimeAligner()

    # Get the align method
    align_method = getattr(aligner, "align")

    # Check it accepts the expected parameters
    import inspect

    sig = inspect.signature(align_method)
    params = list(sig.parameters.keys())

    assert "gc_candles" in params
    assert "dxy_candles" in params
    assert "timeframe" in params


def test_multiple_align_calls():
    """Test that multiple align calls work correctly."""
    aligner = TimeAligner()

    # First call
    result1 = aligner.align([], [], "1m")
    assert result1 == []

    # Second call
    result2 = aligner.align([], [], "5m")
    assert result2 == []

    # Results should be independent
    assert result1 == result2 == []


def test_align_return_type_annotation():
    """Test that align method has correct return type annotation."""
    aligner = TimeAligner()

    import inspect
    from typing import get_type_hints

    # Get type hints
    hints = get_type_hints(aligner.align)

    # Check return type exists
    assert "return" in hints

    # The return type should be list
    return_type = hints["return"]
    assert hasattr(return_type, "__origin__")
