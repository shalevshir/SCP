"""Tests for Candle dataclass."""

from datetime import datetime, timezone

import pytest

from common.exceptions import NormalizationError
from common.types import Candle


def test_candle_creation_with_valid_data():
    """Test creating a candle with valid data."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    candle = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    assert candle.timestamp == timestamp
    assert candle.open == 100.0
    assert candle.high == 105.0
    assert candle.low == 95.0
    assert candle.close == 102.0
    assert candle.volume == 1000.0
    assert candle.symbol == "GC"
    assert candle.timeframe == "1m"
    assert candle.source == "CSV"


def test_candle_with_zero_volume():
    """Test that candles can have zero volume."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    candle = Candle(
        timestamp=timestamp,
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=0.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    assert candle.volume == 0.0


def test_candle_with_equal_ohlc():
    """Test candle where all OHLC values are equal (valid case)."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    candle = Candle(
        timestamp=timestamp,
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=500.0,
        symbol="DXY",
        timeframe="5m",
        source="SIMULATION",
    )

    assert candle.open == candle.high == candle.low == candle.close


def test_candle_high_less_than_low_raises_error():
    """Test that high < low raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=95.0,  # Invalid: high < low
            low=105.0,
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

    assert "high" in str(exc_info.value).lower()
    assert "low" in str(exc_info.value).lower()


def test_candle_high_less_than_open_raises_error():
    """Test that high < open raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=105.0,
            high=100.0,  # Invalid: high < open
            low=95.0,
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

    assert "high" in str(exc_info.value).lower()


def test_candle_high_less_than_close_raises_error():
    """Test that high < close raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=100.0,
            low=95.0,
            close=105.0,  # Invalid: close > high
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

    assert "high" in str(exc_info.value).lower()


def test_candle_low_greater_than_open_raises_error():
    """Test that low > open raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=95.0,
            high=105.0,
            low=100.0,  # Invalid: low > open
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

    assert "low" in str(exc_info.value).lower()


def test_candle_low_greater_than_close_raises_error():
    """Test that low > close raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=102.0,
            close=100.0,  # Invalid: close < low
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

    assert "low" in str(exc_info.value).lower()


def test_candle_negative_open_raises_error():
    """Test that negative open price raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=-100.0,  # Invalid: negative
            high=105.0,
            low=95.0,
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

    assert (
        "positive" in str(exc_info.value).lower()
        or "negative" in str(exc_info.value).lower()
    )


def test_candle_negative_high_raises_error():
    """Test that negative high price raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError):
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=-105.0,  # Invalid: negative
            low=95.0,
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )


def test_candle_negative_low_raises_error():
    """Test that negative low price raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError):
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=-95.0,  # Invalid: negative
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )


def test_candle_negative_close_raises_error():
    """Test that negative close price raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError):
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=95.0,
            close=-100.0,  # Invalid: negative
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )


def test_candle_zero_ohlc_raises_error():
    """Test that zero OHLC prices raise NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError):
        Candle(
            timestamp=timestamp,
            open=0.0,  # Invalid: zero
            high=0.0,
            low=0.0,
            close=0.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )


def test_candle_negative_volume_raises_error():
    """Test that negative volume raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=95.0,
            close=100.0,
            volume=-1000.0,  # Invalid: negative
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

    assert "volume" in str(exc_info.value).lower()
    assert "negative" in str(exc_info.value).lower()


def test_candle_naive_timestamp_raises_error():
    """Test that naive datetime (no timezone) raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0)  # No timezone

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=95.0,
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

    assert (
        "timezone" in str(exc_info.value).lower()
        or "aware" in str(exc_info.value).lower()
    )


def test_candle_empty_symbol_raises_error():
    """Test that empty symbol raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=95.0,
            close=100.0,
            volume=1000.0,
            symbol="",  # Invalid: empty
            timeframe="1m",
            source="CSV",
        )

    assert "symbol" in str(exc_info.value).lower()
    assert "empty" in str(exc_info.value).lower()


def test_candle_empty_timeframe_raises_error():
    """Test that empty timeframe raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=95.0,
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="",  # Invalid: empty
            source="CSV",
        )

    assert "timeframe" in str(exc_info.value).lower()
    assert "empty" in str(exc_info.value).lower()


def test_candle_empty_source_raises_error():
    """Test that empty source raises NormalizationError."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(NormalizationError) as exc_info:
        Candle(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=95.0,
            close=100.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="",  # Invalid: empty
        )

    assert "source" in str(exc_info.value).lower()
    assert "empty" in str(exc_info.value).lower()


def test_candle_is_immutable():
    """Test that Candle is immutable (frozen dataclass)."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    candle = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    with pytest.raises(AttributeError):
        candle.open = 110.0  # type: ignore[misc]


def test_candle_string_representation():
    """Test that Candle has a useful string representation."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    candle = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    repr_str = repr(candle)
    assert "Candle" in repr_str
    assert "GC" in repr_str
    assert "1m" in repr_str


def test_candle_equality():
    """Test that two candles with same data are equal."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    candle1 = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )
    candle2 = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    assert candle1 == candle2


def test_candle_inequality():
    """Test that candles with different data are not equal."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    candle1 = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )
    candle2 = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=103.0,  # Different close
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    assert candle1 != candle2


def test_candle_hashable():
    """Test that Candle can be hashed (used in sets/dicts)."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    candle1 = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )
    candle2 = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    # Same data should have same hash
    assert hash(candle1) == hash(candle2)

    # Should work in a set
    candle_set = {candle1, candle2}
    assert len(candle_set) == 1  # Only one unique candle


def test_candle_with_different_symbols():
    """Test candles with different valid symbols."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    gc_candle = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    dxy_candle = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="DXY",
        timeframe="1m",
        source="CSV",
    )

    assert gc_candle.symbol == "GC"
    assert dxy_candle.symbol == "DXY"
    assert gc_candle != dxy_candle


def test_candle_with_different_timeframes():
    """Test candles with different valid timeframes."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    candle_1m = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="CSV",
    )

    candle_5m = Candle(
        timestamp=timestamp,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="CSV",
    )

    assert candle_1m.timeframe == "1m"
    assert candle_5m.timeframe == "5m"
    assert candle_1m != candle_5m
