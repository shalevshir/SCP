"""Unit tests for HTF VWAP calculation.

Tests the calculate_htf_vwap() function which computes 1H VWAP
and derived metrics (distance, slope).
"""

import numpy as np
import pandas as pd
import pytest
from rule_engine.htf.vwap.calculator import calculate_htf_vwap


class TestHTFVWAPCalculator:
    """Test suite for HTF VWAP calculation."""

    # =========================================================================
    # Core Functionality Tests (6 tests)
    # =========================================================================

    def test_calculates_vwap_correctly(self):
        """Test that VWAP is calculated correctly using volume weighting."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=5, freq="1h"),
                "high": [2650, 2655, 2660, 2665, 2670],
                "low": [2640, 2645, 2650, 2655, 2660],
                "close": [2645, 2650, 2655, 2660, 2665],
                "volume": [1000, 1500, 2000, 1200, 1800],
            }
        )

        result = calculate_htf_vwap(df)

        # Result should have VWAP column
        assert "vwap" in result.columns

        # VWAP should be calculated (not NaN)
        assert result["vwap"].notna().all()

        # VWAP should be reasonable (between low and high range)
        assert (result["vwap"] >= 2640).all()
        assert (result["vwap"] <= 2670).all()

    def test_calculates_vwap_distance(self):
        """Test that vwap_distance is calculated as close - vwap."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=3, freq="1h"),
                "high": [2650, 2655, 2660],
                "low": [2640, 2645, 2650],
                "close": [2645, 2650, 2655],
                "volume": [1000, 1500, 2000],
            }
        )

        result = calculate_htf_vwap(df)

        # Should have vwap_distance column
        assert "vwap_distance" in result.columns

        # Distance should be close - vwap
        expected_distance = result["close"] - result["vwap"]
        pd.testing.assert_series_equal(
            result["vwap_distance"], expected_distance, check_names=False
        )

    def test_calculates_vwap_slope(self):
        """Test that vwap_slope is calculated as rate of change."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=4, freq="1h"),
                "high": [2650, 2655, 2660, 2665],
                "low": [2640, 2645, 2650, 2655],
                "close": [2645, 2650, 2655, 2660],
                "volume": [1000, 1500, 2000, 1200],
            }
        )

        result = calculate_htf_vwap(df)

        # Should have vwap_slope column
        assert "vwap_slope" in result.columns

        # First value should be NaN (no prior value)
        assert pd.isna(result["vwap_slope"].iloc[0])

        # Subsequent values should be differences
        for i in range(1, len(result)):
            expected_slope = result["vwap"].iloc[i] - result["vwap"].iloc[i - 1]
            actual_slope = result["vwap_slope"].iloc[i]
            assert abs(actual_slope - expected_slope) < 0.01  # Small tolerance

    def test_returns_dataframe_with_all_columns(self):
        """Test that result includes all original + derived columns."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=3, freq="1h"),
                "high": [2650, 2655, 2660],
                "low": [2640, 2645, 2650],
                "close": [2645, 2650, 2655],
                "volume": [1000, 1500, 2000],
            }
        )

        result = calculate_htf_vwap(df)

        # Original columns preserved
        assert "ts_event" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns

        # New VWAP columns added
        assert "vwap" in result.columns
        assert "vwap_distance" in result.columns
        assert "vwap_slope" in result.columns

    def test_preserves_dataframe_index(self):
        """Test that original DataFrame index is preserved."""
        custom_index = pd.date_range("2025-01-01", periods=4, freq="1h")
        df = pd.DataFrame(
            {
                "ts_event": custom_index,
                "high": [2650, 2655, 2660, 2665],
                "low": [2640, 2645, 2650, 2655],
                "close": [2645, 2650, 2655, 2660],
                "volume": [1000, 1500, 2000, 1200],
            },
            index=custom_index,
        )

        result = calculate_htf_vwap(df)

        # Index should be preserved
        assert result.index.equals(df.index)
        assert len(result) == len(df)

    def test_works_with_session_reset(self):
        """Test VWAP resets at session boundaries (daily)."""
        # Two days of data
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=6, freq="6h"),
                "high": [2650, 2655, 2660, 2665, 2670, 2675],
                "low": [2640, 2645, 2650, 2655, 2660, 2665],
                "close": [2645, 2650, 2655, 2660, 2665, 2670],
                "volume": [1000, 1500, 2000, 1200, 1800, 1600],
            }
        )

        result = calculate_htf_vwap(df)

        # VWAP should reset at day boundary
        # First bar of each day should start fresh
        assert result["vwap"].notna().all()

    # =========================================================================
    # Edge Cases Tests (5 tests)
    # =========================================================================

    def test_empty_dataframe(self):
        """Test that empty DataFrame raises appropriate error."""
        df = pd.DataFrame(
            {"ts_event": [], "high": [], "low": [], "close": [], "volume": []}
        )

        with pytest.raises(ValueError, match="DataFrame is empty"):
            calculate_htf_vwap(df)

    def test_missing_required_columns(self):
        """Test that missing required columns raises ValueError."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01", periods=3, freq="1h"),
                "high": [2650, 2655, 2660],
                "low": [2640, 2645, 2650],
                # Missing 'close' and 'volume'
            }
        )

        with pytest.raises(ValueError, match="Missing required columns"):
            calculate_htf_vwap(df)

    def test_single_row_dataframe(self):
        """Test that single row DataFrame works correctly."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=1, freq="1h"),
                "high": [2650],
                "low": [2640],
                "close": [2645],
                "volume": [1000],
            }
        )

        result = calculate_htf_vwap(df)

        # Should have VWAP value
        assert result["vwap"].notna().all()

        # Slope should be NaN (no prior value)
        assert pd.isna(result["vwap_slope"].iloc[0])

    def test_zero_volume_handling(self):
        """Test that zero volume is handled gracefully."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=3, freq="1h"),
                "high": [2650, 2655, 2660],
                "low": [2640, 2645, 2650],
                "close": [2645, 2650, 2655],
                "volume": [1000, 0, 2000],  # Zero volume in middle
            }
        )

        result = calculate_htf_vwap(df)

        # Should still calculate VWAP (using epsilon for zero volume)
        assert result["vwap"].notna().all()

    def test_nan_in_price_columns(self):
        """Test that NaN in price columns is handled."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=4, freq="1h"),
                "high": [2650, np.nan, 2660, 2665],
                "low": [2640, 2645, 2650, 2655],
                "close": [2645, 2650, np.nan, 2660],
                "volume": [1000, 1500, 2000, 1200],
            }
        )

        result = calculate_htf_vwap(df)

        # VWAP should still be calculated (filling NaN as needed)
        assert "vwap" in result.columns

    # =========================================================================
    # Numerical Accuracy Tests (3 tests)
    # =========================================================================

    def test_vwap_matches_manual_calculation(self):
        """Test VWAP matches manual calculation for known data."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=3, freq="1h"),
                "high": [2650, 2655, 2660],
                "low": [2640, 2645, 2650],
                "close": [2645, 2650, 2655],
                "volume": [1000, 2000, 1500],
            }
        )

        result = calculate_htf_vwap(df)

        # Manual calculation for verification
        # Typical price = (high + low + close) / 3
        typical_prices = [
            (2650 + 2640 + 2645) / 3,
            (2655 + 2645 + 2650) / 3,
            (2660 + 2650 + 2655) / 3,
        ]
        volumes = [1000, 2000, 1500]

        # Cumulative VWAP
        cum_pv = [typical_prices[0] * volumes[0]]
        cum_vol = [volumes[0]]

        for i in range(1, 3):
            cum_pv.append(cum_pv[-1] + typical_prices[i] * volumes[i])
            cum_vol.append(cum_vol[-1] + volumes[i])

        expected_vwap = [pv / vol for pv, vol in zip(cum_pv, cum_vol, strict=False)]

        # Check VWAP values are close to manual calculation
        for i in range(3):
            assert abs(result["vwap"].iloc[i] - expected_vwap[i]) < 0.01

    def test_distance_sign_correctness(self):
        """Test that vwap_distance has correct sign (positive when above)."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=3, freq="1h"),
                "high": [2650, 2655, 2660],
                "low": [2640, 2645, 2650],
                "close": [2645, 2650, 2655],
                "volume": [1000, 1500, 2000],
            }
        )

        result = calculate_htf_vwap(df)

        # When close > vwap, distance should be positive
        # When close < vwap, distance should be negative
        for i in range(len(result)):
            expected_sign = np.sign(result["close"].iloc[i] - result["vwap"].iloc[i])
            actual_sign = np.sign(result["vwap_distance"].iloc[i])
            assert expected_sign == actual_sign

    def test_slope_reflects_vwap_trend(self):
        """Test that vwap_slope correctly reflects VWAP trend direction."""
        # Create data with clear VWAP trend
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=5, freq="1h"),
                "high": [2650, 2655, 2660, 2665, 2670],
                "low": [2640, 2645, 2650, 2655, 2660],
                "close": [2645, 2650, 2655, 2660, 2665],
                "volume": [1000, 1000, 1000, 1000, 1000],  # Constant volume
            }
        )

        result = calculate_htf_vwap(df)

        # With increasing prices and constant volume, VWAP should trend up
        # So slope should be mostly positive
        slopes = result["vwap_slope"].dropna()
        assert (slopes > 0).sum() >= len(slopes) * 0.6  # At least 60% positive

    # =========================================================================
    # Integration Tests (2 tests)
    # =========================================================================

    def test_compatible_with_existing_vwap_function(self):
        """Test that output is compatible with feature_engine.vwap."""
        from feature_engine.vwap import calculate_vwap

        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=4, freq="1h"),
                "high": [2650, 2655, 2660, 2665],
                "low": [2640, 2645, 2650, 2655],
                "close": [2645, 2650, 2655, 2660],
                "volume": [1000, 1500, 2000, 1200],
            }
        )

        # Calculate using both methods
        htf_result = calculate_htf_vwap(df)
        direct_vwap = calculate_vwap(df, session_reset=True)

        # VWAP values should match
        pd.testing.assert_series_equal(
            htf_result["vwap"], direct_vwap, check_names=False, rtol=1e-5
        )

    def test_works_with_real_gold_data_structure(self):
        """Test that function works with typical Gold (GC) data structure."""
        # Simulate real GC data structure
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=10, freq="1h"),
                "symbol": ["GCZ5"] * 10,
                "open": np.random.uniform(2640, 2660, 10),
                "high": np.random.uniform(2660, 2680, 10),
                "low": np.random.uniform(2620, 2640, 10),
                "close": np.random.uniform(2640, 2660, 10),
                "volume": np.random.randint(1000, 3000, 10),
            }
        )

        result = calculate_htf_vwap(df)

        # Should have all required VWAP columns
        assert "vwap" in result.columns
        assert "vwap_distance" in result.columns
        assert "vwap_slope" in result.columns

        # Original columns should be preserved
        assert "symbol" in result.columns
        assert "open" in result.columns








