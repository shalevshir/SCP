"""Unit tests for VWAP Reclaim State Machine.

Tests the state machine lifecycle following TDD principles:
1. Write failing tests that capture requirements
2. Implement minimal code to pass tests
3. Refactor with tests green

Tests cover:
- All valid state transitions
- Invalid transition rejection
- Expiration at MAX_CONFIRM_WINDOW
- can_execute() gating by state
- Transition history preservation
"""

import pytest
from feature_engine.vwap_reclaim_state_machine import (
    VWAPReclaimState,
    VWAPReclaimStateMachine,
)


class TestVWAPReclaimStateMachine:
    """Test suite for VWAPReclaimStateMachine lifecycle."""

    def test_initial_state_is_none(self):
        """State machine starts in NONE state."""
        sm = VWAPReclaimStateMachine()
        assert sm.current_state == VWAPReclaimState.NONE
        assert sm.detection_bar_idx is None

    def test_reclaim_detected_transitions_to_pending(self):
        """on_reclaim_detected() transitions NONE -> DETECTED -> PENDING."""
        sm = VWAPReclaimStateMachine()
        
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        assert sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE
        assert sm.detection_bar_idx == 100
        assert sm.reclaim_direction == "above"

    def test_confirmation_transitions_pending_to_confirmed(self):
        """on_confirmation() transitions PENDING -> CONFIRMED."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        sm.on_confirmation(bar_idx=103, confirmation_type="vwap_hold")
        
        assert sm.current_state == VWAPReclaimState.CONFIRMED
        assert len(sm.confirmations) == 1
        assert "vwap_hold" in sm.confirmations

    def test_multiple_confirmations_accumulate(self):
        """Multiple confirmations can be added before CONFIRMED state."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        sm.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        sm.on_confirmation(bar_idx=103, confirmation_type="volume_expansion")
        
        assert sm.current_state == VWAPReclaimState.CONFIRMED
        assert len(sm.confirmations) == 2
        assert "vwap_hold" in sm.confirmations
        assert "volume_expansion" in sm.confirmations

    def test_execution_transitions_confirmed_to_executed(self):
        """on_execution() transitions CONFIRMED -> EXECUTED."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=103, confirmation_type="vwap_hold")
        
        sm.on_execution(bar_idx=104)
        
        assert sm.current_state == VWAPReclaimState.EXECUTED

    def test_expiration_transitions_pending_to_expired(self):
        """on_expiration() transitions PENDING -> EXPIRED."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        sm.on_expiration(bar_idx=111)
        
        assert sm.current_state == VWAPReclaimState.EXPIRED

    def test_expiration_at_max_confirm_window(self):
        """Reclaim expires after MAX_CONFIRM_WINDOW bars."""
        MAX_CONFIRM_WINDOW = 10
        sm = VWAPReclaimStateMachine(max_confirm_window=MAX_CONFIRM_WINDOW)
        sm.on_reclaim_detected(bar_idx=5, direction="above")
        
        # At bar 15, exactly 10 bars have passed since bar 5
        # Should NOT be expired yet (need > 10 bars)
        assert not sm.is_expired(current_bar_idx=15)
        
        # At bar 16, 11 bars have passed since bar 5
        # Should be expired (> 10 bars)
        assert sm.is_expired(current_bar_idx=16)

    def test_invalidation_from_any_state(self):
        """on_invalidation() can transition from any state."""
        # Test from PENDING
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_invalidation(bar_idx=105, reason="htf_break")
        assert sm.current_state == VWAPReclaimState.INVALIDATED
        
        # Test from CONFIRMED
        sm2 = VWAPReclaimStateMachine()
        sm2.on_reclaim_detected(bar_idx=100, direction="above")
        sm2.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        sm2.on_invalidation(bar_idx=105, reason="vwap_loss")
        assert sm2.current_state == VWAPReclaimState.INVALIDATED

    def test_can_execute_only_in_confirmed_state(self):
        """can_execute() returns True only when state == CONFIRMED."""
        sm = VWAPReclaimStateMachine()
        
        # NONE state
        assert not sm.can_execute()
        
        # PENDING state
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        assert not sm.can_execute()
        
        # CONFIRMED state
        sm.on_confirmation(bar_idx=103, confirmation_type="vwap_hold")
        assert sm.can_execute()
        
        # EXECUTED state
        sm.on_execution(bar_idx=104)
        assert not sm.can_execute()

    def test_can_execute_false_after_expiration(self):
        """can_execute() returns False after expiration."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_expiration(bar_idx=111)
        
        assert not sm.can_execute()

    def test_can_execute_false_after_invalidation(self):
        """can_execute() returns False after invalidation."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=103, confirmation_type="vwap_hold")
        sm.on_invalidation(bar_idx=105, reason="htf_break")
        
        assert not sm.can_execute()

    def test_transition_history_preserved(self):
        """All state transitions are recorded in history."""
        sm = VWAPReclaimStateMachine()
        
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=103, confirmation_type="vwap_hold")
        sm.on_execution(bar_idx=104)
        
        assert len(sm.transition_history) >= 3
        
        # Check that history contains the key transitions
        states_in_history = [t.to_state for t in sm.transition_history]
        assert VWAPReclaimState.PENDING_ACCEPTANCE in states_in_history
        assert VWAPReclaimState.CONFIRMED in states_in_history
        assert VWAPReclaimState.EXECUTED in states_in_history

    def test_bars_since_detection(self):
        """bars_since_detection() returns correct bar count."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        assert sm.bars_since_detection(current_bar_idx=100) == 0
        assert sm.bars_since_detection(current_bar_idx=105) == 5
        assert sm.bars_since_detection(current_bar_idx=110) == 10

    def test_reset_clears_state(self):
        """reset() returns state machine to NONE and clears tracking."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=103, confirmation_type="vwap_hold")
        
        sm.reset()
        
        assert sm.current_state == VWAPReclaimState.NONE
        assert sm.detection_bar_idx is None
        assert len(sm.confirmations) == 0
        # Transition history should be preserved for diagnostics
        assert len(sm.transition_history) > 0

    def test_cannot_confirm_in_expired_state(self):
        """Attempting confirmation in EXPIRED state should be rejected."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_expiration(bar_idx=111)
        
        # This should either be a no-op or raise an error
        # Let's test it doesn't change state
        with pytest.raises(ValueError, match="Cannot confirm.*EXPIRED"):
            sm.on_confirmation(bar_idx=112, confirmation_type="vwap_hold")

    def test_cannot_execute_in_pending_state(self):
        """Attempting execution in PENDING state should be rejected."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        with pytest.raises(ValueError, match="Cannot execute.*pending"):
            sm.on_execution(bar_idx=102)

    def test_transition_logging_includes_bar_index(self):
        """All transitions log bar index and reason."""
        sm = VWAPReclaimStateMachine()
        
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        assert len(sm.transition_history) >= 1
        last_transition = sm.transition_history[-1]
        assert hasattr(last_transition, "bar_idx")
        assert last_transition.bar_idx == 100
        assert hasattr(last_transition, "reason")
        assert last_transition.reason is not None

