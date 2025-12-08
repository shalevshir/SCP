"""Tests for structure event candle extraction.

Tests the extraction of BOS, CHoCH, sweep, and confirmation candles
from structure detection results.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest
from common.types import Candle
from rule_engine.htf.structure.events import (
    extract_bos_candle,
    extract_choch_candle,
    extract_confirmation_candle,
    extract_structure_candles,
    extract_sweep_candle,
)


@pytest.fixture
def sample_df():
    """Create sample OHLCV DataFrame for testing."""
    timestamps = pd.date_range(
        start="2025-01-01 10:00:00",
        periods=10,
        freq="1h",
        tz=timezone.utc,
    )
    
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 103.5, 103.0, 102.5, 102.0, 101.5],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0, 104.0, 103.5, 103.0, 102.5, 102.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0, 102.5, 102.0, 101.5, 101.0, 100.5],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5, 103.0, 102.5, 102.0, 101.5, 101.0],
            "volume": [1000.0] * 10,
        },
        index=timestamps,
    )
    
    return df


@pytest.fixture
def bos_series(sample_df):
    """Create sample BOS series."""
    series = pd.Series(None, index=sample_df.index, dtype="object")
    # Mark index 4 as bullish BOS
    series.iloc[4] = "bullish_bos"
    return series


@pytest.fixture
def choch_series(sample_df):
    """Create sample CHoCH series."""
    series = pd.Series(None, index=sample_df.index, dtype="object")
    # Mark index 6 as bearish CHoCH
    series.iloc[6] = "bearish_choch"
    return series


@pytest.fixture
def sweep_series(sample_df):
    """Create sample sweep events series."""
    series = pd.Series(None, index=sample_df.index, dtype="object")
    # Mark index 3 as sweep high
    series.iloc[3] = "sweep_high"
    return series


class TestExtractBOSCandle:
    """Tests for extract_bos_candle function."""
    
    def test_extract_bos_candle_success(self, sample_df, bos_series):
        """Test successful BOS candle extraction."""
        current_ts = sample_df.index[8]
        
        candle = extract_bos_candle(sample_df, bos_series, current_ts)
        
        assert candle is not None
        assert isinstance(candle, Candle)
        assert candle.timestamp == sample_df.index[4].to_pydatetime()
        assert candle.high == 105.0
        assert candle.low == 103.0
        assert candle.source == "HTF_BOS"
    
    def test_extract_bos_candle_no_bos(self, sample_df):
        """Test extraction when no BOS exists."""
        empty_series = pd.Series(None, index=sample_df.index, dtype="object")
        current_ts = sample_df.index[8]
        
        candle = extract_bos_candle(sample_df, empty_series, current_ts)
        
        assert candle is None
    
    def test_extract_bos_candle_future_bos(self, sample_df, bos_series):
        """Test extraction doesn't see future BOS."""
        # Current timestamp before BOS
        current_ts = sample_df.index[2]
        
        candle = extract_bos_candle(sample_df, bos_series, current_ts)
        
        assert candle is None
    
    def test_extract_bos_candle_none_series(self, sample_df):
        """Test extraction with None series."""
        current_ts = sample_df.index[8]
        
        candle = extract_bos_candle(sample_df, None, current_ts)
        
        assert candle is None


class TestExtractCHoCHCandle:
    """Tests for extract_choch_candle function."""
    
    def test_extract_choch_candle_success(self, sample_df, choch_series):
        """Test successful CHoCH candle extraction."""
        current_ts = sample_df.index[8]
        
        candle = extract_choch_candle(sample_df, choch_series, current_ts)
        
        assert candle is not None
        assert isinstance(candle, Candle)
        assert candle.timestamp == sample_df.index[6].to_pydatetime()
        assert candle.high == 103.5
        assert candle.low == 102.0
        assert candle.source == "HTF_CHOCH"
    
    def test_extract_choch_candle_no_choch(self, sample_df):
        """Test extraction when no CHoCH exists."""
        empty_series = pd.Series(None, index=sample_df.index, dtype="object")
        current_ts = sample_df.index[8]
        
        candle = extract_choch_candle(sample_df, empty_series, current_ts)
        
        assert candle is None


class TestExtractSweepCandle:
    """Tests for extract_sweep_candle function."""
    
    def test_extract_sweep_candle_success(self, sample_df, sweep_series):
        """Test successful sweep candle extraction."""
        current_ts = sample_df.index[8]
        
        candle = extract_sweep_candle(sample_df, sweep_series, current_ts)
        
        assert candle is not None
        assert isinstance(candle, Candle)
        assert candle.timestamp == sample_df.index[3].to_pydatetime()
        assert candle.high == 104.0
        assert candle.low == 102.0
        assert candle.source == "HTF_SWEEP"
    
    def test_extract_sweep_candle_no_sweep(self, sample_df):
        """Test extraction when no sweep exists."""
        empty_series = pd.Series(None, index=sample_df.index, dtype="object")
        current_ts = sample_df.index[8]
        
        candle = extract_sweep_candle(sample_df, empty_series, current_ts)
        
        assert candle is None


class TestExtractConfirmationCandle:
    """Tests for extract_confirmation_candle function."""
    
    def test_extract_confirmation_candle_current(self, sample_df):
        """Test extraction of current candle (lookback=0)."""
        current_ts = sample_df.index[5]
        
        candle = extract_confirmation_candle(sample_df, current_ts, lookback=0)
        
        assert candle is not None
        assert isinstance(candle, Candle)
        assert candle.timestamp == sample_df.index[5].to_pydatetime()
        assert candle.close == 103.0
        assert candle.source == "CONFIRMATION"
    
    def test_extract_confirmation_candle_previous(self, sample_df):
        """Test extraction of previous candle (lookback=1)."""
        current_ts = sample_df.index[5]
        
        candle = extract_confirmation_candle(sample_df, current_ts, lookback=1)
        
        assert candle is not None
        assert candle.timestamp == sample_df.index[4].to_pydatetime()
        assert candle.close == 104.5
    
    def test_extract_confirmation_candle_excessive_lookback(self, sample_df):
        """Test extraction with lookback exceeding available data."""
        current_ts = sample_df.index[2]
        
        # Lookback of 10 but only 3 candles available
        candle = extract_confirmation_candle(sample_df, current_ts, lookback=10)
        
        assert candle is not None
        # Should return first available candle
        assert candle.timestamp == sample_df.index[0].to_pydatetime()
    
    def test_extract_confirmation_candle_empty_df(self):
        """Test extraction with empty DataFrame."""
        empty_df = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"]
        ).set_index(pd.DatetimeIndex([], name="timestamp", tz=timezone.utc))
        
        current_ts = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        
        candle = extract_confirmation_candle(empty_df, current_ts)
        
        assert candle is None


class TestExtractStructureCandles:
    """Tests for extract_structure_candles function."""
    
    def test_extract_structure_candles_all_present(
        self, sample_df, bos_series, choch_series, sweep_series
    ):
        """Test extraction when all structure events are present."""
        current_ts = sample_df.index[8]
        
        # Use sample_df for both 1h and 15m (simplified)
        candles = extract_structure_candles(
            df_1h=sample_df,
            df_15m=sample_df,
            bos_series=bos_series,
            choch_series=choch_series,
            sweep_events=sweep_series,
            current_timestamp=current_ts,
        )
        
        assert "bos_candle" in candles
        assert "choch_candle" in candles
        assert "sweep_candle" in candles
        
        assert candles["bos_candle"] is not None
        assert candles["choch_candle"] is not None
        assert candles["sweep_candle"] is not None
        
        assert candles["bos_candle"].timestamp == sample_df.index[4].to_pydatetime()
        assert candles["choch_candle"].timestamp == sample_df.index[6].to_pydatetime()
        assert candles["sweep_candle"].timestamp == sample_df.index[3].to_pydatetime()
    
    def test_extract_structure_candles_none_present(self, sample_df):
        """Test extraction when no structure events are present."""
        current_ts = sample_df.index[8]
        
        candles = extract_structure_candles(
            df_1h=sample_df,
            df_15m=sample_df,
            bos_series=None,
            choch_series=None,
            sweep_events=None,
            current_timestamp=current_ts,
        )
        
        assert candles["bos_candle"] is None
        assert candles["choch_candle"] is None
        assert candles["sweep_candle"] is None
    
    def test_extract_structure_candles_partial(self, sample_df, bos_series):
        """Test extraction when only some structure events are present."""
        current_ts = sample_df.index[8]
        
        candles = extract_structure_candles(
            df_1h=sample_df,
            df_15m=None,
            bos_series=bos_series,
            choch_series=None,
            sweep_events=None,
            current_timestamp=current_ts,
        )
        
        assert candles["bos_candle"] is not None
        assert candles["choch_candle"] is None
        assert candles["sweep_candle"] is None

