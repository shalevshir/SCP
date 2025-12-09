"""
Integration tests for CSV data cleaning workflow.

Tests the complete pipeline with realistic data scenarios.
"""

from pathlib import Path

import pandas as pd
import pytest
from scripts.clean_csv_data import process_csv_file


class TestIntegrationWorkflow:
    """Test complete workflow with realistic data scenarios."""

    def test_realistic_gc_data_workflow(self, tmp_path: Path):
        """
        Test with realistic Gold futures data including:
        - Multiple contracts (GCZ24, GCF25, GCM25)
        - Spread instruments (GCZ24-GCF25, GC-DX)
        - Other instruments (SIZ24, DXZ24)
        - Varying volumes throughout the day
        """
        # Create realistic sample data
        data = {
            "ts_event": [
                # 10:00 - Multiple GC contracts, one spread, other instruments
                "2025-07-01 10:00:00",
                "2025-07-01 10:00:00",
                "2025-07-01 10:00:00",
                "2025-07-01 10:00:00",
                "2025-07-01 10:00:00",
                "2025-07-01 10:00:00",
                # 10:01 - GCF25 has highest volume
                "2025-07-01 10:01:00",
                "2025-07-01 10:01:00",
                "2025-07-01 10:01:00",
                # 10:02 - GCZ24 has highest volume (roll approaching)
                "2025-07-01 10:02:00",
                "2025-07-01 10:02:00",
                # 10:03 - Only one GC contract
                "2025-07-01 10:03:00",
            ],
            "symbol": [
                # 10:00
                "GCZ24",  # Front month, moderate volume
                "GCF25",  # Next month, highest volume
                "GCM25",  # Further out, low volume
                "GCZ24-GCF25",  # Spread - should be removed
                "GC-DX",  # Spread - should be removed
                "DXZ24",  # Dollar index - should be removed for GC
                # 10:01
                "GCZ24",
                "GCF25",  # Highest
                "SIZ24",  # Silver - should be removed
                # 10:02
                "GCZ24",  # Highest
                "GCF25",
                # 10:03
                "GCZ24",
            ],
            "open": [
                2000.0,
                2001.0,
                2002.0,
                2000.5,
                2003.0,
                95.0,
                2004.0,
                2005.0,
                25.0,
                2006.0,
                2007.0,
                2008.0,
            ],
            "high": [
                2005.0,
                2006.0,
                2007.0,
                2005.5,
                2008.0,
                96.0,
                2009.0,
                2010.0,
                26.0,
                2011.0,
                2012.0,
                2013.0,
            ],
            "low": [
                1995.0,
                1996.0,
                1997.0,
                1995.5,
                1998.0,
                94.0,
                1999.0,
                2000.0,
                24.0,
                2001.0,
                2002.0,
                2003.0,
            ],
            "close": [
                2002.0,
                2003.0,
                2004.0,
                2002.5,
                2005.0,
                95.5,
                2006.0,
                2007.0,
                25.5,
                2008.0,
                2009.0,
                2010.0,
            ],
            "volume": [
                # 10:00 - GCF25 has highest volume (1500)
                800,
                1500,
                200,
                300,
                100,
                500,
                # 10:01 - GCF25 has highest volume (2000)
                1200,
                2000,
                150,
                # 10:02 - GCZ24 has highest volume (2500)
                2500,
                1800,
                # 10:03 - Only GCZ24
                1000,
            ],
        }

        df = pd.DataFrame(data)

        # Save to temporary CSV
        input_file = tmp_path / "glbx_raw.csv"
        output_file = tmp_path / "GC_clean.csv"
        df.to_csv(input_file, index=False)

        # Process the file
        process_csv_file(
            input_path=input_file,
            output_path=output_file,
            instrument_prefix="GC",
        )

        # Load and verify output
        result = pd.read_csv(output_file)

        # Should have 4 rows (one per unique timestamp)
        assert len(result) == 4, f"Expected 4 rows, got {len(result)}"

        # Verify all symbols are normalized to "GC"
        assert all(result["symbol"] == "GC"), "All symbols should be normalized to 'GC'"

        # Verify highest volume selection per timestamp (by checking volume)
        row_1000 = result[result["ts_event"] == "2025-07-01 10:00:00"].iloc[0]
        assert row_1000["symbol"] == "GC"
        assert (
            row_1000["volume"] == 1500
        ), "10:00 should have GCF25's data (volume 1500)"

        row_1001 = result[result["ts_event"] == "2025-07-01 10:01:00"].iloc[0]
        assert row_1001["symbol"] == "GC"
        assert (
            row_1001["volume"] == 2000
        ), "10:01 should have GCF25's data (volume 2000)"

        row_1002 = result[result["ts_event"] == "2025-07-01 10:02:00"].iloc[0]
        assert row_1002["symbol"] == "GC"
        assert (
            row_1002["volume"] == 2500
        ), "10:02 should have GCZ24's data (volume 2500)"

        row_1003 = result[result["ts_event"] == "2025-07-01 10:03:00"].iloc[0]
        assert row_1003["symbol"] == "GC"
        assert (
            row_1003["volume"] == 1000
        ), "10:03 should have GCZ24's data (only contract)"

        # Verify sorted by timestamp
        timestamps = result["ts_event"].tolist()
        assert timestamps == sorted(timestamps), "Output should be sorted by timestamp"

    def test_realistic_dx_data_workflow(self, tmp_path: Path):
        """
        Test with realistic Dollar Index data including:
        - Multiple DX contracts
        - Spread instruments
        - Other instruments
        """
        data = {
            "ts_event": [
                "2025-07-01 10:00:00",
                "2025-07-01 10:00:00",
                "2025-07-01 10:00:00",
                "2025-07-01 10:00:00",
                "2025-07-01 10:01:00",
                "2025-07-01 10:01:00",
            ],
            "symbol": [
                "DXZ24",  # Front month
                "DXF25",  # Next month, highest volume
                "DX-GC",  # Spread - should be removed
                "GCZ24",  # Gold - should be removed for DX
                "DXZ24",  # Highest volume
                "DXF25",
            ],
            "open": [95.0, 95.5, 96.0, 2000.0, 96.5, 97.0],
            "high": [96.0, 96.5, 97.0, 2005.0, 97.5, 98.0],
            "low": [94.0, 94.5, 95.0, 1995.0, 95.5, 96.0],
            "close": [95.5, 96.0, 96.5, 2002.0, 97.0, 97.5],
            "volume": [1000, 2000, 500, 800, 1500, 800],
        }

        df = pd.DataFrame(data)

        # Save to temporary CSV
        input_file = tmp_path / "dxy_raw.csv"
        output_file = tmp_path / "DX_clean.csv"
        df.to_csv(input_file, index=False)

        # Process the file
        process_csv_file(
            input_path=input_file,
            output_path=output_file,
            instrument_prefix="DX",
        )

        # Load and verify output
        result = pd.read_csv(output_file)

        # Should have 2 rows
        assert len(result) == 2

        # Verify all symbols are normalized to "DX"
        assert all(result["symbol"] == "DX")

        # Verify highest volume selection (by checking volume)
        row_1000 = result[result["ts_event"] == "2025-07-01 10:00:00"].iloc[0]
        assert row_1000["symbol"] == "DX"
        assert row_1000["volume"] == 2000

        row_1001 = result[result["ts_event"] == "2025-07-01 10:01:00"].iloc[0]
        assert row_1001["symbol"] == "DX"
        assert row_1001["volume"] == 1500

    def test_handles_case_insensitive_symbols(self, tmp_path: Path):
        """Test that symbol matching is case-insensitive."""
        data = {
            "ts_event": ["2025-07-01 10:00:00"] * 3,
            "symbol": ["gcz24", "GCZ24", "Gcf25"],  # Mixed case
            "open": [2000.0, 2001.0, 2002.0],
            "high": [2005.0, 2006.0, 2007.0],
            "low": [1995.0, 1996.0, 1997.0],
            "close": [2002.0, 2003.0, 2004.0],
            "volume": [100, 500, 200],  # GCZ24 has highest
        }

        df = pd.DataFrame(data)
        input_file = tmp_path / "mixed_case.csv"
        output_file = tmp_path / "output.csv"
        df.to_csv(input_file, index=False)

        process_csv_file(input_file, output_file, "GC")

        result = pd.read_csv(output_file)
        assert len(result) == 1
        assert result.iloc[0]["volume"] == 500  # GCZ24 had highest volume

    def test_preserves_ohlcv_data_integrity(self, tmp_path: Path):
        """Ensure all OHLCV columns are preserved correctly with normalized symbol."""
        data = {
            "ts_event": ["2025-07-01 10:00:00", "2025-07-01 10:00:00"],
            "symbol": ["GCZ24", "GCF25"],
            "open": [2000.12, 2001.34],
            "high": [2005.56, 2006.78],
            "low": [1995.90, 1996.12],
            "close": [2002.34, 2003.56],
            "volume": [100, 500],  # GCF25 wins
        }

        df = pd.DataFrame(data)
        input_file = tmp_path / "input.csv"
        output_file = tmp_path / "output.csv"
        df.to_csv(input_file, index=False)

        process_csv_file(input_file, output_file, "GC")

        result = pd.read_csv(output_file)
        row = result.iloc[0]

        # Verify exact OHLCV values from GCF25 with normalized symbol
        assert row["symbol"] == "GC"  # Normalized
        assert row["open"] == pytest.approx(2001.34)
        assert row["high"] == pytest.approx(2006.78)
        assert row["low"] == pytest.approx(1996.12)
        assert row["close"] == pytest.approx(2003.56)
        assert row["volume"] == 500

    def test_handles_missing_input_file(self, tmp_path: Path):
        """Should raise error for missing input file."""
        input_file = tmp_path / "nonexistent.csv"
        output_file = tmp_path / "output.csv"

        with pytest.raises(FileNotFoundError):
            process_csv_file(input_file, output_file, "GC")

    def test_creates_output_directory_if_needed(self, tmp_path: Path):
        """Should create output directory if it doesn't exist."""
        data = {
            "ts_event": ["2025-07-01 10:00:00"],
            "symbol": ["GCZ24"],
            "open": [2000.0],
            "high": [2005.0],
            "low": [1995.0],
            "close": [2002.0],
            "volume": [100],
        }

        df = pd.DataFrame(data)
        input_file = tmp_path / "input.csv"
        output_file = tmp_path / "nested" / "dir" / "output.csv"
        df.to_csv(input_file, index=False)

        # Output directory doesn't exist yet
        assert not output_file.parent.exists()

        process_csv_file(input_file, output_file, "GC")

        # Should create the directory and file
        assert output_file.exists()
        result = pd.read_csv(output_file)
        assert len(result) == 1
