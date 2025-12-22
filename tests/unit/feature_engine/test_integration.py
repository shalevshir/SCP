"""Unit tests for feature_engine/integration.py - feature processing integration.

Tests are specification-driven, based on docstrings and contracts.
Focus on error handling, edge cases, and missing data scenarios.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from feature_engine.integration import (
    align_dataframes,
    prepare_for_aggregation,
    process_features,
)


class TestPrepareForAggregation:
    """Test prepare_for_aggregation() - specification-based."""

    def test_converts_datetime_index_to_ts_event_column(self):
        """Converts DataFrame from timestamp index to ts_event column.

        Specification: "Convert DataFrame from timestamp index format to ts_event column format"
        """
        # Create DataFrame with timestamp index
        timestamps = pd.date_range("2024-07-01 10:00", periods=5, freq="1min", tz=UTC)
        df = pd.DataFrame(
            {
                "open": [2650.0, 2651.0, 2652.0, 2653.0, 2654.0],
                "close": [2650.5, 2651.5, 2652.5, 2653.5, 2654.5],
            },
            index=timestamps,
        )

        result = prepare_for_aggregation(df)

        # Should have ts_event column
        assert "ts_event" in result.columns

        # Should have RangeIndex
        assert isinstance(result.index, pd.RangeIndex)

        # ts_event should contain original timestamps
        assert all(result["ts_event"] == timestamps)

    def test_raises_error_on_non_datetime_index(self):
        """Raises ValueError if DataFrame doesn't have DatetimeIndex.

        Specification: "Raises: ValueError: If DataFrame doesn't have a DatetimeIndex"
        """
        # Create DataFrame with regular integer index
        df = pd.DataFrame(
            {
                "open": [2650.0, 2651.0],
                "close": [2650.5, 2651.5],
            }
        )

        with pytest.raises(ValueError) as exc_info:
            prepare_for_aggregation(df)

        assert "Expected DataFrame with DatetimeIndex" in str(exc_info.value)

    def test_preserves_all_original_columns(self):
        """Preserves all other columns from original DataFrame.

        Specification: "preserving all other columns"
        """
        timestamps = pd.date_range("2024-07-01 10:00", periods=3, freq="1min", tz=UTC)
        df = pd.DataFrame(
            {
                "open": [2650.0, 2651.0, 2652.0],
                "high": [2651.0, 2652.0, 2653.0],
                "low": [2649.0, 2650.0, 2651.0],
                "close": [2650.5, 2651.5, 2652.5],
                "volume": [1000, 1100, 1200],
                "custom_field": ["a", "b", "c"],
            },
            index=timestamps,
        )

        result = prepare_for_aggregation(df)

        # All original columns should be present
        for col in ["open", "high", "low", "close", "volume", "custom_field"]:
            assert col in result.columns

        # Plus ts_event
        assert "ts_event" in result.columns

    def test_returns_copy_not_reference(self):
        """Returns a copy, not a reference to original DataFrame.

        Specification: "result = df.copy()"
        """
        timestamps = pd.date_range("2024-07-01 10:00", periods=2, freq="1min", tz=UTC)
        df = pd.DataFrame({"open": [2650.0, 2651.0]}, index=timestamps)

        result = prepare_for_aggregation(df)

        # Modify result
        result.loc[0, "open"] = 9999.0

        # Original should be unchanged
        assert df.iloc[0]["open"] == 2650.0


class TestAlignDataframes:
    """Test align_dataframes() - specification-based."""

    def test_aligns_by_timestamp_inner_join(self):
        """Aligns GC and DXY DataFrames by timestamp using inner join.

        Specification: "Performs inner join on timestamps"
        """
        # GC with timestamps 10:00-10:04
        gc_timestamps = pd.date_range(
            "2024-07-01 10:00", periods=5, freq="1min", tz=UTC
        )
        gc_df = pd.DataFrame(
            {"open": [2650.0, 2651.0, 2652.0, 2653.0, 2654.0]},
            index=gc_timestamps,
        )

        # DXY with timestamps 10:02-10:06 (partial overlap)
        dxy_timestamps = pd.date_range(
            "2024-07-01 10:02", periods=5, freq="1min", tz=UTC
        )
        dxy_df = pd.DataFrame(
            {"open": [103.0, 103.1, 103.2, 103.3, 103.4]},
            index=dxy_timestamps,
        )

        aligned_gc, aligned_dxy = align_dataframes(gc_df, dxy_df)

        # Should only have overlapping timestamps (10:02-10:04)
        assert len(aligned_gc) == 3
        assert len(aligned_dxy) == 3

    def test_raises_error_on_gc_without_datetime_index_or_ts_event(self):
        """Raises ValueError if GC DataFrame has neither DatetimeIndex nor ts_event.

        Specification: "raise ValueError('GC DataFrame must have either DatetimeIndex or ts_event column')"
        """
        # GC without DatetimeIndex or ts_event
        gc_df = pd.DataFrame({"open": [2650.0, 2651.0]})

        # DXY with DatetimeIndex
        dxy_timestamps = pd.date_range(
            "2024-07-01 10:00", periods=2, freq="1min", tz=UTC
        )
        dxy_df = pd.DataFrame({"open": [103.0, 103.1]}, index=dxy_timestamps)

        with pytest.raises(ValueError) as exc_info:
            align_dataframes(gc_df, dxy_df)

        assert "GC DataFrame must have either DatetimeIndex or ts_event column" in str(
            exc_info.value
        )

    def test_raises_error_on_dxy_without_datetime_index_or_ts_event(self):
        """Raises ValueError if DXY DataFrame has neither DatetimeIndex nor ts_event.

        Specification: "raise ValueError('DXY DataFrame must have either DatetimeIndex or ts_event column')"
        """
        # GC with DatetimeIndex
        gc_timestamps = pd.date_range(
            "2024-07-01 10:00", periods=2, freq="1min", tz=UTC
        )
        gc_df = pd.DataFrame({"open": [2650.0, 2651.0]}, index=gc_timestamps)

        # DXY without DatetimeIndex or ts_event
        dxy_df = pd.DataFrame({"open": [103.0, 103.1]})

        with pytest.raises(ValueError) as exc_info:
            align_dataframes(gc_df, dxy_df)

        assert "DXY DataFrame must have either DatetimeIndex or ts_event column" in str(
            exc_info.value
        )

    def test_handles_dataframes_with_ts_event_column(self):
        """Handles DataFrames that already have ts_event column.

        Specification: Works with both timestamp index and ts_event column formats.
        """
        # Both DataFrames with ts_event column
        timestamps = pd.date_range("2024-07-01 10:00", periods=3, freq="1min", tz=UTC)
        gc_df = pd.DataFrame(
            {
                "ts_event": timestamps,
                "open": [2650.0, 2651.0, 2652.0],
            }
        )
        dxy_df = pd.DataFrame(
            {
                "ts_event": timestamps,
                "open": [103.0, 103.1, 103.2],
            }
        )

        # Should not raise
        aligned_gc, aligned_dxy = align_dataframes(gc_df, dxy_df)

        assert len(aligned_gc) == 3
        assert len(aligned_dxy) == 3


class TestProcessFeatures:
    """Test process_features() - specification-based."""

    def test_raises_type_error_on_non_dataframe_gc(self):
        """Raises TypeError if gc_df is not a DataFrame.

        Specification: "if not isinstance(gc_df, pd.DataFrame): raise TypeError"
        """
        dxy_timestamps = pd.date_range(
            "2024-07-01 10:00", periods=2, freq="1min", tz=UTC
        )
        dxy_df = pd.DataFrame({"open": [103.0, 103.1]}, index=dxy_timestamps)

        with pytest.raises(TypeError) as exc_info:
            process_features("not a dataframe", dxy_df, timeframe="1m")

        assert "gc_df must be a pandas DataFrame" in str(exc_info.value)

    def test_raises_type_error_on_non_dataframe_dxy(self):
        """Raises TypeError if dxy_df is not a DataFrame.

        Specification: "if not isinstance(dxy_df, pd.DataFrame): raise TypeError"
        """
        gc_timestamps = pd.date_range(
            "2024-07-01 10:00", periods=2, freq="1min", tz=UTC
        )
        gc_df = pd.DataFrame(
            {
                "open": [2650.0, 2651.0],
                "high": [2651.0, 2652.0],
                "low": [2649.0, 2650.0],
                "close": [2650.5, 2651.5],
                "volume": [1000, 1100],
            },
            index=gc_timestamps,
        )

        with pytest.raises(TypeError) as exc_info:
            process_features(gc_df, "not a dataframe", timeframe="1m")

        assert "dxy_df must be a pandas DataFrame" in str(exc_info.value)

    def test_raises_value_error_on_missing_required_columns(self):
        """Raises ValueError if GC DataFrame missing required columns.

        Specification: "raise ValueError(f'GC DataFrame missing required columns: {missing_cols}')"
        """
        timestamps = pd.date_range("2024-07-01 10:00", periods=2, freq="1min", tz=UTC)

        # GC missing 'volume' column
        gc_df = pd.DataFrame(
            {
                "open": [2650.0, 2651.0],
                "high": [2651.0, 2652.0],
                "low": [2649.0, 2650.0],
                "close": [2650.5, 2651.5],
                # Missing 'volume'
            },
            index=timestamps,
        )

        dxy_df = pd.DataFrame({"open": [103.0, 103.1]}, index=timestamps)

        with pytest.raises(ValueError) as exc_info:
            process_features(gc_df, dxy_df, timeframe="1m")

        assert "missing required columns" in str(exc_info.value).lower()
        assert "volume" in str(exc_info.value).lower()

    def test_processes_minimal_valid_data(self):
        """Processes minimal valid data without error.

        Specification: Should handle minimal but valid data.
        """
        timestamps = pd.date_range("2024-07-01 10:00", periods=60, freq="1min", tz=UTC)

        gc_df = pd.DataFrame(
            {
                "open": [2650.0] * 60,
                "high": [2651.0] * 60,
                "low": [2649.0] * 60,
                "close": [2650.5] * 60,
                "volume": [1000] * 60,
            },
            index=timestamps,
        )

        dxy_df = pd.DataFrame(
            {
                "open": [103.0] * 60,
                "high": [103.1] * 60,
                "low": [102.9] * 60,
                "close": [103.05] * 60,
            },
            index=timestamps,
        )

        # Should not raise
        features = process_features(gc_df, dxy_df, timeframe="1m")

        assert isinstance(features, pd.DataFrame)
        assert len(features) > 0


class TestProcessFeaturesWithValidation:
    """Test process_features_with_validation() - specification-based.

    Note: This is a deep integration function that calls many components.
    These tests focus on the entry point behavior and basic error handling.
    """

    def test_handles_complete_valid_inputs(self):
        """Handles complete valid inputs without crashing.

        Specification: Main integration function should work with valid inputs.
        """
        from feature_engine.integration import process_features_with_validation
        from rule_engine.htf.types import HTFBias

        # Create complete features
        features = pd.Series(
            {
                "timestamp": datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "open": 2650.0,
                "high": 2651.0,
                "low": 2649.0,
                "close": 2650.5,
                "volume": 1000,
                "vwap": 2650.0,
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
                "structure_label": "HH",
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )

        market_state = {
            "buffer_phase": "growth",
            "tier_active": "Conservative",  # Use Conservative to avoid CEO directive requirement
            "ceo_directive_active": False,
            "news_ok": True,
        }

        # Should not crash
        signal = process_features_with_validation(
            features=features,
            htf_bias=htf_bias,
            market_state=market_state,
            session_constraints=None,
            guardrail_result=None,
        )

        # Should return None or valid Signal
        assert signal is None or hasattr(signal, "score")





