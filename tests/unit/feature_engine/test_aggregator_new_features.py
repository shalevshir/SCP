"""Unit tests for new feature computations in aggregator.

Tests ATR, wick percentages, and VWAP difference calculations added to
aggregate_features() for diagnostic and scoring purposes.
"""

import pandas as pd
import pytest

from feature_engine.aggregator import aggregate_features


class TestATRComputation:
    """Test Average True Range (ATR) calculation."""

    def test_atr_basic_calculation(self):
        """Test ATR calculation with known values."""
        # Create sample data with known ranges
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=20, freq="1min"),
                "open": [100.0] * 20,
                "high": [102.0] * 20,  # Range of 2.0
                "low": [100.0] * 20,
                "close": [101.0] * 20,
                "volume": [1000.0] * 20,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # ATR should be ~2.0 after warmup (14 periods)
        assert "atr" in result.columns
        assert result["atr"].iloc[13] == pytest.approx(2.0, abs=0.01)
        # Earlier values should be NaN (warmup period)
        assert pd.isna(result["atr"].iloc[0])

    def test_atr_with_gaps(self):
        """Test ATR calculation with price gaps."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=20, freq="1min"),
                "open": [100.0] * 5 + [105.0] * 15,  # Gap up
                "high": [102.0] * 5 + [107.0] * 15,
                "low": [100.0] * 5 + [105.0] * 15,
                "close": [101.0] * 5 + [106.0] * 15,
                "volume": [1000.0] * 20,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # ATR should increase after gap (includes previous close distance)
        assert "atr" in result.columns
        # After gap, true range includes gap distance (5.0)
        assert result["atr"].iloc[15] > 2.0  # Higher than normal range


class TestWickPercentages:
    """Test wick percentage calculations relative to body."""

    def test_bullish_candle_wicks(self):
        """Test wick percentages for bullish candle."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=5, freq="1min"),
                "open": [100.0, 100.0, 100.0, 100.0, 100.0],
                "high": [105.0, 105.0, 105.0, 105.0, 105.0],  # Upper wick = 1.0
                "low": [98.0, 98.0, 98.0, 98.0, 98.0],  # Lower wick = 2.0
                "close": [104.0, 104.0, 104.0, 104.0, 104.0],  # Body = 4.0
                "volume": [1000.0] * 5,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Upper wick = 105 - 104 = 1.0, body = 4.0, ratio = 0.25
        assert result["upper_wick_pct"].iloc[0] == pytest.approx(0.25, abs=0.01)
        # Lower wick = 100 - 98 = 2.0, body = 4.0, ratio = 0.5
        assert result["lower_wick_pct"].iloc[0] == pytest.approx(0.5, abs=0.01)

    def test_bearish_candle_wicks(self):
        """Test wick percentages for bearish candle."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=5, freq="1min"),
                "open": [104.0, 104.0, 104.0, 104.0, 104.0],
                "high": [105.0, 105.0, 105.0, 105.0, 105.0],  # Upper wick = 1.0
                "low": [98.0, 98.0, 98.0, 98.0, 98.0],  # Lower wick = 2.0
                "close": [100.0, 100.0, 100.0, 100.0, 100.0],  # Body = 4.0
                "volume": [1000.0] * 5,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Upper wick = 105 - 104 = 1.0, body = 4.0, ratio = 0.25
        assert result["upper_wick_pct"].iloc[0] == pytest.approx(0.25, abs=0.01)
        # Lower wick = 100 - 98 = 2.0, body = 4.0, ratio = 0.5
        assert result["lower_wick_pct"].iloc[0] == pytest.approx(0.5, abs=0.01)

    def test_doji_candle_wicks(self):
        """Test wick percentages for doji (no body)."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=5, freq="1min"),
                "open": [100.0, 100.0, 100.0, 100.0, 100.0],
                "high": [102.0, 102.0, 102.0, 102.0, 102.0],
                "low": [98.0, 98.0, 98.0, 98.0, 98.0],
                "close": [100.0, 100.0, 100.0, 100.0, 100.0],  # Doji (body = 0)
                "volume": [1000.0] * 5,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # For doji, body is replaced with small epsilon (0.0001 * high)
        # Both wicks should have reasonable values (not infinity)
        assert result["upper_wick_pct"].iloc[0] > 0
        assert result["lower_wick_pct"].iloc[0] > 0
        assert not pd.isna(result["upper_wick_pct"].iloc[0])
        assert not pd.isna(result["lower_wick_pct"].iloc[0])

    def test_strong_rejection_wick(self):
        """Test strong rejection candle (wick > 2x body)."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=5, freq="1min"),
                "open": [100.0, 100.0, 100.0, 100.0, 100.0],
                "high": [101.0, 101.0, 101.0, 101.0, 101.0],  # Body = 1.0
                "low": [97.0, 97.0, 97.0, 97.0, 97.0],  # Lower wick = 3.0
                "close": [101.0, 101.0, 101.0, 101.0, 101.0],
                "volume": [1000.0] * 5,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Lower wick = 3.0, body = 1.0, ratio = 3.0 (strong rejection)
        assert result["lower_wick_pct"].iloc[0] == pytest.approx(3.0, abs=0.01)
        # Verify this exceeds the 2x threshold for rejection candles
        assert result["lower_wick_pct"].iloc[0] > 2.0


class TestVWAPDifference:
    """Test VWAP difference calculations (absolute and percentage)."""

    def test_close_above_vwap(self):
        """Test VWAP difference when close is above VWAP."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=5, freq="1min"),
                "open": [100.0, 100.0, 100.0, 100.0, 100.0],
                "high": [102.0, 102.0, 102.0, 102.0, 102.0],
                "low": [98.0, 98.0, 98.0, 98.0, 98.0],
                "close": [101.0, 101.0, 101.0, 101.0, 101.0],
                "volume": [1000.0] * 5,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # VWAP should be close to typical price = (H+L+C)/3 = (102+98+101)/3 = 100.33
        # close_vwap_diff should be positive (close > vwap)
        assert "close_vwap_diff" in result.columns
        assert "close_vwap_pct" in result.columns
        assert result["close_vwap_diff"].iloc[0] > 0
        # Percentage should be small (< 1%)
        assert 0 < result["close_vwap_pct"].iloc[0] < 1.0

    def test_close_below_vwap(self):
        """Test VWAP difference when close is below VWAP."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=5, freq="1min"),
                "open": [102.0, 102.0, 102.0, 102.0, 102.0],
                "high": [104.0, 104.0, 104.0, 104.0, 104.0],
                "low": [100.0, 100.0, 100.0, 100.0, 100.0],
                "close": [100.5, 100.5, 100.5, 100.5, 100.5],
                "volume": [1000.0] * 5,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # VWAP should be close to typical price = (H+L+C)/3 = (104+100+100.5)/3 = 101.5
        # close_vwap_diff should be negative (close < vwap)
        assert result["close_vwap_diff"].iloc[0] < 0
        # Percentage should be negative and small (> -1%)
        assert -1.0 < result["close_vwap_pct"].iloc[0] < 0

    def test_close_at_vwap(self):
        """Test VWAP difference when close equals VWAP."""
        # Create candles where close = typical price = VWAP
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=5, freq="1min"),
                "open": [100.0, 100.0, 100.0, 100.0, 100.0],
                "high": [101.0, 101.0, 101.0, 101.0, 101.0],
                "low": [99.0, 99.0, 99.0, 99.0, 99.0],
                "close": [100.0, 100.0, 100.0, 100.0, 100.0],
                "volume": [1000.0] * 5,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # close_vwap_diff should be very small (near zero)
        assert abs(result["close_vwap_diff"].iloc[0]) < 0.1
        # Percentage should also be very small
        assert abs(result["close_vwap_pct"].iloc[0]) < 0.1

    def test_vwap_proximity_threshold(self):
        """Test VWAP proximity detection (within 0.15% = 0.0015)."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=5, freq="1min"),
                "open": [2650.0, 2650.0, 2650.0, 2650.0, 2650.0],
                "high": [2652.0, 2652.0, 2652.0, 2652.0, 2652.0],
                "low": [2648.0, 2648.0, 2648.0, 2648.0, 2648.0],
                "close": [2650.0, 2650.0, 2650.0, 2650.0, 2650.0],
                "volume": [1000.0] * 5,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Calculate expected proximity: 0.15% of 2650 = ~4.0 points
        # close_vwap_diff should be within ±4.0 for "close to VWAP"
        assert abs(result["close_vwap_diff"].iloc[0]) < 4.0
        # Percentage should be within 0.15%
        assert abs(result["close_vwap_pct"].iloc[0]) < 0.15


class TestFeatureIntegration:
    """Test that new features integrate correctly with existing features."""

    def test_all_new_features_present(self):
        """Test that all new features are computed."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=20, freq="1min"),
                "open": [100.0] * 20,
                "high": [102.0] * 20,
                "low": [98.0] * 20,
                "close": [101.0] * 20,
                "volume": [1000.0] * 20,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Check all new features are present
        expected_features = [
            "atr",
            "upper_wick_pct",
            "lower_wick_pct",
            "close_vwap_diff",
            "close_vwap_pct",
        ]
        for feature in expected_features:
            assert feature in result.columns, f"Missing feature: {feature}"

    def test_new_features_with_existing_features(self):
        """Test that new features don't break existing features."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=20, freq="1min"),
                "open": [100.0] * 20,
                "high": [102.0] * 20,
                "low": [98.0] * 20,
                "close": [101.0] * 20,
                "volume": [1000.0] * 20,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Check existing features still work
        assert "vwap" in result.columns
        assert "rsi" in result.columns
        assert "ema_9" in result.columns
        assert "volume_sma_20" in result.columns
        assert "dxy_corr" in result.columns

        # Check new features coexist
        assert "atr" in result.columns
        assert "upper_wick_pct" in result.columns
        assert "close_vwap_diff" in result.columns

    def test_feature_values_are_numeric(self):
        """Test that all new features produce numeric values."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 10:00", periods=20, freq="1min"),
                "open": [100.0] * 20,
                "high": [102.0] * 20,
                "low": [98.0] * 20,
                "close": [101.0] * 20,
                "volume": [1000.0] * 20,
            }
        )
        dxy_df = gc_df.copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Check all new features are numeric (float64)
        assert result["atr"].dtype == "float64"
        assert result["upper_wick_pct"].dtype == "float64"
        assert result["lower_wick_pct"].dtype == "float64"
        assert result["close_vwap_diff"].dtype == "float64"
        assert result["close_vwap_pct"].dtype == "float64"
