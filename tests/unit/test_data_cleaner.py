"""
Tests for data CSV cleaning script.

Following TDD: These tests define the behavior we need:
1. Remove spread instruments (e.g., "GC-DX")
2. Filter only GC or DX instruments
3. Keep only highest volume contract per minute
4. Remove duplicate timestamps
"""


import pandas as pd
from scripts.clean_csv_data import (
    clean_csv_data,
    filter_primary_instruments,
    is_spread_instrument,
    select_highest_volume_per_minute,
)


class TestSpreadDetection:
    """Test detection and filtering of spread instruments."""

    def test_identifies_spread_instrument_with_dash(self):
        """Spread instruments contain dashes like GC-DX."""
        assert is_spread_instrument("GC-DX") is True
        assert is_spread_instrument("GCZ4-GCF5") is True

    def test_identifies_regular_instrument(self):
        """Regular instruments don't have dashes."""
        assert is_spread_instrument("GCZ24") is False
        assert is_spread_instrument("DXZ24") is False

    def test_identifies_spread_with_multiple_dashes(self):
        """Complex spread instruments."""
        assert is_spread_instrument("GC-DX-SI") is True


class TestInstrumentFiltering:
    """Test filtering to keep only GC or DX instruments."""

    def test_keeps_gc_instruments(self):
        """Should keep instruments starting with GC."""
        df = pd.DataFrame(
            {
                "symbol": ["GCZ24", "GCF25", "SIZ24", "DXZ24"],
                "volume": [100, 200, 150, 300],
            }
        )
        result = filter_primary_instruments(df, prefix="GC")
        assert len(result) == 2
        assert all(result["symbol"].str.startswith("GC"))

    def test_keeps_dx_instruments(self):
        """Should keep instruments starting with DX."""
        df = pd.DataFrame(
            {
                "symbol": ["GCZ24", "GCF25", "SIZ24", "DXZ24", "DXF25"],
                "volume": [100, 200, 150, 300, 250],
            }
        )
        result = filter_primary_instruments(df, prefix="DX")
        assert len(result) == 2
        assert all(result["symbol"].str.startswith("DX"))

    def test_removes_spread_instruments(self):
        """Should remove spread instruments even if they start with GC/DX."""
        df = pd.DataFrame(
            {
                "symbol": ["GCZ24", "GC-DX", "DXZ24", "GCZ24-GCF25"],
                "volume": [100, 200, 300, 150],
            }
        )
        result = filter_primary_instruments(df, prefix="GC")
        assert len(result) == 1
        assert "GC-DX" not in result["symbol"].values
        assert "GCZ24-GCF25" not in result["symbol"].values
        assert "GCZ24" in result["symbol"].values

    def test_case_insensitive_prefix_matching(self):
        """Prefix matching should be case-insensitive."""
        df = pd.DataFrame(
            {
                "symbol": ["gcz24", "GCZ24", "Gcf25"],
                "volume": [100, 200, 150],
            }
        )
        result = filter_primary_instruments(df, prefix="GC")
        assert len(result) == 3


class TestVolumeSelection:
    """Test selection of highest volume contract per minute."""

    def test_selects_highest_volume_per_timestamp(self):
        """Should keep only the row with highest volume for each timestamp."""
        df = pd.DataFrame(
            {
                "ts_event": [
                    "2025-01-01 10:00:00",
                    "2025-01-01 10:00:00",
                    "2025-01-01 10:01:00",
                ],
                "symbol": ["GCZ24", "GCF25", "GCZ24"],
                "volume": [100, 300, 150],
                "open": [2000.0, 2001.0, 2002.0],
                "high": [2005.0, 2006.0, 2007.0],
                "low": [1995.0, 1996.0, 1997.0],
                "close": [2002.0, 2003.0, 2004.0],
            }
        )
        result = select_highest_volume_per_minute(df)

        # Should have 2 rows (one per unique timestamp)
        assert len(result) == 2

        # First timestamp should have GCF25 (volume 300)
        first_row = result[result["ts_event"] == "2025-01-01 10:00:00"].iloc[0]
        assert first_row["symbol"] == "GCF25"
        assert first_row["volume"] == 300

        # Second timestamp should have GCZ24 (volume 150)
        second_row = result[result["ts_event"] == "2025-01-01 10:01:00"].iloc[0]
        assert second_row["symbol"] == "GCZ24"
        assert second_row["volume"] == 150

    def test_preserves_all_ohlcv_columns(self):
        """Should preserve all OHLCV data when selecting highest volume."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00", "2025-01-01 10:00:00"],
                "symbol": ["GCZ24", "GCF25"],
                "open": [2000.0, 2001.0],
                "high": [2005.0, 2006.0],
                "low": [1995.0, 1996.0],
                "close": [2002.0, 2003.0],
                "volume": [100, 300],
            }
        )
        result = select_highest_volume_per_minute(df)

        assert len(result) == 1
        row = result.iloc[0]
        assert row["symbol"] == "GCF25"
        assert row["open"] == 2001.0
        assert row["high"] == 2006.0
        assert row["low"] == 1996.0
        assert row["close"] == 2003.0
        assert row["volume"] == 300

    def test_handles_single_contract_per_minute(self):
        """Should handle case where each minute has only one contract."""
        df = pd.DataFrame(
            {
                "ts_event": [
                    "2025-01-01 10:00:00",
                    "2025-01-01 10:01:00",
                    "2025-01-01 10:02:00",
                ],
                "symbol": ["GCZ24", "GCZ24", "GCZ24"],
                "volume": [100, 150, 200],
                "open": [2000.0, 2001.0, 2002.0],
                "high": [2005.0, 2006.0, 2007.0],
                "low": [1995.0, 1996.0, 1997.0],
                "close": [2002.0, 2003.0, 2004.0],
            }
        )
        result = select_highest_volume_per_minute(df)
        assert len(result) == 3

    def test_removes_duplicate_timestamps_after_filtering(self):
        """After selecting highest volume, no duplicate timestamps should remain."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00"] * 5,
                "symbol": ["GCZ24", "GCF25", "GCM25", "GCU25", "GCZ25"],
                "volume": [100, 500, 200, 150, 300],
                "open": [2000.0] * 5,
                "high": [2005.0] * 5,
                "low": [1995.0] * 5,
                "close": [2002.0] * 5,
            }
        )
        result = select_highest_volume_per_minute(df)

        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "GCF25"  # Highest volume (500)
        assert result["ts_event"].nunique() == 1

    def test_skips_highest_volume_if_has_negative_ohlc(self):
        """Should skip highest volume row if it has negative OHLC values."""
        df = pd.DataFrame(
            {
                "ts_event": [
                    "2025-01-01 10:00:00",
                    "2025-01-01 10:00:00",
                    "2025-01-01 10:00:00",
                ],
                "symbol": ["GCZ24", "GCF25", "GCM25"],
                "volume": [100, 500, 200],  # GCF25 has highest volume
                "open": [2000.0, -1.0, 2002.0],  # But GCF25 has negative open
                "high": [2005.0, 2006.0, 2007.0],
                "low": [1995.0, 1996.0, 1997.0],
                "close": [2002.0, 2003.0, 2004.0],
            }
        )
        result = select_highest_volume_per_minute(df)

        # Should select GCM25 (volume 200, second highest with valid OHLC)
        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "GCM25"
        assert result.iloc[0]["volume"] == 200

    def test_skips_highest_volume_if_has_negative_high(self):
        """Should skip if high is negative."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00", "2025-01-01 10:00:00"],
                "symbol": ["GCZ24", "GCF25"],
                "volume": [100, 500],
                "open": [2000.0, 2001.0],
                "high": [2005.0, -1.0],  # Negative high
                "low": [1995.0, 1996.0],
                "close": [2002.0, 2003.0],
            }
        )
        result = select_highest_volume_per_minute(df)
        assert result.iloc[0]["symbol"] == "GCZ24"

    def test_skips_highest_volume_if_has_negative_low(self):
        """Should skip if low is negative."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00", "2025-01-01 10:00:00"],
                "symbol": ["GCZ24", "GCF25"],
                "volume": [100, 500],
                "open": [2000.0, 2001.0],
                "high": [2005.0, 2006.0],
                "low": [1995.0, -1.0],  # Negative low
                "close": [2002.0, 2003.0],
            }
        )
        result = select_highest_volume_per_minute(df)
        assert result.iloc[0]["symbol"] == "GCZ24"

    def test_skips_highest_volume_if_has_negative_close(self):
        """Should skip if close is negative."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00", "2025-01-01 10:00:00"],
                "symbol": ["GCZ24", "GCF25"],
                "volume": [100, 500],
                "open": [2000.0, 2001.0],
                "high": [2005.0, 2006.0],
                "low": [1995.0, 1996.0],
                "close": [2002.0, -1.0],  # Negative close
            }
        )
        result = select_highest_volume_per_minute(df)
        assert result.iloc[0]["symbol"] == "GCZ24"

    def test_skips_all_invalid_rows_until_finding_valid(self):
        """Should skip multiple invalid rows to find first valid one."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00"] * 4,
                "symbol": ["GCZ24", "GCF25", "GCM25", "GCU25"],
                "volume": [50, 500, 300, 200],  # Descending by volume
                "open": [2000.0, -1.0, -1.0, 2003.0],  # First two highest are invalid
                "high": [2005.0, 2006.0, 2007.0, 2008.0],
                "low": [1995.0, 1996.0, 1997.0, 1998.0],
                "close": [2002.0, 2003.0, 2004.0, 2005.0],
            }
        )
        result = select_highest_volume_per_minute(df)

        # Should select GCU25 (volume 200, highest valid)
        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "GCU25"
        assert result.iloc[0]["volume"] == 200

    def test_returns_empty_if_all_rows_have_negative_values(self):
        """Should return empty if no valid rows exist."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00", "2025-01-01 10:00:00"],
                "symbol": ["GCZ24", "GCF25"],
                "volume": [100, 500],
                "open": [-1.0, -2.0],  # All invalid
                "high": [2005.0, 2006.0],
                "low": [1995.0, 1996.0],
                "close": [2002.0, 2003.0],
            }
        )
        result = select_highest_volume_per_minute(df)

        # Should return empty DataFrame for this timestamp
        assert len(result) == 0

    def test_skips_highest_volume_if_has_zero_open(self):
        """Should skip rows with zero OHLC values (also invalid)."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00", "2025-01-01 10:00:00"],
                "symbol": ["GCZ24", "GCF25"],
                "volume": [100, 500],
                "open": [2000.0, 0.0],  # Zero is invalid
                "high": [2005.0, 2006.0],
                "low": [1995.0, 1996.0],
                "close": [2002.0, 2003.0],
            }
        )
        result = select_highest_volume_per_minute(df)
        assert result.iloc[0]["symbol"] == "GCZ24"

    def test_skips_all_zero_ohlc_values(self):
        """Should skip rows where all OHLC values are zero."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00", "2025-01-01 10:00:00"],
                "symbol": ["GCZ24", "GCF25"],
                "volume": [100, 500],
                "open": [2000.0, 0.0],
                "high": [2005.0, 0.0],
                "low": [1995.0, 0.0],
                "close": [2002.0, 0.0],
            }
        )
        result = select_highest_volume_per_minute(df)
        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "GCZ24"


class TestEndToEndCleaning:
    """Test the complete cleaning pipeline."""

    def test_cleans_gc_data_end_to_end(self):
        """Complete pipeline: filter GC, remove spreads, select highest volume, normalize symbol."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00"] * 4 + ["2025-01-01 10:01:00"] * 2,
                "symbol": ["GCZ24", "GCF25", "GC-DX", "DXZ24", "GCZ24", "SIZ24"],
                "open": [2000.0, 2001.0, 2002.0, 95.0, 2003.0, 25.0],
                "high": [2005.0, 2006.0, 2007.0, 96.0, 2008.0, 26.0],
                "low": [1995.0, 1996.0, 1997.0, 94.0, 1998.0, 24.0],
                "close": [2002.0, 2003.0, 2004.0, 95.5, 2005.0, 25.5],
                "volume": [100, 500, 200, 300, 150, 100],
            }
        )

        result = clean_csv_data(df, instrument_prefix="GC")

        # Should have 2 rows (one per unique timestamp)
        assert len(result) == 2

        # All symbols should be normalized to "GC"
        assert all(result["symbol"] == "GC")

        # First timestamp should have GCF25's data (volume 500, highest among GC)
        first_row = result[result["ts_event"] == "2025-01-01 10:00:00"].iloc[0]
        assert first_row["symbol"] == "GC"
        assert first_row["volume"] == 500

        # Second timestamp should have GCZ24's data (only GC instrument)
        second_row = result[result["ts_event"] == "2025-01-01 10:01:00"].iloc[0]
        assert second_row["symbol"] == "GC"
        assert second_row["volume"] == 150

    def test_cleans_dx_data_end_to_end(self):
        """Complete pipeline for DX data with symbol normalization."""
        df = pd.DataFrame(
            {
                "ts_event": ["2025-01-01 10:00:00"] * 3,
                "symbol": ["DXZ24", "DXF25", "DX-GC"],
                "open": [95.0, 95.5, 96.0],
                "high": [96.0, 96.5, 97.0],
                "low": [94.0, 94.5, 95.0],
                "close": [95.5, 96.0, 96.5],
                "volume": [100, 300, 200],
            }
        )

        result = clean_csv_data(df, instrument_prefix="DX")

        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "DX"  # Normalized to "DX"
        assert result.iloc[0]["volume"] == 300

    def test_handles_empty_dataframe(self):
        """Should handle empty input gracefully."""
        df = pd.DataFrame(
            columns=["ts_event", "symbol", "open", "high", "low", "close", "volume"]
        )
        result = clean_csv_data(df, instrument_prefix="GC")
        assert len(result) == 0

    def test_sorts_by_timestamp(self):
        """Output should be sorted by timestamp with normalized symbols."""
        df = pd.DataFrame(
            {
                "ts_event": [
                    "2025-01-01 10:02:00",
                    "2025-01-01 10:00:00",
                    "2025-01-01 10:01:00",
                ],
                "symbol": ["GCZ24", "GCZ24", "GCZ24"],
                "open": [2000.0, 2001.0, 2002.0],
                "high": [2005.0, 2006.0, 2007.0],
                "low": [1995.0, 1996.0, 1997.0],
                "close": [2002.0, 2003.0, 2004.0],
                "volume": [100, 150, 200],
            }
        )

        result = clean_csv_data(df, instrument_prefix="GC")

        timestamps = result["ts_event"].tolist()
        assert timestamps == sorted(timestamps)

        # All symbols should be normalized
        assert all(result["symbol"] == "GC")
