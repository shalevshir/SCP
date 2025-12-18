"""Unit tests for VWAP reclaim tracking and second confirmation in StructureContextTracker.

This tests the second-confirmation requirement for VWAP_RECLAIM entries,
ensuring early entries are prevented before pullback fully resolves.
"""

import pytest

from feature_engine.structure import StructureContextTracker


class TestVWAPStateTracking:
    """Test VWAP cross detection and state updates."""

    def test_update_vwap_state_detects_cross_above(self):
        """Test VWAP cross detection when price crosses above."""
        tracker = StructureContextTracker()

        # Initial state - price below VWAP
        tracker.update(high=100.5, low=99.5, close=99.8)
        tracker.update_vwap_state(vwap=100.0, close=99.8)

        # Cross above VWAP
        tracker.update(high=101.0, low=100.0, close=100.5)
        tracker.update_vwap_state(vwap=100.2, close=100.5)

        assert tracker.vwap_reclaim_bar_idx == 1  # Second bar (0-indexed)
        assert tracker.vwap_reclaim_direction == "above"

    def test_update_vwap_state_detects_cross_below(self):
        """Test VWAP cross detection when price crosses below."""
        tracker = StructureContextTracker()

        # Initial state - price above VWAP
        tracker.update(high=101.0, low=100.0, close=100.5)
        tracker.update_vwap_state(vwap=100.2, close=100.5)

        # Cross below VWAP
        tracker.update(high=100.0, low=99.0, close=99.5)
        tracker.update_vwap_state(vwap=100.0, close=99.5)

        assert tracker.vwap_reclaim_bar_idx == 1  # Second bar (0-indexed)
        assert tracker.vwap_reclaim_direction == "below"

    def test_update_volume_state(self):
        """Test volume buffer updates."""
        tracker = StructureContextTracker()

        for i in range(5):
            tracker.update(high=100.0, low=99.0, close=99.5)
            tracker.update_volume_state(volume=1000.0 + i * 100)

        assert len(tracker.volume_buffer) == 5
        assert tracker.volume_buffer[-1] == 1400.0


class TestSecondConfirmationComputation:
    """Test second confirmation computation for various scenarios."""

    def test_vwap_hold_confirmation_long(self):
        """Test VWAP hold confirmation for long direction."""
        tracker = StructureContextTracker()

        # Build up state with VWAP cross
        for i in range(5):
            tracker.update(high=100.0, low=99.0, close=99.5)
            tracker.update_vwap_state(vwap=100.0, close=99.5)
            tracker.update_volume_state(volume=1000.0)

        # Cross above VWAP
        tracker.update(high=101.0, low=100.0, close=100.5)
        tracker.update_vwap_state(vwap=100.2, close=100.5)

        # Hold above VWAP for 2 bars
        tracker.update(high=101.5, low=100.5, close=101.0)
        tracker.update_vwap_state(vwap=100.3, close=101.0)

        tracker.update(high=102.0, low=101.0, close=101.5)
        tracker.update_vwap_state(vwap=100.4, close=101.5)

        # Compute confirmation
        result = tracker.compute_second_confirmation("long")

        assert result["confirmed"] is True
        assert "vwap_hold" in result["reasons"][0]
        assert result["bars_since_reclaim"] == 2

    def test_volume_expansion_confirmation(self):
        """Test volume expansion confirmation."""
        tracker = StructureContextTracker()

        # Build up state with normal volume
        for i in range(10):
            tracker.update(high=100.0, low=99.0, close=99.5)
            tracker.update_vwap_state(vwap=100.0, close=99.5)
            tracker.update_volume_state(volume=1000.0)

        # Cross above VWAP
        tracker.update(high=101.0, low=100.0, close=100.5)
        tracker.update_vwap_state(vwap=100.2, close=100.5)

        # High volume expansion bar
        tracker.update(high=102.0, low=101.0, close=101.8)
        tracker.update_vwap_state(vwap=100.3, close=101.8)
        tracker.update_volume_state(volume=2000.0)  # 2x average

        # Compute confirmation
        result = tracker.compute_second_confirmation("long")

        # Should have either vwap_hold or volume_expansion (or both)
        assert result["confirmed"] is True
        assert result["bars_since_reclaim"] >= 1

    def test_micro_higher_low_confirmation(self):
        """Test micro higher low formation confirmation."""
        tracker = StructureContextTracker()

        # Build up state
        for i in range(5):
            tracker.update(high=100.0, low=99.0, close=99.5)
            tracker.update_vwap_state(vwap=100.0, close=99.5)

        # Cross above VWAP
        tracker.update(high=101.0, low=100.5, close=100.8)
        tracker.update_vwap_state(vwap=100.2, close=100.8)

        # Form higher low above VWAP
        tracker.update(high=101.5, low=100.7, close=101.0)  # Low = 100.7
        tracker.update_vwap_state(vwap=100.3, close=101.0)

        tracker.update(high=102.0, low=100.9, close=101.5)  # Higher low = 100.9
        tracker.update_vwap_state(vwap=100.4, close=101.5)

        # Compute confirmation
        result = tracker.compute_second_confirmation("long")

        # Should confirm via vwap_hold or micro_hl
        assert result["confirmed"] is True

    def test_stale_reclaim_expires_not_auto_confirmed(self):
        """Test stale reclaim EXPIRES after MAX_RECLAIM_AGE bars without confirmation.

        Per vwap_Reclain_fix.mdc Task 3:
        - "If no confirmation within window → setup expires"
        - "Prevent stale reclaim execution"

        Stale reclaims should NOT be auto-confirmed; they should expire.
        """
        tracker = StructureContextTracker()

        # Build up state - price below VWAP
        for i in range(5):
            tracker.update(high=100.0, low=99.0, close=99.5)
            tracker.update_vwap_state(vwap=100.0, close=99.5)

        # Cross above VWAP
        tracker.update(high=101.0, low=100.0, close=100.5)
        tracker.update_vwap_state(vwap=100.2, close=100.5)

        # Wait more than 10 bars WITHOUT any genuine confirmation signals
        # Price doesn't hold, volume doesn't expand, no micro HL
        for i in range(15):
            # Price falls back below VWAP (no hold confirmation)
            tracker.update(high=100.0, low=99.0, close=99.5)
            tracker.update_vwap_state(vwap=100.0, close=99.5)
            tracker.update_volume_state(volume=1000.0)  # Normal volume

        # Compute confirmation
        result = tracker.compute_second_confirmation("long")

        # Stale reclaim should EXPIRE, not be auto-confirmed
        assert result["confirmed"] is False, \
            "Stale reclaims should expire (confirmed=False), not auto-confirm"
        assert result["confirmation_type"] == "expired"
        assert result["bars_since_reclaim"] > 10
        assert "expired" in result["reasons"][0].lower()

    def test_no_confirmation_immediately_after_reclaim(self):
        """Test that no confirmation exists immediately after reclaim (bars_since=0)."""
        tracker = StructureContextTracker()

        # Cross above VWAP
        tracker.update(high=101.0, low=100.0, close=100.5)
        tracker.update_vwap_state(vwap=100.2, close=100.5)

        # Compute confirmation immediately
        result = tracker.compute_second_confirmation("long")

        assert result["confirmed"] is False
        assert result["bars_since_reclaim"] == 0

    def test_independent_long_short_confirmations(self):
        """Test that long and short confirmations are computed independently."""
        tracker = StructureContextTracker()

        # Build up state
        for i in range(5):
            tracker.update(high=100.0, low=99.0, close=99.5)
            tracker.update_vwap_state(vwap=100.0, close=99.5)

        # Cross above VWAP
        tracker.update(high=101.0, low=100.0, close=100.5)
        tracker.update_vwap_state(vwap=100.2, close=100.5)

        # Hold above for 2 bars
        tracker.update(high=101.5, low=100.5, close=101.0)
        tracker.update_vwap_state(vwap=100.3, close=101.0)

        tracker.update(high=102.0, low=101.0, close=101.5)
        tracker.update_vwap_state(vwap=100.4, close=101.5)

        # Compute both directions
        long_result = tracker.compute_second_confirmation("long")
        short_result = tracker.compute_second_confirmation("short")

        # Long should be confirmed (price holding above VWAP)
        assert long_result["confirmed"] is True

        # Short should NOT be confirmed (price is above VWAP, not below)
        assert short_result["confirmed"] is False or short_result["confirmation_type"] is None
