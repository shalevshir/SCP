"""Unit tests for VWAP calculation."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from feature_engine.vwap import calculate_vwap, calculate_vwap_deviation

# Path to project root (two levels up from this test file)
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestVWAPCalculation:
    """Test VWAP calculation against benchmarks and edge cases."""

    @pytest.fixture
    def simple_ohlcv(self) -> pd.DataFrame:
        """Create a simple OHLCV dataset for testing."""
        return pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01 09:00", periods=5, freq="1min"),
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                "volume": [1000, 1500, 2000, 1800, 1200],
            }
        )

    @pytest.fixture
    def real_gc_data(self) -> pd.DataFrame:
        """Load real GC OHLCV data from CSV."""
        data_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "GC_ohlcv-1m.csv"
        df = pd.read_csv(data_path, parse_dates=["ts_event"])
        # Filter to single symbol and take first 100 rows for testing
        df = df[df["symbol"] == "GCZ5"].head(100).copy()
        return df

    def test_vwap_basic_calculation(self, simple_ohlcv: pd.DataFrame) -> None:
        """Test VWAP calculation on simple dataset with manual verification."""
        result = calculate_vwap(simple_ohlcv, session_reset=False)

        # Manual calculation for first row:
        # Typical price = (high + low + close) / 3
        # VWAP = sum(typical_price * volume) / sum(volume)
        typical_prices = (
            simple_ohlcv["high"] + simple_ohlcv["low"] + simple_ohlcv["close"]
        ) / 3

        # First row VWAP
        expected_vwap_0 = typical_prices.iloc[0]
        assert np.isclose(result.iloc[0], expected_vwap_0, rtol=1e-5)

        # Second row VWAP (cumulative)
        cum_volume_1 = simple_ohlcv["volume"].iloc[:2].sum()
        cum_pv_1 = (typical_prices.iloc[:2] * simple_ohlcv["volume"].iloc[:2]).sum()
        expected_vwap_1 = cum_pv_1 / cum_volume_1
        assert np.isclose(result.iloc[1], expected_vwap_1, rtol=1e-5)

    def test_vwap_against_talib(self, real_gc_data: pd.DataFrame) -> None:
        """Test VWAP calculation against TA-Lib implementation if available."""
        try:
            import talib
        except ImportError:
            pytest.skip("TA-Lib not installed")

        result = calculate_vwap(real_gc_data, session_reset=False)

        # Check if TA-Lib has VWAP function
        if hasattr(talib, "VWAP"):
            talib_vwap = talib.VWAP(
                real_gc_data["high"].values,
                real_gc_data["low"].values,
                real_gc_data["close"].values,
                real_gc_data["volume"].values,
            )
            # Remove NaN values for comparison
            valid_mask = ~np.isnan(talib_vwap) & ~np.isnan(result)
            correlation = np.corrcoef(result[valid_mask], talib_vwap[valid_mask])[0, 1]
            assert correlation >= 0.99, f"Correlation {correlation} < 0.99"
        else:
            # If TA-Lib doesn't have VWAP, verify against manual calculation
            typical_prices = (
                real_gc_data["high"] + real_gc_data["low"] + real_gc_data["close"]
            ) / 3
            cum_volume = real_gc_data["volume"].cumsum()
            cum_pv = (typical_prices * real_gc_data["volume"]).cumsum()
            expected_vwap = cum_pv / cum_volume

            correlation = np.corrcoef(result, expected_vwap)[0, 1]
            assert correlation >= 0.99, f"Correlation {correlation} < 0.99"

    def test_vwap_with_zero_volume(self, simple_ohlcv: pd.DataFrame) -> None:
        """Test VWAP handles zero volume periods correctly."""
        # Set middle row to zero volume
        simple_ohlcv.loc[2, "volume"] = 0
        result = calculate_vwap(simple_ohlcv, session_reset=False)

        # Should not have NaN propagation
        assert not result.isna().any(), "VWAP should handle zero volume without NaN"

    def test_vwap_with_nan_values(self) -> None:
        """Test VWAP handles NaN in price data."""
        df = pd.DataFrame(
            {
                "ts_event": pd.date_range("2025-01-01", periods=5, freq="1min"),
                "open": [100.0, np.nan, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, np.nan, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                "volume": [1000, 1500, 2000, 1800, 1200],
            }
        )
        result = calculate_vwap(df, session_reset=False)

        # Should handle NaN gracefully
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)

    def test_vwap_single_row(self) -> None:
        """Test VWAP with single row DataFrame."""
        df = pd.DataFrame(
            {
                "ts_event": [pd.Timestamp("2025-01-01 09:00")],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            }
        )
        result = calculate_vwap(df, session_reset=False)

        # VWAP should equal typical price for single row
        expected = (101.0 + 99.0 + 100.5) / 3
        assert np.isclose(result.iloc[0], expected, rtol=1e-5)

    def test_vwap_session_reset(self) -> None:
        """Test VWAP with session reset functionality."""
        # Create data spanning two days
        df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(
                    [
                        "2025-01-01 09:00",
                        "2025-01-01 10:00",
                        "2025-01-01 11:00",
                        "2025-01-02 09:00",  # New day
                        "2025-01-02 10:00",
                    ]
                ),
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                "volume": [1000, 1500, 2000, 1800, 1200],
            }
        )

        result = calculate_vwap(df, session_reset=True)

        # VWAP on day 2 should reset (not be cumulative from day 1)
        # Row 3 (index 3) should have VWAP equal to its own typical price
        typical_price_day2_start = (104.0 + 102.0 + 103.5) / 3
        assert np.isclose(result.iloc[3], typical_price_day2_start, rtol=1e-5)

    def test_vwap_return_type_and_index(self, simple_ohlcv: pd.DataFrame) -> None:
        """Test that VWAP returns Series with correct index."""
        result = calculate_vwap(simple_ohlcv, session_reset=False)

        assert isinstance(result, pd.Series)
        assert len(result) == len(simple_ohlcv)
        assert result.index.equals(simple_ohlcv.index)


class TestVWAPDeviation:
    """Test VWAP deviation calculation."""

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
        assert deviation.iloc[0] == pytest.approx(0.189, abs=0.01)  # (2650-2645)/2645*100
        assert deviation.iloc[1] == pytest.approx(0.378, abs=0.01)  # (2655-2645)/2645*100
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

    def test_raises_error_for_negative_vwap(self) -> None:
        """Test that error is raised for negative VWAP values."""
        df = pd.DataFrame({"close": [2650.0], "vwap": [-100.0]})

        with pytest.raises(ValueError, match="VWAP values must be positive"):
            calculate_vwap_deviation(df)

    def test_raises_error_for_nan_vwap(self) -> None:
        """Test that error is raised for NaN VWAP values."""
        df = pd.DataFrame(
            {
                "close": [2650.0, 2655.0, 2645.0],
                "vwap": [2645.0, np.nan, 2645.0],
            }
        )

        with pytest.raises(ValueError, match="VWAP values must be positive.*NaN"):
            calculate_vwap_deviation(df)

    def test_raises_error_for_all_nan_vwap(self) -> None:
        """Test that error is raised when all VWAP values are NaN."""
        df = pd.DataFrame(
            {
                "close": [2650.0, 2655.0, 2645.0],
                "vwap": [np.nan, np.nan, np.nan],
            }
        )

        with pytest.raises(ValueError, match="VWAP values must be positive.*NaN"):
            calculate_vwap_deviation(df)
