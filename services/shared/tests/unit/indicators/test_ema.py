"""Unit tests for EMA (Exponential Moving Average) calculation."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scp_shared.indicators.ema import calculate_ema, calculate_ema_multiple

# Path to project root (6 levels up from services/shared/tests/unit/indicators/ to repository root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent


class TestEMACalculation:
    """Test EMA calculation against benchmarks and edge cases."""

    @pytest.fixture
    def simple_price_data(self) -> pd.DataFrame:
        """Create simple price data for manual EMA verification."""
        return pd.DataFrame(
            {
                "close": [
                    22.27,
                    22.19,
                    22.08,
                    22.17,
                    22.18,
                    22.13,
                    22.23,
                    22.43,
                    22.24,
                    22.29,
                    22.15,
                    22.39,
                    22.38,
                    22.61,
                    23.36,
                ]
            }
        )

    @pytest.fixture
    def real_gc_data(self) -> pd.DataFrame:
        """Load real GC OHLCV data from CSV."""
        data_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "GC_ohlcv-1m.csv"
        if not data_path.exists():
            pytest.skip(f"Test data not found at {data_path}")
        df = pd.read_csv(data_path, parse_dates=["ts_event"])
        # Filter to single symbol and take first 200 rows for testing
        df = df[df["symbol"] == "GCZ5"].head(200).copy()
        return df

    def test_ema_basic_calculation(self, simple_price_data: pd.DataFrame) -> None:
        """Test EMA calculation on simple dataset."""
        result = calculate_ema(simple_price_data, period=10)

        # Should have same length as input
        assert len(result) == len(simple_price_data)

        # First value should equal first price (seed)
        assert np.isclose(result.iloc[0], simple_price_data["close"].iloc[0])

        # All values should be valid (no NaN)
        assert result.notna().all()

        # EMA should be between min and max of prices
        assert result.min() >= simple_price_data["close"].min()
        assert result.max() <= simple_price_data["close"].max()

    def test_ema_against_talib(self, real_gc_data: pd.DataFrame) -> None:
        """Test EMA calculation against TA-Lib implementation."""
        try:
            import talib
        except ImportError:
            pytest.skip("TA-Lib not installed")

        for period in [9, 20, 50]:
            result = calculate_ema(real_gc_data, period=period, price_column="close")
            talib_ema = talib.EMA(real_gc_data["close"].values, timeperiod=period)

            # Remove NaN values for comparison
            valid_mask = ~np.isnan(talib_ema) & ~np.isnan(result)

            # Calculate maximum absolute difference
            max_diff = np.abs(result[valid_mask] - talib_ema[valid_mask]).max()

            # Should match within ±0.01 precision (per DoD)
            assert (
                max_diff <= 0.01
            ), f"Period {period}: Max difference {max_diff} exceeds ±0.01 precision"

    def test_ema_manual_verification(self) -> None:
        """Test EMA with manually calculated values."""
        # Simple dataset for hand calculation
        prices = pd.DataFrame({"close": [10.0, 11.0, 12.0, 11.5, 12.5]})

        result = calculate_ema(prices, period=3)

        # Alpha = 2 / (period + 1) = 2 / 4 = 0.5
        alpha = 2 / (3 + 1)

        # First value is the price itself
        assert np.isclose(result.iloc[0], 10.0)

        # Second value: EMA = price * alpha + EMA_prev * (1 - alpha)
        expected_1 = 11.0 * alpha + 10.0 * (1 - alpha)
        assert np.isclose(result.iloc[1], expected_1, rtol=1e-5)

        # Third value
        expected_2 = 12.0 * alpha + expected_1 * (1 - alpha)
        assert np.isclose(result.iloc[2], expected_2, rtol=1e-5)

    def test_ema_sop_periods(self, simple_price_data: pd.DataFrame) -> None:
        """Test EMA with SOP periods (9, 20, 50)."""
        for period in [9, 20, 50]:
            result = calculate_ema(simple_price_data, period=period)

            assert len(result) == len(simple_price_data)
            assert result.notna().all()
            assert result.iloc[0] == simple_price_data["close"].iloc[0]

    def test_ema_custom_periods(self, simple_price_data: pd.DataFrame) -> None:
        """Test EMA with various custom periods."""
        for period in [5, 14, 21, 100, 200]:
            result = calculate_ema(simple_price_data, period=period)

            assert isinstance(result, pd.Series)
            assert len(result) == len(simple_price_data)

    def test_ema_single_row(self) -> None:
        """Test EMA with single row - should equal price."""
        df = pd.DataFrame({"close": [100.0]})
        result = calculate_ema(df, period=20)

        assert len(result) == 1
        assert result.iloc[0] == 100.0

    def test_ema_custom_price_column(self, real_gc_data: pd.DataFrame) -> None:
        """Test EMA with custom price column."""
        for col in ["high", "low", "open"]:
            result = calculate_ema(real_gc_data, period=20, price_column=col)

            assert isinstance(result, pd.Series)
            assert len(result) == len(real_gc_data)
            assert result.notna().all()

    def test_ema_return_type_and_index(self, simple_price_data: pd.DataFrame) -> None:
        """Test that EMA returns Series with correct index."""
        result = calculate_ema(simple_price_data, period=10)

        assert isinstance(result, pd.Series)
        assert len(result) == len(simple_price_data)
        assert result.index.equals(simple_price_data.index)

    def test_ema_invalid_period(self) -> None:
        """Test EMA with invalid period values."""
        df = pd.DataFrame({"close": [100 + i for i in range(20)]})

        # Period < 1 should raise ValueError
        with pytest.raises(ValueError, match="period must be >= 1"):
            calculate_ema(df, period=0)

        with pytest.raises(ValueError, match="period must be >= 1"):
            calculate_ema(df, period=-1)

    def test_ema_missing_column(self) -> None:
        """Test EMA with missing price column."""
        df = pd.DataFrame({"open": [100 + i for i in range(20)]})

        # Missing 'close' column should raise ValueError
        with pytest.raises(ValueError, match="Column 'close' not found"):
            calculate_ema(df, period=20)

    def test_ema_multiple_basic(self, simple_price_data: pd.DataFrame) -> None:
        """Test calculate_ema_multiple function."""
        result = calculate_ema_multiple(simple_price_data, periods=[9, 20, 50])

        # Should return DataFrame with correct columns
        assert isinstance(result, pd.DataFrame)
        assert "ema_9" in result.columns
        assert "ema_20" in result.columns
        assert "ema_50" in result.columns

        # All columns should have same length as input
        assert len(result) == len(simple_price_data)

        # No NaN values
        assert result.notna().all().all()

    def test_ema_multiple_matches_individual(
        self, simple_price_data: pd.DataFrame
    ) -> None:
        """Test that multiple EMA matches individual calculations."""
        result_multiple = calculate_ema_multiple(simple_price_data, periods=[9, 20, 50])

        # Calculate individually
        ema_9 = calculate_ema(simple_price_data, period=9)
        ema_20 = calculate_ema(simple_price_data, period=20)
        ema_50 = calculate_ema(simple_price_data, period=50)

        # Should match
        assert np.allclose(result_multiple["ema_9"], ema_9)
        assert np.allclose(result_multiple["ema_20"], ema_20)
        assert np.allclose(result_multiple["ema_50"], ema_50)

    def test_ema_multiple_custom_periods(self, simple_price_data: pd.DataFrame) -> None:
        """Test multiple EMA with custom periods."""
        result = calculate_ema_multiple(simple_price_data, periods=[5, 10, 15])

        assert "ema_5" in result.columns
        assert "ema_10" in result.columns
        assert "ema_15" in result.columns

    def test_ema_crossover_detection(self) -> None:
        """Test EMA crossover detection (trend change signal)."""
        # Create trending data
        df = pd.DataFrame(
            {
                "close": [
                    100,
                    101,
                    102,
                    103,
                    104,  # Uptrend
                    103,
                    102,
                    101,
                    100,
                    99,  # Downtrend
                    100,
                    101,
                    102,
                    103,
                    104,
                ]
            }  # Uptrend again
        )

        emas = calculate_ema_multiple(df, periods=[3, 10])

        # Fast EMA crosses above slow EMA = bullish signal
        bullish_cross = (emas["ema_3"] > emas["ema_10"]) & (
            emas["ema_3"].shift(1) <= emas["ema_10"].shift(1)
        )

        # Should detect some crossovers
        assert bullish_cross.any()

    def test_ema_price_relationship(self, simple_price_data: pd.DataFrame) -> None:
        """Test price vs EMA relationship."""
        simple_price_data["ema_20"] = calculate_ema(simple_price_data, period=20)

        # Price above EMA = potential uptrend
        simple_price_data["above_ema"] = (
            simple_price_data["close"] > simple_price_data["ema_20"]
        )

        # Price below EMA = potential downtrend
        simple_price_data["below_ema"] = (
            simple_price_data["close"] < simple_price_data["ema_20"]
        )

        # Should have some of each condition
        assert (
            simple_price_data["above_ema"].any() or simple_price_data["below_ema"].any()
        )

    def test_ema_multiple_alignment(self) -> None:
        """Test multiple EMA alignment (all EMAs trending together)."""
        # Strong uptrend data
        df = pd.DataFrame({"close": [100 + i * 2 for i in range(100)]})

        emas = calculate_ema_multiple(df, periods=[9, 20, 50])

        # In strong uptrend, fast EMA > medium EMA > slow EMA (bullish alignment)
        # Check last 10 values
        bullish_alignment = (
            (emas["ema_9"] > emas["ema_20"]) & (emas["ema_20"] > emas["ema_50"])
        ).iloc[-10:]

        # Most should be aligned in strong trend
        assert bullish_alignment.sum() > 7

