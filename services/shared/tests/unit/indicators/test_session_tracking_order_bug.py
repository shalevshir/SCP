"""Test for session tracking order bug in StreamingFeatureProcessor.

This test verifies that session state is updated BEFORE structure context is created,
ensuring prior_session_high/low values are current in the returned context.

Bug: update_session_state() is called AFTER update(), causing stale values at boundaries.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scp_shared.indicators.structure import StructureContextTracker


class TestSessionTrackingOrderBug:
    """Test that session state updates happen before context creation."""

    def test_session_boundary_values_available_in_returned_context(self) -> None:
        """Test that prior session values are available in context AT session boundary.

        This test reproduces the bug where update() is called before update_session_state(),
        causing the returned StructureContext to have stale prior_session values.

        Expected: At session boundary, the StructureContext returned by update()
        should contain the newly rolled-over prior_session_high/low values.

        Bug: If update() is called first, it returns context with old (None) prior values,
        and update_session_state() updates the state AFTER the context is already created.
        """
        tracker = StructureContextTracker()

        # Session 1: Jan 15 - build up extremes
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        
        # CORRECT ORDER: update_session_state BEFORE update
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)
        context1 = tracker.update(high=2650.0, low=2645.0, close=2648.0)
        
        ts2 = datetime(2024, 1, 15, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2660.0, low=2642.0)
        context2 = tracker.update(high=2660.0, low=2642.0, close=2658.0)

        # Prior should be None (no session boundary yet)
        assert context2.prior_session_high is None
        assert context2.prior_session_low is None

        # Session boundary - Jan 16 at 08:20 ET
        ts3 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        
        # CORRECT ORDER: update_session_state BEFORE update
        # This allows the session boundary detection to happen first,
        # rolling over prior values, so that update() sees the new prior values
        tracker.update_session_state(ts3, high=2655.0, low=2650.0)
        context3 = tracker.update(high=2655.0, low=2650.0, close=2653.0)

        # CRITICAL: Prior should have Session 1 extremes IN THE RETURNED CONTEXT
        assert context3.prior_session_high == 2660.0, \
            f"Expected prior_session_high=2660.0 at boundary, got {context3.prior_session_high}"
        assert context3.prior_session_low == 2642.0, \
            f"Expected prior_session_low=2642.0 at boundary, got {context3.prior_session_low}"

    def test_wrong_order_causes_stale_values_at_boundary(self) -> None:
        """Demonstrate the bug: calling update() before update_session_state().

        This test shows what happens when the calls are in the wrong order
        (as in the current streaming.py code).
        """
        tracker = StructureContextTracker()

        # Session 1: Jan 15
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)
        tracker.update(high=2650.0, low=2645.0, close=2648.0)
        
        ts2 = datetime(2024, 1, 15, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2660.0, low=2642.0)
        tracker.update(high=2660.0, low=2642.0, close=2658.0)

        # Session boundary - Jan 16 at 08:20 ET
        ts3 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        
        # WRONG ORDER: update() called BEFORE update_session_state()
        # This is the bug - update() creates context with stale prior values
        context3_wrong = tracker.update(high=2655.0, low=2650.0, close=2653.0)
        
        # BUG: Context still has None because session boundary hasn't been detected yet
        assert context3_wrong.prior_session_high is None, \
            "Bug reproduced: prior_session_high is None when update() called before update_session_state()"
        assert context3_wrong.prior_session_low is None, \
            "Bug reproduced: prior_session_low is None when update() called before update_session_state()"
        
        # Now call update_session_state() - this detects boundary and rolls over
        tracker.update_session_state(ts3, high=2655.0, low=2650.0)
        
        # The internal state is NOW correct
        assert tracker.prior_session_high == 2660.0
        assert tracker.prior_session_low == 2642.0
        
        # But the context that was already returned to the caller has stale values!
        # This is the bug: the context is already published with None values

    def test_production_pattern_simulates_streaming_processor(self) -> None:
        """Simulate the exact pattern used in StreamingFeatureProcessor.process().

        This test simulates what happens in production code to verify the fix works.
        """
        tracker = StructureContextTracker()

        # Process several bars in Session 1
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        # Correct order: session state first
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)
        context1 = tracker.update(high=2650.0, low=2645.0, close=2648.0)
        
        ts2 = datetime(2024, 1, 15, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2660.0, low=2642.0)
        context2 = tracker.update(high=2660.0, low=2642.0, close=2658.0)

        # At session boundary (08:20 ET next day)
        ts3 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        
        # MUST call session state first to detect boundary
        tracker.update_session_state(ts3, high=2655.0, low=2650.0)
        # Then update() will see the rolled-over prior values
        context3 = tracker.update(high=2655.0, low=2650.0, close=2653.0)

        # Verify prior session values are immediately available
        assert context3.prior_session_high == 2660.0
        assert context3.prior_session_low == 2642.0
