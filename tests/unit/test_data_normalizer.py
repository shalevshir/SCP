"""Tests for DataNormalizer."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from common.exceptions import NormalizationError
from common.types import Candle
from data_layer.normalizer import DataNormalizer


@pytest.fixture
def normalizer():
    """Create a DataNormalizer instance for testing."""
    return DataNormalizer()


@pytest.fixture
def valid_candle_1():
    """Create a valid candle for testing."""
    return Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )


@pytest.fixture
def valid_candle_2():
    """Create another valid candle for testing (later timestamp)."""
    return Candle(
        timestamp=datetime(2025, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
        open=102.0,
        high=107.0,
        low=100.0,
        close=105.0,
        volume=1200.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )


@pytest.fixture
def valid_candle_3():
    """Create a third valid candle for testing (earliest timestamp)."""
    return Candle(
        timestamp=datetime(2025, 1, 1, 11, 55, 0, tzinfo=timezone.utc),
        open=98.0,
        high=103.0,
        low=97.0,
        close=100.0,
        volume=900.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )


def test_normalizer_initialization(normalizer):
    """Test that DataNormalizer initializes correctly."""
    assert normalizer is not None
    assert isinstance(normalizer, DataNormalizer)


def test_normalize_empty_list(normalizer):
    """Test that normalizing an empty list returns an empty list."""
    result = normalizer.normalize([])
    assert result == []


def test_normalize_single_candle(normalizer, valid_candle_1):
    """Test that normalizing a single candle returns it unchanged."""
    result = normalizer.normalize([valid_candle_1])
    assert len(result) == 1
    assert result[0] == valid_candle_1


def test_normalize_already_sorted_candles(normalizer, valid_candle_1, valid_candle_2):
    """Test that normalizing already-sorted candles preserves order."""
    candles = [valid_candle_1, valid_candle_2]
    result = normalizer.normalize(candles)
    
    assert len(result) == 2
    assert result[0] == valid_candle_1
    assert result[1] == valid_candle_2


def test_normalize_unsorted_candles(normalizer, valid_candle_1, valid_candle_2, valid_candle_3):
    """Test that normalizing unsorted candles returns them in timestamp order."""
    # Input order: 12:00, 12:05, 11:55
    candles = [valid_candle_1, valid_candle_2, valid_candle_3]
    result = normalizer.normalize(candles)
    
    # Expected order: 11:55, 12:00, 12:05
    assert len(result) == 3
    assert result[0] == valid_candle_3  # 11:55
    assert result[1] == valid_candle_1  # 12:00
    assert result[2] == valid_candle_2  # 12:05


def test_normalize_reverse_sorted_candles(normalizer, valid_candle_1, valid_candle_2, valid_candle_3):
    """Test that normalizing reverse-sorted candles returns them in ascending order."""
    # Input order: 12:05, 12:00, 11:55
    candles = [valid_candle_2, valid_candle_1, valid_candle_3]
    result = normalizer.normalize(candles)
    
    # Expected order: 11:55, 12:00, 12:05
    assert len(result) == 3
    assert result[0] == valid_candle_3  # 11:55
    assert result[1] == valid_candle_1  # 12:00
    assert result[2] == valid_candle_2  # 12:05


def test_normalize_logs_warning_for_unsorted_input(normalizer, valid_candle_1, valid_candle_2):
    """Test that normalizer logs a warning when input is unsorted."""
    with patch("data_layer.normalizer.logger") as mock_logger:
        # Input out of order: later candle first
        candles = [valid_candle_2, valid_candle_1]
        normalizer.normalize(candles)
        
        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        assert "out of order" in mock_logger.warning.call_args[0][0].lower()


def test_normalize_does_not_log_for_sorted_input(normalizer, valid_candle_1, valid_candle_2):
    """Test that normalizer does not log warning when input is already sorted."""
    with patch("data_layer.normalizer.logger") as mock_logger:
        # Input in correct order
        candles = [valid_candle_1, valid_candle_2]
        normalizer.normalize(candles)
        
        # Verify no warnings were logged
        mock_logger.warning.assert_not_called()


def test_normalize_detects_duplicate_timestamps(normalizer):
    """Test that normalizer detects and logs duplicate timestamps for same symbol."""
    duplicate_candle_1 = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    duplicate_candle_2 = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=101.0,
        high=106.0,
        low=96.0,
        close=103.0,
        volume=1100.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    
    with patch("data_layer.normalizer.logger") as mock_logger:
        candles = [duplicate_candle_1, duplicate_candle_2]
        result = normalizer.normalize(candles)
        
        # Both candles should still be returned
        assert len(result) == 2
        
        # Verify warning was logged about duplicates
        mock_logger.warning.assert_called_once()
        assert "duplicate" in mock_logger.warning.call_args[0][0].lower()


def test_normalize_allows_same_timestamp_different_symbols(normalizer):
    """Test that same timestamp is allowed for different symbols."""
    gc_candle = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    dxy_candle = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=105.0,
        high=106.0,
        low=104.0,
        close=105.5,
        volume=500.0,
        symbol="DXY",
        timeframe="5m",
        source="ICE",
    )
    
    with patch("data_layer.normalizer.logger") as mock_logger:
        candles = [gc_candle, dxy_candle]
        result = normalizer.normalize(candles)
        
        # Both candles should be returned
        assert len(result) == 2
        
        # No duplicate warning should be logged (different symbols)
        mock_logger.warning.assert_not_called()


def test_normalize_preserves_candle_immutability(normalizer, valid_candle_1):
    """Test that normalize does not modify the input candles."""
    original_timestamp = valid_candle_1.timestamp
    original_open = valid_candle_1.open
    
    result = normalizer.normalize([valid_candle_1])
    
    # Original candle should be unchanged
    assert valid_candle_1.timestamp == original_timestamp
    assert valid_candle_1.open == original_open


def test_normalize_does_not_modify_input_list(normalizer, valid_candle_1, valid_candle_2):
    """Test that normalize does not modify the input list."""
    original_candles = [valid_candle_2, valid_candle_1]
    original_order = list(original_candles)
    
    result = normalizer.normalize(original_candles)
    
    # Input list should be unchanged
    assert original_candles == original_order
    # Result should be sorted
    assert result[0] == valid_candle_1
    assert result[1] == valid_candle_2


def test_normalize_handles_multiple_duplicates(normalizer):
    """Test that normalizer handles multiple sets of duplicates."""
    candle_1a = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    candle_1b = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=101.0,
        high=106.0,
        low=96.0,
        close=103.0,
        volume=1100.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    candle_2a = Candle(
        timestamp=datetime(2025, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
        open=102.0,
        high=107.0,
        low=100.0,
        close=105.0,
        volume=1200.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    candle_2b = Candle(
        timestamp=datetime(2025, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
        open=103.0,
        high=108.0,
        low=101.0,
        close=106.0,
        volume=1300.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    
    with patch("data_layer.normalizer.logger") as mock_logger:
        candles = [candle_1a, candle_1b, candle_2a, candle_2b]
        result = normalizer.normalize(candles)
        
        # All candles should be returned
        assert len(result) == 4
        
        # Should log warnings about duplicates
        assert mock_logger.warning.call_count >= 1


def test_normalize_with_mixed_symbols_sorted(normalizer):
    """Test normalization with multiple symbols maintains sort order."""
    gc_early = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    dxy_middle = Candle(
        timestamp=datetime(2025, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
        open=105.0,
        high=106.0,
        low=104.0,
        close=105.5,
        volume=500.0,
        symbol="DXY",
        timeframe="5m",
        source="ICE",
    )
    gc_late = Candle(
        timestamp=datetime(2025, 1, 1, 12, 10, 0, tzinfo=timezone.utc),
        open=102.0,
        high=107.0,
        low=100.0,
        close=105.0,
        volume=1200.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    
    # Input out of order
    candles = [gc_late, gc_early, dxy_middle]
    result = normalizer.normalize(candles)
    
    # Should be sorted by timestamp regardless of symbol
    assert len(result) == 3
    assert result[0] == gc_early    # 12:00
    assert result[1] == dxy_middle  # 12:05
    assert result[2] == gc_late     # 12:10


def test_normalize_does_not_modify_candle_fields(normalizer):
    """Test that normalize does not modify any candle fields."""
    original = Candle(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CME",
    )
    
    result = normalizer.normalize([original])
    
    # All fields should be exactly the same
    assert result[0].timestamp == original.timestamp
    assert result[0].open == original.open
    assert result[0].high == original.high
    assert result[0].low == original.low
    assert result[0].close == original.close
    assert result[0].volume == original.volume
    assert result[0].symbol == original.symbol
    assert result[0].timeframe == original.timeframe
    assert result[0].source == original.source

