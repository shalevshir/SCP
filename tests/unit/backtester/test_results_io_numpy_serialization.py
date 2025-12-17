"""Test numpy type serialization in results I/O.

This test ensures that numpy types (bool_, int64, float64, etc.) are properly
converted to native Python types before JSON serialization.
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from backtester.results_io import convert_numpy_types, save_results
from backtester.replay_loop import BacktestResults
from backtester.entry_model import EntryExecution
from rule_engine.signal import Signal


class TestNumpyTypeSerialization:
    """Test that numpy types are properly converted for JSON serialization."""

    def test_convert_numpy_bool(self):
        """numpy bool_ should convert to native Python bool."""
        result = convert_numpy_types(np.bool_(True))
        assert result is True
        assert type(result) is bool

        result = convert_numpy_types(np.bool_(False))
        assert result is False
        assert type(result) is bool

    def test_convert_numpy_int(self):
        """numpy integer types should convert to native Python int."""
        result = convert_numpy_types(np.int64(42))
        assert result == 42
        assert type(result) is int

        result = convert_numpy_types(np.int32(100))
        assert result == 100
        assert type(result) is int

    def test_convert_numpy_float(self):
        """numpy float types should convert to native Python float."""
        result = convert_numpy_types(np.float64(3.14))
        assert result == 3.14
        assert type(result) is float

        result = convert_numpy_types(np.float32(2.71))
        assert abs(result - 2.71) < 0.01
        assert type(result) is float

    def test_convert_dict_with_numpy_types(self):
        """Dictionaries containing numpy types should be recursively converted."""
        data = {
            "bool_field": np.bool_(True),
            "int_field": np.int64(42),
            "float_field": np.float64(3.14),
            "str_field": "unchanged",
            "nested": {
                "nested_bool": np.bool_(False),
                "nested_int": np.int32(100),
            },
        }

        result = convert_numpy_types(data)

        assert type(result["bool_field"]) is bool
        assert type(result["int_field"]) is int
        assert type(result["float_field"]) is float
        assert type(result["str_field"]) is str
        assert type(result["nested"]["nested_bool"]) is bool
        assert type(result["nested"]["nested_int"]) is int

    def test_convert_list_with_numpy_types(self):
        """Lists containing numpy types should be recursively converted."""
        data = [
            np.bool_(True),
            np.int64(42),
            np.float64(3.14),
            {"nested_bool": np.bool_(False)},
        ]

        result = convert_numpy_types(data)

        assert type(result[0]) is bool
        assert type(result[1]) is int
        assert type(result[2]) is float
        assert type(result[3]["nested_bool"]) is bool

    def test_save_results_with_numpy_types(self, tmp_path: Path):
        """save_results should handle numpy types in validation_flags and other fields."""
        # Create a signal with numpy types in validation_flags (common from pandas)
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0),
            symbol="GC",
            timeframe="5m",
            direction="long",
            setup_type="vwap_fade",
            htf_bias="bullish",
            score=8.5,
            confidence=0.85,
            factors={"structure": 3.0, "vwap": 2.5},
            rationale="Test signal",
            validation_flags={
                "chop_detected": np.bool_(True),  # numpy bool from pandas
                "htf_aligned": np.bool_(False),
                "structure_count": np.int64(2),
                "vwap_distance": np.float64(0.5),
            },
            enforcer_tier="early_mild",
            diagnostics={},
        )

        execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0),
            entry_timestamp=datetime(2025, 1, 1, 10, 1),
            entry_price=2000.0,
            signal=signal,
            executed=np.bool_(True),  # numpy bool
            rejection_reason=None,
        )

        results = BacktestResults(
            trades=[],
            executions=[execution],
            total_pnl=0.0,
            total_pnl_dollars=None,
            win_rate=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            average_r=0.0,
            max_consecutive_losses=0,
            pdll_hits=0,
            session_resets=0,
        )

        output_file = tmp_path / "test_results.json"

        # This should NOT raise a TypeError about numpy types
        save_results(results, output_file)

        # Verify the file was created and is valid JSON
        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)

        # Verify numpy types were converted
        exec_data = data["executions"][0]
        assert type(exec_data["executed"]) is bool
        assert type(exec_data["signal"]["validation_flags"]["chop_detected"]) is bool
        assert type(exec_data["signal"]["validation_flags"]["htf_aligned"]) is bool
        assert type(exec_data["signal"]["validation_flags"]["structure_count"]) is int
        assert type(exec_data["signal"]["validation_flags"]["vwap_distance"]) is float

