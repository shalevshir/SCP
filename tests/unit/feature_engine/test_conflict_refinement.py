"""Unit tests for refined conflict detection (Task 1: Structural Chop Recalibration).

Tests verify that:
1. Single pullbacks in a trend are NOT flagged as conflict
2. Meaningful conflicts (alternating HH/LL or >= 2 of each) ARE flagged
3. Trend protection prevents false positives (high clarity + confidence)
"""

import pytest

from feature_engine.structure import StructureContextTracker


class TestRefinedConflictDetection:
    """Test suite for refined _detect_conflict() logic."""

    def test_single_pullback_not_conflict(self):
        """Single LL in bullish HH/HL sequence should NOT be conflict."""
        tracker = StructureContextTracker(swing_window=2)
        
        # Build bullish structure with enough bars for swing detection
        # Need at least swing_window*2+1 bars (5 bars) for first swing
        prices = [
            (2640, 2635, 2638),  # Bar 0
            (2645, 2640, 2643),  # Bar 1
            (2650, 2645, 2648),  # Bar 2 - potential swing low at bar 0
            (2655, 2650, 2653),  # Bar 3 - potential swing high
            (2653, 2648, 2650),  # Bar 4 - potential swing low (HL)
            (2658, 2653, 2656),  # Bar 5 - swing high (HH)
            (2656, 2651, 2653),  # Bar 6 - swing low (HL)
            (2661, 2656, 2659),  # Bar 7 - swing high (HH)
            (2659, 2654, 2656),  # Bar 8 - swing low (HL)
            (2656, 2651, 2653),  # Bar 9 - minor LL (single pullback)
        ]
        
        for high, low, close in prices:
            context = tracker.update(high, low, close)
        
        # Should NOT trigger conflict (just 1 LL among HH/HL)
        # The refined logic requires >= 2 of each type
        assert context.structure_conflict_flag is False, \
            f"Single pullback LL should not trigger conflict in bullish trend " \
            f"(labels: {list(tracker.label_history)})"

    def test_meaningful_conflict_detected(self):
        """Alternating HH/LL pattern should trigger conflict."""
        tracker = StructureContextTracker(swing_window=2)
        
        # Build alternating pattern with enough bars for swing detection
        prices = [
            (2650, 2645, 2648),  # Bar 0
            (2655, 2650, 2653),  # Bar 1
            (2660, 2655, 2658),  # Bar 2 - swing high
            (2658, 2653, 2655),  # Bar 3
            (2655, 2650, 2652),  # Bar 4 - swing low
            (2665, 2660, 2663),  # Bar 5 - HH (higher than bar 2)
            (2663, 2658, 2660),  # Bar 6
            (2660, 2640, 2642),  # Bar 7 - LL (lower than bar 4)
            (2670, 2665, 2668),  # Bar 8 - HH again
            (2668, 2663, 2665),  # Bar 9
            (2665, 2635, 2637),  # Bar 10 - LL again
            (2675, 2670, 2673),  # Bar 11 - HH again
        ]
        
        for high, low, close in prices:
            context = tracker.update(high, low, close)
        
        # Should trigger conflict (multiple HH and LL alternating)
        assert context.structure_conflict_flag is True, \
            f"Alternating HH/LL pattern should trigger conflict " \
            f"(labels: {list(tracker.label_history)})"

    def test_trend_protection_overrides_conflict(self):
        """High clarity + confidence should prevent conflict flag."""
        tracker = StructureContextTracker(swing_window=2)
        
        # Build strong bullish trend with high clarity (larger price moves)
        prices = [
            (2640, 2635, 2638),  # Bar 0
            (2650, 2645, 2648),  # Bar 1
            (2660, 2655, 2658),  # Bar 2 - swing high
            (2658, 2653, 2655),  # Bar 3
            (2655, 2645, 2647),  # Bar 4 - swing low (HL)
            (2670, 2665, 2668),  # Bar 5 - HH
            (2668, 2663, 2665),  # Bar 6
            (2665, 2655, 2657),  # Bar 7 - HL
            (2680, 2675, 2678),  # Bar 8 - HH
            (2678, 2673, 2675),  # Bar 9
            (2675, 2665, 2667),  # Bar 10 - HL
            (2690, 2685, 2688),  # Bar 11 - HH
            (2688, 2683, 2685),  # Bar 12
            (2685, 2675, 2677),  # Bar 13 - HL
        ]
        
        for high, low, close in prices:
            context = tracker.update(high, low, close)
        
        # Should have high clarity and confidence
        assert context.structure_clarity >= 0.5, \
            f"Expected clarity >= 0.5, got {context.structure_clarity} " \
            f"(labels: {list(tracker.label_history)})"
        assert context.trend_confidence >= 0.7, \
            f"Expected confidence >= 0.7, got {context.trend_confidence}"
        
        # Now add a single LL (minor pullback)
        # With trend protection, this should NOT trigger conflict
        context = tracker.update(2680, 2660, 2662)  # LL (deeper pullback)
        
        # Trend protection should prevent conflict flag
        # (only 1 LL vs multiple HH/HL, so not severe)
        assert context.structure_conflict_flag is False, \
            f"Single LL in strong trend should not trigger conflict " \
            f"(clarity={context.structure_clarity}, confidence={context.trend_confidence}, " \
            f"labels={list(tracker.label_history)})"
        context = tracker.update(2654, 2644, 2646)  # Minor LL
        
        # Conflict might be detected structurally but should not block
        # with strong trend (this is what we'll implement)

    def test_conflict_requires_meaningful_ratio(self):
        """Require >= 2 of each label type for conflict (not just presence)."""
        tracker = StructureContextTracker(swing_window=2)
        
        # Build sequence with 1 HH and multiple LL (bearish but not conflicting)
        prices = [
            (2650, 2645, 2648),  # Bar 0
            (2655, 2650, 2653),  # Bar 1
            (2660, 2655, 2658),  # Bar 2 - swing high
            (2658, 2653, 2655),  # Bar 3
            (2655, 2650, 2652),  # Bar 4 - swing low
            (2665, 2660, 2663),  # Bar 5 - HH (single opposing label)
            (2663, 2658, 2660),  # Bar 6
            (2660, 2645, 2647),  # Bar 7 - LL
            (2647, 2644, 2645),  # Bar 8
            (2645, 2635, 2637),  # Bar 9 - LL
            (2637, 2634, 2635),  # Bar 10
            (2635, 2625, 2627),  # Bar 11 - LL
        ]
        
        for high, low, close in prices:
            context = tracker.update(high, low, close)
        
        # Should NOT trigger conflict (only 1 HH vs multiple LL - clearly bearish)
        assert context.structure_conflict_flag is False, \
            f"Single opposing label should not trigger conflict " \
            f"(labels: {list(tracker.label_history)})"

    def test_rangebound_whipsaw_triggers_conflict(self):
        """Range-bound whipsaw (multiple HH and LL) should trigger conflict."""
        tracker = StructureContextTracker(swing_window=2)
        
        # Range-bound market with multiple HH and LL
        prices = [
            (2650, 2645, 2648),  # Bar 0
            (2655, 2650, 2653),  # Bar 1
            (2660, 2655, 2658),  # Bar 2 - swing high
            (2658, 2653, 2655),  # Bar 3
            (2655, 2645, 2647),  # Bar 4 - swing low
            (2665, 2660, 2663),  # Bar 5 - HH
            (2663, 2658, 2660),  # Bar 6
            (2660, 2640, 2642),  # Bar 7 - LL
            (2670, 2665, 2668),  # Bar 8 - HH
            (2668, 2663, 2665),  # Bar 9
            (2665, 2638, 2640),  # Bar 10 - LL
            (2675, 2670, 2673),  # Bar 11 - HH
            (2673, 2668, 2670),  # Bar 12
            (2670, 2636, 2638),  # Bar 13 - LL
        ]
        
        for high, low, close in prices:
            context = tracker.update(high, low, close)
        
        # Should trigger conflict (multiple HH and LL in recent history)
        assert context.structure_conflict_flag is True, \
            f"Range-bound whipsaw should trigger conflict " \
            f"(labels: {list(tracker.label_history)})"


class TestStructuralChopWithConflictFix:
    """Test that structural chop uses refined conflict detection."""
    
    def test_structural_chop_not_triggered_in_clean_trend(self):
        """Clean trending structure should NOT trigger structural chop."""
        tracker = StructureContextTracker(swing_window=2)
        
        # Build clean bullish trend
        prices = [
            (2650, 2645, 2648),
            (2655, 2650, 2653),  # HH
            (2653, 2648, 2650),  # HL
            (2658, 2653, 2656),  # HH
            (2656, 2651, 2653),  # HL
            (2661, 2656, 2659),  # HH
        ]
        
        for high, low, close in prices:
            context = tracker.update(high, low, close)
        
        # Should have clean structure without chop
        assert context.is_structural_chop is False, \
            f"Clean trend should not trigger structural chop " \
            f"(clarity={context.structure_clarity}, " \
            f"confidence={context.trend_confidence})"

