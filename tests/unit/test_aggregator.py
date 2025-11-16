"""
Unit tests for feature engine aggregator.

Tests the aggregate_features() function that combines all technical indicators
into a unified DataFrame with modular configuration.
"""

from pathlib import Path

import pandas as pd
import pytest
from feature_engine.aggregator import aggregate_features

# Path to test data
PROJECT_ROOT = Path(__file__).parent.parent.parent
GC_DATA_PATH = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "GC_ohlcv-1m.csv"
DXY_DATA_PATH = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "DX_ohlcv-1m.csv"


class TestAggregatorBasic:
    """Test basic aggregator functionality with default parameters."""

    def test_aggregate_all_indicators_with_defaults(self) -> None:
        """Test aggregating all indicators with default parameters."""
        # Create minimal OHLCV data for GC
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "open": [2000.0 + i * 0.5 for i in range(100)],
            "high": [2001.0 + i * 0.5 for i in range(100)],
            "low": [1999.0 + i * 0.5 for i in range(100)],
            "close": [2000.0 + i * 0.5 for i in range(100)],
            "volume": [1000 + i * 10 for i in range(100)],
        }
        gc_df = pd.DataFrame(gc_data)

        # Create minimal OHLCV data for DXY (inverse relationship)
        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "close": [100.0 - i * 0.01 for i in range(100)],
        }
        dxy_df = pd.DataFrame(dxy_data)

        # Aggregate features with defaults (all indicators)
        result = aggregate_features(gc_df, dxy_df, timeframe="1m")

        # Verify output structure
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(gc_df)

        # Verify all original GC columns are preserved
        for col in gc_df.columns:
            assert col in result.columns

        # Verify all default feature columns are added
        expected_features = ["vwap", "rsi", "ema_9", "ema_20", "ema_50", "dxy_corr"]
        for feature in expected_features:
            assert feature in result.columns, f"Missing feature column: {feature}"

        # Verify feature columns are numeric
        for feature in expected_features:
            assert pd.api.types.is_numeric_dtype(
                result[feature]
            ), f"Feature {feature} is not numeric"

    def test_aggregate_preserves_gc_index(self) -> None:
        """Test that aggregator preserves the GC DataFrame index."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)
        gc_df.index = gc_df.index * 2  # Custom index

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        result = aggregate_features(gc_df, dxy_df, timeframe="1m")

        # Verify index is preserved
        pd.testing.assert_index_equal(result.index, gc_df.index)

    def test_aggregate_returns_copy_not_reference(self) -> None:
        """Test that aggregator returns a copy, not a reference to input."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        result = aggregate_features(gc_df, dxy_df, timeframe="1m")

        # Modify result
        result["new_column"] = 123

        # Verify original gc_df is unchanged
        assert "new_column" not in gc_df.columns
        assert "vwap" not in gc_df.columns


class TestAggregatorTimeframeValidation:
    """Test timeframe validation against ALLOWED_TIMEFRAMES."""

    @pytest.mark.parametrize(
        "valid_timeframe", ["1s", "1m", "15m", "1h"], ids=["1s", "1m", "15m", "1h"]
    )
    def test_aggregate_accepts_valid_timeframes(self, valid_timeframe: str) -> None:
        """Test that aggregator accepts all valid timeframes."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        # Should not raise
        result = aggregate_features(gc_df, dxy_df, timeframe=valid_timeframe)
        assert isinstance(result, pd.DataFrame)

    @pytest.mark.parametrize(
        "invalid_timeframe",
        ["5m", "30m", "4h", "1d", "invalid", ""],
        ids=["5m", "30m", "4h", "1d", "invalid", "empty"],
    )
    def test_aggregate_rejects_invalid_timeframes(
        self, invalid_timeframe: str
    ) -> None:
        """Test that aggregator rejects invalid timeframes."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        with pytest.raises(ValueError) as exc_info:
            aggregate_features(gc_df, dxy_df, timeframe=invalid_timeframe)

        assert "timeframe" in str(exc_info.value).lower()
        assert "allowed" in str(exc_info.value).lower() or "valid" in str(
            exc_info.value
        ).lower()


class TestAggregatorModularSelection:
    """Test modular indicator selection (on/off combinations)."""

    def test_aggregate_with_only_vwap(self) -> None:
        """Test aggregating with only VWAP indicator."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        indicators = {
            "vwap": True,
            "rsi": False,
            "ema": False,
            "dxy_correlation": False,
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify only VWAP is present
        assert "vwap" in result.columns
        assert "rsi" not in result.columns
        assert "ema_9" not in result.columns
        assert "ema_20" not in result.columns
        assert "ema_50" not in result.columns
        assert "dxy_corr" not in result.columns

    def test_aggregate_with_only_rsi(self) -> None:
        """Test aggregating with only RSI indicator."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        indicators = {
            "vwap": False,
            "rsi": True,
            "ema": False,
            "dxy_correlation": False,
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify only RSI is present
        assert "vwap" not in result.columns
        assert "rsi" in result.columns
        assert "ema_9" not in result.columns
        assert "dxy_corr" not in result.columns

    def test_aggregate_with_rsi_and_ema(self) -> None:
        """Test aggregating with multiple selected indicators."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        indicators = {"vwap": False, "rsi": True, "ema": True, "dxy_correlation": None}

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify selected indicators are present
        assert "vwap" not in result.columns
        assert "rsi" in result.columns
        assert "ema_9" in result.columns
        assert "ema_20" in result.columns
        assert "ema_50" in result.columns
        assert "dxy_corr" not in result.columns

    def test_aggregate_with_all_disabled(self) -> None:
        """Test aggregating with all indicators disabled (should return GC df only)."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        indicators = {
            "vwap": False,
            "rsi": False,
            "ema": False,
            "dxy_correlation": False,
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify no feature columns added
        assert "vwap" not in result.columns
        assert "rsi" not in result.columns
        assert "ema_9" not in result.columns
        assert "dxy_corr" not in result.columns

        # Verify original columns preserved
        for col in gc_df.columns:
            assert col in result.columns


class TestAggregatorCustomParameters:
    """Test aggregator with custom indicator parameters."""

    def test_aggregate_with_custom_rsi_period(self) -> None:
        """Test aggregating with custom RSI period."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "open": [2000.0 + i * 0.5 for i in range(100)],
            "high": [2001.0 + i * 0.5 for i in range(100)],
            "low": [1999.0 + i * 0.5 for i in range(100)],
            "close": [2000.0 + i * 0.5 for i in range(100)],
            "volume": [1000 + i * 10 for i in range(100)],
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "close": [100.0 - i * 0.01 for i in range(100)],
        }
        dxy_df = pd.DataFrame(dxy_data)

        # Use RSI with period 21 instead of default 14
        indicators = {
            "vwap": False,
            "rsi": {"period": 21},
            "ema": False,
            "dxy_correlation": False,
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify RSI is present
        assert "rsi" in result.columns
        assert pd.api.types.is_numeric_dtype(result["rsi"])

        # RSI with period 21 should have more NaN values than period 14
        # (first 21 bars will be NaN)
        assert result["rsi"].isna().sum() >= 21

    def test_aggregate_with_custom_ema_periods(self) -> None:
        """Test aggregating with custom EMA periods."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "open": [2000.0] * 100,
            "high": [2001.0] * 100,
            "low": [1999.0] * 100,
            "close": [2000.0] * 100,
            "volume": [1000] * 100,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "close": [100.0] * 100,
        }
        dxy_df = pd.DataFrame(dxy_data)

        # Use only EMA 20 and 50 (skip EMA 9)
        indicators = {
            "vwap": False,
            "rsi": False,
            "ema": {"periods": [20, 50]},
            "dxy_correlation": False,
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify only EMA 20 and 50 are present
        assert "ema_20" in result.columns
        assert "ema_50" in result.columns
        assert "ema_9" not in result.columns

    def test_aggregate_with_custom_dxy_window(self) -> None:
        """Test aggregating with custom DXY correlation window."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "open": [2000.0 + i * 0.5 for i in range(100)],
            "high": [2001.0 + i * 0.5 for i in range(100)],
            "low": [1999.0 + i * 0.5 for i in range(100)],
            "close": [2000.0 + i * 0.5 for i in range(100)],
            "volume": [1000 + i * 10 for i in range(100)],
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "close": [100.0 - i * 0.01 for i in range(100)],
        }
        dxy_df = pd.DataFrame(dxy_data)

        # Use DXY correlation with window 30 instead of default 50
        indicators = {
            "vwap": False,
            "rsi": False,
            "ema": False,
            "dxy_correlation": {"window": 30},
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify DXY correlation is present
        assert "dxy_corr" in result.columns
        assert pd.api.types.is_numeric_dtype(result["dxy_corr"])

    def test_aggregate_with_custom_vwap_session_reset(self) -> None:
        """Test aggregating with custom VWAP session reset."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        # Use VWAP without session reset (cumulative)
        indicators = {
            "vwap": {"session_reset": False},
            "rsi": False,
            "ema": False,
            "dxy_correlation": False,
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify VWAP is present
        assert "vwap" in result.columns
        assert pd.api.types.is_numeric_dtype(result["vwap"])

    def test_aggregate_with_mixed_custom_and_default(self) -> None:
        """Test aggregating with mix of custom params and defaults."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "open": [2000.0 + i * 0.5 for i in range(100)],
            "high": [2001.0 + i * 0.5 for i in range(100)],
            "low": [1999.0 + i * 0.5 for i in range(100)],
            "close": [2000.0 + i * 0.5 for i in range(100)],
            "volume": [1000 + i * 10 for i in range(100)],
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=100, freq="1min"),
            "close": [100.0 - i * 0.01 for i in range(100)],
        }
        dxy_df = pd.DataFrame(dxy_data)

        # Mix: custom RSI, default VWAP, skip EMA and DXY
        indicators = {
            "vwap": True,  # Use default
            "rsi": {"period": 21},  # Custom
            "ema": False,  # Skip
            "dxy_correlation": None,  # Skip
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify selected indicators
        assert "vwap" in result.columns
        assert "rsi" in result.columns
        assert "ema_9" not in result.columns
        assert "dxy_corr" not in result.columns


class TestAggregatorEdgeCases:
    """Test aggregator edge cases and error handling."""

    def test_aggregate_with_empty_indicators_dict(self) -> None:
        """Test aggregating with empty indicators dict (should use defaults)."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        # Empty dict should use defaults
        result = aggregate_features(gc_df, dxy_df, "1m", indicators={})

        # Verify all default features are present
        expected_features = ["vwap", "rsi", "ema_9", "ema_20", "ema_50", "dxy_corr"]
        for feature in expected_features:
            assert feature in result.columns

    def test_aggregate_with_missing_gc_columns_raises_error(self) -> None:
        """Test that aggregator raises error for missing GC columns."""
        # Missing 'volume' column
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        with pytest.raises(ValueError) as exc_info:
            aggregate_features(gc_df, dxy_df, "1m")

        assert "missing required columns" in str(exc_info.value).lower()
        assert "volume" in str(exc_info.value).lower()

    def test_aggregate_with_non_dataframe_gc_raises_error(self) -> None:
        """Test that aggregator raises TypeError for non-DataFrame GC input."""
        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "close": [100.0] * 50,
        }
        dxy_df = pd.DataFrame(dxy_data)

        with pytest.raises(TypeError) as exc_info:
            aggregate_features([1, 2, 3], dxy_df, "1m")  # type: ignore

        assert "dataframe" in str(exc_info.value).lower()

    def test_aggregate_with_non_dataframe_dxy_raises_error(self) -> None:
        """Test that aggregator raises TypeError for non-DataFrame DXY input."""
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=50, freq="1min"),
            "open": [2000.0] * 50,
            "high": [2001.0] * 50,
            "low": [1999.0] * 50,
            "close": [2000.0] * 50,
            "volume": [1000] * 50,
        }
        gc_df = pd.DataFrame(gc_data)

        with pytest.raises(TypeError) as exc_info:
            aggregate_features(gc_df, {"close": [100.0]}, "1m")  # type: ignore

        assert "dataframe" in str(exc_info.value).lower()

    def test_aggregate_with_minimal_data(self) -> None:
        """Test aggregator with minimal data (enough for warmup periods)."""
        # Use 60 bars (enough for RSI 14 + EMA 50 warmup)
        gc_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=60, freq="1min"),
            "open": [2000.0 + i * 0.1 for i in range(60)],
            "high": [2001.0 + i * 0.1 for i in range(60)],
            "low": [1999.0 + i * 0.1 for i in range(60)],
            "close": [2000.0 + i * 0.1 for i in range(60)],
            "volume": [1000 + i * 10 for i in range(60)],
        }
        gc_df = pd.DataFrame(gc_data)

        dxy_data = {
            "ts_event": pd.date_range("2025-01-01 09:00", periods=60, freq="1min"),
            "close": [100.0 - i * 0.01 for i in range(60)],
        }
        dxy_df = pd.DataFrame(dxy_data)

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Should complete without errors
        assert len(result) == 60
        assert "vwap" in result.columns
        assert "rsi" in result.columns
        assert "ema_50" in result.columns
        assert "dxy_corr" in result.columns


class TestAggregatorRealData:
    """Test aggregator with real GC/DXY market data (DoD validation)."""

    def test_aggregate_with_real_1m_data(self) -> None:
        """Test aggregator with real 1m GC and DXY data (DoD requirement)."""
        if not GC_DATA_PATH.exists() or not DXY_DATA_PATH.exists():
            pytest.skip("Real market data not available")

        # Load real 1m data
        gc_df = pd.read_csv(GC_DATA_PATH, parse_dates=["ts_event"])
        dxy_df = pd.read_csv(DXY_DATA_PATH, parse_dates=["ts_event"])

        # Take a reasonable subset (500 bars for performance)
        gc_df = gc_df.head(500)
        dxy_df = dxy_df.head(500)

        # Aggregate all features with defaults
        result = aggregate_features(gc_df, dxy_df, "1m")

        # DoD: Output includes VWAP, RSI, EMA9/20/50, DXY_corr columns
        expected_features = ["vwap", "rsi", "ema_9", "ema_20", "ema_50", "dxy_corr"]
        for feature in expected_features:
            assert (
                feature in result.columns
            ), f"DoD requirement failed: missing {feature}"

        # DoD: All feature columns are numeric
        for feature in expected_features:
            assert pd.api.types.is_numeric_dtype(
                result[feature]
            ), f"DoD requirement failed: {feature} is not numeric"

        # Verify data quality (should have valid values after warmup)
        assert result["vwap"].notna().sum() > 0, "VWAP has no valid values"
        assert result["rsi"].notna().sum() > 0, "RSI has no valid values"
        assert result["ema_9"].notna().sum() > 0, "EMA 9 has no valid values"
        assert result["ema_20"].notna().sum() > 0, "EMA 20 has no valid values"
        assert result["ema_50"].notna().sum() > 0, "EMA 50 has no valid values"
        assert (
            result["dxy_corr"].notna().sum() > 0
        ), "DXY correlation has no valid values"

    def test_aggregate_preserves_original_gc_data(self) -> None:
        """Test that aggregator preserves all original GC columns and data."""
        if not GC_DATA_PATH.exists() or not DXY_DATA_PATH.exists():
            pytest.skip("Real market data not available")

        gc_df = pd.read_csv(GC_DATA_PATH, parse_dates=["ts_event"])
        dxy_df = pd.read_csv(DXY_DATA_PATH, parse_dates=["ts_event"])

        gc_df = gc_df.head(200)
        dxy_df = dxy_df.head(200)

        # Store original values
        original_close = gc_df["close"].copy()

        result = aggregate_features(gc_df, dxy_df, "1m")

        # Verify all original columns present
        for col in gc_df.columns:
            assert col in result.columns

        # Verify original data unchanged
        pd.testing.assert_series_equal(
            result["close"], original_close, check_names=False
        )

    def test_aggregate_validates_timeframe_on_real_data(self) -> None:
        """Test timeframe validation with real data (DoD requirement)."""
        if not GC_DATA_PATH.exists() or not DXY_DATA_PATH.exists():
            pytest.skip("Real market data not available")

        gc_df = pd.read_csv(GC_DATA_PATH, parse_dates=["ts_event"])
        dxy_df = pd.read_csv(DXY_DATA_PATH, parse_dates=["ts_event"])

        gc_df = gc_df.head(100)
        dxy_df = dxy_df.head(100)

        # DoD: Timeframe validated against ALLOWED_TIMEFRAMES
        # Valid timeframe should pass
        result = aggregate_features(gc_df, dxy_df, "1m")
        assert isinstance(result, pd.DataFrame)

        # Invalid timeframe should fail
        with pytest.raises(ValueError) as exc_info:
            aggregate_features(gc_df, dxy_df, "5m")  # Not in ALLOWED_TIMEFRAMES

        assert "1s" in str(exc_info.value) or "allowed" in str(exc_info.value).lower()

    def test_aggregate_modular_selection_on_real_data(self) -> None:
        """Test modular indicator selection with real market data."""
        if not GC_DATA_PATH.exists() or not DXY_DATA_PATH.exists():
            pytest.skip("Real market data not available")

        gc_df = pd.read_csv(GC_DATA_PATH, parse_dates=["ts_event"])
        dxy_df = pd.read_csv(DXY_DATA_PATH, parse_dates=["ts_event"])

        gc_df = gc_df.head(200)
        dxy_df = dxy_df.head(200)

        # Test selective indicators
        indicators = {"vwap": True, "rsi": True, "ema": False, "dxy_correlation": False}

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify only selected indicators present
        assert "vwap" in result.columns
        assert "rsi" in result.columns
        assert "ema_9" not in result.columns
        assert "ema_20" not in result.columns
        assert "ema_50" not in result.columns
        assert "dxy_corr" not in result.columns

    def test_aggregate_custom_parameters_on_real_data(self) -> None:
        """Test custom indicator parameters with real market data."""
        if not GC_DATA_PATH.exists() or not DXY_DATA_PATH.exists():
            pytest.skip("Real market data not available")

        gc_df = pd.read_csv(GC_DATA_PATH, parse_dates=["ts_event"])
        dxy_df = pd.read_csv(DXY_DATA_PATH, parse_dates=["ts_event"])

        gc_df = gc_df.head(200)
        dxy_df = dxy_df.head(200)

        # Use custom parameters
        indicators = {
            "vwap": {"session_reset": False},  # Cumulative
            "rsi": {"period": 21},  # Non-default period
            "ema": {"periods": [10, 30]},  # Custom periods
            "dxy_correlation": {"window": 30},  # Smaller window
        }

        result = aggregate_features(gc_df, dxy_df, "1m", indicators=indicators)

        # Verify custom EMA periods
        assert "ema_10" in result.columns
        assert "ema_30" in result.columns
        assert "ema_9" not in result.columns  # Default period not present
        assert "ema_20" not in result.columns
        assert "ema_50" not in result.columns

        # Verify all selected indicators present
        assert "vwap" in result.columns
        assert "rsi" in result.columns
        assert "dxy_corr" in result.columns

