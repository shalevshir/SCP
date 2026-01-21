"""Tests for session high/low tracking in StructureContextTracker.

This module tests session boundary detection and prior session extreme tracking
for TP structural target selection (SOP Section 4.3 Priority #3).

Sessions run from 08:20 ET to 08:19:59 ET next day (Gold futures RTH open).
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scp_shared.indicators.structure import StructureContextTracker


class TestSessionTracking:
    """Test session boundary detection and extremes tracking."""

    def test_first_bar_initializes_current_session_prior_is_none(self) -> None:
        """Test that first bar initializes current session and prior remains None.

        Expected behavior:
        - current_session_id set to bar's session
        - current_session_high/low set to bar's high/low
        - prior_session_high/low remain None (no prior session yet)
        """
        tracker = StructureContextTracker()

        # First bar at 10:00 ET on Jan 15, 2024
        timestamp = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        high = 2650.0
        low = 2645.0

        tracker.update_session_state(timestamp, high, low)

        # Current session should be initialized
        assert tracker.current_session_id is not None
        assert tracker.current_session_high == 2650.0
        assert tracker.current_session_low == 2645.0

        # Prior session should remain None (no previous session yet)
        assert tracker.prior_session_high is None
        assert tracker.prior_session_low is None

    def test_session_extremes_updated_within_session(self) -> None:
        """Test that session high/low are updated when exceeded within same session.

        Expected behavior:
        - Session high updated when new high > current high
        - Session low updated when new low < current low
        - Prior session values unchanged
        """
        tracker = StructureContextTracker()

        # First bar at 10:00 ET
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)

        # Second bar - new high
        ts2 = datetime(2024, 1, 15, 11, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2655.0, low=2647.0)

        assert tracker.current_session_high == 2655.0  # Updated
        assert tracker.current_session_low == 2645.0  # Unchanged (2647 > 2645)

        # Third bar - new low
        ts3 = datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2652.0, low=2640.0)

        assert tracker.current_session_high == 2655.0  # Unchanged (2652 < 2655)
        assert tracker.current_session_low == 2640.0  # Updated

        # Prior session should still be None
        assert tracker.prior_session_high is None
        assert tracker.prior_session_low is None

    def test_session_boundary_at_0820_et_rolls_over_extremes(self) -> None:
        """Test that session boundary at 08:20 ET rolls over current to prior.

        Expected behavior:
        - At 08:20 ET next day, session_id changes
        - Current session extremes moved to prior
        - Current session reset with new bar's values
        """
        tracker = StructureContextTracker()

        # First session - Jan 15 at 10:00 ET (after 08:20)
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)

        # Update session extremes
        ts2 = datetime(2024, 1, 15, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2660.0, low=2640.0)

        assert tracker.current_session_high == 2660.0
        assert tracker.current_session_low == 2640.0
        assert tracker.prior_session_high is None
        assert tracker.prior_session_low is None

        # Session boundary - Jan 16 at 08:20 ET (new session starts)
        ts3 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2655.0, low=2650.0)

        # Prior session should now have Jan 15 extremes
        assert tracker.prior_session_high == 2660.0
        assert tracker.prior_session_low == 2640.0

        # Current session should be reset with new bar
        assert tracker.current_session_high == 2655.0
        assert tracker.current_session_low == 2650.0

    def test_prior_session_values_persist_across_new_session(self) -> None:
        """Test that prior session values persist as session continues.

        Expected behavior:
        - After session boundary, prior values remain constant
        - Current session values continue to update
        - Prior values only change at next session boundary
        """
        tracker = StructureContextTracker()

        # Session 1: Jan 15
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2640.0)

        # Session boundary - Jan 16 at 08:20 ET
        ts2 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2655.0, low=2650.0)

        assert tracker.prior_session_high == 2650.0
        assert tracker.prior_session_low == 2640.0

        # Continue session 2 - prior should remain unchanged
        ts3 = datetime(2024, 1, 16, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2660.0, low=2645.0)

        assert tracker.prior_session_high == 2650.0  # Unchanged
        assert tracker.prior_session_low == 2640.0  # Unchanged
        assert tracker.current_session_high == 2660.0
        assert tracker.current_session_low == 2645.0

        # Session boundary - Jan 17 at 08:20 ET
        ts4 = datetime(2024, 1, 17, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts4, high=2658.0, low=2652.0)

        # Prior should now have Jan 16 extremes
        assert tracker.prior_session_high == 2660.0
        assert tracker.prior_session_low == 2645.0

    def test_session_boundary_before_0820_belongs_to_prior_day(self) -> None:
        """Test that bars before 08:20 ET belong to previous day's session.

        Per get_vwap_session_id():
        - 08:19 ET on Jan 16 belongs to Jan 15 session
        - 08:20 ET on Jan 16 starts Jan 16 session
        """
        tracker = StructureContextTracker()

        # First bar at 08:00 ET on Jan 16 (belongs to Jan 15 session)
        ts1 = datetime(2024, 1, 16, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)

        # Bar at 08:19 ET on Jan 16 (still Jan 15 session)
        ts2 = datetime(2024, 1, 16, 8, 19, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2655.0, low=2642.0)

        # Session should still be Jan 15
        assert tracker.current_session_high == 2655.0
        assert tracker.current_session_low == 2642.0

        # Bar at 08:20 ET on Jan 16 (Jan 16 session starts)
        ts3 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2652.0, low=2648.0)

        # Now prior should have Jan 15 extremes
        assert tracker.prior_session_high == 2655.0
        assert tracker.prior_session_low == 2642.0
        assert tracker.current_session_high == 2652.0
        assert tracker.current_session_low == 2648.0

    def test_session_extremes_integration_with_update(self) -> None:
        """Test that prior session values flow through to StructureContext.

        This integration test verifies the full flow from update_session_state()
        through update() to StructureContext output.
        """
        tracker = StructureContextTracker()

        # Session 1: Build up extremes
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        context1 = tracker.update(high=2650.0, low=2645.0, close=2648.0)
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)

        ts2 = datetime(2024, 1, 15, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        context2 = tracker.update(high=2660.0, low=2642.0, close=2658.0)
        tracker.update_session_state(ts2, high=2660.0, low=2642.0)

        # Prior should be None (no session boundary yet)
        assert context2.prior_session_high is None
        assert context2.prior_session_low is None

        # Session boundary - Jan 16 at 08:20 ET
        ts3 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2655.0, low=2650.0)
        context3 = tracker.update(high=2655.0, low=2650.0, close=2653.0)

        # Prior should now have Session 1 extremes
        assert context3.prior_session_high == 2660.0
        assert context3.prior_session_low == 2642.0

    def test_dst_transition_handled_correctly(self) -> None:
        """Test that DST transitions don't cause spurious session boundaries.

        get_vwap_session_id() handles DST automatically, so session boundaries
        should remain consistent across DST transitions.
        """
        tracker = StructureContextTracker()

        # Before DST transition (EST) - March 9, 2024 at 08:20 ET
        ts1 = datetime(2024, 3, 9, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)

        # Same day, later time
        ts2 = datetime(2024, 3, 9, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2655.0, low=2640.0)

        assert tracker.current_session_high == 2655.0
        assert tracker.current_session_low == 2640.0

        # After DST transition (EDT) - March 11, 2024 at 08:20 ET
        # DST transition happened March 10, 2024 at 2:00 AM
        ts3 = datetime(2024, 3, 11, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2652.0, low=2648.0)

        # Should properly detect new session despite DST
        assert tracker.prior_session_high == 2655.0
        assert tracker.prior_session_low == 2640.0

    def test_gap_days_preserve_prior_session_values(self) -> None:
        """Test that data gaps (weekend, holidays) preserve prior session values.

        Expected behavior:
        - If data gaps over session boundary, prior values persist
        - Next session boundary updates prior with most recent session
        """
        tracker = StructureContextTracker()

        # Friday Jan 12 session
        ts1 = datetime(2024, 1, 12, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2640.0)

        # Monday Jan 15 at 08:20 ET (new session, gap over weekend)
        ts2 = datetime(2024, 1, 15, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2652.0, low=2648.0)

        # Prior should have Friday's extremes
        assert tracker.prior_session_high == 2650.0
        assert tracker.prior_session_low == 2640.0

        # Continue Monday session
        ts3 = datetime(2024, 1, 15, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2660.0, low=2645.0)

        # Prior should still be Friday's values
        assert tracker.prior_session_high == 2650.0
        assert tracker.prior_session_low == 2640.0
        assert tracker.current_session_high == 2660.0
        assert tracker.current_session_low == 2645.0

        # Tuesday Jan 16 at 08:20 ET (new session)
        ts4 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts4, high=2658.0, low=2650.0)

        # Prior should now have Monday's extremes
        assert tracker.prior_session_high == 2660.0
        assert tracker.prior_session_low == 2645.0

    def test_multiple_session_rollovers(self) -> None:
        """Test multiple consecutive session boundaries work correctly.

        Verifies that prior session values update correctly through
        multiple session rollovers.
        """
        tracker = StructureContextTracker()

        # Session 1: Jan 15
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2640.0)
        assert tracker.prior_session_high is None
        assert tracker.prior_session_low is None

        # Session 2: Jan 16 at 08:20 ET
        ts2 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2660.0, low=2655.0)
        assert tracker.prior_session_high == 2650.0  # Session 1
        assert tracker.prior_session_low == 2640.0

        # Continue session 2
        ts3 = datetime(2024, 1, 16, 14, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2665.0, low=2652.0)
        assert tracker.prior_session_high == 2650.0  # Still session 1
        assert tracker.prior_session_low == 2640.0
        assert tracker.current_session_high == 2665.0
        assert tracker.current_session_low == 2652.0

        # Session 3: Jan 17 at 08:20 ET
        ts4 = datetime(2024, 1, 17, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts4, high=2658.0, low=2655.0)
        assert tracker.prior_session_high == 2665.0  # Session 2
        assert tracker.prior_session_low == 2652.0

        # Session 4: Jan 18 at 08:20 ET
        ts5 = datetime(2024, 1, 18, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts5, high=2670.0, low=2665.0)
        assert tracker.prior_session_high == 2658.0  # Session 3
        assert tracker.prior_session_low == 2655.0

    def test_utc_timestamps_converted_to_et_correctly(self) -> None:
        """Test that UTC timestamps are correctly converted to ET for session ID.

        get_vwap_session_id() should handle timezone conversion automatically.
        """
        tracker = StructureContextTracker()

        # Jan 15 at 15:00 UTC = Jan 15 at 10:00 ET (during EST)
        ts1 = datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc)
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)

        # Jan 16 at 13:20 UTC = Jan 16 at 08:20 ET (session boundary)
        ts2 = datetime(2024, 1, 16, 13, 20, tzinfo=timezone.utc)
        tracker.update_session_state(ts2, high=2655.0, low=2650.0)

        # Prior should have Jan 15 session extremes
        assert tracker.prior_session_high == 2650.0
        assert tracker.prior_session_low == 2645.0
        assert tracker.current_session_high == 2655.0
        assert tracker.current_session_low == 2650.0

    def test_early_morning_bars_before_0820_belong_to_prior_day(self) -> None:
        """Test that bars before 08:20 ET belong to previous day's session.

        Example: 06:00 ET on Jan 16 belongs to Jan 15 session.
        """
        tracker = StructureContextTracker()

        # Bar at 10:00 ET on Jan 15 (Jan 15 session)
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)

        # Bar at 06:00 ET on Jan 16 (still Jan 15 session)
        ts2 = datetime(2024, 1, 16, 6, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2655.0, low=2642.0)

        # Should update same session extremes (no session boundary)
        assert tracker.current_session_high == 2655.0
        assert tracker.current_session_low == 2642.0
        assert tracker.prior_session_high is None  # No prior session yet

        # Bar at 08:20 ET on Jan 16 (Jan 16 session starts)
        ts3 = datetime(2024, 1, 16, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2652.0, low=2648.0)

        # Now prior should have Jan 15 session (which included the 06:00 bar)
        assert tracker.prior_session_high == 2655.0
        assert tracker.prior_session_low == 2642.0

    def test_session_high_only_updates_when_exceeded(self) -> None:
        """Test that session high only updates when new high exceeds current high."""
        tracker = StructureContextTracker()

        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)
        assert tracker.current_session_high == 2650.0

        # Lower high - should NOT update
        ts2 = datetime(2024, 1, 15, 11, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2648.0, low=2643.0)
        assert tracker.current_session_high == 2650.0  # Unchanged

        # Equal high - should NOT update
        ts3 = datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2650.0, low=2644.0)
        assert tracker.current_session_high == 2650.0  # Unchanged

        # Higher high - SHOULD update
        ts4 = datetime(2024, 1, 15, 13, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts4, high=2651.0, low=2646.0)
        assert tracker.current_session_high == 2651.0  # Updated

    def test_session_low_only_updates_when_exceeded(self) -> None:
        """Test that session low only updates when new low is below current low."""
        tracker = StructureContextTracker()

        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts1, high=2650.0, low=2645.0)
        assert tracker.current_session_low == 2645.0

        # Higher low - should NOT update
        ts2 = datetime(2024, 1, 15, 11, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts2, high=2652.0, low=2647.0)
        assert tracker.current_session_low == 2645.0  # Unchanged

        # Equal low - should NOT update
        ts3 = datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts3, high=2653.0, low=2645.0)
        assert tracker.current_session_low == 2645.0  # Unchanged

        # Lower low - SHOULD update
        ts4 = datetime(2024, 1, 15, 13, 0, tzinfo=ZoneInfo("America/New_York"))
        tracker.update_session_state(ts4, high=2654.0, low=2644.0)
        assert tracker.current_session_low == 2644.0  # Updated
