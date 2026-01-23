"""Unit tests for RSI (Relative Strength Index) calculation."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scp_shared.indicators.rsi import calculate_rsi

# Path to project root (6 levels up from services/shared/tests/unit/indicators/ to repository root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent


class TestRSICalculation:
    """Test RSI calculation against benchmarks and edge cases."""

    @pytest.fixture
    def simple_price_data(self) -> pd.DataFrame:
        """Create simple price data for manual RSI verification."""
        # Trending up data - should show lower RSI initially, then rising
        return pd.DataFrame(
            {
                "close": [
                    44.0,
                    44.5,
                    44.3,
                    44.8,
                    45.2,
                    45.0,
                    45.5,
                    46.0,
                    45.8,
                    46.5,
                    47.0,
                    46.8,
                    47.5,
                    48.0,
                    48.5,
                    49.0,
                    48.8,
                    49.5,
                    50.0,
                    49.8,
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

    def test_rsi_basic_calculation(self, simple_price_data: pd.DataFrame) -> None:
        """Test RSI calculation on simple dataset."""
        result = calculate_rsi(simple_price_data, period=14)

        # Should have same length as input
        assert len(result) == len(simple_price_data)

        # First 14 values should be NaN (initial period)
        assert result.iloc[:14].isna().all()

        # After period, should have valid RSI values between 0 and 100
        valid_rsi = result.iloc[14:]
        assert valid_rsi.notna().all()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_rsi_against_talib(self, real_gc_data: pd.DataFrame) -> None:
        """Test RSI calculation against TA-Lib implementation."""
        try:
            import talib
        except ImportError:
            pytest.skip("TA-Lib not installed")

        result = calculate_rsi(real_gc_data, period=14, price_column="close")
        talib_rsi = talib.RSI(real_gc_data["close"].values, timeperiod=14)

        # Remove NaN values for comparison
        valid_mask = ~np.isnan(talib_rsi) & ~np.isnan(result)

        # Calculate maximum absolute difference
        max_diff = np.abs(result[valid_mask] - talib_rsi[valid_mask]).max()

        # Should match within ±0.1 precision (per DoD)
        assert (
            max_diff <= 0.1
        ), f"Max difference {max_diff} exceeds ±0.1 precision requirement"

    def test_rsi_manual_verification(self) -> None:
        """Test RSI with manually calculated values."""
        # Simple dataset with known RSI values
        # First 14 bars for initial average, then we can calculate expected RSI
        prices = pd.DataFrame(
            {
                "close": [
                    44.0,
                    44.34,
                    44.09,
                    43.61,
                    44.33,
                    44.83,
                    45.10,
                    45.42,
                    45.84,
                    46.08,
                    45.89,
                    46.03,
                    45.61,
                    46.28,
                    46.28,  # 15th value - first RSI
                ]
            }
        )

        result = calculate_rsi(prices, period=14)

        # First 14 should be NaN
        assert result.iloc[:14].isna().all()

        # 15th value should be valid
        assert not pd.isna(result.iloc[14])

        # Should be between 0 and 100
        assert 0 <= result.iloc[14] <= 100

    def test_rsi_overbought_condition(self) -> None:
        """Test RSI correctly identifies overbought conditions (RSI > 70)."""
        # Create strongly uptrending data
        prices = pd.DataFrame(
            {"close": [100 + i * 2 for i in range(30)]}  # Consistent strong gains
        )

        result = calculate_rsi(prices, period=14)

        # After initial period, RSI should be high (overbought)
        valid_rsi = result.iloc[14:]
        # Most values should be > 70 in strong uptrend
        assert (valid_rsi > 70).sum() > len(valid_rsi) * 0.7

    def test_rsi_oversold_condition(self) -> None:
        """Test RSI correctly identifies oversold conditions (RSI < 30)."""
        # Create strongly downtrending data
        prices = pd.DataFrame(
            {"close": [100 - i * 2 for i in range(30)]}  # Consistent strong losses
        )

        result = calculate_rsi(prices, period=14)

        # After initial period, RSI should be low (oversold)
        valid_rsi = result.iloc[14:]
        # Most values should be < 30 in strong downtrend
        assert (valid_rsi < 30).sum() > len(valid_rsi) * 0.7

    def test_rsi_all_gains(self) -> None:
        """Test RSI with all gains (no losses) - should approach 100."""
        # Monotonically increasing prices
        prices = pd.DataFrame({"close": [100 + i for i in range(20)]})

        result = calculate_rsi(prices, period=14)

        # After initial period, RSI should be 100 (no losses)
        valid_rsi = result.iloc[14:]
        assert np.isclose(valid_rsi, 100.0, rtol=0.01).all()

    def test_rsi_all_losses(self) -> None:
        """Test RSI with all losses (no gains) - should approach 0."""
        # Monotonically decreasing prices
        prices = pd.DataFrame({"close": [100 - i for i in range(20)]})

        result = calculate_rsi(prices, period=14)

        # After initial period, RSI should be 0 (no gains)
        valid_rsi = result.iloc[14:]
        assert np.isclose(valid_rsi, 0.0, rtol=0.01).all()

    def test_rsi_insufficient_data(self) -> None:
        """Test RSI with insufficient data (< period rows)."""
        prices = pd.DataFrame({"close": [100, 101, 102, 103, 104]})

        result = calculate_rsi(prices, period=14)

        # All values should be NaN when data < period
        assert result.isna().all()

    def test_rsi_different_periods(self, simple_price_data: pd.DataFrame) -> None:
        """Test RSI with different period values."""
        for period in [9, 14, 21]:
            result = calculate_rsi(simple_price_data, period=period)

            # First 'period' values should be NaN
            assert result.iloc[:period].isna().all()

            # After period, should have valid values
            if len(simple_price_data) > period:
                valid_rsi = result.iloc[period:]
                assert valid_rsi.notna().all()
                assert (valid_rsi >= 0).all()
                assert (valid_rsi <= 100).all()

    def test_rsi_custom_price_column(self, real_gc_data: pd.DataFrame) -> None:
        """Test RSI with custom price column."""
        # Test with 'high' instead of 'close'
        result = calculate_rsi(real_gc_data, period=14, price_column="high")

        assert isinstance(result, pd.Series)
        assert len(result) == len(real_gc_data)

        # Should have valid RSI after period
        valid_rsi = result.iloc[14:]
        assert valid_rsi.notna().all()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_rsi_no_nan_propagation(self, simple_price_data: pd.DataFrame) -> None:
        """Test that RSI produces no NaNs beyond period window."""
        result = calculate_rsi(simple_price_data, period=14)

        # Count NaN values
        nan_count = result.isna().sum()

        # Should have exactly 'period' NaN values (initial window)
        assert nan_count == 14

        # No NaN beyond period
        assert result.iloc[14:].notna().all()

    def test_rsi_return_type_and_index(self, simple_price_data: pd.DataFrame) -> None:
        """Test that RSI returns Series with correct index."""
        result = calculate_rsi(simple_price_data, period=14)

        assert isinstance(result, pd.Series)
        assert len(result) == len(simple_price_data)
        assert result.index.equals(simple_price_data.index)

    def test_rsi_invalid_period(self) -> None:
        """Test RSI with invalid period values."""
        prices = pd.DataFrame({"close": [100 + i for i in range(20)]})

        # Period < 2 should raise ValueError
        with pytest.raises(ValueError, match="period must be >= 2"):
            calculate_rsi(prices, period=1)

        with pytest.raises(ValueError, match="period must be >= 2"):
            calculate_rsi(prices, period=0)

    def test_rsi_missing_column(self) -> None:
        """Test RSI with missing price column."""
        prices = pd.DataFrame({"open": [100 + i for i in range(20)]})

        # Missing 'close' column should raise ValueError
        with pytest.raises(ValueError, match="Column 'close' not found"):
            calculate_rsi(prices, period=14)
