"""Integration tests for StructureContextTracker with VWAPReclaimStateMachine.

Tests the integration between StructureContextTracker and VWAPReclaimStateMachine,
ensuring proper lifecycle management for VWAP reclaim setups.

Following TDD: These tests define expected behavior before implementation.
"""


from feature_engine.structure import StructureContextTracker
from feature_engine.vwap_reclaim_state_machine import VWAPReclaimState


class TestStructureTrackerStateMachineIntegration:
    """Test integration between StructureContextTracker and state machine."""

    def test_tracker_has_state_machine(self):
        """StructureContextTracker should have a VWAPReclaimStateMachine instance."""
        tracker = StructureContextTracker()
        
        assert hasattr(tracker, "vwap_reclaim_sm")
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.NONE

    def test_vwap_cross_triggers_state_machine_detection(self):
        """VWAP cross in update_vwap_state() should trigger state machine."""
        tracker = StructureContextTracker()
        
        # Initialize with some bars to set up buffers
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        # Update VWAP state with values below VWAP
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        
        # Now cross above VWAP (long reclaim)
        tracker.bar_count += 1
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        
        # State machine should be in PENDING_ACCEPTANCE
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE
        assert tracker.vwap_reclaim_sm.reclaim_direction == "above"

    def test_update_reclaim_state_checks_expiration(self):
        """update_reclaim_state() should check and trigger expiration."""
        MAX_CONFIRM_WINDOW = 10
        tracker = StructureContextTracker()
        
        # Setup: detect reclaim at bar 100
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        tracker.bar_count += 1
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        detection_bar = tracker.bar_count - 1
        
        # Advance past MAX_CONFIRM_WINDOW without confirmation
        for i in range(MAX_CONFIRM_WINDOW + 2):
            tracker.bar_count += 1
            tracker.update_reclaim_state(tracker.bar_count)
        
        # State machine should be EXPIRED
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.EXPIRED

    def test_compute_second_confirmation_returns_early_if_expired(self):
        """compute_second_confirmation() should return early if state is EXPIRED."""
        tracker = StructureContextTracker()
        
        # Setup: detect reclaim
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        tracker.bar_count += 1
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        
        # Manually expire the reclaim
        tracker.vwap_reclaim_sm.on_expiration(bar_idx=tracker.bar_count + 15)
        
        # compute_second_confirmation should return early with expired status
        result = tracker.compute_second_confirmation(direction="long")
        
        assert result["confirmed"] is False
        assert result["confirmation_type"] == "expired"

    def test_compute_second_confirmation_returns_early_if_invalidated(self):
        """compute_second_confirmation() should return early if state is INVALIDATED."""
        tracker = StructureContextTracker()
        
        # Setup: detect reclaim
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        tracker.bar_count += 1
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        
        # Manually invalidate the reclaim
        tracker.vwap_reclaim_sm.on_invalidation(
            bar_idx=tracker.bar_count + 2, reason="htf_break"
        )
        
        # compute_second_confirmation should return early
        result = tracker.compute_second_confirmation(direction="long")
        
        assert result["confirmed"] is False
        # Should indicate invalidation
        assert "invalidated" in result.get("confirmation_type", "").lower() or \
               "invalid" in str(result.get("reasons", [])).lower()

    def test_compute_second_confirmation_triggers_state_transition(self):
        """compute_second_confirmation() should trigger state machine on confirmation."""
        tracker = StructureContextTracker()
        
        # Setup: detect reclaim at bar X
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        # Initialize VWAP and volume buffers
        for i in range(10):
            tracker.update_vwap_state(vwap=2650.0, close=2645.0)
            tracker.update_volume_state(volume=100.0)
        
        # Detect reclaim (cross above VWAP)
        tracker.bar_count += 1
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        tracker.update_volume_state(volume=100.0)
        
        # Advance 2 bars with price holding above VWAP (should trigger confirmation)
        for i in range(2):
            tracker.bar_count += 1
            tracker.update_vwap_state(vwap=2650.0, close=2656.0)
            tracker.update_volume_state(volume=100.0)
        
        # Check confirmation
        result = tracker.compute_second_confirmation(direction="long")
        
        # Should be confirmed
        assert result["confirmed"] is True
        
        # State machine should be CONFIRMED
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.CONFIRMED

    def test_state_machine_reset_on_new_reclaim(self):
        """New reclaim detection should reset state machine."""
        tracker = StructureContextTracker()
        
        # Setup: detect first reclaim
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        tracker.bar_count += 1
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        
        first_detection_bar = tracker.vwap_reclaim_sm.detection_bar_idx
        
        # Detect second reclaim (should reset)
        tracker.bar_count += 5
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        tracker.bar_count += 1
        tracker.update_vwap_state(vwap=2650.0, close=2656.0)
        
        second_detection_bar = tracker.vwap_reclaim_sm.detection_bar_idx
        
        # Detection bar should have changed
        assert second_detection_bar != first_detection_bar
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE

    def test_state_machine_preserves_bars_since_reclaim_compatibility(self):
        """State machine should maintain backward compatibility with bars_since_reclaim."""
        tracker = StructureContextTracker()
        
        # Setup: detect reclaim
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        tracker.bar_count += 1
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        # Detection happens at bar_count - 1 due to the logic in update_vwap_state
        detection_bar = tracker.bar_count - 1
        
        # Advance a few bars
        tracker.bar_count += 5
        
        # Check that bars_since_detection matches expected calculation
        expected_bars_since = tracker.bar_count - detection_bar
        actual_bars_since = tracker.vwap_reclaim_sm.bars_since_detection(tracker.bar_count)
        
        assert actual_bars_since == expected_bars_since

    def test_reclaim_expires_automatically_through_update(self):
        """Reclaims should expire automatically when update() is called repeatedly.
        
        CRITICAL: This verifies the fix for the bug where update_reclaim_state()
        was never called from production code, defeating expiration logic.
        """
        MAX_CONFIRM_WINDOW = 10
        tracker = StructureContextTracker()
        
        # Setup: detect reclaim through normal flow
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        # Setup VWAP state
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)  # Cross above = reclaim
        
        # Verify reclaim was detected
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE
        
        # Now call update() repeatedly (normal production flow)
        # This should trigger expiration automatically after MAX_CONFIRM_WINDOW
        for i in range(MAX_CONFIRM_WINDOW + 2):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        # Reclaim should have expired automatically
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.EXPIRED
    
    def test_expiration_prevents_late_confirmation(self):
        """Expired reclaims should not accept confirmations even through update() flow."""
        MAX_CONFIRM_WINDOW = 10
        tracker = StructureContextTracker()
        
        # Setup: detect reclaim
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        # Initialize VWAP tracking
        for i in range(10):
            tracker.update_vwap_state(vwap=2650.0, close=2645.0)
            tracker.update_volume_state(volume=100.0)
        
        # Detect reclaim
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        tracker.update_volume_state(volume=100.0)
        
        # Let it expire through normal update() calls
        for i in range(MAX_CONFIRM_WINDOW + 2):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
            tracker.update_vwap_state(vwap=2650.0, close=2656.0)
            tracker.update_volume_state(volume=100.0)
        
        # Try to confirm after expiration
        result = tracker.compute_second_confirmation(direction="long")
        
        # Should be rejected as expired
        assert result["confirmed"] is False
        assert result["confirmation_type"] == "expired"

    def test_expiration_bar_count_is_exact(self):
        """Reclaim should expire exactly after MAX_CONFIRM_WINDOW bars, not off-by-one.
        
        This test verifies the fix for the bug where update_reclaim_state(bar_count)
        passed bar_count instead of bar_count - 1, causing early expiration.
        
        Detection stores bar_count - 1, so expiration check must also use bar_count - 1
        for consistent bar indexing.
        """
        MAX_CONFIRM_WINDOW = 10
        tracker = StructureContextTracker()
        
        # Setup initial bars
        for i in range(5):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        # Setup VWAP state (below VWAP)
        tracker.update_vwap_state(vwap=2650.0, close=2645.0)
        
        # Trigger reclaim (cross above VWAP)
        tracker.update_vwap_state(vwap=2650.0, close=2655.0)
        detection_bar = tracker.vwap_reclaim_sm.detection_bar_idx
        
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE
        
        # Call update() exactly MAX_CONFIRM_WINDOW times
        # After these calls, we should NOT be expired yet (exactly at threshold)
        for i in range(MAX_CONFIRM_WINDOW):
            tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        # At exactly MAX_CONFIRM_WINDOW bars, should NOT be expired
        # (is_expired checks > max_confirm_window, not >=)
        current_bar = tracker.bar_count - 1
        bars_since = current_bar - detection_bar
        assert bars_since == MAX_CONFIRM_WINDOW, (
            f"Expected {MAX_CONFIRM_WINDOW} bars since detection, got {bars_since}"
        )
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE, (
            f"Should still be PENDING at exactly {MAX_CONFIRM_WINDOW} bars, "
            f"but state is {tracker.vwap_reclaim_sm.current_state.value}"
        )
        
        # One more update should trigger expiration
        tracker.update(high=2650.0, low=2640.0, close=2645.0)
        
        current_bar = tracker.bar_count - 1
        bars_since = current_bar - detection_bar
        assert bars_since == MAX_CONFIRM_WINDOW + 1
        assert tracker.vwap_reclaim_sm.current_state == VWAPReclaimState.EXPIRED, (
            f"Should be EXPIRED at {MAX_CONFIRM_WINDOW + 1} bars, "
            f"but state is {tracker.vwap_reclaim_sm.current_state.value}"
        )

