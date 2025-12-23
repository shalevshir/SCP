"""Unit tests for VWAPReclaimStateMachine."""

import pytest

from scp_shared.indicators.vwap_reclaim_state_machine import (
    VWAPReclaimState,
    VWAPReclaimStateMachine,
    MAX_EXECUTIONS_PER_RECLAIM,
)


class TestVWAPReclaimStateMachine:
    """Test VWAPReclaimStateMachine class."""
    
    def test_initial_state_is_none(self) -> None:
        """Initial state is NONE."""
        sm = VWAPReclaimStateMachine()
        
        assert sm.current_state == VWAPReclaimState.NONE
        assert sm.detection_bar_idx is None
        assert sm.reclaim_direction is None
    
    def test_on_reclaim_detected_transitions_to_pending(self) -> None:
        """Detected reclaim transitions to PENDING_ACCEPTANCE."""
        sm = VWAPReclaimStateMachine()
        
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        assert sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE
        assert sm.detection_bar_idx == 100
        assert sm.reclaim_direction == "above"
    
    def test_on_reclaim_detected_below(self) -> None:
        """Detected reclaim below VWAP sets correct direction."""
        sm = VWAPReclaimStateMachine()
        
        sm.on_reclaim_detected(bar_idx=100, direction="below")
        
        assert sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE
        assert sm.reclaim_direction == "below"
    
    def test_on_confirmation_transitions_to_confirmed(self) -> None:
        """Confirmation transitions to CONFIRMED state."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        sm.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        
        assert sm.current_state == VWAPReclaimState.CONFIRMED
    
    def test_can_execute_when_confirmed(self) -> None:
        """can_execute returns True when CONFIRMED."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        
        assert sm.can_execute() is True
    
    def test_cannot_execute_when_pending(self) -> None:
        """can_execute returns False when PENDING."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        # Still in PENDING_ACCEPTANCE
        assert sm.can_execute() is False
    
    def test_on_execution_transitions_to_executed(self) -> None:
        """Execution transitions to EXECUTED state."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        
        sm.on_execution(bar_idx=103)
        
        assert sm.current_state == VWAPReclaimState.EXECUTED
        assert sm.execution_count == 1
    
    def test_on_expiration_transitions_to_expired(self) -> None:
        """Expiration transitions to EXPIRED state."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        # Simulate timeout (10 bars)
        sm.on_expiration(bar_idx=111)
        
        assert sm.current_state == VWAPReclaimState.EXPIRED
    
    def test_is_expired_returns_true_after_window(self) -> None:
        """is_expired returns True after confirmation window."""
        sm = VWAPReclaimStateMachine(max_confirm_window=10)
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        # At edge of window (10 bars)
        assert sm.is_expired(110) is False
        
        # Past window
        assert sm.is_expired(111) is True
    
    def test_is_expired_returns_false_when_no_detection(self) -> None:
        """is_expired returns False when no detection."""
        sm = VWAPReclaimStateMachine()
        
        # No detection, so not expired
        assert sm.is_expired(200) is False
    
    def test_on_invalidation_transitions_to_invalidated(self) -> None:
        """Invalidation transitions to INVALIDATED state."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        sm.on_invalidation(bar_idx=105, reason="HTF_BREAK")
        
        assert sm.current_state == VWAPReclaimState.INVALIDATED
    
    def test_on_invalidation_works_from_any_state(self) -> None:
        """Invalidation works from any state."""
        # From PENDING
        sm1 = VWAPReclaimStateMachine()
        sm1.on_reclaim_detected(bar_idx=100, direction="above")
        sm1.on_invalidation(bar_idx=102, reason="VWAP_LOSS")
        assert sm1.current_state == VWAPReclaimState.INVALIDATED
        
        # From CONFIRMED
        sm2 = VWAPReclaimStateMachine()
        sm2.on_reclaim_detected(bar_idx=100, direction="above")
        sm2.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        sm2.on_invalidation(bar_idx=105, reason="STRUCTURE_BREAK")
        assert sm2.current_state == VWAPReclaimState.INVALIDATED
    
    def test_reset_clears_state(self) -> None:
        """reset() clears all state."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        sm.on_execution(bar_idx=103)
        
        sm.reset()
        
        assert sm.current_state == VWAPReclaimState.NONE
        assert sm.detection_bar_idx is None
        assert sm.reclaim_direction is None
    
    def test_execution_count_limits_re_entry(self) -> None:
        """Execution count limits re-entry per reclaim context."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        
        # First execution allowed
        assert sm.can_execute() is True
        sm.on_execution(bar_idx=103)
        
        # After execution, cannot execute again
        assert sm.can_execute() is False
        assert sm.execution_count == 1
    
    def test_transition_history_tracked(self) -> None:
        """Transition history is tracked."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=102, confirmation_type="vwap_hold")
        
        # Should have transitions: NONE -> DETECTED -> PENDING -> CONFIRMED
        assert len(sm.transition_history) >= 2
    
    def test_custom_confirm_window(self) -> None:
        """Custom confirmation window is respected."""
        sm = VWAPReclaimStateMachine(max_confirm_window=5)
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        # At edge (5 bars)
        assert sm.is_expired(105) is False
        
        # Past window (6 bars)
        assert sm.is_expired(106) is True


class TestVWAPReclaimStateMachineEdgeCases:
    """Test edge cases for VWAPReclaimStateMachine."""
    
    def test_confirmation_before_detection_raises_error(self) -> None:
        """Confirmation before detection raises ValueError."""
        sm = VWAPReclaimStateMachine()
        
        # Should raise ValueError when not in PENDING_ACCEPTANCE state
        with pytest.raises(ValueError, match="Must be PENDING_ACCEPTANCE"):
            sm.on_confirmation(bar_idx=100, confirmation_type="vwap_hold")
    
    def test_execution_before_confirmation_is_blocked(self) -> None:
        """Execution before confirmation is blocked."""
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        # can_execute should be False
        assert sm.can_execute() is False
    
    def test_multiple_detections_updates_state(self) -> None:
        """Multiple detections update the state machine."""
        sm = VWAPReclaimStateMachine()
        
        # First detection
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        assert sm.detection_bar_idx == 100
        
        # Reset and new detection
        sm.reset()
        sm.on_reclaim_detected(bar_idx=200, direction="below")
        
        assert sm.detection_bar_idx == 200
        assert sm.reclaim_direction == "below"
    
    def test_max_executions_constant(self) -> None:
        """MAX_EXECUTIONS_PER_RECLAIM is defined."""
        assert MAX_EXECUTIONS_PER_RECLAIM == 1
