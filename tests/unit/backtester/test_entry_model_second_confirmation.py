"""Unit tests for second confirmation gate in entry model.

Tests that VWAP_RECLAIM entries require second confirmation before execution.
"""

from datetime import datetime, timezone

import pytest

from backtester.entry_model import execute_entry_at_next_open
from common.types import Candle
from rule_engine.signal import Signal


@pytest.fixture
def valid_signal_with_confirmation():
    """Create an A+ VWAP_RECLAIM signal with second confirmation satisfied."""
    return Signal(
        timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=9.0,
        confidence="A+",
        factors={"structure_alignment": 2.0},
        rationale="Test signal",
        validation_flags={"htf_valid": True},
        enforcer_tier="Early Mild",
        diagnostics={
            "second_confirmation_satisfied": True,
            "second_confirmation_type": "vwap_hold",
            "second_confirmation_reasons": ["vwap_hold: price holding above VWAP"],
            "bars_since_reclaim": 3,
        },
    )


@pytest.fixture
def valid_signal_without_confirmation():
    """Create an A+ VWAP_RECLAIM signal WITHOUT second confirmation."""
    return Signal(
        timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=9.0,
        confidence="A+",
        factors={"structure_alignment": 2.0},
        rationale="Test signal",
        validation_flags={"htf_valid": True},
        enforcer_tier="Early Mild",
        diagnostics={
            "second_confirmation_satisfied": False,
            "second_confirmation_type": None,
            "second_confirmation_reasons": [],
            "bars_since_reclaim": 1,
        },
    )


@pytest.fixture
def valid_signal_non_vwap_reclaim():
    """Create an A+ signal for a different setup type (should not be gated)."""
    return Signal(
        timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="DXY_CONTINUATION",
        htf_bias="bullish",
        score=9.0,
        confidence="A+",
        factors={"structure_alignment": 2.0},
        rationale="Test signal",
        validation_flags={"htf_valid": True},
        enforcer_tier="Early Mild",
        diagnostics={},
    )


@pytest.fixture
def next_candle():
    """Create a valid next candle."""
    return Candle(
        timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
        open=2650.0,
        high=2652.0,
        low=2649.0,
        close=2651.0,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )


class TestSecondConfirmationGate:
    """Test second confirmation gate in entry model."""

    def test_vwap_reclaim_with_confirmation_executes(
        self, valid_signal_with_confirmation, next_candle
    ):
        """Test that VWAP_RECLAIM with confirmation executes entry."""
        execution = execute_entry_at_next_open(valid_signal_with_confirmation, next_candle)

        assert execution.executed is True
        assert execution.entry_price == 2650.0
        assert execution.rejection_reason is None

    def test_vwap_reclaim_without_confirmation_rejects(
        self, valid_signal_without_confirmation, next_candle
    ):
        """Test that VWAP_RECLAIM without confirmation rejects entry."""
        execution = execute_entry_at_next_open(valid_signal_without_confirmation, next_candle)

        assert execution.executed is False
        assert "no second confirmation" in execution.rejection_reason.lower()

    def test_non_vwap_reclaim_setup_not_gated(
        self, valid_signal_non_vwap_reclaim, next_candle
    ):
        """Test that non-VWAP_RECLAIM setups are not gated by second confirmation."""
        execution = execute_entry_at_next_open(valid_signal_non_vwap_reclaim, next_candle)

        assert execution.executed is True
        assert execution.entry_price == 2650.0

    def test_vwap_reclaim_stale_expired_rejects_entry(self, next_candle):
        """Test that stale/expired reclaim REJECTS entry.

        Per vwap_Reclain_fix.mdc Task 3:
        - "If no confirmation within window → setup expires"
        - "Prevent stale reclaim execution"
        """
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test signal",
            validation_flags={"htf_valid": True},
            enforcer_tier="Early Mild",
            diagnostics={
                "second_confirmation_satisfied": False,  # Expired = not confirmed
                "second_confirmation_type": "expired",
                "second_confirmation_reasons": ["Reclaim expired: no confirmation within window"],
                "bars_since_reclaim": 15,
            },
        )

        execution = execute_entry_at_next_open(signal, next_candle)

        # Expired reclaims should be REJECTED
        assert execution.executed is False
        assert "no second confirmation" in execution.rejection_reason.lower()

    def test_vwap_reclaim_missing_diagnostics_rejects(self, next_candle):
        """Test that VWAP_RECLAIM signal without diagnostics rejects entry."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test signal",
            validation_flags={"htf_valid": True},
            enforcer_tier="Early Mild",
            diagnostics=None,  # Missing diagnostics
        )

        execution = execute_entry_at_next_open(signal, next_candle)

        assert execution.executed is False
        assert "no second confirmation" in execution.rejection_reason.lower()

    def test_vwap_reclaim_with_expansion_confirmation_executes(self, next_candle):
        """Test that VWAP_RECLAIM with expansion signal as confirmation executes entry.
        
        This test verifies the fix for the execution deadlock: expansion signals
        (BOS, range expansion, ATR expansion, displacement) now count as valid
        second confirmation, allowing execution to proceed.
        """
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test signal",
            validation_flags={"htf_valid": True},
            enforcer_tier="Early Mild",
            diagnostics={
                "second_confirmation_satisfied": True,
                "second_confirmation_type": "expansion_recent_bos",
                "second_confirmation_reasons": ["expansion_recent_bos: market resolving from compression"],
                "bars_since_reclaim": 2,
            },
        )

        execution = execute_entry_at_next_open(signal, next_candle)

        assert execution.executed is True
        assert execution.entry_price == 2650.0
        assert execution.rejection_reason is None

