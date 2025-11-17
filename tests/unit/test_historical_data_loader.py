"""Tests for HistoricalDataLoader."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from common.exceptions import DataSourceError
from data_layer.loader import HistoricalDataLoader


class TestHistoricalDataLoader:
    """Tests for HistoricalDataLoader class."""

    @pytest.fixture
    def data_dir(self) -> Path:
        """Provide path to test data directory."""
        return Path("data/gc_dx_ohlcv")

    @pytest.fixture
    def loader(self, data_dir: Path) -> HistoricalDataLoader:
        """Create a HistoricalDataLoader instance."""
        return HistoricalDataLoader(data_dir)

    def test_loader_initialization(self, data_dir: Path) -> None:
        """Test that loader can be initialized with data directory."""
        loader = HistoricalDataLoader(data_dir)
        assert loader is not None
        assert isinstance(loader, HistoricalDataLoader)

    def test_load_single_symbol_returns_dataframe_with_timestamp_index(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test loading a single symbol returns DataFrame with timestamp index."""
        start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 4, 30, 0, tzinfo=UTC)

        result = loader.load(["GC"], "1m", start, end)

        assert isinstance(result, dict)
        assert "GC" in result
        assert isinstance(result["GC"], pd.DataFrame)
        assert isinstance(result["GC"].index, pd.DatetimeIndex)
        assert result["GC"].index.name == "timestamp"

    def test_load_multiple_symbols_returns_dict_of_dataframes(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test loading multiple symbols returns dict with DataFrames for each."""
        start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 4, 30, 0, tzinfo=UTC)

        result = loader.load(["GC", "DXY"], "1m", start, end)

        assert isinstance(result, dict)
        assert "GC" in result
        assert "DXY" in result
        assert isinstance(result["GC"], pd.DataFrame)
        assert isinstance(result["DXY"], pd.DataFrame)

    def test_load_filters_by_date_range(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test that load filters data by date range."""
        start = datetime(2025, 9, 30, 4, 21, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 4, 23, 0, tzinfo=UTC)

        result = loader.load(["GC"], "1m", start, end)

        df = result["GC"]
        assert df.index.min() >= start
        assert df.index.max() < end

    def test_load_handles_empty_results(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test that load handles empty results gracefully."""
        # Date range with no data
        start = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2020, 1, 2, 0, 0, 0, tzinfo=UTC)

        result = loader.load(["GC"], "1m", start, end)

        assert isinstance(result, dict)
        assert "GC" in result
        assert isinstance(result["GC"], pd.DataFrame)
        assert len(result["GC"]) == 0

    def test_load_raises_error_for_missing_file(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test that load raises error for missing file."""
        start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC)

        with pytest.raises(DataSourceError):
            loader.load(["NONEXISTENT"], "1m", start, end)

    def test_load_validates_timeframe_parameter(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test that load validates timeframe parameter."""
        start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 4, 30, 0, tzinfo=UTC)

        # Valid timeframes should work (1s excluded as not in repo)
        for timeframe in ["1m", "15m", "1h"]:
            result = loader.load(["GC"], timeframe, start, end)
            assert isinstance(result, dict)

    def test_dataframe_has_correct_columns_and_types(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test that DataFrame has correct columns and data types."""
        start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 4, 30, 0, tzinfo=UTC)

        result = loader.load(["GC"], "1m", start, end)
        df = result["GC"]

        # Check columns exist
        expected_columns = ["open", "high", "low", "close", "volume", "symbol"]
        for col in expected_columns:
            assert col in df.columns

        # Check data types
        assert df["open"].dtype == float
        assert df["high"].dtype == float
        assert df["low"].dtype == float
        assert df["close"].dtype == float
        assert df["volume"].dtype == float
        assert df["symbol"].dtype == object  # string type

    def test_dataframe_index_is_sorted_and_unique(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test that DataFrame index is sorted and has unique timestamps."""
        start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 4, 30, 0, tzinfo=UTC)

        result = loader.load(["GC"], "1m", start, end)
        df = result["GC"]

        # Check index is sorted
        assert df.index.is_monotonic_increasing

        # Check index is unique
        assert df.index.is_unique

    def test_dxy_symbol_maps_to_dx_file(
        self, loader: HistoricalDataLoader
    ) -> None:
        """Test that DXY symbol correctly maps to DX_ohlcv file."""
        start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=UTC)
        end = datetime(2025, 9, 30, 4, 30, 0, tzinfo=UTC)

        result = loader.load(["DXY"], "1m", start, end)

        assert "DXY" in result
        assert isinstance(result["DXY"], pd.DataFrame)
        assert len(result["DXY"]) > 0

