"""Unit tests for VWAP Reclaim execution decision instrumentation.

Tests comprehensive logging and structured decision tracking for VWAP_RECLAIM
execution decisions, ensuring full visibility for debugging.

Following TDD: Tests define expected logging behavior before implementation.
"""

import json
from datetime import UTC, datetime

from backtester.entry_model import execute_entry_at_next_open
from common.types import Candle
from rule_engine.signal import Signal


class TestVWAPReclaimInstrumentation:
    """Test suite for VWAP_RECLAIM execution decision instrumentation."""

    def test_vwap_reclaim_decision_logged_on_execution(self, caplog):
        """VWAP_RECLAIM execution decision should be logged with full context."""
        # Create A+ VWAP_RECLAIM signal with second confirmation
        signal = Signal(
            timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            confidence="A+",
            score=92.0,
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="EarlyMild",
            diagnostics={
                "second_confirmation_satisfied": True,
                "second_confirmation_type": "vwap_hold",
                "bars_since_reclaim": 3,
                "reclaim_state": "confirmed",
            },
        )
        
        next_candle = Candle(
            timestamp=datetime(2024, 11, 1, 10, 1, tzinfo=UTC),
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Execute entry
        with caplog.at_level("INFO"):
            execution = execute_entry_at_next_open(signal, next_candle)
        
        assert execution.executed is True
        
        # Check that VWAP_RECLAIM_DECISION was logged
        decision_logs = [r for r in caplog.records if "VWAP_RECLAIM_DECISION" in r.message]
        assert len(decision_logs) >= 1, "VWAP_RECLAIM_DECISION should be logged"
        
        # Parse the JSON from the log message
        log_message = decision_logs[0].message
        assert "VWAP_RECLAIM_DECISION:" in log_message
        
        # Extract JSON part (after "VWAP_RECLAIM_DECISION: ")
        json_start = log_message.index("{")
        json_str = log_message[json_start:]
        decision_data = json.loads(json_str)
        
        # Verify all required fields are present
        assert "setup_type" in decision_data
        assert decision_data["setup_type"] == "VWAP_RECLAIM"
        assert "reclaim_state" in decision_data
        assert "bars_since_reclaim" in decision_data
        assert decision_data["bars_since_reclaim"] == 3
        assert "score" in decision_data
        assert decision_data["score"] == 92.0
        assert "confirmations" in decision_data
        assert "vwap_hold" in decision_data["confirmations"]
        assert "executed" in decision_data
        assert decision_data["executed"] is True
        assert "rejection_reason" in decision_data
        assert decision_data["rejection_reason"] is None

    def test_vwap_reclaim_decision_logged_on_rejection(self, caplog):
        """VWAP_RECLAIM rejection should be logged with explicit reason."""
        # Create VWAP_RECLAIM signal WITHOUT second confirmation
        signal = Signal(
            timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            confidence="A+",
            score=88.0,
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="EarlyMild",
            diagnostics={
                "second_confirmation_satisfied": False,
                "second_confirmation_type": None,
                "bars_since_reclaim": 1,
                "reclaim_state": "pending",
            },
        )
        
        next_candle = Candle(
            timestamp=datetime(2024, 11, 1, 10, 1, tzinfo=UTC),
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Execute entry
        with caplog.at_level("INFO"):
            execution = execute_entry_at_next_open(signal, next_candle)
        
        assert execution.executed is False
        
        # Check that VWAP_RECLAIM_DECISION was logged
        decision_logs = [r for r in caplog.records if "VWAP_RECLAIM_DECISION" in r.message]
        assert len(decision_logs) >= 1, "VWAP_RECLAIM_DECISION should be logged even for rejections"
        
        # Parse the JSON
        log_message = decision_logs[0].message
        json_start = log_message.index("{")
        json_str = log_message[json_start:]
        decision_data = json.loads(json_str)
        
        # Verify rejection is logged with reason
        assert decision_data["executed"] is False
        assert decision_data["rejection_reason"] is not None
        assert "no second confirmation" in decision_data["rejection_reason"].lower()

    def test_vwap_reclaim_decision_logged_on_expired_state(self, caplog):
        """VWAP_RECLAIM with expired state should be logged with clear reason."""
        # Create VWAP_RECLAIM signal with expired state
        signal = Signal(
            timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            confidence="A+",
            score=85.0,
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="EarlyMild",
            diagnostics={
                "second_confirmation_satisfied": False,
                "second_confirmation_type": "expired",
                "bars_since_reclaim": 12,
                "reclaim_state": "expired",
            },
        )
        
        next_candle = Candle(
            timestamp=datetime(2024, 11, 1, 10, 1, tzinfo=UTC),
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Execute entry
        with caplog.at_level("INFO"):
            execution = execute_entry_at_next_open(signal, next_candle)
        
        assert execution.executed is False
        
        # Check that expired state is logged
        decision_logs = [r for r in caplog.records if "VWAP_RECLAIM_DECISION" in r.message]
        assert len(decision_logs) >= 1
        
        log_message = decision_logs[0].message
        json_start = log_message.index("{")
        json_str = log_message[json_start:]
        decision_data = json.loads(json_str)
        
        assert decision_data["reclaim_state"] == "expired"
        assert decision_data["bars_since_reclaim"] == 12

    def test_log_format_is_grepable(self, caplog):
        """Log format should be grep-able with consistent structure."""
        signal = Signal(
            timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            confidence="A+",
            score=90.0,
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="EarlyMild",
            diagnostics={
                "second_confirmation_satisfied": True,
                "second_confirmation_type": "volume_expansion",
                "bars_since_reclaim": 4,
                "reclaim_state": "confirmed",
            },
        )
        
        next_candle = Candle(
            timestamp=datetime(2024, 11, 1, 10, 1, tzinfo=UTC),
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
            execute_entry_at_next_open(signal, next_candle)
        
        decision_logs = [r for r in caplog.records if "VWAP_RECLAIM_DECISION" in r.message]
        assert len(decision_logs) >= 1
        
        log_message = decision_logs[0].message
        
        # Log should start with consistent prefix
        assert log_message.startswith("VWAP_RECLAIM_DECISION:")
        
        # Log should contain valid JSON after prefix
        json_start = log_message.index("{")
        json_str = log_message[json_start:]
        decision_data = json.loads(json_str)
        
        # All keys should be present for consistent grep patterns
        required_keys = [
            "setup_type", "reclaim_state", "bars_since_reclaim",
            "score", "confirmations", "executed", "rejection_reason"
        ]
        for key in required_keys:
            assert key in decision_data, f"Required key '{key}' missing from log"

    def test_non_vwap_reclaim_signals_not_instrumented(self, caplog):
        """Non-VWAP_RECLAIM signals should not produce VWAP_RECLAIM_DECISION logs."""
        # Create non-VWAP_RECLAIM signal
        signal = Signal(
            timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            confidence="A+",
            score=88.0,
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="EarlyMild",
            diagnostics={},
        )
        
        next_candle = Candle(
            timestamp=datetime(2024, 11, 1, 10, 1, tzinfo=UTC),
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
            execute_entry_at_next_open(signal, next_candle)
        
        # Should NOT have VWAP_RECLAIM_DECISION logs for other setup types
        decision_logs = [r for r in caplog.records if "VWAP_RECLAIM_DECISION" in r.message]
        assert len(decision_logs) == 0, "VWAP_RECLAIM_DECISION should only log for VWAP_RECLAIM signals"

    def test_session_and_tier_info_included_in_log(self, caplog):
        """Execution decision log should include session and tier context."""
        signal = Signal(
            timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            confidence="A+",
            score=91.0,
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="EarlyMild",
            diagnostics={
                "second_confirmation_satisfied": True,
                "second_confirmation_type": "micro_hl",
                "bars_since_reclaim": 5,
                "reclaim_state": "confirmed",
                "session_ok": True,
                "tier_ok": True,
            },
        )
        
        next_candle = Candle(
            timestamp=datetime(2024, 11, 1, 10, 1, tzinfo=UTC),
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
            execute_entry_at_next_open(signal, next_candle)
        
        decision_logs = [r for r in caplog.records if "VWAP_RECLAIM_DECISION" in r.message]
        log_message = decision_logs[0].message
        json_start = log_message.index("{")
        json_str = log_message[json_start:]
        decision_data = json.loads(json_str)
        
        # Session and tier info should be present
        assert "session_ok" in decision_data
        assert "tier_ok" in decision_data
        assert decision_data["session_ok"] is True
        assert decision_data["tier_ok"] is True

