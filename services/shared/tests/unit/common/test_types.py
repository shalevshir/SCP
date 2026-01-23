"""Unit tests for common types module."""

from datetime import datetime, timezone

import pytest

from scp_shared.common.types import Candle
from scp_shared.common.exceptions import NormalizationError


def create_valid_candle(**kwargs) -> Candle:
    """Create a valid candle with optional overrides."""
    defaults = {
        "timestamp": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1000.0,
        "symbol": "GC",
        "timeframe": "1m",
        "source": "TEST",
    }
    defaults.update(kwargs)
    return Candle(**defaults)


class TestCandleCreation:
    """Tests for valid Candle creation."""

    def test_creates_valid_candle(self) -> None:
        """Creates candle with valid data."""
        candle = create_valid_candle()

        assert candle.open == 100.0
        assert candle.high == 105.0
        assert candle.low == 95.0
        assert candle.close == 102.0
        assert candle.volume == 1000.0
        assert candle.symbol == "GC"

    def test_candle_is_immutable(self) -> None:
        """Candle is immutable (frozen dataclass)."""
        candle = create_valid_candle()

        with pytest.raises(AttributeError):
            candle.close = 110.0  # type: ignore

    def test_allows_zero_volume(self) -> None:
        """Allows zero volume."""
        candle = create_valid_candle(volume=0.0)

        assert candle.volume == 0.0

    def test_allows_equal_high_low(self) -> None:
        """Allows high == low (doji candle)."""
        candle = create_valid_candle(open=100.0, high=100.0, low=100.0, close=100.0)

        assert candle.high == candle.low


class TestCandleTimestampValidation:
    """Tests for timestamp validation."""

    def test_rejects_naive_timestamp(self) -> None:
        """Rejects timezone-naive timestamp."""
        naive_time = datetime(2024, 1, 1, 12, 0)  # No tzinfo

        with pytest.raises(NormalizationError, match="timezone-aware"):
            create_valid_candle(timestamp=naive_time)


class TestCandlePriceValidation:
    """Tests for OHLC price validation."""

    def test_rejects_negative_open(self) -> None:
        """Rejects negative open price."""
        with pytest.raises(NormalizationError, match="Open price must be positive"):
            create_valid_candle(open=-1.0)

    def test_rejects_zero_open(self) -> None:
        """Rejects zero open price."""
        with pytest.raises(NormalizationError, match="Open price must be positive"):
            create_valid_candle(open=0.0)

    def test_rejects_negative_high(self) -> None:
        """Rejects negative high price."""
        with pytest.raises(NormalizationError, match="High price must be positive"):
            create_valid_candle(high=-1.0)

    def test_rejects_negative_low(self) -> None:
        """Rejects negative low price."""
        with pytest.raises(NormalizationError, match="Low price must be positive"):
            create_valid_candle(low=-1.0)

    def test_rejects_negative_close(self) -> None:
        """Rejects negative close price."""
        with pytest.raises(NormalizationError, match="Close price must be positive"):
            create_valid_candle(close=-1.0)


class TestCandleOHLCRelationships:
    """Tests for OHLC relationship validation."""

    def test_rejects_high_less_than_low(self) -> None:
        """Rejects high < low."""
        with pytest.raises(
            NormalizationError, match="High price cannot be less than low"
        ):
            create_valid_candle(high=90.0, low=100.0)

    def test_rejects_high_less_than_open(self) -> None:
        """Rejects high < open."""
        with pytest.raises(
            NormalizationError, match="High price cannot be less than open"
        ):
            create_valid_candle(open=100.0, high=95.0, low=90.0, close=95.0)

    def test_rejects_high_less_than_close(self) -> None:
        """Rejects high < close."""
        with pytest.raises(
            NormalizationError, match="High price cannot be less than close"
        ):
            create_valid_candle(high=100.0, close=105.0, low=95.0, open=99.0)

    def test_rejects_low_greater_than_open(self) -> None:
        """Rejects low > open."""
        with pytest.raises(
            NormalizationError, match="Low price cannot be greater than open"
        ):
            create_valid_candle(open=95.0, low=100.0, high=105.0, close=102.0)

    def test_rejects_low_greater_than_close(self) -> None:
        """Rejects low > close."""
        with pytest.raises(
            NormalizationError, match="Low price cannot be greater than close"
        ):
            create_valid_candle(close=95.0, low=100.0, high=105.0, open=102.0)


class TestCandleVolumeValidation:
    """Tests for volume validation."""

    def test_rejects_negative_volume(self) -> None:
        """Rejects negative volume."""
        with pytest.raises(NormalizationError, match="Volume cannot be negative"):
            create_valid_candle(volume=-1.0)


class TestCandleStringFieldValidation:
    """Tests for string field validation."""

    def test_rejects_empty_symbol(self) -> None:
        """Rejects empty symbol."""
        with pytest.raises(NormalizationError, match="Symbol cannot be empty"):
            create_valid_candle(symbol="")

    def test_rejects_whitespace_symbol(self) -> None:
        """Rejects whitespace-only symbol."""
        with pytest.raises(NormalizationError, match="Symbol cannot be empty"):
            create_valid_candle(symbol="   ")

    def test_rejects_empty_timeframe(self) -> None:
        """Rejects empty timeframe."""
        with pytest.raises(NormalizationError, match="Timeframe cannot be empty"):
            create_valid_candle(timeframe="")

    def test_rejects_whitespace_timeframe(self) -> None:
        """Rejects whitespace-only timeframe."""
        with pytest.raises(NormalizationError, match="Timeframe cannot be empty"):
            create_valid_candle(timeframe="   ")

    def test_rejects_empty_source(self) -> None:
        """Rejects empty source."""
        with pytest.raises(NormalizationError, match="Source cannot be empty"):
            create_valid_candle(source="")

    def test_rejects_whitespace_source(self) -> None:
        """Rejects whitespace-only source."""
        with pytest.raises(NormalizationError, match="Source cannot be empty"):
            create_valid_candle(source="   ")
