"""Unit tests for HTF VWAP calculator module."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from scp_shared.rule_engine.htf.vwap.calculator import calculate_htf_vwap


def create_ohlcv_dataframe(num_bars: int = 10) -> pd.DataFrame:
    """Create a test OHLCV DataFrame."""
    base_time = datetime(2024, 1, 1, 9, 0, 0)

    data = {
        "ts_event": [base_time + timedelta(hours=i) for i in range(num_bars)],
        "open": [100 + i * 0.5 for i in range(num_bars)],
        "high": [101 + i * 0.5 for i in range(num_bars)],
        "low": [99 + i * 0.5 for i in range(num_bars)],
        "close": [100.5 + i * 0.5 for i in range(num_bars)],
        "volume": [1000 + i * 100 for i in range(num_bars)],
    }

    return pd.DataFrame(data)


class TestCalculateHTFVWAP:
    """Tests for calculate_htf_vwap function."""

    def test_calculates_vwap(self) -> None:
        """Calculates VWAP column."""
        df = create_ohlcv_dataframe(10)

        result = calculate_htf_vwap(df)

        assert "vwap" in result.columns
        assert not result["vwap"].isna().all()

    def test_calculates_vwap_distance(self) -> None:
        """Calculates vwap_distance column."""
        df = create_ohlcv_dataframe(10)

        result = calculate_htf_vwap(df)

        assert "vwap_distance" in result.columns
        # vwap_distance = close - vwap
        expected = result["close"] - result["vwap"]
        pd.testing.assert_series_equal(
            result["vwap_distance"], expected, check_names=False
        )

    def test_calculates_vwap_slope(self) -> None:
        """Calculates vwap_slope column."""
        df = create_ohlcv_dataframe(10)

        result = calculate_htf_vwap(df)

        assert "vwap_slope" in result.columns
        # First value should be NaN (no prior bar)
        assert pd.isna(result["vwap_slope"].iloc[0])
        # Subsequent values should be diff of VWAP
        assert not result["vwap_slope"].iloc[1:].isna().all()

    def test_preserves_original_columns(self) -> None:
        """Preserves all original columns."""
        df = create_ohlcv_dataframe(10)
        original_cols = set(df.columns)

        result = calculate_htf_vwap(df)

        for col in original_cols:
            assert col in result.columns

    def test_raises_on_empty_dataframe(self) -> None:
        """Raises ValueError for empty DataFrame."""
        df = pd.DataFrame(columns=["ts_event", "high", "low", "close", "volume"])

        with pytest.raises(ValueError, match="DataFrame is empty"):
            calculate_htf_vwap(df)

    def test_raises_on_missing_columns(self) -> None:
        """Raises ValueError for missing required columns."""
        df = pd.DataFrame(
            {
                "ts_event": [datetime.now()],
                "close": [100],
            }
        )

        with pytest.raises(ValueError, match="Missing required columns"):
            calculate_htf_vwap(df)

    def test_does_not_modify_original(self) -> None:
        """Does not modify the original DataFrame."""
        df = create_ohlcv_dataframe(5)
        original_cols = list(df.columns)

        result = calculate_htf_vwap(df)

        # Original should be unchanged
        assert list(df.columns) == original_cols
        assert "vwap" not in df.columns

    def test_handles_single_bar(self) -> None:
        """Handles DataFrame with single bar."""
        df = pd.DataFrame(
            {
                "ts_event": [datetime(2024, 1, 1, 9, 0)],
                "open": [100],
                "high": [101],
                "low": [99],
                "close": [100.5],
                "volume": [1000],
            }
        )

        result = calculate_htf_vwap(df)

        assert len(result) == 1
        assert "vwap" in result.columns
        assert "vwap_distance" in result.columns
        assert "vwap_slope" in result.columns
