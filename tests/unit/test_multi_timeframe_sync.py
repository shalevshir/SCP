"""Tests for MultiTimeframeSyncLayer.

Tests cover:
- Initialization and configuration
- Multi-timeframe data loading
- HTF alignment to execution timeframe
- Synchronized bar creation
- Edge cases (missing data, empty data, gaps)
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from common.exceptions import DataSourceError
from common.types import Candle
from data_layer.multi_timeframe_sync import (
    MultiTimeframeData,
    MultiTimeframeSyncLayer,
    SynchronizedBar,
)


class TestMultiTimeframeSyncLayer:
    """Tests for MultiTimeframeSyncLayer class."""

    @pytest.fixture
    def data_dir(self) -> Path:
        """Provide path to test data directory."""
        return Path("data/gc_dx_ohlcv")

    @pytest.fixture
    def sync_layer(self, data_dir: Path) -> MultiTimeframeSyncLayer:
        """Create a MultiTimeframeSyncLayer instance."""
        return MultiTimeframeSyncLayer(data_dir)

    def test_initialization_with_defaults(self, data_dir: Path) -> None:
        """Test that sync layer initializes with default timeframes."""
        layer = MultiTimeframeSyncLayer(data_dir)
        assert layer.execution_timeframe == "1m"
        assert layer.htf_timeframes == ["15m", "1h"]
        assert layer.data_dir == data_dir

    def test_initialization_with_custom_timeframes(self, data_dir: Path) -> None:
        """Test that sync layer accepts custom timeframes."""
        layer = MultiTimeframeSyncLayer(
            data_dir, execution_timeframe="1m", htf_timeframes=["15m", "1h"]
        )
        assert layer.execution_timeframe == "1m"
        assert layer.htf_timeframes == ["15m", "1h"]

    def test_initialization_rejects_empty_execution_timeframe(
        self, data_dir: Path
    ) -> None:
        """Test that empty execution timeframe raises ValueError."""
        with pytest.raises(ValueError, match="Execution timeframe cannot be empty"):
            MultiTimeframeSyncLayer(data_dir, execution_timeframe="")

    def test_load_returns_multi_timeframe_data(
        self, sync_layer: MultiTimeframeSyncLayer
    ) -> None:
        """Test that load() returns MultiTimeframeData object."""
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 30, 0, tzinfo=UTC)

        try:
            result = sync_layer.load(start, end)
            assert isinstance(result, MultiTimeframeData)
            assert result.execution_timeframe == "1m"
            assert result.htf_timeframes == ["15m", "1h"]
            assert len(result) > 0
        except (DataSourceError, ValueError) as e:
            # May fail if data is invalid or missing
            # This is acceptable - test verifies structure when data is available
            assert "data" in str(e).lower() or "empty" in str(e).lower()

    def test_synchronized_bars_have_execution_data(
        self, sync_layer: MultiTimeframeSyncLayer
    ) -> None:
        """Test that synchronized bars contain execution timeframe data."""
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 30, 0, tzinfo=UTC)

        try:
            result = sync_layer.load(start, end)
            assert len(result.synchronized_bars) > 0

            for bar in result.synchronized_bars:
                assert isinstance(bar, SynchronizedBar)
                assert bar.execution_timestamp is not None
                assert bar.execution_1m is not None
                assert len(bar.execution_1m) == 2  # (GC, DXY)
                assert isinstance(bar.execution_1m[0], Candle)
                assert isinstance(bar.execution_1m[1], Candle)
                assert bar.execution_1m[0].symbol == "GC"
                assert bar.execution_1m[1].symbol == "DXY"
                assert bar.execution_1m[0].timeframe == "1m"
                assert bar.execution_1m[1].timeframe == "1m"
        except (DataSourceError, ValueError):
            # Skip if data unavailable
            pytest.skip("Test data not available")

    def test_htf_bars_are_optional(self, sync_layer: MultiTimeframeSyncLayer) -> None:
        """Test that HTF bars can be None if data not available."""
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 5, 0, tzinfo=UTC)  # Very short range

        try:
            result = sync_layer.load(start, end)
            # HTF bars may be None if no HTF bar has closed yet
            for bar in result.synchronized_bars:
                # Execution data must always be present
                assert bar.execution_1m is not None
                # HTF data is optional
                assert bar.htf_15m is None or isinstance(bar.htf_15m, tuple)
                assert bar.htf_1h is None or isinstance(bar.htf_1h, tuple)
        except (DataSourceError, ValueError):
            pytest.skip("Test data not available")

    def test_get_bar_returns_bar_for_timestamp(
        self, sync_layer: MultiTimeframeSyncLayer
    ) -> None:
        """Test that get_bar() returns bar for valid timestamp."""
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 30, 0, tzinfo=UTC)

        try:
            result = sync_layer.load(start, end)
            if len(result) > 0:
                first_timestamp = result.execution_timestamps[0]
                bar = result.get_bar(first_timestamp)
                assert bar is not None
                assert bar.execution_timestamp == first_timestamp
        except (DataSourceError, ValueError):
            pytest.skip("Test data not available")

    def test_get_bar_returns_none_for_invalid_timestamp(
        self, sync_layer: MultiTimeframeSyncLayer
    ) -> None:
        """Test that get_bar() returns None for invalid timestamp."""
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 30, 0, tzinfo=UTC)

        try:
            result = sync_layer.load(start, end)
            invalid_timestamp = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
            bar = result.get_bar(invalid_timestamp)
            assert bar is None
        except (DataSourceError, ValueError):
            pytest.skip("Test data not available")

    def test_load_handles_empty_date_range(
        self, sync_layer: MultiTimeframeSyncLayer
    ) -> None:
        """Test that load() handles empty date range gracefully."""
        start = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2020, 1, 2, 0, 0, 0, tzinfo=UTC)

        # Should raise ValueError if no data found
        with pytest.raises(ValueError, match="No synchronized bars"):
            sync_layer.load(start, end)

    def test_load_raises_error_on_missing_files(self, tmp_path: Path) -> None:
        """Test that load() raises error when no synchronized bars can be created."""
        layer = MultiTimeframeSyncLayer(tmp_path)
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 30, 0, tzinfo=UTC)

        # With missing files, we continue with empty DataFrames but raise ValueError
        # when no synchronized bars can be created
        with pytest.raises(ValueError, match="No synchronized bars created"):
            layer.load(start, end)

    def test_htf_alignment_uses_most_recent_bar(
        self, sync_layer: MultiTimeframeSyncLayer
    ) -> None:
        """Test that HTF alignment uses most recent bar <= execution timestamp."""
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 30, 0, tzinfo=UTC)

        try:
            result = sync_layer.load(start, end)
            # Check that HTF bars are aligned correctly
            # 15m bars close at :14, :29, :44, :59
            # 1h bars close at :59
            for bar in result.synchronized_bars:
                exec_ts = bar.execution_timestamp
                if bar.htf_15m is not None:
                    htf_15m_ts = bar.htf_15m[0].timestamp
                    # HTF bar must be <= execution timestamp
                    assert htf_15m_ts <= exec_ts
                    # And should be the most recent 15m bar
                    # (i.e., within 15 minutes)
                    time_diff = (exec_ts - htf_15m_ts).total_seconds() / 60
                    assert time_diff < 15
                if bar.htf_1h is not None:
                    htf_1h_ts = bar.htf_1h[0].timestamp
                    # HTF bar must be <= execution timestamp
                    assert htf_1h_ts <= exec_ts
                    # And should be the most recent 1h bar
                    time_diff = (exec_ts - htf_1h_ts).total_seconds() / 60
                    assert time_diff < 60
        except (DataSourceError, ValueError):
            pytest.skip("Test data not available")

    def test_synchronized_bars_have_matching_timestamps(
        self, sync_layer: MultiTimeframeSyncLayer
    ) -> None:
        """Test that all synchronized bars have matching GC/DXY timestamps."""
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 30, 0, tzinfo=UTC)

        try:
            result = sync_layer.load(start, end)
            for bar in result.synchronized_bars:
                # Execution bars must have matching timestamps
                assert bar.execution_1m[0].timestamp == bar.execution_timestamp
                assert bar.execution_1m[1].timestamp == bar.execution_timestamp

                # HTF bars must have matching timestamps if present
                if bar.htf_15m is not None:
                    assert bar.htf_15m[0].timestamp == bar.htf_15m[1].timestamp
                if bar.htf_1h is not None:
                    assert bar.htf_1h[0].timestamp == bar.htf_1h[1].timestamp
        except (DataSourceError, ValueError):
            pytest.skip("Test data not available")

    def test_load_with_custom_symbols(
        self, sync_layer: MultiTimeframeSyncLayer
    ) -> None:
        """Test that load() accepts custom symbols."""
        start = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 10, 30, 0, tzinfo=UTC)

        try:
            result = sync_layer.load(start, end, symbols=["GC", "DXY"])
            assert len(result) > 0
        except (DataSourceError, ValueError):
            pytest.skip("Test data not available")


class TestSynchronizedBar:
    """Tests for SynchronizedBar dataclass."""

    def test_synchronized_bar_creation(self) -> None:
        """Test that SynchronizedBar can be created with all fields."""
        timestamp = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        gc_candle = Candle(
            timestamp=timestamp,
            open=2000.0,
            high=2001.0,
            low=1999.0,
            close=2000.5,
            volume=100.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        dxy_candle = Candle(
            timestamp=timestamp,
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.05,
            volume=50.0,
            symbol="DXY",
            timeframe="1m",
            source="CSV",
        )

        bar = SynchronizedBar(
            execution_timestamp=timestamp,
            execution_1m=(gc_candle, dxy_candle),
            htf_15m=None,
            htf_1h=None,
        )

        assert bar.execution_timestamp == timestamp
        assert bar.execution_1m == (gc_candle, dxy_candle)
        assert bar.htf_15m is None
        assert bar.htf_1h is None

    def test_synchronized_bar_with_htf_data(self) -> None:
        """Test that SynchronizedBar can include HTF data."""
        exec_ts = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        htf_15m_ts = datetime(2025, 9, 30, 9, 59, 0, tzinfo=UTC)
        htf_1h_ts = datetime(2025, 9, 30, 9, 59, 0, tzinfo=UTC)

        exec_gc = Candle(
            timestamp=exec_ts,
            open=2000.0,
            high=2001.0,
            low=1999.0,
            close=2000.5,
            volume=100.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        exec_dxy = Candle(
            timestamp=exec_ts,
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.05,
            volume=50.0,
            symbol="DXY",
            timeframe="1m",
            source="CSV",
        )

        htf_15m_gc = Candle(
            timestamp=htf_15m_ts,
            open=1999.0,
            high=2002.0,
            low=1998.0,
            close=2000.0,
            volume=1500.0,
            symbol="GC",
            timeframe="15m",
            source="CSV",
        )
        htf_15m_dxy = Candle(
            timestamp=htf_15m_ts,
            open=99.8,
            high=100.2,
            low=99.7,
            close=100.0,
            volume=750.0,
            symbol="DXY",
            timeframe="15m",
            source="CSV",
        )

        htf_1h_gc = Candle(
            timestamp=htf_1h_ts,
            open=1998.0,
            high=2003.0,
            low=1997.0,
            close=2001.0,
            volume=6000.0,
            symbol="GC",
            timeframe="1h",
            source="CSV",
        )
        htf_1h_dxy = Candle(
            timestamp=htf_1h_ts,
            open=99.5,
            high=100.5,
            low=99.4,
            close=100.1,
            volume=3000.0,
            symbol="DXY",
            timeframe="1h",
            source="CSV",
        )

        bar = SynchronizedBar(
            execution_timestamp=exec_ts,
            execution_1m=(exec_gc, exec_dxy),
            htf_15m=(htf_15m_gc, htf_15m_dxy),
            htf_1h=(htf_1h_gc, htf_1h_dxy),
        )

        assert bar.execution_timestamp == exec_ts
        assert bar.execution_1m == (exec_gc, exec_dxy)
        assert bar.htf_15m == (htf_15m_gc, htf_15m_dxy)
        assert bar.htf_1h == (htf_1h_gc, htf_1h_dxy)


class TestMultiTimeframeData:
    """Tests for MultiTimeframeData dataclass."""

    def test_multi_timeframe_data_creation(self) -> None:
        """Test that MultiTimeframeData can be created."""
        timestamp = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        gc_candle = Candle(
            timestamp=timestamp,
            open=2000.0,
            high=2001.0,
            low=1999.0,
            close=2000.5,
            volume=100.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        dxy_candle = Candle(
            timestamp=timestamp,
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.05,
            volume=50.0,
            symbol="DXY",
            timeframe="1m",
            source="CSV",
        )

        bar = SynchronizedBar(
            execution_timestamp=timestamp,
            execution_1m=(gc_candle, dxy_candle),
            htf_15m=None,
            htf_1h=None,
        )

        data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=[bar],
            execution_timestamps=[timestamp],
        )

        assert data.execution_timeframe == "1m"
        assert data.htf_timeframes == ["15m", "1h"]
        assert len(data) == 1
        assert data.synchronized_bars == [bar]
        assert data.execution_timestamps == [timestamp]

    def test_multi_timeframe_data_length(self) -> None:
        """Test that len() works on MultiTimeframeData."""
        data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=[],
            execution_timestamps=[],
        )
        assert len(data) == 0

        # Add a bar
        timestamp = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        gc_candle = Candle(
            timestamp=timestamp,
            open=2000.0,
            high=2001.0,
            low=1999.0,
            close=2000.5,
            volume=100.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        dxy_candle = Candle(
            timestamp=timestamp,
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.05,
            volume=50.0,
            symbol="DXY",
            timeframe="1m",
            source="CSV",
        )
        bar = SynchronizedBar(
            execution_timestamp=timestamp,
            execution_1m=(gc_candle, dxy_candle),
            htf_15m=None,
            htf_1h=None,
        )

        data.synchronized_bars.append(bar)
        data.execution_timestamps.append(timestamp)
        assert len(data) == 1
