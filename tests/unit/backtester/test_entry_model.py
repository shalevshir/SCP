"""Unit tests for entry model - next bar open execution logic."""

import json
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
            diagnostics={
                "second_confirmation_satisfied": True,
                "second_confirmation_type": "vwap_hold",
                "second_confirmation_reasons": [],
                "bars_since_reclaim": 1,
            },
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
            diagnostics={
                "second_confirmation_satisfied": True,
                "second_confirmation_type": "vwap_hold",
                "second_confirmation_reasons": ["vwap_hold: price holding above VWAP"],
                "bars_since_reclaim": 2,
            },
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


class TestVwapReclaimDecisionLogging:
    """Tests for _log_vwap_reclaim_decision logging behavior."""

    def test_explicit_false_in_diagnostics_not_overridden_by_validation_flags(
        self, caplog
    ):
        """Test that explicit False in diagnostics is not overridden.
        
        Bug: Using 'or' operator incorrectly evaluates second operand when
        first is False. When diagnostics.get("session_ok") returns False,
        the 'or' evaluates the second operand from validation_flags,
        incorrectly logging the validation_flags value instead of the
        explicit False from diagnostics.
        
        Expected behavior: diagnostics values should take precedence
        regardless of their boolean value when explicitly set.
        """
        # Create signal with explicit False in diagnostics but True in validation_flags
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
            rationale="Test signal with False flags",
            validation_flags={
                "session_ok": True,  # This should NOT override diagnostics
                "tier_ok": True,     # This should NOT override diagnostics
            },
            enforcer_tier="EarlyMild",
            diagnostics={
                "session_ok": False,  # Explicitly False - should be logged
                "tier_ok": False,     # Explicitly False - should be logged
                "second_confirmation_satisfied": True,
                "second_confirmation_type": "vwap_hold",
                "bars_since_reclaim": 2,
                "reclaim_state": "confirmed",
            },
        )
        
        next_candle = Candle(
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
        
        # Execute entry (which triggers _log_vwap_reclaim_decision)
        with caplog.at_level("INFO"):
            execution = execute_entry_at_next_open(signal, next_candle)
        
        # Find the VWAP_RECLAIM_DECISION log entry
        decision_log = None
        for record in caplog.records:
            if "VWAP_RECLAIM_DECISION" in record.message:
                # Extract JSON from log message
                json_str = record.message.split("VWAP_RECLAIM_DECISION: ")[1]
                decision_log = json.loads(json_str)
                break
        
        assert decision_log is not None, "No VWAP_RECLAIM_DECISION log found"
        
        # BUG: These assertions will fail with current code because 'or'
        # operator incorrectly uses validation_flags when diagnostics=False
        assert decision_log["session_ok"] is False, (
            "session_ok should be False from diagnostics, not True from "
            "validation_flags"
        )
        assert decision_log["tier_ok"] is False, (
            "tier_ok should be False from diagnostics, not True from "
            "validation_flags"
        )
        
        # Verify execution still succeeded (flags don't affect execution logic)
        assert execution.executed is True

    def test_validation_flags_used_when_diagnostics_missing_keys(self, caplog):
        """Test validation_flags fallback when keys absent from diagnostics."""
        # Create signal with missing session_ok/tier_ok in diagnostics
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
            rationale="Test signal fallback to validation_flags",
            validation_flags={
                "session_ok": True,
                "tier_ok": False,
            },
            enforcer_tier="EarlyMild",
            diagnostics={
                # session_ok and tier_ok intentionally omitted
                "second_confirmation_satisfied": True,
                "second_confirmation_type": "vwap_hold",
                "bars_since_reclaim": 1,
            },
        )
        
        next_candle = Candle(
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
        
        with caplog.at_level("INFO"):
            execution = execute_entry_at_next_open(signal, next_candle)
        
        # Find the VWAP_RECLAIM_DECISION log entry
        decision_log = None
        for record in caplog.records:
            if "VWAP_RECLAIM_DECISION" in record.message:
                json_str = record.message.split("VWAP_RECLAIM_DECISION: ")[1]
                decision_log = json.loads(json_str)
                break
        
        assert decision_log is not None
        
        # Should use validation_flags as fallback
        assert decision_log["session_ok"] is True
        assert decision_log["tier_ok"] is False
        assert execution.executed is True
