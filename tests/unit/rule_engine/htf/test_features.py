"""Tests for HTF features computation module.

Tests cover:
- StreamingHTFFeatureComputer incremental updates
- Vectorized HTF feature computation
- Feature extraction from synchronized bars
"""

from datetime import UTC, datetime

import pandas as pd
import pytest
from common.types import Candle

from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar
from rule_engine.htf.features import (
    StreamingHTFFeatureComputer,
    compute_htf_features_vectorized,
)


class TestStreamingHTFFeatureComputer:
    """Tests for StreamingHTFFeatureComputer class."""

    @pytest.fixture
    def htf_computer(self) -> StreamingHTFFeatureComputer:
        """Create a StreamingHTFFeatureComputer instance."""
        return StreamingHTFFeatureComputer()

    def test_initialization(self) -> None:
        """Test that HTF computer initializes correctly."""
        computer = StreamingHTFFeatureComputer()
        assert computer.processor_1h is not None
        assert computer.processor_15m is not None
        assert computer.features_1h.empty
        assert computer.features_15m.empty

    def test_update_from_sync_bar_with_htf_data(
        self, htf_computer: StreamingHTFFeatureComputer
    ) -> None:
        """Test updating features from sync bar with HTF data."""
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
        
        htf_1h_gc = Candle(
            timestamp=datetime(2025, 9, 30, 9, 0, 0, tzinfo=UTC),
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
            timestamp=datetime(2025, 9, 30, 9, 0, 0, tzinfo=UTC),
            open=99.5,
            high=100.5,
            low=99.4,
            close=100.1,
            volume=3000.0,
            symbol="DXY",
            timeframe="1h",
            source="CSV",
        )
        
        sync_bar = SynchronizedBar(
            execution_timestamp=timestamp,
            execution_1m=(exec_gc, exec_dxy),
            htf_15m=(htf_15m_gc, htf_15m_dxy),
            htf_1h=(htf_1h_gc, htf_1h_dxy),
        )
        
        features_15m, features_1h = htf_computer.update_from_sync_bar(sync_bar)
        
        # Features should be computed (may be empty if not warmed up)
        assert isinstance(features_15m, pd.Series)
        assert isinstance(features_1h, pd.Series)

    def test_update_from_sync_bar_without_htf_data(
        self, htf_computer: StreamingHTFFeatureComputer
    ) -> None:
        """Test updating when HTF data is None."""
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
        
        sync_bar = SynchronizedBar(
            execution_timestamp=timestamp,
            execution_1m=(exec_gc, exec_dxy),
            htf_15m=None,
            htf_1h=None,
        )
        
        features_15m, features_1h = htf_computer.update_from_sync_bar(sync_bar)
        
        # Features should still be returned (may be empty)
        assert isinstance(features_15m, pd.Series)
        assert isinstance(features_1h, pd.Series)

    def test_is_warmed_up(self, htf_computer: StreamingHTFFeatureComputer) -> None:
        """Test warmup detection."""
        # Initially not warmed up
        assert not htf_computer.is_warmed_up()
        
        # After processing many bars, should be warmed up
        # (This is a basic test - actual warmup requires many bars)
        # For now, just verify the method exists and returns bool
        result = htf_computer.is_warmed_up()
        assert isinstance(result, bool)


class TestComputeHtfFeaturesVectorized:
    """Tests for compute_htf_features_vectorized function."""

    def test_compute_with_empty_lists(self) -> None:
        """Test vectorized computation with empty candle lists."""
        features_15m, features_1h = compute_htf_features_vectorized(
            gc_candles_15m=[],
            dxy_candles_15m=[],
            gc_candles_1h=[],
            dxy_candles_1h=[],
        )
        
        assert features_15m is None
        assert features_1h is None

    def test_compute_with_single_candles(self) -> None:
        """Test vectorized computation with single candles."""
        gc_15m = Candle(
            timestamp=datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC),
            open=2000.0,
            high=2001.0,
            low=1999.0,
            close=2000.5,
            volume=100.0,
            symbol="GC",
            timeframe="15m",
            source="CSV",
        )
        dxy_15m = Candle(
            timestamp=datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC),
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.05,
            volume=50.0,
            symbol="DXY",
            timeframe="15m",
            source="CSV",
        )
        
        gc_1h = Candle(
            timestamp=datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC),
            open=1999.0,
            high=2002.0,
            low=1998.0,
            close=2001.0,
            volume=600.0,
            symbol="GC",
            timeframe="1h",
            source="CSV",
        )
        dxy_1h = Candle(
            timestamp=datetime(2025, 9, 30, 10, 0, 0, tzinfo=UTC),
            open=99.8,
            high=100.2,
            low=99.7,
            close=100.1,
            volume=300.0,
            symbol="DXY",
            timeframe="1h",
            source="CSV",
        )
        
        features_15m, features_1h = compute_htf_features_vectorized(
            gc_candles_15m=[gc_15m],
            dxy_candles_15m=[dxy_15m],
            gc_candles_1h=[gc_1h],
            dxy_candles_1h=[dxy_1h],
        )
        
        # With single candles, features may be None due to insufficient data
        # for indicators (RSI needs 14, DXY correlation needs 50, etc.)
        # But the function should not crash
        assert features_15m is None or isinstance(features_15m, pd.DataFrame)
        assert features_1h is None or isinstance(features_1h, pd.DataFrame)

    def test_compute_with_multiple_candles(self) -> None:
        """Test vectorized computation with multiple candles."""
        # Create enough candles for indicators to compute
        gc_15m_candles = []
        dxy_15m_candles = []
        gc_1h_candles = []
        dxy_1h_candles = []
        
        # Create 60 15m candles (enough for DXY correlation window of 50)
        for i in range(60):
            # Calculate hours and minutes properly (15m intervals)
            hours = 8 + (i * 15) // 60
            minutes = (i * 15) % 60
            ts_15m = datetime(2025, 9, 30, hours, minutes, 0, tzinfo=UTC)
            gc_15m_candles.append(
                Candle(
                    timestamp=ts_15m,
                    open=2000.0 + i * 0.1,
                    high=2001.0 + i * 0.1,
                    low=1999.0 + i * 0.1,
                    close=2000.5 + i * 0.1,
                    volume=100.0 + i,
                    symbol="GC",
                    timeframe="15m",
                    source="CSV",
                )
            )
            dxy_15m_candles.append(
                Candle(
                    timestamp=ts_15m,
                    open=100.0 - i * 0.01,
                    high=100.1 - i * 0.01,
                    low=99.9 - i * 0.01,
                    close=100.05 - i * 0.01,
                    volume=50.0 + i,
                    symbol="DXY",
                    timeframe="15m",
                    source="CSV",
                )
            )
        
        # Create 60 1h candles (spread across multiple days if needed)
        from datetime import timedelta
        base_date = datetime(2025, 9, 30, 8, 0, 0, tzinfo=UTC)
        for i in range(60):
            ts_1h = base_date + timedelta(hours=i)
            gc_1h_candles.append(
                Candle(
                    timestamp=ts_1h,
                    open=2000.0 + i * 0.5,
                    high=2002.0 + i * 0.5,
                    low=1998.0 + i * 0.5,
                    close=2001.0 + i * 0.5,
                    volume=600.0 + i * 10,
                    symbol="GC",
                    timeframe="1h",
                    source="CSV",
                )
            )
            dxy_1h_candles.append(
                Candle(
                    timestamp=ts_1h,
                    open=100.0 - i * 0.05,
                    high=100.2 - i * 0.05,
                    low=99.8 - i * 0.05,
                    close=100.1 - i * 0.05,
                    volume=300.0 + i * 5,
                    symbol="DXY",
                    timeframe="1h",
                    source="CSV",
                )
            )
        
        features_15m, features_1h = compute_htf_features_vectorized(
            gc_candles_15m=gc_15m_candles,
            dxy_candles_15m=dxy_15m_candles,
            gc_candles_1h=gc_1h_candles,
            dxy_candles_1h=dxy_1h_candles,
        )
        
        # Should have computed features
        assert features_15m is not None
        assert features_1h is not None
        assert isinstance(features_15m, pd.DataFrame)
        assert isinstance(features_1h, pd.DataFrame)
        assert len(features_15m) > 0
        assert len(features_1h) > 0
        
        # Check that expected columns exist
        expected_cols = ["open", "high", "low", "close", "volume"]
        for col in expected_cols:
            assert col in features_15m.columns
            assert col in features_1h.columns

