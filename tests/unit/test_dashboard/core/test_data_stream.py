"""Unit tests for DataStream.

Tests the historical data stream with seeking and warmup functionality.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from common.types import Candle
from dashboard.core.data_stream import DataStream


@pytest.fixture
def mock_loader():
    """Create a mock data loader."""
    with patch("dashboard.core.data_stream.HistoricalDataLoader") as mock:
        yield mock


@pytest.fixture
def sample_candles():
    """Create sample candle data for testing."""
    candles = []
    for i in range(10):
        timestamp = datetime(2025, 1, 1, 10, i, 0, tzinfo=UTC)
        candles.append(
            Candle(
                timestamp=timestamp,
                open=2650.0 + i,
                high=2655.0 + i,
                low=2645.0 + i,
                close=2652.0 + i,
                volume=float(1000 + i * 100),
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
        )
    return candles


class TestDataStream:
    """Tests for DataStream class."""

    def test_initialization(self, mock_loader):
        """Test DataStream initialization."""
        stream = DataStream("/path/to/data")

        assert stream.data_dir == "/path/to/data"
        assert len(stream.gc_candles) == 0
        assert len(stream.dxy_candles) == 0
        assert stream.current_index == 0
        assert stream.stream_start_index == 0

    def test_load_data(self, mock_loader):
        """Test loading data into stream."""
        # Set up mock
        gc_data = {
            "open": [2650.0, 2651.0],
            "high": [2655.0, 2656.0],
            "low": [2645.0, 2646.0],
            "close": [2652.0, 2653.0],
            "volume": [1000.0, 1100.0],
        }
        dxy_data = {
            "open": [104.0, 104.1],
            "high": [104.5, 104.6],
            "low": [103.5, 103.6],
            "close": [104.2, 104.3],
            "volume": [0.0, 0.0],
        }

        gc_df = pd.DataFrame(gc_data)
        gc_df.index = pd.to_datetime(
            ["2025-01-01 10:00:00", "2025-01-01 10:01:00"], utc=True
        )

        dxy_df = pd.DataFrame(dxy_data)
        dxy_df.index = pd.to_datetime(
            ["2025-01-01 10:00:00", "2025-01-01 10:01:00"], utc=True
        )

        mock_instance = MagicMock()
        mock_instance.load.return_value = {"GC": gc_df, "DXY": dxy_df}
        mock_loader.return_value = mock_instance

        stream = DataStream("/path/to/data")
        count = stream.load(
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 2, tzinfo=UTC),
        )

        assert count == 2
        assert len(stream.gc_candles) == 2
        assert len(stream.dxy_candles) == 2

    def test_seek_to_timestamp(self, mock_loader):
        """Test seeking to a specific timestamp."""
        stream = DataStream("/path/to/data")

        # Manually populate candles for this test
        for i in range(10):
            timestamp = datetime(2025, 1, 1, 10, i, 0, tzinfo=UTC)
            gc_candle = Candle(
                timestamp=timestamp,
                open=2650.0,
                high=2655.0,
                low=2645.0,
                close=2652.0,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
            dxy_candle = Candle(
                timestamp=timestamp,
                open=104.0,
                high=104.5,
                low=103.5,
                close=104.2,
                volume=0.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            )
            stream.gc_candles.append(gc_candle)
            stream.dxy_candles.append(dxy_candle)

        # Seek to minute 5
        target = datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC)
        index = stream.seek_to_timestamp(target)

        assert index == 5
        assert stream.stream_start_index == 5
        assert stream.current_index == 5
        assert stream.warmup_bars == 5
        assert stream.stream_bars == 5

    def test_get_warmup_candles(self, mock_loader):
        """Test getting warmup candles."""
        stream = DataStream("/path/to/data")

        # Populate candles
        for i in range(10):
            timestamp = datetime(2025, 1, 1, 10, i, 0, tzinfo=UTC)
            base_price = 2650.0 + i
            gc_candle = Candle(
                timestamp=timestamp,
                open=base_price,
                high=base_price + 5.0,  # Always higher than open
                low=base_price - 5.0,  # Always lower than open
                close=base_price + 2.0,  # Between low and high
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
            dxy_candle = Candle(
                timestamp=timestamp,
                open=104.0,
                high=104.5,
                low=103.5,
                close=104.2,
                volume=0.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            )
            stream.gc_candles.append(gc_candle)
            stream.dxy_candles.append(dxy_candle)

        # Seek to minute 5
        stream.seek_to_timestamp(datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC))

        # Get warmup candles
        warmup = list(stream.get_warmup_candles())

        assert len(warmup) == 5
        # Check first warmup candle is minute 0
        gc, dxy = warmup[0]
        assert gc.timestamp.minute == 0
        # Check last warmup candle is minute 4
        gc, dxy = warmup[-1]
        assert gc.timestamp.minute == 4

    def test_iteration(self, mock_loader):
        """Test iterating through stream."""
        stream = DataStream("/path/to/data")

        # Populate candles
        for i in range(5):
            timestamp = datetime(2025, 1, 1, 10, i, 0, tzinfo=UTC)
            gc_candle = Candle(
                timestamp=timestamp,
                open=2650.0 + i,
                high=2655.0,
                low=2645.0,
                close=2652.0,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
            dxy_candle = Candle(
                timestamp=timestamp,
                open=104.0,
                high=104.5,
                low=103.5,
                close=104.2,
                volume=0.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            )
            stream.gc_candles.append(gc_candle)
            stream.dxy_candles.append(dxy_candle)

        # Iterate
        candles = list(stream)

        assert len(candles) == 5
        for gc, dxy in candles:
            assert gc.symbol == "GC"
            assert dxy.symbol == "DXY"

    def test_progress_tracking(self, mock_loader):
        """Test progress tracking."""
        stream = DataStream("/path/to/data")

        # Populate 10 candles
        for i in range(10):
            timestamp = datetime(2025, 1, 1, 10, i, 0, tzinfo=UTC)
            gc_candle = Candle(
                timestamp=timestamp,
                open=2650.0,
                high=2655.0,
                low=2645.0,
                close=2652.0,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
            dxy_candle = Candle(
                timestamp=timestamp,
                open=104.0,
                high=104.5,
                low=103.5,
                close=104.2,
                volume=0.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            )
            stream.gc_candles.append(gc_candle)
            stream.dxy_candles.append(dxy_candle)

        # Seek to minute 5 (5 warmup, 5 stream)
        stream.seek_to_timestamp(datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC))

        # Initially at 0% of stream
        assert stream.get_progress() == 0.0

        # Advance 2 bars
        stream.advance()
        stream.advance()

        # Should be at 40% (2/5)
        assert stream.get_progress() == pytest.approx(0.4)

    def test_reset(self, mock_loader):
        """Test reset functionality."""
        stream = DataStream("/path/to/data")

        # Populate candles
        for i in range(10):
            timestamp = datetime(2025, 1, 1, 10, i, 0, tzinfo=UTC)
            gc_candle = Candle(
                timestamp=timestamp,
                open=2650.0,
                high=2655.0,
                low=2645.0,
                close=2652.0,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
            dxy_candle = Candle(
                timestamp=timestamp,
                open=104.0,
                high=104.5,
                low=103.5,
                close=104.2,
                volume=0.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            )
            stream.gc_candles.append(gc_candle)
            stream.dxy_candles.append(dxy_candle)

        # Seek to minute 5
        stream.seek_to_timestamp(datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC))

        # Advance a few bars
        stream.advance()
        stream.advance()
        assert stream.current_index == 7

        # Reset to stream start
        stream.reset()
        assert stream.current_index == 5
        assert stream.stream_start_index == 5

        # Reset to beginning
        stream.reset_to_beginning()
        assert stream.current_index == 0
        assert stream.stream_start_index == 0

    def test_multi_timeframe_initialization(self, mock_loader):
        """Test DataStream initialization with multi-timeframe enabled."""
        stream = DataStream("/path/to/data", enable_multi_timeframe=True)

        assert stream.enable_multi_timeframe is True
        assert stream._sync_layer is not None
        assert stream._multi_tf_data is None  # Not loaded yet

    def test_multi_timeframe_disabled_by_default(self, mock_loader):
        """Test that multi-timeframe is disabled by default for backward compatibility."""
        stream = DataStream("/path/to/data")

        assert stream.enable_multi_timeframe is False
        assert stream._sync_layer is None

    def test_get_synchronized_bar_returns_none_when_disabled(self, mock_loader):
        """Test that get_synchronized_bar returns None when multi-timeframe is disabled."""
        stream = DataStream("/path/to/data")
        timestamp = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)

        bar = stream.get_synchronized_bar(timestamp)
        assert bar is None

    def test_get_current_synchronized_bar_returns_none_when_no_data(self, mock_loader):
        """Test that get_current_synchronized_bar returns None when no candles loaded."""
        stream = DataStream("/path/to/data", enable_multi_timeframe=True)

        bar = stream.get_current_synchronized_bar()
        assert bar is None

    def test_multi_timeframe_data_property(self, mock_loader):
        """Test that multi_timeframe_data property returns None when not loaded."""
        stream = DataStream("/path/to/data", enable_multi_timeframe=True)

        assert stream.multi_timeframe_data is None
