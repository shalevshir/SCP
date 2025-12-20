"""Integration test to verify new features flow through BacktestProcessor."""

import pandas as pd
import pytest

from feature_engine.backtesting import BacktestProcessor


class TestNewFeaturesIntegration:
    """Test that new features are properly exposed through BacktestProcessor."""

    def test_new_features_in_backtesting_iteration(self):
        """Test that new features are present in BacktestProcessor output."""
        # Create sample data
        timestamps = pd.date_range("2025-01-01 10:00", periods=50, freq="1min")
        gc_df = pd.DataFrame(
            {
                "open": [2650.0] * 50,
                "high": [2652.0] * 50,
                "low": [2648.0] * 50,
                "close": [2651.0] * 50,
                "volume": [1000.0] * 50,
            },
            index=timestamps,
        )
        dxy_df = gc_df.copy()

        # Create processor
        processor = BacktestProcessor(
            timeframe="1m",
            session_reset=True,
            enable_validation=False,
        )

        # Iterate and check features
        features_list = []
        for features, context in processor.iterate_with_context(gc_df, dxy_df):
            features_list.append(features)

        # Should have features after warmup
        assert len(features_list) > 0

        # Check that new features are present in ALL yielded features
        for features in features_list:
            assert "atr" in features.index, "ATR missing from features"
            assert "upper_wick_pct" in features.index, "upper_wick_pct missing"
            assert "lower_wick_pct" in features.index, "lower_wick_pct missing"
            assert "close_vwap_diff" in features.index, "close_vwap_diff missing"
            assert "close_vwap_pct" in features.index, "close_vwap_pct missing"

        # Check that values are reasonable (not all NaN)
        last_features = features_list[-1]
        assert not pd.isna(last_features["atr"]), "ATR should have value"
        assert not pd.isna(
            last_features["upper_wick_pct"]
        ), "upper_wick_pct should have value"
        assert not pd.isna(
            last_features["lower_wick_pct"]
        ), "lower_wick_pct should have value"
        assert not pd.isna(
            last_features["close_vwap_diff"]
        ), "close_vwap_diff should have value"

    def test_new_features_in_entry_context_iteration(self):
        """Test that new features work in iterate_with_entry_context."""
        timestamps = pd.date_range("2025-01-01 10:00", periods=50, freq="1min")
        gc_df = pd.DataFrame(
            {
                "open": [2650.0] * 50,
                "high": [2652.0] * 50,
                "low": [2648.0] * 50,
                "close": [2651.0] * 50,
                "volume": [1000.0] * 50,
            },
            index=timestamps,
        )
        dxy_df = gc_df.copy()

        processor = BacktestProcessor(
            timeframe="1m",
            session_reset=True,
            enable_validation=False,
        )

        # Iterate with entry context
        features_list = []
        for features, context, next_candle in processor.iterate_with_entry_context(
            gc_df, dxy_df
        ):
            features_list.append(features)

        # Check new features present
        assert len(features_list) > 0
        for features in features_list:
            assert "atr" in features.index
            assert "upper_wick_pct" in features.index
            assert "lower_wick_pct" in features.index
            assert "close_vwap_diff" in features.index
            assert "close_vwap_pct" in features.index

    def test_atr_values_reasonable(self):
        """Test that ATR values are reasonable for Gold futures."""
        # Gold typically has ATR around 2-10 points on 1m
        timestamps = pd.date_range("2025-01-01 10:00", periods=50, freq="1min")
        gc_df = pd.DataFrame(
            {
                "open": [2650.0 + i * 0.5 for i in range(50)],
                "high": [2652.0 + i * 0.5 for i in range(50)],
                "low": [2648.0 + i * 0.5 for i in range(50)],
                "close": [2651.0 + i * 0.5 for i in range(50)],
                "volume": [1000.0] * 50,
            },
            index=timestamps,
        )
        dxy_df = gc_df.copy()

        processor = BacktestProcessor(timeframe="1m", enable_validation=False)

        features_list = list(processor.iterate_with_context(gc_df, dxy_df))
        last_features = features_list[-1][0]

        # ATR should be in reasonable range (2-10 for this data)
        assert (
            0.5 < last_features["atr"] < 10.0
        ), f"ATR out of range: {last_features['atr']}"

    def test_wick_percentages_with_real_candle_shapes(self):
        """Test wick percentages with various realistic candle shapes."""
        timestamps = pd.date_range("2025-01-01 10:00", periods=50, freq="1min")

        # Create diverse candle shapes with changing prices
        gc_df = pd.DataFrame(
            {
                "open": [2650.0 + i * 0.1 for i in range(50)],
                "high": [2652.0 + i * 0.1 for i in range(50)],
                "low": [2648.0 + i * 0.1 for i in range(50)],
                "close": [2651.0 + i * 0.1 for i in range(50)],
                "volume": [1000.0] * 50,
            },
            index=timestamps,
        )
        dxy_df = gc_df.copy()

        processor = BacktestProcessor(timeframe="1m", enable_validation=False)
        features_list = list(processor.iterate_with_context(gc_df, dxy_df))

        # Check that wick percentages are computed
        assert len(features_list) > 0, "Should have features"

        # Check last few candles have valid wick data
        for features, _ in features_list[-5:]:
            lower_wick = features["lower_wick_pct"]
            upper_wick = features["upper_wick_pct"]

            # Should not be NaN
            assert not pd.isna(lower_wick), "Lower wick should not be NaN"
            assert not pd.isna(upper_wick), "Upper wick should not be NaN"

            # Should be non-negative
            assert lower_wick >= 0, f"Lower wick should be >= 0, got {lower_wick}"
            assert upper_wick >= 0, f"Upper wick should be >= 0, got {upper_wick}"




