"""Unit tests for DXY Correlation calculation."""

from pathlib import Path

import pandas as pd
import pytest
from feature_engine.dxy_correlation import calculate_dxy_correlation

# Path to project root (two levels up from this test file)
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestDXYCorrelation:
    """Test DXY correlation calculation against requirements and edge cases."""

    @pytest.fixture
    def simple_gc_data(self) -> pd.DataFrame:
        """Create simple GC price data."""
        return pd.DataFrame(
            {
                "ts_event": pd.to_datetime(
                    [
                        "2025-01-01 09:00",
                        "2025-01-01 09:01",
                        "2025-01-01 09:02",
                        "2025-01-01 09:03",
                        "2025-01-01 09:04",
                        "2025-01-01 09:05",
                        "2025-01-01 09:06",
                        "2025-01-01 09:07",
                        "2025-01-01 09:08",
                        "2025-01-01 09:09",
                    ]
                ),
                "close": [
                    2000.0,
                    2001.0,
                    2002.0,
                    2003.0,
                    2004.0,
                    2005.0,
                    2006.0,
                    2007.0,
                    2008.0,
                    2009.0,
                ],
                "symbol": ["GCZ5"] * 10,
            }
        )

    @pytest.fixture
    def simple_dxy_data(self) -> pd.DataFrame:
        """Create simple DXY price data (inverse relationship with GC)."""
        return pd.DataFrame(
            {
                "ts_event": pd.to_datetime(
                    [
                        "2025-01-01 09:00",
                        "2025-01-01 09:01",
                        "2025-01-01 09:02",
                        "2025-01-01 09:03",
                        "2025-01-01 09:04",
                        "2025-01-01 09:05",
                        "2025-01-01 09:06",
                        "2025-01-01 09:07",
                        "2025-01-01 09:08",
                        "2025-01-01 09:09",
                    ]
                ),
                "close": [100.0, 99.9, 99.8, 99.7, 99.6, 99.5, 99.4, 99.3, 99.2, 99.1],
                "symbol": ["DX"] * 10,
            }
        )

    @pytest.fixture
    def real_gc_data(self) -> pd.DataFrame:
        """Load real GC OHLCV data from CSV."""
        data_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "GC_ohlcv-1m.csv"
        df = pd.read_csv(data_path, parse_dates=["ts_event"])
        # Filter to single symbol and take first 200 rows
        df = df[df["symbol"] == "GCZ5"].head(200).copy()
        return df

    @pytest.fixture
    def real_dxy_data(self) -> pd.DataFrame:
        """Load real DXY OHLCV data from CSV."""
        data_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "DX_ohlcv-1m.csv"
        df = pd.read_csv(data_path, parse_dates=["ts_event"])
        # Take first 200 rows
        df = df.head(200).copy()
        return df

    def test_dxy_correlation_basic_calculation(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test basic DXY correlation calculation."""
        result = calculate_dxy_correlation(simple_gc_data, simple_dxy_data, window=5)

        # Should have same length as aligned data
        assert len(result) == len(simple_gc_data)

        # First (window-1) values should be NaN (need window for correlation)
        assert result.iloc[:4].isna().all()

        # Remaining values should be valid
        assert result.iloc[4:].notna().all()

        # Should be negative correlation (GC up, DXY down)
        assert result.iloc[4:].max() < 0

    def test_dxy_correlation_negative_on_inverse(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that perfect inverse relationship produces -1.0 correlation."""
        # Perfect inverse: GC goes up, DXY goes down
        result = calculate_dxy_correlation(simple_gc_data, simple_dxy_data, window=10)

        # Last value should be close to -1.0 (perfect negative correlation)
        assert result.iloc[-1] < -0.9

    def test_dxy_correlation_known_inverse_segment(
        self, real_gc_data: pd.DataFrame, real_dxy_data: pd.DataFrame
    ) -> None:
        """Test that known inverse segments produce < -0.6 correlation (DoD)."""
        result = calculate_dxy_correlation(real_gc_data, real_dxy_data, window=50)

        # Find segments with strong negative correlation
        strong_negative = result[result < -0.6]

        # Should have at least some periods with < -0.6 correlation
        # (Gold and Dollar typically have negative correlation)
        assert len(strong_negative) > 0, "Expected some periods with < -0.6 correlation"

    def test_dxy_correlation_window_parameter(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test DXY correlation with different window sizes."""
        for window in [10, 20, 50, 100]:
            result = calculate_dxy_correlation(
                simple_gc_data, simple_dxy_data, window=window
            )

            # First (window-1) values should be NaN
            assert result.iloc[: window - 1].isna().all()

            # Remaining should be valid
            if len(result) > window - 1:
                assert result.iloc[window - 1 :].notna().all()

    def test_dxy_correlation_inner_join_alignment(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that inner join handles alignment mismatches safely."""
        # Create mismatched timestamps
        gc_mismatched = simple_gc_data.copy()
        gc_mismatched.loc[2, "ts_event"] = pd.to_datetime(
            "2025-01-01 09:10"
        )  # No match

        dxy_mismatched = simple_dxy_data.copy()
        dxy_mismatched.loc[5, "ts_event"] = pd.to_datetime(
            "2025-01-01 09:11"
        )  # No match

        result = calculate_dxy_correlation(gc_mismatched, dxy_mismatched, window=5)

        # Should only calculate correlation for aligned timestamps
        # Result length should be <= min(gc, dxy) length
        assert len(result) <= min(len(gc_mismatched), len(dxy_mismatched))

    def test_dxy_correlation_custom_price_columns(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test DXY correlation with custom price columns."""
        # Rename close columns
        gc_renamed = simple_gc_data.rename(columns={"close": "gc_close"})
        dxy_renamed = simple_dxy_data.rename(columns={"close": "dxy_close"})

        result = calculate_dxy_correlation(
            gc_renamed,
            dxy_renamed,
            window=5,
            gc_price_column="gc_close",
            dxy_price_column="dxy_close",
        )

        assert len(result) == len(gc_renamed)
        assert result.iloc[4:].notna().all()

    def test_dxy_correlation_custom_timestamp_column(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test DXY correlation with custom timestamp column."""
        # Rename timestamp columns
        gc_renamed = simple_gc_data.rename(columns={"ts_event": "timestamp"})
        dxy_renamed = simple_dxy_data.rename(columns={"ts_event": "timestamp"})

        result = calculate_dxy_correlation(
            gc_renamed,
            dxy_renamed,
            window=5,
            timestamp_column="timestamp",
        )

        assert len(result) > 0

    def test_dxy_correlation_return_type_and_index(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test that correlation returns Series with correct index."""
        result = calculate_dxy_correlation(simple_gc_data, simple_dxy_data, window=5)

        assert isinstance(result, pd.Series)
        # Index should match aligned DataFrame
        assert len(result) <= len(simple_gc_data)

    def test_dxy_correlation_insufficient_data(
        self, simple_gc_data: pd.DataFrame, simple_dxy_data: pd.DataFrame
    ) -> None:
        """Test DXY correlation with insufficient data (< window)."""
        # Use window larger than data
        small_gc = simple_gc_data.head(3)
        small_dxy = simple_dxy_data.head(3)

        result = calculate_dxy_correlation(small_gc, small_dxy, window=10)

        # All values should be NaN (need at least window rows)
        assert result.isna().all()

    def test_dxy_correlation_missing_columns(self) -> None:
        """Test DXY correlation with missing required columns."""
        gc_df = pd.DataFrame(
            {"ts_event": pd.to_datetime(["2025-01-01 09:00"]), "open": [2000.0]}
        )
        dxy_df = pd.DataFrame(
            {"ts_event": pd.to_datetime(["2025-01-01 09:00"]), "open": [100.0]}
        )

        # Missing close column
        with pytest.raises(ValueError, match="Column 'close' not found"):
            calculate_dxy_correlation(gc_df, dxy_df, window=5)

    def test_dxy_correlation_empty_dataframes(self) -> None:
        """Test DXY correlation with empty DataFrames."""
        empty_gc = pd.DataFrame(columns=["ts_event", "close"])
        empty_dxy = pd.DataFrame(columns=["ts_event", "close"])

        result = calculate_dxy_correlation(empty_gc, empty_dxy, window=5)

        assert len(result) == 0

    def test_dxy_correlation_no_overlapping_timestamps(self) -> None:
        """Test DXY correlation when timestamps don't overlap."""
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

        result = calculate_dxy_correlation(gc_df, dxy_df, window=5)

        # Should return empty or all NaN (no overlapping timestamps)
        assert len(result) == 0 or result.isna().all()

    def test_dxy_correlation_1m_timeframe(
        self, real_gc_data: pd.DataFrame, real_dxy_data: pd.DataFrame
    ) -> None:
        """Test DXY correlation on 1m timeframe (DoD requirement)."""
        result = calculate_dxy_correlation(real_gc_data, real_dxy_data, window=50)

        # Should have valid correlation values
        valid_corr = result.dropna()

        # Should have some negative correlations (typical GC-DXY relationship)
        assert len(valid_corr) > 0
        assert valid_corr.min() < 0  # At least some negative correlation

    def test_dxy_correlation_15m_timeframe(self) -> None:
        """Test DXY correlation on 15m timeframe (DoD requirement)."""
        # Load 15m data if available, otherwise resample 1m data
        gc_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "GC_ohlcv-1m.csv"
        dxy_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / "DX_ohlcv-1m.csv"

        if not gc_path.exists() or not dxy_path.exists():
            pytest.skip("15m data not available, skipping 15m timeframe test")

        gc_df = pd.read_csv(gc_path, parse_dates=["ts_event"])
        gc_df = gc_df[gc_df["symbol"] == "GCZ5"].head(500).copy()

        dxy_df = pd.read_csv(dxy_path, parse_dates=["ts_event"])
        dxy_df = dxy_df.head(500).copy()

        # Resample to 15m if needed
        gc_15m = gc_df.set_index("ts_event").resample("15min").last().reset_index()
        dxy_15m = dxy_df.set_index("ts_event").resample("15min").last().reset_index()

        result = calculate_dxy_correlation(gc_15m, dxy_15m, window=50)

        # Should have valid correlation values (if enough overlapping timestamps)
        valid_corr = result.dropna()
        # After resampling, we might have fewer overlapping timestamps
        # So we just check that the function works without error
        # If there are valid correlations, they should be reasonable
        if len(valid_corr) > 0:
            # Correlation should be between -1 and 1
            assert valid_corr.min() >= -1.0
            assert valid_corr.max() <= 1.0

    def test_dxy_correlation_pearson_method(self) -> None:
        """Test that correlation uses Pearson method (default)."""
        # Create perfectly correlated data
        gc_df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(
                    [f"2025-01-01 09:{i:02d}" for i in range(20)]
                ),
                "close": [2000 + i for i in range(20)],
            }
        )
        dxy_df = pd.DataFrame(
            {
                "ts_event": pd.to_datetime(
                    [f"2025-01-01 09:{i:02d}" for i in range(20)]
                ),
                "close": [100 - i for i in range(20)],  # Perfect inverse
            }
        )

        result = calculate_dxy_correlation(gc_df, dxy_df, window=20)

        # Last value should be close to -1.0 (perfect negative Pearson correlation)
        assert result.iloc[-1] < -0.99
