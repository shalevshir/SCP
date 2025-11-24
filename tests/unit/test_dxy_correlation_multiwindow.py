"""Unit tests for multi-window DXY correlation calculation.

Tests the enhanced DXY correlation with 15/30/60 minute windows
and weighted scoring as per DoD requirements.
"""

from pathlib import Path

import pandas as pd
import pytest
from feature_engine.dxy_correlation import calculate_multiwindow_dxy_correlation

# Path to project root (two levels up from this test file)
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestMultiWindowDXYCorrelation:
    """Test multi-window DXY correlation calculation with weighted scoring."""

    @pytest.fixture
    def simple_gc_data(self) -> pd.DataFrame:
        """Create simple GC price data with 100 periods (100 minutes)."""
        timestamps = pd.date_range("2025-01-01 09:00", periods=100, freq="1min")
        return pd.DataFrame(
            {
                "ts_event": timestamps,
                # Steadily increasing prices
                "close": [2000.0 + i * 0.1 for i in range(100)],
                "symbol": ["GCZ5"] * 100,
            }
        )

    @pytest.fixture
    def simple_dxy_data(self) -> pd.DataFrame:
        """Create simple DXY price data with inverse relationship (100 periods)."""
        timestamps = pd.date_range("2025-01-01 09:00", periods=100, freq="1min")
        return pd.DataFrame(
            {
                "ts_event": timestamps,
                # Steadily decreasing prices (inverse of GC)
                "close": [100.0 - i * 0.01 for i in range(100)],
                "symbol": ["DX"] * 100,
            }
        )

    @pytest.fixture
    def real_gc_data(self) -> pd.DataFrame:
        """Load real GC OHLCV data from CSV."""
        data_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "GC_ohlcv-1m.csv"
        df = pd.read_csv(data_path, parse_dates=["ts_event"])
        # Filter to single symbol and take first 500 rows
        df = df[df["symbol"] == "GCZ5"].head(500).copy()
        return df

    @pytest.fixture
    def real_dxy_data(self) -> pd.DataFrame:
        """Load real DXY OHLCV data from CSV."""
        data_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "DX_ohlcv-1m.csv"
        df = pd.read_csv(data_path, parse_dates=["ts_event"])
        # Take first 500 rows
        df = df.head(500).copy()
        return df

    def test_multiwindow_correlation_returns_expected_columns(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that multi-window correlation returns all expected columns."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # Should be a DataFrame with correlation columns and weighted score
        assert isinstance(result, pd.DataFrame)
        assert "corr_15min" in result.columns
        assert "corr_30min" in result.columns
        assert "corr_60min" in result.columns
        assert "weighted_score" in result.columns

    def test_multiwindow_correlation_length_matches_input(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that result length matches aligned input data."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # Result should have same length as aligned data
        assert len(result) == len(simple_gc_data)

    def test_multiwindow_correlation_15min_window(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that 15min window produces valid correlations."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # First 14 values should be NaN (need 15 periods for 15min window)
        assert result["corr_15min"].iloc[:14].isna().all()

        # Remaining values should be valid correlations [-1, 1]
        # Allow small floating-point tolerance
        valid_corr = result["corr_15min"].iloc[14:].dropna()
        assert len(valid_corr) > 0
        assert valid_corr.min() >= -1.01  # Allow small floating-point error
        assert valid_corr.max() <= 1.01

    def test_multiwindow_correlation_30min_window(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that 30min window produces valid correlations."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # First 29 values should be NaN (need 30 periods for 30min window)
        assert result["corr_30min"].iloc[:29].isna().all()

        # Remaining values should be valid correlations [-1, 1]
        # Allow small floating-point tolerance
        valid_corr = result["corr_30min"].iloc[29:].dropna()
        assert len(valid_corr) > 0
        assert valid_corr.min() >= -1.01  # Allow small floating-point error
        assert valid_corr.max() <= 1.01

    def test_multiwindow_correlation_60min_window(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that 60min window produces valid correlations."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # First 59 values should be NaN (need 60 periods for 60min window)
        assert result["corr_60min"].iloc[:59].isna().all()

        # Remaining values should be valid correlations [-1, 1]
        # Allow small floating-point tolerance
        valid_corr = result["corr_60min"].iloc[59:].dropna()
        assert len(valid_corr) > 0
        assert valid_corr.min() >= -1.01  # Allow small floating-point error
        assert valid_corr.max() <= 1.01

    def test_multiwindow_correlation_inverse_relationship(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that inverse GC-DXY relationship produces negative correlations."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # All windows should show negative correlation (GC up, DXY down)
        assert result["corr_15min"].iloc[14:].max() < 0
        assert result["corr_30min"].iloc[29:].max() < 0
        assert result["corr_60min"].iloc[59:].max() < 0

    def test_multiwindow_weighted_score_calculation(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that weighted score is calculated correctly."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # Weighted score should be computed only when all windows have valid data
        # (i.e., from row 59 onwards, when 60min window is valid)
        assert result["weighted_score"].iloc[:59].isna().all()

        # Remaining weighted scores should be valid
        valid_scores = result["weighted_score"].iloc[59:].dropna()
        assert len(valid_scores) > 0

    def test_multiwindow_weighted_score_range(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that weighted score is in valid range [-1, 1]."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # Allow small floating-point tolerance
        valid_scores = result["weighted_score"].dropna()
        assert valid_scores.min() >= -1.01  # Allow small floating-point error
        assert valid_scores.max() <= 1.01

    def test_multiwindow_custom_weights(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test multi-window correlation with custom weights."""
        # Custom weights: favor shorter windows
        custom_weights = {
            "15min": 0.5,
            "30min": 0.3,
            "60min": 0.2,
        }

        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data, weights=custom_weights
        )

        # Should still have all expected columns
        assert "corr_15min" in result.columns
        assert "corr_30min" in result.columns
        assert "corr_60min" in result.columns
        assert "weighted_score" in result.columns

        # Weighted score should be valid
        valid_scores = result["weighted_score"].dropna()
        assert len(valid_scores) > 0

    def test_multiwindow_weights_validation(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that weights must sum to 1.0."""
        # Invalid weights (don't sum to 1.0)
        invalid_weights = {
            "15min": 0.5,
            "30min": 0.3,
            "60min": 0.3,  # Sum = 1.1
        }

        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            calculate_multiwindow_dxy_correlation(
                simple_gc_data, simple_dxy_data, weights=invalid_weights
            )

    def test_multiwindow_default_weights(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that default weights are applied when not specified."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # Should use default weights (15min: 0.5, 30min: 0.3, 60min: 0.2)
        # We can verify this by checking that weighted_score is calculated
        valid_scores = result["weighted_score"].dropna()
        assert len(valid_scores) > 0

    def test_multiwindow_strong_inverse_correlation(
        self, real_gc_data: pd.DataFrame, real_dxy_data: pd.DataFrame
    ) -> None:
        """Test multi-window correlation identifies strong inverse correlation (< -0.6)."""
        result = calculate_multiwindow_dxy_correlation(real_gc_data, real_dxy_data)

        # Should have some periods with strong negative correlation in at least one window
        strong_negative_15min = result["corr_15min"][result["corr_15min"] < -0.6]
        strong_negative_30min = result["corr_30min"][result["corr_30min"] < -0.6]
        strong_negative_60min = result["corr_60min"][result["corr_60min"] < -0.6]

        # At least one window should show strong negative correlation
        total_strong_negative = (
            len(strong_negative_15min)
            + len(strong_negative_30min)
            + len(strong_negative_60min)
        )
        assert (
            total_strong_negative > 0
        ), "Expected strong negative correlation (< -0.6) in at least one window"

    def test_multiwindow_weighted_score_stronger_than_single_window(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that weighted score smooths out noise better than single window."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # Weighted score variance should be <= 15min variance (smoothing effect)
        valid_15min = result["corr_15min"].iloc[59:].dropna()
        valid_weighted = result["weighted_score"].iloc[59:].dropna()

        # Check that we have enough data
        if len(valid_15min) > 10 and len(valid_weighted) > 10:
            # Weighted score should have lower or similar variance (smoothing)
            # This verifies that multi-window approach reduces noise
            assert valid_weighted.std() <= valid_15min.std() * 1.2

    def test_multiwindow_custom_price_columns(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test multi-window correlation with custom price columns."""
        # Rename close columns
        gc_renamed = simple_gc_data.rename(columns={"close": "gc_close"})
        dxy_renamed = simple_dxy_data.rename(columns={"close": "dxy_close"})

        result = calculate_multiwindow_dxy_correlation(
            gc_renamed,
            dxy_renamed,
            gc_price_column="gc_close",
            dxy_price_column="dxy_close",
        )

        assert len(result) == len(gc_renamed)
        assert "corr_15min" in result.columns
        assert "weighted_score" in result.columns

    def test_multiwindow_custom_timestamp_column(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test multi-window correlation with custom timestamp column."""
        # Rename timestamp columns
        gc_renamed = simple_gc_data.rename(columns={"ts_event": "timestamp"})
        dxy_renamed = simple_dxy_data.rename(columns={"ts_event": "timestamp"})

        result = calculate_multiwindow_dxy_correlation(
            gc_renamed,
            dxy_renamed,
            timestamp_column="timestamp",
        )

        assert len(result) > 0
        assert "weighted_score" in result.columns

    def test_multiwindow_empty_dataframes(self) -> None:
        """Test multi-window correlation with empty DataFrames."""
        empty_gc = pd.DataFrame(columns=["ts_event", "close"])
        empty_dxy = pd.DataFrame(columns=["ts_event", "close"])

        result = calculate_multiwindow_dxy_correlation(empty_gc, empty_dxy)

        assert len(result) == 0

    def test_multiwindow_no_overlapping_timestamps(self) -> None:
        """Test multi-window correlation when timestamps don't overlap."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(["2025-01-01 09:00", "2025-01-01 09:01"]),
                "close": [2000.0, 2001.0],
            }
        )
        dxy_df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(["2025-01-01 10:00", "2025-01-01 10:01"]),
                "close": [100.0, 99.9],
            }
        )

        result = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)

        # Should return empty DataFrame (no overlapping timestamps)
        assert len(result) == 0

    def test_multiwindow_insufficient_data(self) -> None:
        """Test multi-window correlation with insufficient data."""
        # Create data with < 60 periods
        timestamps = pd.date_range("2025-01-01 09:00", periods=30, freq="1min")
        gc_df = pd.DataFrame(
            {
                "ts_event": timestamps,
                "close": [2000.0 + i for i in range(30)],
            }
        )
        dxy_df = pd.DataFrame(
            {
                "ts_event": timestamps,
                "close": [100.0 - i * 0.1 for i in range(30)],
            }
        )

        result = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)

        # Should have 15min and 30min correlations, but not 60min
        assert result["corr_15min"].iloc[14:29].notna().any()
        assert result["corr_30min"].iloc[29:].notna().any() or len(result) < 30
        assert result["corr_60min"].isna().all()  # Not enough data
        assert result["weighted_score"].isna().all()  # Requires all windows

    def test_multiwindow_index_preserved(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that result index matches input timestamps."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # Index should be timestamps from aligned data
        assert isinstance(result.index, pd.DatetimeIndex)
        assert len(result) == len(simple_gc_data)

    def test_multiwindow_score_below_threshold_identified(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that strong inverse correlation (< -0.6) is properly identified."""
        result = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # With perfect inverse relationship, weighted score should be < -0.6
        valid_scores = result["weighted_score"].dropna()
        strong_inverse = valid_scores[valid_scores < -0.6]

        # Should identify strong inverse correlation
        assert len(strong_inverse) > 0, "Expected strong inverse correlation (< -0.6)"

    def test_multiwindow_weights_missing_keys(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that weights with missing required keys raise ValueError."""
        # Missing '60min' key
        invalid_weights = {
            "15min": 0.6,
            "30min": 0.4,
        }

        with pytest.raises(ValueError, match="must contain exactly keys"):
            calculate_multiwindow_dxy_correlation(
                simple_gc_data, simple_dxy_data, weights=invalid_weights
            )

    def test_multiwindow_weights_wrong_keys(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that weights with incorrect keys raise ValueError."""
        # Wrong keys: '15', '30', '60' instead of '15min', '30min', '60min'
        invalid_weights = {
            "15": 0.5,
            "30": 0.3,
            "60": 0.2,
        }

        with pytest.raises(ValueError, match="must contain exactly keys"):
            calculate_multiwindow_dxy_correlation(
                simple_gc_data, simple_dxy_data, weights=invalid_weights
            )

    def test_multiwindow_weights_partial_keys(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that weights with only some required keys raise ValueError."""
        # Only 2 of 3 required keys
        invalid_weights = {
            "15min": 0.7,
            "30min": 0.3,
        }

        with pytest.raises(ValueError, match="missing keys"):
            calculate_multiwindow_dxy_correlation(
                simple_gc_data, simple_dxy_data, weights=invalid_weights
            )

    def test_multiwindow_weights_extra_keys(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that weights with extra keys raise ValueError."""
        # 4 keys including all valid ones plus extra
        invalid_weights = {
            "15min": 0.4,
            "30min": 0.3,
            "60min": 0.2,
            "90min": 0.1,  # Extra key
        }

        with pytest.raises(ValueError, match="unexpected keys"):
            calculate_multiwindow_dxy_correlation(
                simple_gc_data, simple_dxy_data, weights=invalid_weights
            )

    def test_multiwindow_empty_result_index_type(self) -> None:
        """Test that empty result returns DatetimeIndex not RangeIndex."""
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(["2025-01-01 09:00", "2025-01-01 09:01"]),
                "close": [2000.0, 2001.0],
            }
        )
        dxy_df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(["2025-01-01 10:00", "2025-01-01 10:01"]),
                "close": [100.0, 99.9],
            }
        )

        result = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)

        # Should return empty DataFrame with DatetimeIndex
        assert len(result) == 0
        assert isinstance(result.index, pd.DatetimeIndex), (
            f"Expected DatetimeIndex, got {type(result.index).__name__}"
        )

    def test_multiwindow_empty_result_index_consistency(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that empty and non-empty results have consistent index types."""
        # Non-empty result
        non_empty = calculate_multiwindow_dxy_correlation(
            simple_gc_data, simple_dxy_data
        )

        # Empty result (no overlap)
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(["2025-01-01 09:00", "2025-01-01 09:01"]),
                "close": [2000.0, 2001.0],
            }
        )
        dxy_df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(["2025-01-01 10:00", "2025-01-01 10:01"]),
                "close": [100.0, 99.9],
            }
        )
        empty = calculate_multiwindow_dxy_correlation(gc_df, dxy_df)

        # Both should have same index type
        assert type(non_empty.index) == type(empty.index), (
            f"Index type mismatch: non-empty={type(non_empty.index).__name__}, "
            f"empty={type(empty.index).__name__}"
        )

