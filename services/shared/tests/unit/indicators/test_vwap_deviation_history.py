"""Tests for VWAP deviation history tracking in StructureContextTracker.

This module tests the deviation history tracking functionality used by the
vwap_reclaim_distance constraint to detect prior excursion from VWAP.
"""

import pytest

from scp_shared.indicators.structure import StructureContextTracker


class TestDeviationHistoryTracking:
    """Test deviation history tracking for excursion detection."""

    def test_deviation_history_accumulation(self):
        """Test that deviation history tracks max/min over multiple bars."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Bar 1: 0.5 ATR away
        tracker.update(high=2650, low=2645, close=2650)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.5)
        assert tracker.max_abs_deviation_last_20 == 0.5
        assert tracker.min_abs_deviation_last_20 == 0.5

        # Bar 2: 1.0 ATR away (new max)
        tracker.update(high=2655, low=2650, close=2655)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=1.0)
        assert tracker.max_abs_deviation_last_20 == 1.0
        assert tracker.min_abs_deviation_last_20 == 0.5

        # Bar 3: Back near VWAP (0.1 ATR) - new min
        tracker.update(high=2651, low=2648, close=2650)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.1)
        assert tracker.max_abs_deviation_last_20 == 1.0  # Still remembers excursion
        assert tracker.min_abs_deviation_last_20 == 0.1

    def test_deviation_direction_agnostic(self):
        """Test that deviation tracking uses absolute values (direction-agnostic)."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Positive deviation
        tracker.update(high=2655, low=2650, close=2655)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=1.5)
        assert tracker.max_abs_deviation_last_20 == 1.5

        # Negative deviation (same magnitude)
        tracker.update(high=2645, low=2640, close=2645)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=-1.5)
        assert tracker.max_abs_deviation_last_20 == 1.5  # Same max

        # Negative deviation (larger magnitude)
        tracker.update(high=2635, low=2630, close=2635)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=-2.0)
        assert tracker.max_abs_deviation_last_20 == 2.0  # Absolute value tracked

    def test_deviation_rolling_window(self):
        """Test that deviation history uses 20-bar rolling window."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Fill 20 bars with low deviation
        for i in range(20):
            tracker.update(high=2650, low=2645, close=2650)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.1)

        assert tracker.max_abs_deviation_last_20 == 0.1
        assert len(tracker.deviation_history) == 20

        # Add 21st bar with high deviation
        tracker.update(high=2655, low=2650, close=2655)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=2.0)

        assert tracker.max_abs_deviation_last_20 == 2.0
        assert len(tracker.deviation_history) == 20  # Still maxlen=20

        # Add 20 more bars with low deviation (pushes out high deviation)
        for i in range(20):
            tracker.update(high=2650, low=2645, close=2650)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.1)

        assert tracker.max_abs_deviation_last_20 == 0.1  # High deviation aged out
        assert tracker.min_abs_deviation_last_20 == 0.1

    def test_deviation_none_handling(self):
        """Test that None values are handled gracefully."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Initial state
        assert tracker.max_abs_deviation_last_20 is None
        assert tracker.min_abs_deviation_last_20 is None

        # Pass None - should not update
        tracker.update(high=2650, low=2645, close=2650)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=None)
        assert tracker.max_abs_deviation_last_20 is None
        assert tracker.min_abs_deviation_last_20 is None

        # Add valid value
        tracker.update(high=2655, low=2650, close=2655)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=1.0)
        assert tracker.max_abs_deviation_last_20 == 1.0

        # Pass None again - should not affect history
        tracker.update(high=2656, low=2651, close=2656)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=None)
        assert tracker.max_abs_deviation_last_20 == 1.0  # Unchanged

    def test_deviation_context_export(self):
        """Test that deviation history is exported in StructureContext."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Add some deviations
        tracker.update(high=2650, low=2645, close=2650)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.5)

        tracker.update(high=2655, low=2650, close=2655)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=1.5)

        # Get context
        context = tracker.update(high=2651, low=2648, close=2650)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.2)

        # Next context should have updated values
        context = tracker.update(high=2652, low=2647, close=2651)

        assert context.max_abs_deviation_last_20 == 1.5
        assert context.min_abs_deviation_last_20 == 0.2


class TestVWAPReclaimExcursionScenarios:
    """Test realistic VWAP reclaim scenarios with excursion tracking."""

    def test_valid_reclaim_with_excursion(self):
        """Test valid VWAP reclaim: price excursed away, then returned and consolidated."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Scenario: Price stretches to 1.5 ATR away from VWAP
        for i in range(5):
            tracker.update(high=2655 + i, low=2650 + i, close=2655 + i)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=1.0 + i * 0.1)

        # Check excursion recorded
        assert tracker.max_abs_deviation_last_20 == pytest.approx(1.4, rel=0.01)

        # Price returns to VWAP and consolidates (0.2 ATR away)
        for i in range(5):
            tracker.update(high=2650, low=2648, close=2649)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.2)

        # Excursion still remembered
        assert tracker.max_abs_deviation_last_20 == pytest.approx(1.4, rel=0.01)

        # Current consolidation near VWAP (min should be 0.2)
        assert tracker.min_abs_deviation_last_20 == 0.2

        # This would pass vwap_reclaim_distance constraint (max >= 0.5)

    def test_invalid_reclaim_no_excursion(self):
        """Test invalid VWAP reclaim: price consolidating AT VWAP without prior excursion."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Scenario: Price consolidates near VWAP for 10 bars (never stretched away)
        for i in range(10):
            tracker.update(high=2650, low=2648, close=2649)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.2)

        # No significant excursion
        assert tracker.max_abs_deviation_last_20 == 0.2  # < 0.5 threshold

        # This would fail vwap_reclaim_distance constraint (max < 0.5)

    def test_excursion_aging_out(self):
        """Test that old excursions age out of the 20-bar window."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Bar 1-5: Excursion to 2.0 ATR
        for i in range(5):
            tracker.update(high=2660, low=2655, close=2660)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=2.0)

        assert tracker.max_abs_deviation_last_20 == 2.0

        # Bar 6-20: Consolidation near VWAP (15 bars)
        for i in range(15):
            tracker.update(high=2650, low=2648, close=2649)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.2)

        # Excursion still visible (20 bars total)
        assert tracker.max_abs_deviation_last_20 == 2.0

        # Bar 21: One more bar pushes oldest excursion out
        tracker.update(high=2650, low=2648, close=2649)
        tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.2)

        # Excursion starting to age out (19 bars with 0.2, 1 bar with 2.0)
        assert tracker.max_abs_deviation_last_20 == 2.0

        # Bar 22-25: Continue consolidation (4 more bars)
        for i in range(4):
            tracker.update(high=2650, low=2648, close=2649)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.2)

        # All excursion bars now aged out
        assert tracker.max_abs_deviation_last_20 == 0.2

    def test_multiple_excursions(self):
        """Test tracking max across multiple excursions."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # First excursion: 1.0 ATR
        for i in range(3):
            tracker.update(high=2655, low=2650, close=2655)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=1.0)

        assert tracker.max_abs_deviation_last_20 == 1.0

        # Return to VWAP
        for i in range(3):
            tracker.update(high=2650, low=2648, close=2649)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.1)

        assert tracker.max_abs_deviation_last_20 == 1.0  # First excursion remembered

        # Second excursion: 2.0 ATR (larger)
        for i in range(3):
            tracker.update(high=2665, low=2660, close=2665)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=2.0)

        assert tracker.max_abs_deviation_last_20 == 2.0  # Tracks largest excursion

        # Return to VWAP again
        for i in range(3):
            tracker.update(high=2650, low=2648, close=2649)
            tracker.update_vwap_deviation_history(vwap_deviation_normalized=0.1)

        assert tracker.max_abs_deviation_last_20 == 2.0  # Still remembers largest
