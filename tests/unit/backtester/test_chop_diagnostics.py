"""Tests for chop diagnostics calculation in replay loop.

These tests verify that _calculate_chop_diagnostics correctly tracks
chop-related statistics using the current validation flow fields
(chop_severity/chop_ok in validation_flags, chop_detected in diagnostics).
"""

import pytest
from datetime import datetime, timezone

from backtester.entry_model import EntryExecution
from rule_engine.signal import Signal


class TestCalculateChopDiagnostics:
    """Test _calculate_chop_diagnostics correctly reads chop state."""

    def _make_execution(
        self,
        setup_type: str = "VWAP_RECLAIM",
        executed: bool = True,
        rejection_reason: str | None = None,
        chop_severity: str = "none",
        chop_ok: bool = True,
        diagnostics_chop_detected: bool = False,
    ) -> EntryExecution:
        """Create a mock EntryExecution with specified chop state.
        
        The validation flow stores:
        - validation_flags["chop_severity"] = "none" | "soft" | "hard"
        - validation_flags["chop_ok"] = True/False
        - signal.diagnostics["chop_detected"] = True/False
        """
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type=setup_type,
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test signal",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "chop_severity": chop_severity,
                "chop_ok": chop_ok,
            },
            enforcer_tier="EarlyMild",
            diagnostics={
                "chop_detected": diagnostics_chop_detected,
                "chop_severity": chop_severity,
            },
        )
        return EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0 if executed else 0.0,
            signal=signal,
            executed=executed,
            rejection_reason=rejection_reason,
        )

    def test_detects_chop_from_chop_severity_in_validation_flags(self) -> None:
        """Test that chop is detected using chop_severity != 'none'.
        
        BUG: Prior implementation checked validation_flags["chop_detected"],
        which doesn't exist. Must use chop_severity or signal.diagnostics.
        """
        from backtester.replay_loop import BacktestReplayLoop
        
        # Create mock executions with different chop severities
        executions = [
            self._make_execution(
                setup_type="VWAP_RECLAIM",
                executed=True,
                chop_severity="none",
                chop_ok=True,
                diagnostics_chop_detected=False,
            ),
            self._make_execution(
                setup_type="VWAP_RECLAIM",
                executed=True,
                chop_severity="soft",
                chop_ok=True,  # Soft chop allows reclaim with penalty
                diagnostics_chop_detected=True,
            ),
            self._make_execution(
                setup_type="DXY_CONTINUATION",
                executed=False,
                rejection_reason="DXY_CONTINUATION blocked: chop detected",
                chop_severity="soft",
                chop_ok=False,
                diagnostics_chop_detected=True,
            ),
            self._make_execution(
                setup_type="VWAP_FADE",
                executed=True,
                chop_severity="hard",
                chop_ok=True,  # Fade allowed in chop
                diagnostics_chop_detected=True,
            ),
        ]
        
        # Create a minimal BacktestReplayLoop instance for testing
        loop = BacktestReplayLoop.__new__(BacktestReplayLoop)
        loop._all_executions = executions
        
        result = loop._calculate_chop_diagnostics()
        
        # 3 signals evaluated during chop (soft, soft, hard)
        assert result["signals_evaluated_during_chop"] == 3, (
            f"Expected 3 signals during chop, got {result['signals_evaluated_during_chop']}. "
            "This indicates _calculate_chop_diagnostics is not correctly detecting chop state."
        )
        
        # 1 signal blocked by chop (continuation)
        assert result["signals_blocked_by_chop"] == 1
        
        # 1 fade allowed during chop
        assert result["fades_allowed_during_chop"] == 1
        
        # 1 reclaim penalized (soft chop, not blocked)
        assert result["reclaims_penalized_by_chop"] == 1
        
        # 1 continuation blocked
        assert result["continuations_blocked_by_chop"] == 1
        
        # Severity distribution
        assert result["chop_severity_distribution"] == {
            "none": 1,
            "soft": 2,
            "hard": 1,
        }

    def test_handles_missing_validation_flags_gracefully(self) -> None:
        """Test that missing validation_flags keys don't cause errors."""
        from backtester.replay_loop import BacktestReplayLoop
        
        # Signal with minimal validation_flags (no chop keys)
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={"session_ok": True},  # No chop keys
            enforcer_tier="EarlyMild",
            diagnostics={},  # Empty diagnostics
        )
        execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        
        loop = BacktestReplayLoop.__new__(BacktestReplayLoop)
        loop._all_executions = [execution]
        
        # Should not raise
        result = loop._calculate_chop_diagnostics()
        
        # Should count as no chop
        assert result["signals_evaluated_during_chop"] == 0
        assert result["chop_severity_distribution"]["none"] == 1

