"""Test for BOS index type bug fix.

This test verifies that compute_htf_bias correctly converts BOS index labels
(Timestamps) to integer positions when calling compute_htf_range.

Bug: bos_index obtained via bos_detected_bars.index[-1] returns a Timestamp,
but compute_htf_range expects an integer position.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from scp_shared.rule_engine.htf.calculator import compute_htf_bias
from scp_shared.rule_engine.htf.types import HTFBias


class TestBOSIndexTypeConversion:
    """Test that BOS index is correctly converted from Timestamp to integer position."""

    def test_bos_index_with_datetime_index_calls_compute_htf_range(self) -> None:
        """Test that BOS index is converted to integer position for compute_htf_range.

        This test reproduces the bug where bos_detected_bars.index[-1] returns
        a Timestamp, causing TypeError in compute_htf_range when it tries to
        compare the Timestamp to len(df) or use it with .iloc[].

        Expected: compute_htf_bias should convert the Timestamp to an integer
        position before passing to compute_htf_range.
        """
        # Create DataFrame with DatetimeIndex (real-world scenario)
        timestamps = [datetime(2024, 1, 1, i) for i in range(10, 20)]
        df_1h = pd.DataFrame(
            {
                "timestamp": timestamps,
                "high": [2100, 2110, 2120, 2130, 2140, 2130, 2120, 2110, 2100, 2090],
                "low": [2090, 2100, 2110, 2120, 2130, 2120, 2110, 2100, 2090, 2080],
                "close": [2095, 2105, 2115, 2125, 2135, 2125, 2115, 2105, 2095, 2085],
                "vwap": [2092, 2102, 2112, 2122, 2132, 2122, 2112, 2102, 2092, 2082],
                # BOS detected at index 5 (timestamp 2024-01-01 15:00:00)
                "bos": [
                    None,
                    None,
                    None,
                    None,
                    None,
                    "bullish_bos",
                    None,
                    None,
                    None,
                    None,
                ],
            }
        )
        df_1h = df_1h.set_index("timestamp")

        # Create features for last bar
        features_1h = pd.Series(
            {
                "close": 2085.0,
                "structure_label": "HH",
                "ema_9": 2090.0,
                "ema_20": 2095.0,
                "ema_50": 2100.0,
                "vwap": 2082.0,
            }
        )

        features_15m = pd.Series(
            {
                "close": 2085.0,
                "structure_label": "HH",
            }
        )

        # This should NOT raise TypeError
        # Bug: bos_index would be pd.Timestamp("2024-01-01 15:00:00") instead of int(5)
        # causing TypeError: '>=' not supported between 'Timestamp' and 'int'
        result = compute_htf_bias(
            features_1h=features_1h,
            features_15m=features_15m,
            df_1h=df_1h,
            timestamp=timestamps[-1],
        )

        # Verify result is valid HTFBias object
        assert isinstance(result, HTFBias)
        # If we got here without TypeError, the bug is fixed
        # HTF range should be computed from BOS onwards (index 5 to end)
        # Range high should be 2140 (max high from index 5+)
        # Range low should be 2080 (min low from index 5+)
        assert result.htf_range_high is not None or result.htf_range_low is not None

    def test_bos_index_none_when_no_bos_detected(self) -> None:
        """Test that bos_index is None when no BOS is detected.

        This is the existing behavior - just ensuring we don't break it.
        """
        timestamps = [datetime(2024, 1, 1, i) for i in range(10, 15)]
        df_1h = pd.DataFrame(
            {
                "timestamp": timestamps,
                "high": [2100, 2110, 2120, 2130, 2140],
                "low": [2090, 2100, 2110, 2120, 2130],
                "close": [2095, 2105, 2115, 2125, 2135],
                "vwap": [2092, 2102, 2112, 2122, 2132],
                # No BOS detected
                "bos": [None, None, None, None, None],
            }
        )
        df_1h = df_1h.set_index("timestamp")

        features_1h = pd.Series(
            {
                "close": 2135.0,
                "structure_label": "HH",
                "ema_9": 2130.0,
                "ema_20": 2125.0,
                "ema_50": 2120.0,
                "vwap": 2132.0,
            }
        )

        features_15m = pd.Series(
            {
                "close": 2135.0,
                "structure_label": "HH",
            }
        )

        result = compute_htf_bias(
            features_1h=features_1h,
            features_15m=features_15m,
            df_1h=df_1h,
            timestamp=timestamps[-1],
        )

        assert isinstance(result, HTFBias)
        # When no BOS, bos_index should be None, and compute_htf_range uses entire df
        # This should work without errors

    def test_bos_index_with_integer_index_still_works(self) -> None:
        """Test that integer-based index still works (backwards compatibility).

        Some tests use integer-based indices, ensure we don't break those.
        """
        # DataFrame with default integer index
        df_1h = pd.DataFrame(
            {
                "high": [2100, 2110, 2120, 2130, 2140, 2130, 2120],
                "low": [2090, 2100, 2110, 2120, 2130, 2120, 2110],
                "close": [2095, 2105, 2115, 2125, 2135, 2125, 2115],
                "vwap": [2092, 2102, 2112, 2122, 2132, 2122, 2112],
                "bos": [None, None, None, None, None, "bullish_bos", None],
            }
        )
        # Leave default integer index (0, 1, 2, 3, 4, 5, 6)

        features_1h = pd.Series(
            {
                "close": 2115.0,
                "structure_label": "HH",
                "ema_9": 2120.0,
                "ema_20": 2125.0,
                "ema_50": 2130.0,
                "vwap": 2112.0,
            }
        )

        features_15m = pd.Series(
            {
                "close": 2115.0,
                "structure_label": "HH",
            }
        )

        # This should work (no timestamp, but integer index)
        result = compute_htf_bias(
            features_1h=features_1h,
            features_15m=features_15m,
            df_1h=df_1h,
        )

        assert isinstance(result, HTFBias)
        # Should compute HTF range from BOS onwards (index 5 to end)
