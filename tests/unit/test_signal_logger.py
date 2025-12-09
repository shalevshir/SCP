"""Unit tests for Signal logger.

Tests JSON logging of signals to files for auditability and analysis.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from rule_engine.signal import Signal
from rule_engine.signal_logger import log_signal, signal_to_dict


class TestSignalToDict:
    """Test Signal to dictionary conversion."""

    def test_signal_to_dict_structure(self) -> None:
        """Test that signal converts to proper dict structure."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test rationale",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="Early Mild",
        )

        signal_dict = signal_to_dict(signal)

        assert isinstance(signal_dict, dict)
        assert signal_dict["symbol"] == "GC"
        assert signal_dict["timeframe"] == "1m"
        assert signal_dict["direction"] == "long"
        assert signal_dict["setup_type"] == "VWAP_RECLAIM"
        assert signal_dict["score"] == 9.0
        assert signal_dict["confidence"] == "A+"
        assert "factors" in signal_dict
        assert "validation_flags" in signal_dict

    def test_signal_to_dict_timestamp_serialization(self) -> None:
        """Test that timestamp is serialized to ISO format string."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 30, 45, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="Early Mild",
        )

        signal_dict = signal_to_dict(signal)

        assert "timestamp" in signal_dict
        assert isinstance(signal_dict["timestamp"], str)
        assert signal_dict["timestamp"] == "2025-01-01T10:30:45+00:00"

    def test_signal_to_dict_json_serializable(self) -> None:
        """Test that resulting dict is JSON serializable."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="Early Mild",
        )

        signal_dict = signal_to_dict(signal)

        # Should not raise
        json_str = json.dumps(signal_dict)
        assert isinstance(json_str, str)


class TestLogSignal:
    """Test signal logging to JSONL files."""

    def test_log_signal_creates_file(self, tmp_path: Path) -> None:
        """Test that log_signal creates the log file."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="Early Mild",
        )

        log_dir = tmp_path / "logs" / "signals"
        log_signal(signal, log_dir=str(log_dir))

        # Check file was created
        expected_file = log_dir / "2025-01-01.jsonl"
        assert expected_file.exists()

    def test_log_signal_writes_jsonl_format(self, tmp_path: Path) -> None:
        """Test that signals are written in JSONL format (one JSON per line)."""
        signals = [
            Signal(
                timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                direction="long",
                setup_type="VWAP_RECLAIM",
                htf_bias="bullish",
                score=9.0,
                confidence="A+",
                factors={},
                rationale="First signal",
                validation_flags={},
                enforcer_tier="Early Mild",
            ),
            Signal(
                timestamp=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                direction="short",
                setup_type="VWAP_FADE",
                htf_bias="bearish",
                score=8.0,
                confidence="A+",
                factors={},
                rationale="Second signal",
                validation_flags={},
                enforcer_tier="Mild",
            ),
        ]

        log_dir = tmp_path / "logs" / "signals"
        for signal in signals:
            log_signal(signal, log_dir=str(log_dir))

        # Read file and verify JSONL format
        log_file = log_dir / "2025-01-01.jsonl"
        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 2

        # Each line should be valid JSON
        for line in lines:
            signal_data = json.loads(line)
            assert "symbol" in signal_data
            assert "timestamp" in signal_data

    def test_log_signal_appends_to_existing_file(self, tmp_path: Path) -> None:
        """Test that logging appends to existing file instead of overwriting."""
        signal1 = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="First",
            validation_flags={},
            enforcer_tier="Early Mild",
        )

        signal2 = Signal(
            timestamp=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=8.0,
            confidence="A+",
            factors={},
            rationale="Second",
            validation_flags={},
            enforcer_tier="Mild",
        )

        log_dir = tmp_path / "logs" / "signals"

        log_signal(signal1, log_dir=str(log_dir))
        log_signal(signal2, log_dir=str(log_dir))

        # Check both signals are in the file
        log_file = log_dir / "2025-01-01.jsonl"
        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 2

    def test_log_signal_creates_separate_files_per_day(self, tmp_path: Path) -> None:
        """Test that signals from different days go to separate files."""
        signal1 = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Day 1",
            validation_flags={},
            enforcer_tier="Early Mild",
        )

        signal2 = Signal(
            timestamp=datetime(2025, 1, 2, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.0,
            confidence="A+",
            factors={},
            rationale="Day 2",
            validation_flags={},
            enforcer_tier="Early Mild",
        )

        log_dir = tmp_path / "logs" / "signals"

        log_signal(signal1, log_dir=str(log_dir))
        log_signal(signal2, log_dir=str(log_dir))

        # Check separate files exist
        file1 = log_dir / "2025-01-01.jsonl"
        file2 = log_dir / "2025-01-02.jsonl"

        assert file1.exists()
        assert file2.exists()

        # Each file should have one signal
        with open(file1) as f:
            assert len(f.readlines()) == 1

        with open(file2) as f:
            assert len(f.readlines()) == 1

    def test_log_signal_preserves_all_data(self, tmp_path: Path) -> None:
        """Test that all signal data is preserved in the log."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Complete signal test",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="Early Mild",
        )

        log_dir = tmp_path / "logs" / "signals"
        log_signal(signal, log_dir=str(log_dir))

        # Read back and verify all data
        log_file = log_dir / "2025-01-01.jsonl"
        with open(log_file) as f:
            logged_data = json.loads(f.read())

        assert logged_data["symbol"] == "GC"
        assert logged_data["direction"] == "long"
        assert logged_data["score"] == 9.0
        assert logged_data["confidence"] == "A+"
        assert logged_data["rationale"] == "Complete signal test"
        assert "structure_alignment" in logged_data["factors"]
        assert "session_ok" in logged_data["validation_flags"]
