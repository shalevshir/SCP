"""Unit tests for entry model - next bar open execution logic."""

from datetime import UTC, datetime, timedelta

import pytest
from backtester.entry_model import EntryExecution, execute_entry_at_next_open
from common.exceptions import NormalizationError
from common.types import Candle
from rule_engine.signal import Signal


class TestEntryExecution:
    """Tests for EntryExecution dataclass."""

    def test_entry_execution_is_immutable(self):
        """Test that EntryExecution is immutable (frozen dataclass)."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure": 2.0},
            rationale="Test signal",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Attempting to modify should raise an error
        with pytest.raises(AttributeError):
            execution.entry_price = 2700.0


class TestExecuteEntryAtNextOpen:
    """Tests for execute_entry_at_next_open function."""

    @pytest.fixture
    def valid_signal(self):
        """Create a valid A+ signal for testing."""
        return Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0, "vwap_relation": 2.0},
            rationale="HTF HH/HL intact, VWAP reclaim confirmed",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="EarlyMild",
        )

    @pytest.fixture
    def valid_next_candle(self):
        """Create a valid next candle for testing."""
        return Candle(
            timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

    def test_execute_entry_with_valid_next_candle(
        self, valid_signal, valid_next_candle
    ):
        """Test successful entry execution with valid next candle."""
        execution = execute_entry_at_next_open(valid_signal, valid_next_candle)

        assert execution.executed is True
        assert execution.entry_price == valid_next_candle.open
        assert execution.entry_timestamp == valid_next_candle.timestamp
        assert execution.signal_timestamp == valid_signal.timestamp
        assert execution.signal == valid_signal
        assert execution.rejection_reason is None

    def test_execute_entry_with_no_next_candle(self, valid_signal):
        """Test entry rejection when next candle is None (end of dataset)."""
        execution = execute_entry_at_next_open(valid_signal, None)

        assert execution.executed is False
        assert execution.entry_price == 0.0
        assert execution.entry_timestamp == valid_signal.timestamp
        assert execution.signal_timestamp == valid_signal.timestamp
        assert execution.signal == valid_signal
        assert "No next candle available" in execution.rejection_reason

    def test_execute_entry_rejects_reject_confidence(self, valid_next_candle):
        """Test that signals with 'Reject' confidence are not executed."""
        reject_signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="REJECTED",
            htf_bias="neutral",
            score=5.0,
            confidence="Reject",
            factors={},
            rationale="HTF conflict",
            validation_flags={"htf_valid": False},
            enforcer_tier="Conservative",
        )

        execution = execute_entry_at_next_open(reject_signal, valid_next_candle)

        assert execution.executed is False
        assert execution.entry_price == 0.0
        assert "confidence Reject not tradeable" in execution.rejection_reason

    def test_execute_entry_rejects_watch_confidence(self, valid_next_candle):
        """Test that signals with 'Watch' confidence are not executed."""
        watch_signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=7.0,
            confidence="Watch",
            factors={"structure_alignment": 1.5},
            rationale="Marginal setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )

        execution = execute_entry_at_next_open(watch_signal, valid_next_candle)

        assert execution.executed is False
        assert execution.entry_price == 0.0
        assert "confidence Watch not tradeable" in execution.rejection_reason

    @pytest.mark.parametrize("confidence", ["A", "B", "C", "D"])
    def test_execute_entry_rejects_non_aplus_confidence(
        self, confidence, valid_next_candle
    ):
        """Ensure only A+ confidence signals reach execution."""
        downgraded_signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence=confidence,
            factors={"structure_alignment": 1.5},
            rationale="Sub-A+ confidence should be rejected",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        execution = execute_entry_at_next_open(downgraded_signal, valid_next_candle)

        assert execution.executed is False
        assert execution.entry_price == 0.0
        assert f"confidence {confidence} not tradeable" in execution.rejection_reason

    def test_entry_price_matches_next_open_exactly(self, valid_signal):
        """Test that entry price matches next candle open exactly (no slippage)."""
        next_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            open=2651.25,  # Specific price to test exact match
            high=2655.0,
            low=2650.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        execution = execute_entry_at_next_open(valid_signal, next_candle)

        assert execution.entry_price == 2651.25
        assert execution.entry_price == next_candle.open

    def test_entry_handles_invalid_next_candle_open_price(self, valid_signal):
        """Test rejection when next candle has invalid (negative/zero) open price."""
        # We can't create a Candle with invalid open due to validation
        # So this test verifies the Candle validation catches it
        with pytest.raises(NormalizationError):
            Candle(
                timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
                open=-100.0,  # Invalid
                high=2655.0,
                low=2648.0,
                close=2652.0,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )

    def test_entry_execution_is_deterministic(self, valid_signal, valid_next_candle):
        """Test that same inputs produce identical EntryExecution (no randomness)."""
        execution1 = execute_entry_at_next_open(valid_signal, valid_next_candle)
        execution2 = execute_entry_at_next_open(valid_signal, valid_next_candle)

        # All fields should be identical
        assert execution1.signal_timestamp == execution2.signal_timestamp
        assert execution1.entry_timestamp == execution2.entry_timestamp
        assert execution1.entry_price == execution2.entry_price
        assert execution1.executed == execution2.executed
        assert execution1.rejection_reason == execution2.rejection_reason
        assert execution1.signal == execution2.signal

    def test_entry_with_different_timeframes(self, valid_signal):
        """Test entry works correctly with different timeframes."""
        # 5m timeframe
        next_candle_5m = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2660.0,
            low=2645.0,
            close=2655.0,
            volume=5000.0,
            symbol="GC",
            timeframe="5m",
            source="TEST",
        )

        execution = execute_entry_at_next_open(valid_signal, next_candle_5m)

        assert execution.executed is True
        assert execution.entry_price == 2650.0
        assert execution.entry_timestamp == next_candle_5m.timestamp

    def test_entry_timestamp_delta(self, valid_signal, valid_next_candle):
        """Test that entry timestamp is after signal timestamp."""
        execution = execute_entry_at_next_open(valid_signal, valid_next_candle)

        time_delta = execution.entry_timestamp - execution.signal_timestamp
        assert time_delta > timedelta(0)
        assert time_delta == timedelta(minutes=1)

    def test_signal_reference_preserved(self, valid_signal, valid_next_candle):
        """Test that original signal is preserved in execution for traceability."""
        execution = execute_entry_at_next_open(valid_signal, valid_next_candle)

        # Verify all signal attributes are accessible through execution
        assert execution.signal.direction == "long"
        assert execution.signal.setup_type == "VWAP_RECLAIM"
        assert execution.signal.score == 9.0
        assert execution.signal.confidence == "A+"
