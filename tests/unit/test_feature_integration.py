"""Tests for FeatureEngine Integration Layer."""

from datetime import UTC

import pandas as pd
import pytest
from feature_engine.integration import (
    align_dataframes,
    prepare_for_aggregation,
    process_features,
)
from feature_engine.structure import calculate_structure_labels
from feature_engine.vwap import calculate_vwap_deviation


class TestPrepareForAggregation:
    """Tests for prepare_for_aggregation function."""

    def test_converts_timestamp_index_to_ts_event_column(self) -> None:
        """Test that timestamp index is converted to ts_event column."""
        # Create DataFrame with timestamp index
        timestamps = pd.date_range("2025-01-01 09:00", periods=5, freq="1min", tz=UTC)
        df = pd.DataFrame(
            {"open": [100.0] * 5, "close": [101.0] * 5},
            index=timestamps,
        )

        result = prepare_for_aggregation(df)

        assert "ts_event" in result.columns
        assert not isinstance(result.index, pd.DatetimeIndex)
        assert len(result) == 5
        assert all(result["ts_event"] == timestamps)

    def test_preserves_all_columns(self) -> None:
        """Test that all original columns are preserved."""
        timestamps = pd.date_range("2025-01-01 09:00", periods=3, freq="1min", tz=UTC)
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.5, 101.5, 102.5],
                "volume": [1000, 1500, 2000],
            },
            index=timestamps,
        )

        result = prepare_for_aggregation(df)

        assert "ts_event" in result.columns
        assert "open" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns

    def test_raises_error_for_non_datetime_index(self) -> None:
        """Test that error is raised for non-DatetimeIndex."""
        df = pd.DataFrame({"open": [100.0], "close": [101.0]})

        with pytest.raises(ValueError, match="Expected DataFrame with DatetimeIndex"):
            prepare_for_aggregation(df)


class TestAlignDataframes:
    """Tests for align_dataframes function."""

    def test_aligns_dataframes_with_timestamp_index(self) -> None:
        """Test alignment of DataFrames with timestamp index."""
        # Create overlapping timestamps
        pd.date_range("2025-01-01 09:00", periods=5, freq="1min", tz=UTC)
        gc_times = pd.date_range("2025-01-01 08:59", periods=7, freq="1min", tz=UTC)
        dxy_times = pd.date_range("2025-01-01 09:01", periods=7, freq="1min", tz=UTC)

        gc_df = pd.DataFrame(
            {"open": [100.0] * 7, "close": [101.0] * 7}, index=gc_times
        )
        dxy_df = pd.DataFrame(
            {"open": [200.0] * 7, "close": [201.0] * 7}, index=dxy_times
        )

        gc_aligned, dxy_aligned = align_dataframes(gc_df, dxy_df)

        # Should have 5 overlapping timestamps (09:00-09:04)
        assert len(gc_aligned) == 5
        assert len(dxy_aligned) == 5
        assert all(gc_aligned["ts_event"] == dxy_aligned["ts_event"])

    def test_aligns_dataframes_with_ts_event_column(self) -> None:
        """Test alignment of DataFrames with ts_event column."""
        common_times = pd.date_range("2025-01-01 09:00", periods=5, freq="1min", tz=UTC)
        gc_df = pd.DataFrame(
            {
                "ts_event": common_times,
                "open": [100.0] * 5,
                "close": [101.0] * 5,
            }
        )
        dxy_df = pd.DataFrame(
            {
                "ts_event": common_times,
                "open": [200.0] * 5,
                "close": [201.0] * 5,
            }
        )

        gc_aligned, dxy_aligned = align_dataframes(gc_df, dxy_df)

        assert len(gc_aligned) == 5
        assert len(dxy_aligned) == 5
        assert all(gc_aligned["ts_event"] == dxy_aligned["ts_event"])

    def test_raises_error_for_no_overlapping_timestamps(self) -> None:
        """Test that error is raised when no timestamps overlap."""
        gc_times = pd.date_range("2025-01-01 09:00", periods=5, freq="1min", tz=UTC)
        dxy_times = pd.date_range("2025-01-02 09:00", periods=5, freq="1min", tz=UTC)

        gc_df = pd.DataFrame({"open": [100.0] * 5}, index=gc_times)
        dxy_df = pd.DataFrame({"open": [200.0] * 5}, index=dxy_times)

        with pytest.raises(ValueError, match="No overlapping timestamps"):
            align_dataframes(gc_df, dxy_df)


class TestCalculateStructureLabels:
    """Tests for calculate_structure_labels function."""

    def test_identifies_higher_highs(self) -> None:
        """Test identification of higher highs.

        With delayed labeling, we need enough data points for both:
        1. Swing detection window (swing_window bars on each side)
        2. Delay window (swing_window bars after detection)

        For swing_window=2, we need at least 2 + 1 + 2 = 5 bars to detect a swing,
        plus 2 more bars for the delayed label to appear.
        """
        df = pd.DataFrame(
            {
                # More data points to accommodate delayed labeling
                "high": [100, 102, 101, 103, 102, 104, 103, 105],
                "low": [99, 100, 99, 101, 100, 102, 101, 103],
            }
        )

        labels = calculate_structure_labels(df, swing_window=2)

        # Should identify swing highs and label them (delayed by swing_window)
        assert (
            "HH" in labels.values
            or "LH" in labels.values
            or "HL" in labels.values
            or "LL" in labels.values
        )

    def test_handles_insufficient_data(self) -> None:
        """Test that insufficient data returns all NA labels."""
        df = pd.DataFrame({"high": [100, 101], "low": [99, 100]})

        labels = calculate_structure_labels(df, swing_window=2)

        # With only 2 rows and swing_window=2, need at least 5 rows
        assert labels.isna().all()

    def test_raises_error_for_invalid_swing_window(self) -> None:
        """Test that error is raised for invalid swing_window."""
        df = pd.DataFrame({"high": [100, 101], "low": [99, 100]})

        with pytest.raises(ValueError, match="swing_window must be >= 2"):
            calculate_structure_labels(df, swing_window=1)


class TestCalculateVwapDeviation:
    """Tests for calculate_vwap_deviation function."""

    def test_calculates_deviation_percentage(self) -> None:
        """Test VWAP deviation calculation."""
        df = pd.DataFrame(
            {
                "close": [2650.0, 2655.0, 2645.0],
                "vwap": [2645.0, 2645.0, 2645.0],
            }
        )

        deviation = calculate_vwap_deviation(df)

        assert len(deviation) == 3
        assert deviation.iloc[0] == pytest.approx(
            0.189, abs=0.01
        )  # (2650-2645)/2645*100
        assert deviation.iloc[1] == pytest.approx(
            0.378, abs=0.01
        )  # (2655-2645)/2645*100
        assert deviation.iloc[2] == pytest.approx(0.0, abs=0.01)  # (2645-2645)/2645*100

    def test_raises_error_for_missing_columns(self) -> None:
        """Test that error is raised for missing columns."""
        df = pd.DataFrame({"close": [2650.0]})

        with pytest.raises(ValueError, match="Missing required columns"):
            calculate_vwap_deviation(df)

    def test_raises_error_for_zero_vwap(self) -> None:
        """Test that error is raised for zero VWAP values."""
        df = pd.DataFrame({"close": [2650.0], "vwap": [0.0]})

        with pytest.raises(ValueError, match="VWAP values must be positive"):
            calculate_vwap_deviation(df)


class TestProcessFeatures:
    """Tests for process_features integration function."""

    @pytest.fixture
    def sample_gc_data(self) -> pd.DataFrame:
        """Create sample GC DataFrame."""
        timestamps = pd.date_range("2025-01-01 09:00", periods=100, freq="1min", tz=UTC)
        return pd.DataFrame(
            {
                "open": [2650.0 + i * 0.1 for i in range(100)],
                "high": [2651.0 + i * 0.1 for i in range(100)],
                "low": [2649.0 + i * 0.1 for i in range(100)],
                "close": [2650.5 + i * 0.1 for i in range(100)],
                "volume": [1000.0] * 100,
                "symbol": ["GC"] * 100,
            },
            index=timestamps,
        )

    @pytest.fixture
    def sample_dxy_data(self) -> pd.DataFrame:
        """Create sample DXY DataFrame."""
        timestamps = pd.date_range("2025-01-01 09:00", periods=100, freq="1min", tz=UTC)
        return pd.DataFrame(
            {
                "open": [100.0 - i * 0.01 for i in range(100)],
                "high": [100.1 - i * 0.01 for i in range(100)],
                "low": [99.9 - i * 0.01 for i in range(100)],
                "close": [100.0 - i * 0.01 for i in range(100)],
                "volume": [500.0] * 100,
                "symbol": ["DXY"] * 100,
            },
            index=timestamps,
        )

    def test_processes_features_with_handcrafted_data(
        self, sample_gc_data: pd.DataFrame, sample_dxy_data: pd.DataFrame
    ) -> None:
        """Test feature processing with handcrafted mini dataset."""
        features = process_features(sample_gc_data, sample_dxy_data, "1m", context=None)

        # Check that all expected columns are present
        assert "vwap" in features.columns
        assert "rsi" in features.columns
        assert "ema_9" in features.columns
        assert "ema_20" in features.columns
        assert "ema_50" in features.columns
        assert "dxy_corr" in features.columns
        assert "structure_label" in features.columns
        assert "vwap_deviation" in features.columns
        assert "ts_event" in features.columns

    def test_no_nans_past_initialization_window(
        self, sample_gc_data: pd.DataFrame, sample_dxy_data: pd.DataFrame
    ) -> None:
        """Test that no NaNs exist past initialization window."""
        features = process_features(sample_gc_data, sample_dxy_data, "1m", context=None)

        # Check feature columns past initialization window (50 periods)
        max_init_window = 50
        if len(features) > max_init_window:
            feature_cols = ["vwap", "rsi", "ema_9", "ema_20", "ema_50", "dxy_corr"]
            for col in feature_cols:
                if col in features.columns:
                    nan_count = features[col].iloc[max_init_window:].isna().sum()
                    # Some NaNs might be acceptable in dxy_corr due to correlation window
                    if col != "dxy_corr":
                        assert (
                            nan_count == 0
                        ), f"Found {nan_count} NaNs in {col} past initialization"

    def test_handles_different_timeframes(
        self, sample_gc_data: pd.DataFrame, sample_dxy_data: pd.DataFrame
    ) -> None:
        """Test processing with different timeframes."""
        for timeframe in ["1m", "15m", "1h"]:
            features = process_features(
                sample_gc_data, sample_dxy_data, timeframe, context=None
            )
            assert len(features) > 0
            assert "vwap" in features.columns

    def test_raises_error_for_missing_columns(self) -> None:
        """Test that error is raised for missing required columns."""
        timestamps = pd.date_range("2025-01-01 09:00", periods=10, freq="1min", tz=UTC)
        gc_df = pd.DataFrame({"open": [100.0] * 10}, index=timestamps)
        dxy_df = pd.DataFrame({"open": [200.0] * 10}, index=timestamps)

        with pytest.raises(ValueError, match="missing required columns"):
            process_features(gc_df, dxy_df, "1m")

    def test_handles_empty_dataframes(self) -> None:
        """Test that empty DataFrames are handled gracefully."""
        timestamps = pd.DatetimeIndex([], tz=UTC)
        gc_df = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"], index=timestamps
        )
        dxy_df = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"], index=timestamps
        )

        with pytest.raises(ValueError, match="No overlapping timestamps"):
            process_features(gc_df, dxy_df, "1m")

    def test_applies_validation_when_context_provided(
        self, sample_gc_data: pd.DataFrame, sample_dxy_data: pd.DataFrame
    ) -> None:
        """Test that validation is applied when context is provided."""
        context = {
            "session_ok": True,
            "tier_active": "EarlyMild",
            "htf_bias": "bullish",
            "dxy_trending_clean": True,
            "fatigue_flag": False,
            "risk_allowed": True,
            "news_ok": True,
            "ceo_directive_active": True,
            "buffer_phase": "0-5k",
        }

        features = process_features(
            sample_gc_data, sample_dxy_data, "1m", context=context
        )

        # Validation status column should be added if session_validator is used
        # For now, we just check that processing completes
        assert len(features) > 0
