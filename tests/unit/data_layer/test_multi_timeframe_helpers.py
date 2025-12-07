"""Tests for multi_timeframe_helpers module."""

from datetime import UTC, datetime

import pandas as pd
import pytest
from common.types import Candle

from data_layer.multi_timeframe_helpers import (
    build_htf_dataframe_from_candles,
    candles_to_dataframe,
    extract_execution_dataframes,
    extract_htf_candles_by_timeframe,
)
from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar


class TestExtractExecutionDataframes:
    """Tests for extract_execution_dataframes function."""

    def test_extract_empty_data(self) -> None:
        """Test extraction from empty MultiTimeframeData."""
        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=[],
            execution_timestamps=[],
        )
        
        gc_df, dxy_df = extract_execution_dataframes(multi_tf_data)
        
        assert isinstance(gc_df, pd.DataFrame)
        assert isinstance(dxy_df, pd.DataFrame)
        assert len(gc_df) == 0
        assert len(dxy_df) == 0
        assert isinstance(gc_df.index, pd.DatetimeIndex)
        assert isinstance(dxy_df.index, pd.DatetimeIndex)

    def test_extract_single_bar(self) -> None:
        """Test extraction from single synchronized bar."""
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
        
        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=[bar],
            execution_timestamps=[timestamp],
        )
        
        gc_df, dxy_df = extract_execution_dataframes(multi_tf_data)
        
        assert len(gc_df) == 1
        assert len(dxy_df) == 1
        assert gc_df.index[0] == timestamp
        assert dxy_df.index[0] == timestamp
        assert gc_df.loc[timestamp, "open"] == 2000.0
        assert dxy_df.loc[timestamp, "open"] == 100.0

    def test_extract_multiple_bars(self) -> None:
        """Test extraction from multiple synchronized bars."""
        bars = []
        timestamps = []
        for i in range(5):
            ts = datetime(2025, 9, 30, 10, i, 0, tzinfo=UTC)
            gc_candle = Candle(
                timestamp=ts,
                open=2000.0 + i,
                high=2001.0 + i,
                low=1999.0 + i,
                close=2000.5 + i,
                volume=100.0 + i,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )
            dxy_candle = Candle(
                timestamp=ts,
                open=100.0 + i * 0.1,
                high=100.1 + i * 0.1,
                low=99.9 + i * 0.1,
                close=100.05 + i * 0.1,
                volume=50.0 + i,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )
            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(gc_candle, dxy_candle),
                    htf_15m=None,
                    htf_1h=None,
                )
            )
            timestamps.append(ts)
        
        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=bars,
            execution_timestamps=timestamps,
        )
        
        gc_df, dxy_df = extract_execution_dataframes(multi_tf_data)
        
        assert len(gc_df) == 5
        assert len(dxy_df) == 5
        assert list(gc_df.index) == timestamps
        assert list(dxy_df.index) == timestamps


class TestCandlesToDataframe:
    """Tests for candles_to_dataframe function."""

    def test_empty_list(self) -> None:
        """Test conversion of empty candle list."""
        df = candles_to_dataframe([], "1m")
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_single_candle(self) -> None:
        """Test conversion of single candle."""
        timestamp = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        candle = Candle(
            timestamp=timestamp,
            open=2000.0,
            high=2001.0,
            low=1999.0,
            close=2000.5,
            volume=100.0,
            symbol="GC",
            timeframe="15m",
            source="CSV",
        )
        
        df = candles_to_dataframe([candle], "15m")
        
        assert len(df) == 1
        assert df.index[0] == timestamp
        assert df.loc[timestamp, "open"] == 2000.0
        assert df.loc[timestamp, "close"] == 2000.5

    def test_multiple_candles(self) -> None:
        """Test conversion of multiple candles."""
        candles = []
        for i in range(3):
            ts = datetime(2025, 9, 30, 10, i * 15, 0, tzinfo=UTC)
            candles.append(
                Candle(
                    timestamp=ts,
                    open=2000.0 + i,
                    high=2001.0 + i,
                    low=1999.0 + i,
                    close=2000.5 + i,
                    volume=100.0 + i,
                    symbol="GC",
                    timeframe="15m",
                    source="CSV",
                )
            )
        
        df = candles_to_dataframe(candles, "15m")
        
        assert len(df) == 3
        assert list(df.index) == [c.timestamp for c in candles]


class TestExtractHtfCandlesByTimeframe:
    """Tests for extract_htf_candles_by_timeframe function."""

    def test_extract_15m_candles(self) -> None:
        """Test extraction of 15m HTF candles."""
        timestamp = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        exec_gc = Candle(
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
        exec_dxy = Candle(
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
        
        htf_15m_gc = Candle(
            timestamp=datetime(2025, 9, 30, 9, 59, 0, tzinfo=UTC),
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
            timestamp=datetime(2025, 9, 30, 9, 59, 0, tzinfo=UTC),
            open=99.8,
            high=100.2,
            low=99.7,
            close=100.0,
            volume=750.0,
            symbol="DXY",
            timeframe="15m",
            source="CSV",
        )
        
        bar = SynchronizedBar(
            execution_timestamp=timestamp,
            execution_1m=(exec_gc, exec_dxy),
            htf_15m=(htf_15m_gc, htf_15m_dxy),
            htf_1h=None,
        )
        
        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=[bar],
            execution_timestamps=[timestamp],
        )
        
        gc_15m, dxy_15m = extract_htf_candles_by_timeframe(multi_tf_data, "15m")
        
        assert len(gc_15m) == 1
        assert len(dxy_15m) == 1
        assert gc_15m[0] == htf_15m_gc
        assert dxy_15m[0] == htf_15m_dxy

    def test_extract_missing_timeframe(self) -> None:
        """Test extraction when timeframe not in HTF timeframes."""
        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=[],
            execution_timestamps=[],
        )
        
        gc_5m, dxy_5m = extract_htf_candles_by_timeframe(multi_tf_data, "5m")
        
        assert len(gc_5m) == 0
        assert len(dxy_5m) == 0

    def test_extract_when_htf_none(self) -> None:
        """Test extraction when HTF bars are None."""
        timestamp = datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC)
        exec_gc = Candle(
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
        exec_dxy = Candle(
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
            execution_1m=(exec_gc, exec_dxy),
            htf_15m=None,  # No HTF data
            htf_1h=None,
        )
        
        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=[bar],
            execution_timestamps=[timestamp],
        )
        
        gc_15m, dxy_15m = extract_htf_candles_by_timeframe(multi_tf_data, "15m")
        
        assert len(gc_15m) == 0
        assert len(dxy_15m) == 0

    def test_extract_deduplicates_forward_filled_candles(self) -> None:
        """Test that extraction deduplicates HTF candles that are forward-filled.
        
        When multiple 1m execution bars reference the same HTF candle (forward-fill),
        the function should return only unique candles based on timestamp.
        """
        # Create a single unique 15m HTF candle
        htf_15m_gc = Candle(
            timestamp=datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC),
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
            timestamp=datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC),
            open=99.8,
            high=100.2,
            low=99.7,
            close=100.0,
            volume=750.0,
            symbol="DXY",
            timeframe="15m",
            source="CSV",
        )
        
        # Create 15 synchronized bars (15 minutes of 1m data) all referencing the same 15m candle
        synchronized_bars = []
        execution_timestamps = []
        for i in range(15):
            exec_timestamp = datetime(2025, 9, 30, 10, i, 0, tzinfo=UTC)
            exec_gc = Candle(
                timestamp=exec_timestamp,
                open=2000.0 + i * 0.1,
                high=2001.0 + i * 0.1,
                low=1999.0 + i * 0.1,
                close=2000.5 + i * 0.1,
                volume=100.0,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )
            exec_dxy = Candle(
                timestamp=exec_timestamp,
                open=100.0 + i * 0.01,
                high=100.1 + i * 0.01,
                low=99.9 + i * 0.01,
                close=100.05 + i * 0.01,
                volume=50.0,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )
            
            # All bars reference the same 15m HTF candle (forward-fill behavior)
            bar = SynchronizedBar(
                execution_timestamp=exec_timestamp,
                execution_1m=(exec_gc, exec_dxy),
                htf_15m=(htf_15m_gc, htf_15m_dxy),  # Same candle referenced 15 times
                htf_1h=None,
            )
            synchronized_bars.append(bar)
            execution_timestamps.append(exec_timestamp)
        
        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=synchronized_bars,
            execution_timestamps=execution_timestamps,
        )
        
        # Extract should return only 1 unique candle, not 15 duplicates
        gc_15m, dxy_15m = extract_htf_candles_by_timeframe(multi_tf_data, "15m")
        
        # Should have only 1 unique candle, not 15 duplicates
        assert len(gc_15m) == 1, f"Expected 1 unique candle, got {len(gc_15m)} duplicates"
        assert len(dxy_15m) == 1, f"Expected 1 unique candle, got {len(dxy_15m)} duplicates"
        assert gc_15m[0] == htf_15m_gc
        assert dxy_15m[0] == htf_15m_dxy
        
        # Verify DataFrame has unique timestamps (no duplicates)
        gc_df = candles_to_dataframe(gc_15m, "15m")
        assert len(gc_df) == 1
        assert not gc_df.index.duplicated().any(), "DataFrame should not have duplicate timestamps"


class TestBuildHtfDataframeFromCandles:
    """Tests for build_htf_dataframe_from_candles function."""

    def test_empty_list_returns_none(self) -> None:
        """Test that empty list returns None."""
        result = build_htf_dataframe_from_candles([], "15m")
        assert result is None

    def test_builds_dataframe_from_candles(self) -> None:
        """Test DataFrame building from candles."""
        candles = [
            Candle(
                timestamp=datetime(2025, 9, 30, 10, i * 15, 0, tzinfo=UTC),
                open=2000.0 + i,
                high=2001.0 + i,
                low=1999.0 + i,
                close=2000.5 + i,
                volume=100.0 + i,
                symbol="GC",
                timeframe="15m",
                source="CSV",
            )
            for i in range(3)
        ]
        
        df = build_htf_dataframe_from_candles(candles, "15m")
        
        assert df is not None
        assert len(df) == 3
        assert isinstance(df.index, pd.DatetimeIndex)

