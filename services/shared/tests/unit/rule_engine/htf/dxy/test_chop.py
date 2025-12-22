"""Unit tests for DXY chop detection.

Tests the DXY chop (ranging) detection logic which identifies wick-to-wick
behavior in the Dollar Index. When detected, HTF bias should be forced to neutral.
"""

from pathlib import Path

import pandas as pd
import pytest
from scp_shared.rule_engine.htf.dxy.chop import detect_dxy_chop

# Path to project root (8 levels up from services/shared/tests/unit/rule_engine/htf/dxy/ to repository root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent.parent.parent


class TestDXYChopDetection:
    """Test DXY chop detection with wick-to-body ratio logic."""

    @pytest.fixture
    def simple_chop_data(self) -> pd.DataFrame:
        """Create simple DXY data with chop candles (large wicks, small bodies)."""
        return pd.DataFrame(
            {
                "high": [101.0, 101.5, 102.0, 102.5, 103.0],
                "low": [99.0, 99.5, 100.0, 100.5, 101.0],
                "open": [100.0, 100.5, 101.0, 101.5, 102.0],
                "close": [100.2, 100.7, 101.2, 101.7, 102.2],
                # Body = 0.2, Wicks = 1.8 total, ratio = 9.0 (high chop)
            }
        )

    @pytest.fixture
    def simple_trending_data(self) -> pd.DataFrame:
        """Create simple DXY data with trending candles (small wicks, large bodies)."""
        return pd.DataFrame(
            {
                "high": [100.5, 101.5, 102.5, 103.5, 104.5],
                "low": [100.0, 101.0, 102.0, 103.0, 104.0],
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                # Body = 0.5, Wicks = 0 total, ratio = 0 (trending)
            }
        )

    @pytest.fixture
    def mixed_chop_data(self) -> pd.DataFrame:
        """Create DXY data with mix of chop and trending candles."""
        return pd.DataFrame(
            {
                "high": [101.0, 101.5, 102.5, 102.0, 103.0, 103.5, 104.0],
                "low": [99.0, 99.5, 102.0, 100.5, 101.5, 103.0, 103.5],
                "open": [100.0, 100.5, 102.0, 101.5, 102.0, 103.0, 103.5],
                "close": [100.2, 100.7, 102.5, 101.7, 102.8, 103.5, 104.0],
                # 0-1: chop, 2: trending, 3-4: chop, 5-6: trending
            }
        )

    def test_detect_chop_basic(self, simple_chop_data: pd.DataFrame) -> None:
        """Test basic chop detection with default parameters."""
        result = detect_dxy_chop(simple_chop_data)

        # Should return Series with same length
        assert isinstance(result, pd.Series)
        assert len(result) == len(simple_chop_data)

        # Should be boolean dtype
        assert result.dtype == bool

    def test_detect_chop_three_consecutive_triggers(
        self, simple_chop_data: pd.DataFrame
    ) -> None:
        """Test that 3+ consecutive chop candles trigger chop condition."""
        result = detect_dxy_chop(
            simple_chop_data, wick_threshold=0.5, min_chop_candles=3
        )

        # First 2 candles should be False (need 3 consecutive)
        assert not result.iloc[0]
        assert not result.iloc[1]

        # From candle 3 onwards should be True (3+ consecutive chop)
        assert result.iloc[2]
        assert result.iloc[3]
        assert result.iloc[4]

    def test_detect_chop_two_consecutive_not_enough(
        self, simple_chop_data: pd.DataFrame
    ) -> None:
        """Test that 2 consecutive chop candles don't trigger (need 3)."""
        # Take only first 2 candles
        data = simple_chop_data.head(2)
        result = detect_dxy_chop(data, wick_threshold=0.5, min_chop_candles=3)

        # Should all be False (need 3 consecutive)
        assert not result.any()

    def test_detect_chop_single_candle_not_enough(
        self, simple_chop_data: pd.DataFrame
    ) -> None:
        """Test that single chop candle doesn't trigger."""
        # Take only first candle
        data = simple_chop_data.head(1)
        result = detect_dxy_chop(data, wick_threshold=0.5, min_chop_candles=3)

        # Should be False
        assert not result.iloc[0]

    def test_detect_chop_trending_data_no_trigger(
        self, simple_trending_data: pd.DataFrame
    ) -> None:
        """Test that trending candles (small wicks) don't trigger chop."""
        result = detect_dxy_chop(simple_trending_data, wick_threshold=0.5)

        # All should be False (no chop in trending data)
        assert not result.any()

    def test_detect_chop_interrupted_sequence_resets(
        self, mixed_chop_data: pd.DataFrame
    ) -> None:
        """Test that non-chop candle interrupts and resets the count."""
        result = detect_dxy_chop(
            mixed_chop_data, wick_threshold=0.5, min_chop_candles=3
        )

        # Candles 0-1: chop but only 2 (not enough)
        assert not result.iloc[0]
        assert not result.iloc[1]

        # Candle 2: trending (resets count)
        assert not result.iloc[2]

        # Candles 3-4: chop but only 2 (not enough, count was reset)
        assert not result.iloc[3]
        assert not result.iloc[4]

        # Candles 5-6: trending
        assert not result.iloc[5]
        assert not result.iloc[6]

    def test_detect_chop_custom_threshold(self, simple_chop_data: pd.DataFrame) -> None:
        """Test chop detection with custom wick threshold."""
        # Very high threshold (only extreme wicks trigger)
        result_high = detect_dxy_chop(simple_chop_data, wick_threshold=10.0)
        assert not result_high.any()  # No candles meet threshold

        # Very low threshold (almost all candles trigger)
        result_low = detect_dxy_chop(simple_chop_data, wick_threshold=0.1)
        assert result_low.iloc[2:].all()  # Most candles meet threshold

    def test_detect_chop_custom_min_candles(
        self, simple_chop_data: pd.DataFrame
    ) -> None:
        """Test chop detection with custom minimum consecutive candles."""
        # Need 5 consecutive chop candles
        result = detect_dxy_chop(simple_chop_data, min_chop_candles=5)

        # First 4 should be False
        assert not result.iloc[:4].any()

        # 5th candle should be True (5 consecutive)
        assert result.iloc[4]

    def test_detect_chop_doji_candles(self) -> None:
        """Test that doji candles (zero body) are treated as chop."""
        doji_data = pd.DataFrame(
            {
                "high": [101.0, 101.5, 102.0],
                "low": [99.0, 99.5, 100.0],
                "open": [100.0, 100.5, 101.0],
                "close": [100.0, 100.5, 101.0],  # Same as open (doji)
            }
        )

        result = detect_dxy_chop(doji_data, wick_threshold=0.5, min_chop_candles=3)

        # All doji should be considered chop
        # Third candle should trigger (3 consecutive)
        assert result.iloc[2]

    def test_detect_chop_empty_dataframe(self) -> None:
        """Test chop detection with empty DataFrame."""
        empty_df = pd.DataFrame(columns=["high", "low", "open", "close"])
        result = detect_dxy_chop(empty_df)

        # Should return empty Series
        assert len(result) == 0
        assert isinstance(result, pd.Series)

    def test_detect_chop_insufficient_data(self) -> None:
        """Test chop detection with insufficient data (< min_chop_candles)."""
        small_df = pd.DataFrame(
            {
                "high": [101.0, 101.5],
                "low": [99.0, 99.5],
                "open": [100.0, 100.5],
                "close": [100.2, 100.7],
            }
        )

        result = detect_dxy_chop(small_df, min_chop_candles=3)

        # All should be False (need 3 candles, only have 2)
        assert not result.any()

    def test_detect_chop_missing_high_column(self) -> None:
        """Test that missing 'high' column raises ValueError."""
        invalid_df = pd.DataFrame(
            {
                "low": [99.0, 99.5],
                "open": [100.0, 100.5],
                "close": [100.2, 100.7],
            }
        )

        with pytest.raises(ValueError, match="Missing required column.*high"):
            detect_dxy_chop(invalid_df)

    def test_detect_chop_missing_low_column(self) -> None:
        """Test that missing 'low' column raises ValueError."""
        invalid_df = pd.DataFrame(
            {
                "high": [101.0, 101.5],
                "open": [100.0, 100.5],
                "close": [100.2, 100.7],
            }
        )

        with pytest.raises(ValueError, match="Missing required column.*low"):
            detect_dxy_chop(invalid_df)

    def test_detect_chop_missing_open_column(self) -> None:
        """Test that missing 'open' column raises ValueError."""
        invalid_df = pd.DataFrame(
            {
                "high": [101.0, 101.5],
                "low": [99.0, 99.5],
                "close": [100.2, 100.7],
            }
        )

        with pytest.raises(ValueError, match="Missing required column.*open"):
            detect_dxy_chop(invalid_df)

    def test_detect_chop_missing_close_column(self) -> None:
        """Test that missing 'close' column raises ValueError."""
        invalid_df = pd.DataFrame(
            {
                "high": [101.0, 101.5],
                "low": [99.0, 99.5],
                "open": [100.0, 100.5],
            }
        )

        with pytest.raises(ValueError, match="Missing required column.*close"):
            detect_dxy_chop(invalid_df)

    def test_detect_chop_invalid_threshold(self) -> None:
        """Test that invalid wick_threshold raises ValueError."""
        df = pd.DataFrame(
            {
                "high": [101.0],
                "low": [99.0],
                "open": [100.0],
                "close": [100.2],
            }
        )

        with pytest.raises(ValueError, match="wick_threshold must be > 0"):
            detect_dxy_chop(df, wick_threshold=0)

        with pytest.raises(ValueError, match="wick_threshold must be > 0"):
            detect_dxy_chop(df, wick_threshold=-0.5)

    def test_detect_chop_invalid_min_candles(self) -> None:
        """Test that invalid min_chop_candles raises ValueError."""
        df = pd.DataFrame(
            {
                "high": [101.0],
                "low": [99.0],
                "open": [100.0],
                "close": [100.2],
            }
        )

        with pytest.raises(ValueError, match="min_chop_candles must be >= 1"):
            detect_dxy_chop(df, min_chop_candles=0)

        with pytest.raises(ValueError, match="min_chop_candles must be >= 1"):
            detect_dxy_chop(df, min_chop_candles=-1)

    def test_detect_chop_nan_values(self) -> None:
        """Test chop detection with NaN values in data."""
        nan_data = pd.DataFrame(
            {
                "high": [101.0, float("nan"), 102.0, 102.5, 103.0],
                "low": [99.0, 99.5, 100.0, 100.5, 101.0],
                "open": [100.0, 100.5, 101.0, 101.5, 102.0],
                "close": [100.2, 100.7, 101.2, 101.7, 102.2],
            }
        )

        result = detect_dxy_chop(nan_data, wick_threshold=0.5, min_chop_candles=3)

        # Should handle NaN gracefully
        assert isinstance(result, pd.Series)
        assert len(result) == len(nan_data)

        # NaN row should not be considered chop
        assert not result.iloc[1]

    def test_detect_chop_index_preserved(self, simple_chop_data: pd.DataFrame) -> None:
        """Test that result preserves input DataFrame index."""
        # Set custom index
        simple_chop_data.index = pd.date_range(
            "2025-01-01", periods=len(simple_chop_data), freq="1H"
        )

        result = detect_dxy_chop(simple_chop_data)

        # Index should match input
        assert result.index.equals(simple_chop_data.index)

    def test_detect_chop_return_type(self, simple_chop_data: pd.DataFrame) -> None:
        """Test that result is pd.Series with bool dtype."""
        result = detect_dxy_chop(simple_chop_data)

        assert isinstance(result, pd.Series)
        assert result.dtype == bool
        assert result.name == "dxy_chop"

    def test_detect_chop_wick_ratio_calculation(self) -> None:
        """Test wick ratio calculation logic."""
        # Candle with known wick ratio
        test_data = pd.DataFrame(
            {
                "high": [102.0],
                "low": [98.0],
                "open": [100.0],
                "close": [101.0],
                # Upper wick: 102 - 101 = 1
                # Lower wick: 100 - 98 = 2
                # Body: |101 - 100| = 1
                # Ratio: (1 + 2) / 1 = 3.0
            }
        )

        # Ratio is 3.0, threshold 0.5, should trigger chop
        result = detect_dxy_chop(test_data, wick_threshold=0.5, min_chop_candles=1)
        assert result.iloc[0]

        # Ratio is 3.0, threshold 5.0, should not trigger chop
        result = detect_dxy_chop(test_data, wick_threshold=5.0, min_chop_candles=1)
        assert not result.iloc[0]

    def test_detect_chop_consecutive_count_accuracy(self) -> None:
        """Test accurate consecutive counting with interruptions."""
        # Pattern: chop, chop, trend, chop, chop, chop, chop
        test_data = pd.DataFrame(
            {
                "high": [101.0, 101.0, 102.0, 101.5, 101.5, 101.5, 101.5],
                "low": [99.0, 99.0, 101.5, 99.5, 99.5, 99.5, 99.5],
                "open": [100.0, 100.0, 101.5, 100.5, 100.5, 100.5, 100.5],
                "close": [100.1, 100.1, 102.0, 100.6, 100.6, 100.6, 100.6],
                # 0-1: chop (ratio ~19), 2: trend (ratio 0), 3-6: chop (ratio ~16.6)
            }
        )

        result = detect_dxy_chop(test_data, wick_threshold=0.5, min_chop_candles=3)

        # First 2: chop but not enough
        assert not result.iloc[0]
        assert not result.iloc[1]

        # Candle 2: trend (resets)
        assert not result.iloc[2]

        # Candles 3-4: chop but only 2 after reset
        assert not result.iloc[3]
        assert not result.iloc[4]

        # Candles 5-6: 3rd and 4th consecutive chop, should trigger
        assert result.iloc[5]
        assert result.iloc[6]
