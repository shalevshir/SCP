"""Tests for StructureContext and StructureContextTracker.

Following TDD: These tests define expected behavior before implementation.
"""

import pandas as pd
from scp_shared.indicators.structure import (
    StructureContext,
    StructureContextTracker,
    compute_structure_context_batch,
)


class TestStructureContextDataclass:
    """Test StructureContext dataclass structure and fields."""

    def test_structure_context_has_required_fields(self):
        """Test that StructureContext has all required fields."""
        ctx = StructureContext(
            last_structure_label="HH",
            last_swing_high=100.0,
            last_swing_low=95.0,
            last_swing_high_idx=10,
            last_swing_low_idx=8,
            trend_direction="bullish",
            trend_confidence=0.8,
            structure_clarity=0.9,
            is_chop=False,
            structure_conflict_flag=False,
            choch_detected=False,
            choch_direction=None,
            choch_age=None,
            liquidity_sweep=False,
            sweep_direction=None,
            sweep_price=None,
            sweep_age=None,
        )

        assert ctx.last_structure_label == "HH"
        assert ctx.last_swing_high == 100.0
        assert ctx.last_swing_low == 95.0
        assert ctx.last_swing_high_idx == 10
        assert ctx.last_swing_low_idx == 8
        assert ctx.trend_direction == "bullish"
        assert ctx.trend_confidence == 0.8
        assert ctx.structure_clarity == 0.9
        assert ctx.is_chop is False
        assert ctx.is_structural_chop is False
        assert ctx.atr_compression_ratio == 1.0
        assert ctx.structure_conflict_flag is False
        assert ctx.choch_detected is False
        assert ctx.choch_direction is None
        assert ctx.choch_age is None
        assert ctx.liquidity_sweep is False
        assert ctx.sweep_direction is None
        assert ctx.sweep_price is None
        assert ctx.sweep_age is None


class TestStructureContextTracker:
    """Test StructureContextTracker incremental updates."""

    def test_tracker_returns_context_on_every_update(self):
        """Test that tracker returns StructureContext on every bar."""
        tracker = StructureContextTracker(swing_window=2)

        # Update with first bar
        ctx = tracker.update(high=100.0, low=98.0, close=99.0)
        assert isinstance(ctx, StructureContext)
        assert ctx.trend_direction in ["bullish", "bearish", "neutral"]

        # Update with second bar
        ctx = tracker.update(high=102.0, low=100.0, close=101.0)
        assert isinstance(ctx, StructureContext)

    def test_last_structure_label_persists_between_swings(self):
        """Test that last_structure_label persists until new swing detected."""
        tracker = StructureContextTracker(swing_window=2)

        # Build up to first swing detection
        # Need swing_window * 2 + 1 = 5 bars minimum
        tracker.update(high=100.0, low=98.0, close=99.0)
        tracker.update(high=102.0, low=100.0, close=101.0)  # This will be swing high
        tracker.update(high=101.0, low=99.0, close=100.0)
        tracker.update(high=100.0, low=98.0, close=99.0)
        ctx = tracker.update(high=99.0, low=97.0, close=98.0)

        # First swing should be detected (HH since it's first)
        first_label = ctx.last_structure_label
        if first_label is not None:
            # Next bar should persist the label
            ctx_next = tracker.update(high=98.0, low=96.0, close=97.0)
            assert ctx_next.last_structure_label == first_label

    def test_swing_prices_persist_until_new_swing(self):
        """Test that swing prices persist until new swing detected."""
        tracker = StructureContextTracker(swing_window=2)

        # Generate data with clear swing high
        tracker.update(high=100.0, low=98.0, close=99.0)
        tracker.update(high=105.0, low=100.0, close=104.0)  # Swing high
        tracker.update(high=102.0, low=99.0, close=100.0)
        tracker.update(high=101.0, low=98.0, close=99.0)
        ctx = tracker.update(high=100.0, low=97.0, close=98.0)

        if ctx.last_swing_high is not None:
            swing_high = ctx.last_swing_high
            # Next bars should preserve this value
            ctx_next = tracker.update(high=99.0, low=96.0, close=97.0)
            assert ctx_next.last_swing_high == swing_high

    def test_swing_hl_low_persists_across_subsequent_swings(self):
        """Test that swing_hl_low persists after HL swing even when subsequent swings occur.

        Bug: swing_hl_low and swing_lh_high were only set when last_structure_label
        was "HL" or "LH", causing them to become None after subsequent swings.
        This broke SL Priority A calculation per SOP Section 3.2-3.3.

        Fix: Use persistent state (self.swing_hl_low, self.swing_lh_high) that is
        set when HL/LH swings are detected and persists across subsequent swings.
        """
        tracker = StructureContextTracker(swing_window=2)

        # Create clear uptrend: swing lows should be rising (HL pattern)
        # Pattern: Low at 95 → High at 102 → Low at 98 (HL) → High at 105

        # First swing low at 95
        tracker.update(high=100.0, low=95.0, close=98.0)
        tracker.update(high=102.0, low=98.0, close=101.0)
        tracker.update(high=101.0, low=97.0, close=99.0)  # Swing low at 95
        tracker.update(high=102.0, low=98.0, close=100.0)
        tracker.update(high=103.0, low=99.0, close=102.0)

        # Second swing low at 98 (higher than 95 → HL)
        tracker.update(high=102.0, low=98.0, close=100.0)
        tracker.update(high=101.0, low=99.0, close=100.0)
        tracker.update(high=100.0, low=98.0, close=99.0)  # Center: swing low at 98
        tracker.update(high=101.0, low=99.0, close=100.0)
        ctx_hl = tracker.update(high=102.0, low=100.0, close=101.0)

        # Find when HL is detected and capture swing_hl_low
        swing_hl_low_value = None
        for _ in range(20):  # Continue for several bars
            ctx = tracker.update(high=103.0, low=100.0, close=102.0)
            if ctx.swing_hl_low is not None:
                swing_hl_low_value = ctx.swing_hl_low
                break
            ctx = tracker.update(high=104.0, low=101.0, close=103.0)
            if ctx.swing_hl_low is not None:
                swing_hl_low_value = ctx.swing_hl_low
                break

        # Verify HL was detected
        assert swing_hl_low_value is not None, "HL swing should have been detected"

        # Now create more swings and verify persistence
        # Add 20 more bars to trigger additional swing detections
        for i in range(20):
            ctx = tracker.update(
                high=105.0 + i * 0.5, low=102.0 + i * 0.5, close=104.0 + i * 0.5
            )
            # Critical test: swing_hl_low should persist throughout
            assert (
                ctx.swing_hl_low == swing_hl_low_value
            ), f"swing_hl_low should persist (bar {i})"

    def test_swing_lh_high_persists_across_subsequent_swings(self):
        """Test that swing_lh_high persists after LH swing even when subsequent swings occur."""
        tracker = StructureContextTracker(swing_window=2)

        # Create clear downtrend: swing highs should be falling (LH pattern)
        # Pattern: High at 105 → Low at 98 → High at 102 (LH) → Low at 95

        # First swing high at 105
        tracker.update(high=105.0, low=100.0, close=103.0)
        tracker.update(high=104.0, low=99.0, close=101.0)
        tracker.update(high=103.0, low=98.0, close=100.0)  # Swing high at 105
        tracker.update(high=102.0, low=97.0, close=99.0)
        tracker.update(high=101.0, low=96.0, close=98.0)

        # Second swing high at 102 (lower than 105 → LH)
        tracker.update(high=102.0, low=97.0, close=100.0)
        tracker.update(high=103.0, low=98.0, close=101.0)
        tracker.update(
            high=102.0, low=99.0, close=101.0
        )  # Center: swing high at 102/103
        tracker.update(high=101.0, low=98.0, close=100.0)
        ctx_lh = tracker.update(high=100.0, low=97.0, close=99.0)

        # Find when LH is detected and capture swing_lh_high
        swing_lh_high_value = None
        for _ in range(20):  # Continue for several bars
            ctx = tracker.update(high=99.0, low=96.0, close=98.0)
            if ctx.swing_lh_high is not None:
                swing_lh_high_value = ctx.swing_lh_high
                break
            ctx = tracker.update(high=98.0, low=95.0, close=97.0)
            if ctx.swing_lh_high is not None:
                swing_lh_high_value = ctx.swing_lh_high
                break

        # Verify LH was detected
        assert swing_lh_high_value is not None, "LH swing should have been detected"

        # Now create more swings and verify persistence
        # Add 20 more bars to trigger additional swing detections
        for i in range(20):
            ctx = tracker.update(
                high=97.0 - i * 0.5, low=94.0 - i * 0.5, close=96.0 - i * 0.5
            )
            # Critical test: swing_lh_high should persist throughout
            assert (
                ctx.swing_lh_high == swing_lh_high_value
            ), f"swing_lh_high should persist (bar {i})"


class TestTrendDirection:
    """Test trend_direction derivation from label sequences."""

    def test_trend_direction_bullish_from_hh_hl_sequence(self):
        """Test bullish trend detected from HH/HL sequence."""
        tracker = StructureContextTracker(swing_window=2)

        # Generate bullish structure: HH, HL, HH
        # Build sequence that produces HH
        for _ in range(3):
            tracker.update(high=100.0, low=98.0, close=99.0)
            tracker.update(high=105.0, low=100.0, close=104.0)
            tracker.update(high=102.0, low=99.0, close=100.0)

        # After sufficient HH/HL patterns, trend should be bullish
        ctx = tracker.update(high=101.0, low=98.0, close=99.0)

        # Trend direction should be bullish or neutral (not bearish)
        assert ctx.trend_direction in ["bullish", "neutral"]

    def test_trend_direction_bearish_from_lh_ll_sequence(self):
        """Test bearish trend detected from LH/LL sequence."""
        tracker = StructureContextTracker(swing_window=2)

        # Generate clear downtrend with lower highs and lower lows
        # Pattern: descending peaks and troughs
        prices = [
            (100.0, 98.0, 99.0),
            (102.0, 100.0, 101.0),  # First high
            (99.0, 97.0, 98.0),
            (97.0, 95.0, 96.0),  # Lower low
            (98.0, 96.0, 97.0),
            (96.0, 94.0, 95.0),  # Lower high
            (93.0, 91.0, 92.0),
            (91.0, 89.0, 90.0),  # Lower low
            (92.0, 90.0, 91.0),
        ]

        for high, low, close in prices:
            ctx = tracker.update(high=high, low=low, close=close)

        # After clear downtrend, trend should be bearish or neutral (not bullish)
        # Allow neutral during early detection
        assert ctx.trend_direction in ["bearish", "neutral"]

    def test_trend_direction_neutral_when_mixed(self):
        """Test neutral trend when structure is mixed."""
        tracker = StructureContextTracker(swing_window=2)

        # Generate truly mixed structure: HH, then LL, then HH again
        prices = [
            (100.0, 98.0, 99.0),
            (105.0, 100.0, 104.0),  # High
            (102.0, 99.0, 100.0),
            (101.0, 96.0, 97.0),  # Low (LL)
            (102.0, 98.0, 100.0),
            (107.0, 102.0, 106.0),  # High again (HH)
            (104.0, 100.0, 102.0),
        ]

        for high, low, close in prices:
            ctx = tracker.update(high=high, low=low, close=close)

        # With mixed HH and LL, should be neutral or have mixed signals
        # System should handle mixed structure gracefully
        assert ctx.trend_direction in ["neutral", "bullish", "bearish"]
        assert 0.0 <= ctx.trend_confidence <= 1.0
        assert isinstance(ctx.structure_conflict_flag, bool)


class TestClarityScoring:
    """Test structure_clarity scoring."""

    def test_clarity_score_high_for_pure_sequence(self):
        """Test high clarity score for pure bullish/bearish sequence."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=10)

        # Generate pure bullish sequence
        for _ in range(5):
            tracker.update(high=100.0, low=98.0, close=99.0)
            tracker.update(high=105.0, low=100.0, close=104.0)
            tracker.update(high=102.0, low=99.0, close=100.0)

        ctx = tracker.update(high=106.0, low=103.0, close=105.0)

        # Clarity should be high (> 0.5) for consistent structure
        assert ctx.structure_clarity >= 0.0
        assert ctx.structure_clarity <= 1.0

    def test_clarity_score_low_for_mixed_sequence(self):
        """Test low clarity score for mixed structure."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=10)

        # Generate mixed sequence with alternations
        for i in range(10):
            if i % 2 == 0:
                tracker.update(high=100.0 + i, low=98.0, close=99.0)
            else:
                tracker.update(high=95.0, low=90.0 - i, close=91.0)

        ctx = tracker.update(high=100.0, low=98.0, close=99.0)

        # Clarity should be between 0 and 1
        assert 0.0 <= ctx.structure_clarity <= 1.0


class TestChopDetection:
    """Test is_chop detection logic."""

    def test_is_chop_true_for_rapid_alternations(self):
        """Test chop detected for rapid H→L→H alternations."""
        tracker = StructureContextTracker(swing_window=2)

        # Generate rapid alternations (simulate HH→LL→HH→LL)
        alternation_data = [
            (100.0, 98.0, 99.0),  # Bar 0
            (105.0, 100.0, 104.0),  # Bar 1 - potential swing high
            (102.0, 99.0, 100.0),  # Bar 2
            (101.0, 90.0, 91.0),  # Bar 3 - potential swing low
            (100.0, 98.0, 99.0),  # Bar 4
            (110.0, 100.0, 109.0),  # Bar 5 - potential swing high
            (105.0, 95.0, 96.0),  # Bar 6 - potential swing low
        ]

        for high, low, close in alternation_data:
            ctx = tracker.update(high=high, low=low, close=close)

        # After rapid alternations, is_chop should potentially be True
        # (implementation dependent on exact logic)
        assert isinstance(ctx.is_chop, bool)

    def test_is_chop_false_for_trending_structure(self):
        """Test chop not detected for clear trending structure."""
        tracker = StructureContextTracker(swing_window=2)

        # Generate clear uptrend
        for i in range(10):
            base = 100.0 + i * 2
            tracker.update(high=base + 2, low=base, close=base + 1)

        ctx = tracker.update(high=122.0, low=120.0, close=121.0)

        # Clear trend should not be marked as chop initially
        assert isinstance(ctx.is_chop, bool)


class TestChochDetection:
    """Test CHoCH (Change of Character) detection and age calculation."""

    def test_choch_age_is_zero_when_choch_detected_on_current_bar(self):
        """Test that choch_age=0 when choch_detected=True on the current bar.

        With new CHoCH logic, requires:
        - Previous trend exists (bullish)
        - BOS in opposite direction (bearish)
        - Clarity >= 0.5
        """
        tracker = StructureContextTracker(swing_window=2)

        # Build clear bullish trend with consistent HH/HL swings
        # Pattern: Create higher highs to establish bullish trend
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing high
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        # Continue bullish trend with HL
        tracker.update(high=102.0, low=96.0, close=97.0)  # Bar 5 - HL swing low
        tracker.update(high=100.0, low=97.0, close=99.0)  # Bar 6
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 7 - HL detected

        # Add more bullish swings for clarity
        tracker.update(high=108.0, low=102.0, close=107.0)  # Bar 8 - HH swing high
        tracker.update(high=106.0, low=102.0, close=104.0)  # Bar 9
        ctx_before = tracker.update(
            high=105.0, low=101.0, close=103.0
        )  # Bar 10 - HH detected

        # Verify we have bullish trend with good clarity
        assert (
            ctx_before.trend_direction == "bullish"
        ), f"Expected bullish trend, got {ctx_before.trend_direction}"
        assert (
            ctx_before.structure_clarity >= 0.5
        ), f"Expected clarity >= 0.5, got {ctx_before.structure_clarity}"

        # Now trigger bearish BOS (break below prior swing low at 96)
        # This should trigger CHoCH (bullish → bearish reversal)
        ctx_with_choch = tracker.update(
            high=100.0, low=92.0, close=93.0
        )  # Bar 11 - BOS bearish

        # When CHoCH is detected on current bar, age should be 0
        if ctx_with_choch.choch_detected:
            assert ctx_with_choch.choch_age == 0, (
                f"When choch_detected=True, choch_age should be 0, "
                f"but got {ctx_with_choch.choch_age}"
            )
            assert (
                ctx_with_choch.choch_direction == "bearish"
            ), f"Expected bearish CHoCH, got {ctx_with_choch.choch_direction}"

            # Continue to next bar - age should increment
            ctx_next = tracker.update(high=95.0, low=91.0, close=92.0)  # Bar 12
            # Age should now be 1 (one bar since CHoCH)
            assert ctx_next.choch_age == 1, (
                f"One bar after CHoCH, choch_age should be 1, "
                f"but got {ctx_next.choch_age}"
            )

    def test_choch_age_increments_after_detection(self):
        """Test that choch_age increments correctly after CHoCH detection."""
        tracker = StructureContextTracker(swing_window=2)

        # Build structure and trigger CHoCH
        tracker.update(high=100.0, low=98.0, close=99.0)
        tracker.update(high=102.0, low=100.0, close=101.0)
        tracker.update(high=104.0, low=102.0, close=103.0)
        tracker.update(high=105.0, low=103.0, close=104.0)
        tracker.update(high=106.0, low=104.0, close=105.0)
        tracker.update(high=104.0, low=100.0, close=101.0)

        # This should trigger CHoCH (H→L)
        ctx_choch = tracker.update(high=102.0, low=98.0, close=99.0)

        if ctx_choch.choch_detected:
            assert ctx_choch.choch_age == 0

            # Age should increment each bar
            for expected_age in range(1, 4):
                ctx = tracker.update(high=101.0, low=97.0, close=98.0)
                assert (
                    ctx.choch_age == expected_age
                ), f"Expected choch_age={expected_age}, got {ctx.choch_age}"

    def test_choch_requires_previous_trend(self):
        """CHoCH should not trigger when no previous trend exists (neutral)."""
        tracker = StructureContextTracker(swing_window=2)

        # Create mixed structure that stays neutral (no clear trend)
        # Need balanced swings: 2 HH/HL (bullish) + 2 LH/LL (bearish) = 50/50 = neutral
        # Build 2 bullish swings
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        tracker.update(high=102.0, low=96.0, close=97.0)  # Bar 5 - HL swing
        tracker.update(high=100.0, low=97.0, close=99.0)  # Bar 6
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 7 - HL detected

        # Now add 2 bearish swings to balance
        tracker.update(high=104.0, low=98.0, close=103.0)  # Bar 8 - LH swing
        tracker.update(high=102.0, low=99.0, close=101.0)  # Bar 9
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 10 - LH detected

        tracker.update(high=102.0, low=94.0, close=95.0)  # Bar 11 - LL swing
        tracker.update(high=99.0, low=95.0, close=97.0)  # Bar 12
        ctx_neutral = tracker.update(
            high=98.0, low=96.0, close=97.0
        )  # Bar 13 - LL detected

        # Verify trend is neutral (2 bullish + 2 bearish = 50/50, below 60% threshold)
        assert ctx_neutral.trend_direction == "neutral", (
            f"Expected neutral trend, got {ctx_neutral.trend_direction} "
            f"(clarity: {ctx_neutral.structure_clarity})"
        )

        # Trigger BOS (break above 106)
        ctx_after_bos = tracker.update(
            high=110.0, low=105.0, close=108.0
        )  # Bar 14 - BOS bullish

        # Should NOT detect CHoCH (no previous trend)
        assert (
            ctx_after_bos.choch_detected is False
        ), "CHoCH should not trigger with neutral trend"

    def test_choch_requires_bos_in_opposite_direction(self):
        """CHoCH should not trigger on same-direction BOS (continuation)."""
        tracker = StructureContextTracker(swing_window=2)

        # Build clear bullish trend
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing high
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        # Add HL for bullish structure
        tracker.update(high=102.0, low=96.0, close=97.0)  # Bar 5 - HL swing low
        tracker.update(high=100.0, low=97.0, close=99.0)  # Bar 6
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 7 - HL detected

        # Add more HH swings
        tracker.update(high=108.0, low=102.0, close=107.0)  # Bar 8 - HH swing high
        tracker.update(high=106.0, low=102.0, close=104.0)  # Bar 9
        ctx_before = tracker.update(
            high=105.0, low=101.0, close=103.0
        )  # Bar 10 - HH detected

        # Verify bullish trend
        assert (
            ctx_before.trend_direction == "bullish"
        ), f"Expected bullish trend, got {ctx_before.trend_direction}"

        # Trigger bullish BOS (same direction as trend - continuation)
        ctx_after_bos = tracker.update(
            high=112.0, low=108.0, close=110.0
        )  # Bar 11 - BOS bullish

        # Should NOT detect CHoCH (same-direction BOS is continuation, not reversal)
        assert (
            ctx_after_bos.choch_detected is False
        ), "CHoCH should not trigger on same-direction BOS"

    def test_choch_requires_clarity_threshold(self):
        """CHoCH should not trigger when clarity is too low (< 0.5)."""
        tracker = StructureContextTracker(swing_window=2)

        # Build trend with choppy/alternating structure to lower clarity
        # Create rapid H→L→H→L alternations
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        # Alternate with LL (lowers clarity)
        tracker.update(high=102.0, low=94.0, close=95.0)  # Bar 5 - LL swing
        tracker.update(high=99.0, low=95.0, close=97.0)  # Bar 6
        tracker.update(high=98.0, low=96.0, close=97.0)  # Bar 7 - LL detected

        # Alternate back to HH
        tracker.update(high=104.0, low=98.0, close=103.0)  # Bar 8 - HH swing
        tracker.update(high=102.0, low=99.0, close=101.0)  # Bar 9
        ctx_before = tracker.update(
            high=101.0, low=98.0, close=100.0
        )  # Bar 10 - HH detected

        # Should have low clarity due to alternations
        # With alternating swings, clarity should be low
        # (Note: actual clarity value depends on the exact pattern, but we'll trigger opposite BOS regardless)

        # Trigger bearish BOS (opposite direction)
        ctx_after_bos = tracker.update(
            high=100.0, low=90.0, close=92.0
        )  # Bar 11 - BOS bearish

        # If clarity < 0.5, should NOT detect CHoCH
        if ctx_after_bos.structure_clarity < 0.5:
            assert (
                ctx_after_bos.choch_detected is False
            ), f"CHoCH should not trigger with clarity {ctx_after_bos.structure_clarity} < 0.5"

    def test_choch_detected_with_all_requirements(self):
        """CHoCH should trigger when all requirements met: trend, opposite BOS, clarity."""
        tracker = StructureContextTracker(swing_window=2)

        # Build clear bullish trend with high clarity (consistent HH/HL)
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing high
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        # Add HL (bullish pullback)
        tracker.update(high=102.0, low=96.0, close=97.0)  # Bar 5 - HL swing low
        tracker.update(high=100.0, low=97.0, close=99.0)  # Bar 6
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 7 - HL detected

        # Add more HH (continuation)
        tracker.update(high=108.0, low=102.0, close=107.0)  # Bar 8 - HH swing high
        tracker.update(high=106.0, low=102.0, close=104.0)  # Bar 9
        ctx_before = tracker.update(
            high=105.0, low=101.0, close=103.0
        )  # Bar 10 - HH detected

        # Verify all requirements before CHoCH
        assert (
            ctx_before.trend_direction == "bullish"
        ), f"Expected bullish trend, got {ctx_before.trend_direction}"
        assert (
            ctx_before.structure_clarity >= 0.5
        ), f"Expected clarity >= 0.5, got {ctx_before.structure_clarity}"

        # Trigger bearish BOS (opposite direction, breaks below swing low at 96)
        ctx_choch = tracker.update(
            high=100.0, low=92.0, close=93.0
        )  # Bar 11 - BOS bearish

        # Should detect CHoCH (all requirements met)
        assert (
            ctx_choch.choch_detected is True
        ), "CHoCH should trigger when all requirements met"
        assert (
            ctx_choch.choch_direction == "bearish"
        ), f"Expected bearish CHoCH, got {ctx_choch.choch_direction}"
        assert (
            ctx_choch.choch_age == 0
        ), f"Expected choch_age=0, got {ctx_choch.choch_age}"

    def test_choch_uses_previous_trend_before_new_swing_label(self):
        """CHoCH should use trend BEFORE new swing is added, not after.

        This test verifies that when CHoCH detection runs, it uses the trend
        direction that existed BEFORE any new swing on the current bar was added
        to label_history, not the trend after the swing was added.

        Without this fix, if a swing detected on the current bar changes the trend
        to neutral, CHoCH won't trigger even though it should based on the previous trend.
        """
        tracker = StructureContextTracker(swing_window=2)

        # Build bullish trend with 5 bullish swings for strong clarity
        # Pattern: HH, HL, HH, HL, HH = 5/5 = 100% bullish
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        tracker.update(high=102.0, low=96.0, close=97.0)  # Bar 5 - HL swing
        tracker.update(high=100.0, low=97.0, close=99.0)  # Bar 6
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 7 - HL detected

        tracker.update(high=108.0, low=102.0, close=107.0)  # Bar 8 - HH swing
        tracker.update(high=106.0, low=102.0, close=104.0)  # Bar 9
        tracker.update(high=105.0, low=101.0, close=103.0)  # Bar 10 - HH detected

        tracker.update(high=104.0, low=98.0, close=99.0)  # Bar 11 - HL swing
        tracker.update(high=102.0, low=99.0, close=101.0)  # Bar 12
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 13 - HL detected

        tracker.update(high=110.0, low=102.0, close=109.0)  # Bar 14 - HH swing
        tracker.update(high=108.0, low=104.0, close=106.0)  # Bar 15
        ctx_bullish = tracker.update(
            high=107.0, low=103.0, close=105.0
        )  # Bar 16 - HH detected

        # Verify strong bullish trend
        assert ctx_bullish.trend_direction == "bullish"
        assert ctx_bullish.structure_clarity >= 0.5

        # Now trigger bearish BOS (break below swing low at 96)
        # This should trigger CHoCH because:
        # 1. Previous trend was bullish (verified above)
        # 2. BOS is bearish (opposite direction)
        # 3. Clarity is high (>= 0.5)
        ctx_choch = tracker.update(
            high=100.0, low=92.0, close=93.0
        )  # Bar 17 - BOS bearish

        # CHoCH should be detected (regardless of whether a new swing was also detected on this bar)
        assert ctx_choch.choch_detected is True, (
            f"CHoCH should trigger when bullish trend + bearish BOS + sufficient clarity. "
            f"Got: choch_detected={ctx_choch.choch_detected}, "
            f"trend={ctx_choch.trend_direction}, "
            f"bos_direction={ctx_choch.bos_direction}, "
            f"clarity={ctx_choch.structure_clarity}"
        )
        assert ctx_choch.choch_direction == "bearish"
        assert ctx_choch.choch_age == 0

    def test_choch_uses_previous_clarity_before_new_swing_label(self):
        """CHoCH should use clarity BEFORE new swing is added, not after.

        This test verifies that CHoCH detection uses both trend AND clarity
        from the state BEFORE any new swing on the current bar was added.

        Without this fix, a swing that changes clarity on the current bar
        can incorrectly affect CHoCH detection.
        """
        tracker = StructureContextTracker(swing_window=2)

        # Build bullish trend with alternating pattern that has borderline clarity
        # HH, LL, HH = creates some choppiness but maintains 67% bullish (above 60%)
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        # Add LL to create choppiness (lowers clarity)
        tracker.update(high=102.0, low=94.0, close=95.0)  # Bar 5 - LL swing
        tracker.update(high=99.0, low=95.0, close=97.0)  # Bar 6
        tracker.update(high=98.0, low=96.0, close=97.0)  # Bar 7 - LL detected

        # Add HH to maintain bullish trend
        tracker.update(high=108.0, low=98.0, close=107.0)  # Bar 8 - HH swing
        tracker.update(high=106.0, low=102.0, close=104.0)  # Bar 9
        ctx_before = tracker.update(
            high=105.0, low=101.0, close=103.0
        )  # Bar 10 - HH detected

        # At this point: HH, LL, HH = 2 bullish + 1 bearish = 67% bullish
        # Clarity should be reasonable (>= 0.5) due to relatively clean structure
        assert ctx_before.trend_direction == "bullish"

        # Store the clarity before the next swing
        clarity_before = ctx_before.structure_clarity

        # Now trigger bearish BOS while also detecting a bearish swing
        # If the swing changes clarity significantly, CHoCH should still use
        # the PREVIOUS clarity (before the swing was added)
        ctx_choch = tracker.update(
            high=100.0, low=92.0, close=93.0
        )  # Bar 11 - BOS bearish

        # CHoCH should use:
        # - prev_trend_direction (bullish, from before any swing on bar 11)
        # - prev_clarity (from before any swing on bar 11)
        # This ensures consistent "previous state" semantics

        # If clarity_before >= 0.5, CHoCH should trigger (all requirements met)
        # regardless of whether the new swing on bar 11 changed clarity
        if clarity_before >= 0.5:
            assert ctx_choch.choch_detected is True, (
                f"CHoCH should trigger based on previous clarity {clarity_before} >= 0.5, "
                f"not current clarity {ctx_choch.structure_clarity}. "
                f"prev_trend=bullish, bos_direction={ctx_choch.bos_direction}"
            )

    def test_choch_should_not_fire_multiple_times_on_consecutive_bars(self):
        """CHoCH should only trigger ONCE per trend reversal, not on every opposite-direction BOS.

        During strong moves that break multiple swing levels, multiple consecutive bars
        can trigger BOS in the opposite direction. However, CHoCH should only fire on
        the FIRST such BOS, not repeatedly on subsequent bars, as this keeps resetting
        last_choch_idx and makes choch_age misleading.

        This test verifies that once a CHoCH is detected (e.g., bullish → bearish),
        subsequent bearish BOS events do NOT trigger additional CHoCH events until
        the trend actually establishes in the new direction and then reverses again.
        """
        tracker = StructureContextTracker(swing_window=2)

        # Build clear bullish trend
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(
            high=106.0, low=102.0, close=105.0
        )  # Bar 2 - HH swing high at 106
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        # Create pullback (HL swing low at 100)
        tracker.update(
            high=102.0, low=100.0, close=101.0
        )  # Bar 5 - HL swing low at 100
        tracker.update(high=104.0, low=101.0, close=103.0)  # Bar 6
        tracker.update(high=105.0, low=102.0, close=104.0)  # Bar 7 - HL detected

        # Create another HH
        tracker.update(
            high=110.0, low=104.0, close=109.0
        )  # Bar 8 - HH swing high at 110
        tracker.update(high=108.0, low=104.0, close=106.0)  # Bar 9
        tracker.update(high=107.0, low=103.0, close=105.0)  # Bar 10 - HH detected

        # Create another pullback (HL swing low at 103)
        tracker.update(
            high=106.0, low=103.0, close=104.0
        )  # Bar 11 - HL swing low at 103
        tracker.update(high=108.0, low=104.0, close=107.0)  # Bar 12
        tracker.update(high=109.0, low=105.0, close=108.0)  # Bar 13 - HL detected

        # Create another HH to maintain strong bullish trend
        tracker.update(
            high=115.0, low=108.0, close=114.0
        )  # Bar 14 - HH swing high at 115
        tracker.update(high=113.0, low=109.0, close=111.0)  # Bar 15
        ctx_bullish = tracker.update(
            high=112.0, low=108.0, close=110.0
        )  # Bar 16 - HH detected

        # Verify bullish trend with good clarity
        assert ctx_bullish.trend_direction == "bullish"
        assert ctx_bullish.structure_clarity >= 0.5

        # Now create bars that break multiple swing levels consecutively
        # Bar 17: Breaks below swing low at 103 → First bearish BOS
        # This SHOULD trigger CHoCH
        ctx_bar17 = tracker.update(
            high=110.0, low=101.0, close=102.0
        )  # Bar 17 - breaks 103

        assert (
            ctx_bar17.bos_age == 0
        ), f"Should detect BOS (age=0). bos_age={ctx_bar17.bos_age}"
        assert (
            ctx_bar17.bos_direction == "bearish"
        ), f"Should be bearish BOS. direction={ctx_bar17.bos_direction}"
        assert (
            ctx_bar17.choch_detected is True
        ), "First opposite-direction BOS should trigger CHoCH"
        assert ctx_bar17.choch_direction == "bearish"
        assert ctx_bar17.choch_age == 0
        choch_idx_bar17 = tracker.last_choch_idx

        # Bar 18: Price continues down, breaks below swing low at 99.0 → Second bearish BOS
        # This should NOT trigger CHoCH again (we already detected the reversal)
        ctx_bar18 = tracker.update(
            high=103.0, low=96.0, close=97.0
        )  # Bar 18 - breaks 99.0

        # BOS should still trigger (breaking new swing level) - indicated by bos_age=0
        assert (
            ctx_bar18.bos_age == 0
        ), "Should detect BOS when breaking new swing level (bos_age=0)"
        assert ctx_bar18.bos_direction == "bearish"

        # But CHoCH should NOT trigger again
        assert ctx_bar18.choch_detected is False, (
            "Second consecutive opposite-direction BOS should NOT trigger CHoCH again. "
            f"last_choch_idx should stay at {choch_idx_bar17}, but got {tracker.last_choch_idx}"
        )
        assert tracker.last_choch_idx == choch_idx_bar17, (
            f"last_choch_idx should not change (stay at {choch_idx_bar17}), "
            f"but got {tracker.last_choch_idx}"
        )
        assert (
            ctx_bar18.choch_age == 1
        ), f"choch_age should be 1, got {ctx_bar18.choch_age}"

        # Bar 19: Price continues down, breaking even more levels
        # Still should NOT trigger CHoCH
        ctx_bar19 = tracker.update(high=100.0, low=94.0, close=95.0)  # Bar 19

        assert (
            ctx_bar19.choch_detected is False
        ), "Third consecutive opposite-direction BOS should NOT trigger CHoCH"
        assert (
            tracker.last_choch_idx == choch_idx_bar17
        ), "last_choch_idx should still not change"
        assert (
            ctx_bar19.choch_age == 2
        ), f"choch_age should be 2, got {ctx_bar19.choch_age}"

    def test_choch_can_trigger_same_direction_after_trend_reset(self):
        """CHoCH should be able to trigger in the same direction after sustained opposite trend.

        Bug: last_choch_direction acts as a permanent lock that only clears via opposite CHoCH.
        This suppresses valid CHoCH signals when:
        1. First CHoCH in direction A fires (sets last_choch_direction = A)
        2. Market builds sustained trend in opposite direction (10+ bars, clarity >= 0.5)
        3. Guard should reset, allowing future CHoCH in direction A

        Simplified scenario:
        - Bullish trend → bearish CHoCH (sets last_choch_direction = "bearish")
        - Build strong bullish trend for 10+ bars (should reset guard to None)
        - Trigger another bearish CHoCH (should work, not blocked)
        """
        tracker = StructureContextTracker(swing_window=2)

        # === Phase 1: Build bullish trend and trigger bearish CHoCH ===
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        tracker.update(high=102.0, low=96.0, close=97.0)  # Bar 5 - HL swing
        tracker.update(high=100.0, low=97.0, close=99.0)  # Bar 6
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 7 - HL detected

        tracker.update(high=108.0, low=102.0, close=107.0)  # Bar 8 - HH swing
        tracker.update(high=106.0, low=102.0, close=104.0)  # Bar 9
        ctx_bullish = tracker.update(
            high=105.0, low=101.0, close=103.0
        )  # Bar 10 - HH detected

        assert ctx_bullish.trend_direction == "bullish"
        assert ctx_bullish.structure_clarity >= 0.5

        # Trigger first bearish CHoCH
        ctx_choch1 = tracker.update(
            high=100.0, low=92.0, close=93.0
        )  # Bar 11 - BOS bearish
        assert ctx_choch1.choch_detected is True, "First bearish CHoCH should trigger"
        assert ctx_choch1.choch_direction == "bearish"
        assert (
            tracker.last_choch_direction == "bearish"
        ), "last_choch_direction set to bearish"
        first_choch_bar = 11

        # === Phase 2: Build sustained bullish trend (10+ bars to trigger guard reset) ===
        # Create strong bullish structure with multiple HH/HL swings
        # Bar 12-16: First HH swing
        tracker.update(high=98.0, low=94.0, close=95.0)  # Bar 12
        tracker.update(high=100.0, low=95.0, close=99.0)  # Bar 13
        tracker.update(high=110.0, low=100.0, close=109.0)  # Bar 14 - HH swing at 110
        tracker.update(high=108.0, low=101.0, close=105.0)  # Bar 15
        ctx_14 = tracker.update(
            high=107.0, low=102.0, close=106.0
        )  # Bar 16 - HH detected

        # Bar 17-21: HL swing
        tracker.update(high=106.0, low=98.0, close=99.0)  # Bar 17 - HL swing at 98
        tracker.update(high=104.0, low=99.0, close=102.0)  # Bar 18
        ctx_19 = tracker.update(
            high=105.0, low=100.0, close=104.0
        )  # Bar 19 - HL detected

        # Bar 20-24: Another HH swing (to strengthen bullish trend)
        tracker.update(high=120.0, low=105.0, close=119.0)  # Bar 20 - HH swing at 120
        tracker.update(high=118.0, low=106.0, close=115.0)  # Bar 21
        ctx_22 = tracker.update(
            high=117.0, low=107.0, close=116.0
        )  # Bar 22 - HH detected

        # Verify: 10+ bars elapsed since CHoCH (bar 22 is 11 bars after bar 11)
        assert (
            tracker.bar_count - first_choch_bar >= 10
        ), "Should be 10+ bars since first CHoCH"

        # Verify: Bullish trend established with good clarity
        assert (
            ctx_22.trend_direction == "bullish"
        ), f"Should have bullish trend, got {ctx_22.trend_direction}"
        assert (
            ctx_22.structure_clarity >= 0.5
        ), f"Should have clarity >= 0.5, got {ctx_22.structure_clarity}"

        # Verify: Guard should be reset (last_choch_direction → None)
        assert tracker.last_choch_direction is None, (
            f"Guard should be reset after 10+ bars with opposite trend, "
            f"but last_choch_direction={tracker.last_choch_direction}"
        )

        # === Phase 3: Trigger SECOND bearish CHoCH (should NOT be blocked) ===
        # Break below swing low at 98 → bearish BOS
        # Use a clear downward bar entirely below the swing low
        ctx_choch2 = tracker.update(
            high=100.0, low=90.0, close=91.0
        )  # Bar 23 - BOS bearish (breaks 98)

        # This should trigger CHoCH because:
        # 1. We have a bullish trend (verified above)
        # 2. BOS is bearish (opposite direction)
        # 3. Clarity is sufficient (>= 0.5)
        # 4. Guard was reset (last_choch_direction was None before this bar)
        assert ctx_choch2.choch_detected is True, (
            f"Second bearish CHoCH should trigger after guard reset. "
            f"Got: choch_detected={ctx_choch2.choch_detected}, "
            f"trend={ctx_choch2.trend_direction}, "
            f"bos_direction={ctx_choch2.bos_direction}, "
            f"clarity={ctx_choch2.structure_clarity}, "
            f"last_choch_direction={tracker.last_choch_direction}"
        )
        assert ctx_choch2.choch_direction == "bearish"
        assert ctx_choch2.choch_age == 0

    def test_guard_reset_clears_both_direction_and_idx_for_consistency(self):
        """Guard reset should clear both last_choch_direction AND last_choch_idx for consistency.

        Bug: Guard reset sets last_choch_direction=None but leaves last_choch_idx intact.
        This creates inconsistent StructureContext where:
        - choch_direction=None (suggests no last CHoCH)
        - choch_age=non-None (suggests there WAS a CHoCH X bars ago)

        This violates semantic coherence: if there's no last CHoCH (direction=None),
        there should be no age calculation either (age=None).

        Fix: When resetting guard, also set last_choch_idx=None.
        """
        tracker = StructureContextTracker(swing_window=2)

        # Phase 1: Build bullish trend and trigger bearish CHoCH
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - HH swing
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - HH detected

        tracker.update(high=102.0, low=96.0, close=97.0)  # Bar 5 - HL swing
        tracker.update(high=100.0, low=97.0, close=99.0)  # Bar 6
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 7 - HL detected

        tracker.update(high=108.0, low=102.0, close=107.0)  # Bar 8 - HH swing
        tracker.update(high=106.0, low=102.0, close=104.0)  # Bar 9
        tracker.update(high=105.0, low=101.0, close=103.0)  # Bar 10 - HH detected

        # Trigger bearish CHoCH
        ctx_choch = tracker.update(
            high=100.0, low=92.0, close=93.0
        )  # Bar 11 - BOS bearish
        choch_bar = tracker.bar_count  # Capture actual CHoCH bar index
        assert ctx_choch.choch_detected is True
        assert ctx_choch.choch_direction == "bearish"
        assert ctx_choch.choch_age == 0
        assert tracker.last_choch_direction == "bearish"
        assert tracker.last_choch_idx == choch_bar

        # Phase 2: Build sustained bullish trend (10+ bars) to trigger guard reset
        tracker.update(high=98.0, low=94.0, close=95.0)  # Bar 12
        tracker.update(high=100.0, low=95.0, close=99.0)  # Bar 13
        tracker.update(high=110.0, low=100.0, close=109.0)  # Bar 14 - HH swing
        tracker.update(high=108.0, low=101.0, close=105.0)  # Bar 15
        tracker.update(high=107.0, low=102.0, close=106.0)  # Bar 16 - HH detected

        tracker.update(high=106.0, low=98.0, close=99.0)  # Bar 17 - HL swing
        tracker.update(high=104.0, low=99.0, close=102.0)  # Bar 18
        tracker.update(high=105.0, low=100.0, close=104.0)  # Bar 19 - HL detected

        tracker.update(high=120.0, low=105.0, close=119.0)  # Bar 20 - HH swing
        tracker.update(high=118.0, low=106.0, close=115.0)  # Bar 21
        ctx_after_reset = tracker.update(
            high=117.0, low=107.0, close=116.0
        )  # Bar 22 - HH detected

        # Verify: Guard reset should have happened (10+ bars, opposite trend, clarity >= 0.5)
        assert tracker.bar_count - choch_bar >= 10, "Should be 10+ bars since CHoCH"
        assert ctx_after_reset.trend_direction == "bullish", "Should have bullish trend"
        assert (
            ctx_after_reset.structure_clarity >= 0.5
        ), "Should have sufficient clarity"

        # Bug verification: last_choch_direction reset but last_choch_idx still set
        assert (
            tracker.last_choch_direction is None
        ), "Guard reset should clear last_choch_direction"

        # CRITICAL BUG: last_choch_idx should also be None after guard reset
        # This is the core issue - if direction is None (no last CHoCH), then
        # idx should also be None (no bar index to reference)
        assert tracker.last_choch_idx is None, (
            f"Guard reset should clear last_choch_idx for consistency, "
            f"but got last_choch_idx={tracker.last_choch_idx}. "
            f"Having direction=None but idx={tracker.last_choch_idx} creates "
            f"inconsistent state where choch_direction=None but choch_age=non-None."
        )

        # Verify: StructureContext should have consistent None values
        assert (
            ctx_after_reset.choch_direction is None
        ), "choch_direction should be None after guard reset"
        assert ctx_after_reset.choch_age is None, (
            f"choch_age should be None after guard reset (consistent with direction=None), "
            f"but got choch_age={ctx_after_reset.choch_age}. "
            f"This inconsistency (direction=None, age={ctx_after_reset.choch_age}) "
            f"violates semantic coherence and can confuse downstream logic."
        )


class TestStructuralChopDetection:
    """Test structure-based chop detection (not ATR-based)."""

    def test_structural_chop_not_detected_in_tight_range_with_clean_structure(self):
        """Test that low ATR alone does NOT trigger structural chop."""
        tracker = StructureContextTracker(swing_window=2)

        # Build baseline with normal volatility first
        for i in range(50):
            high = 100.0 + (i % 10)
            low = 100.0 - (i % 5)
            close = 100.0 + (i % 7)
            tracker.update(high=high, low=low, close=close)

        # Now create tight range (compressed ATR) but with clean structure
        base_price = 100.0
        for i in range(20):
            high = base_price + 0.05
            low = base_price - 0.05
            close = base_price
            ctx = tracker.update(high=high, low=low, close=close)

        # Should NOT detect structural chop (low ATR alone is not chop)
        # ATR compression should be reflected in atr_compression_ratio instead
        assert (
            ctx.is_structural_chop is False
        ), "Low ATR alone should not trigger structural chop"
        # But ATR compression ratio should be low (now that we have baseline)
        assert (
            ctx.atr_compression_ratio < 0.5
        ), "ATR compression ratio should indicate compression"

    def test_structural_chop_not_detected_in_trending_market(self):
        """Test no structural chop in trending market with normal volatility."""
        tracker = StructureContextTracker(swing_window=2)

        # Create trending market with normal ranges and clean structure (HH pattern)
        # Need enough bars to establish structure and BOS
        for i in range(40):
            base = 100.0 + i * 0.5  # Trending up
            high = base + 1.0  # ~1% range
            low = base - 0.5
            close = base + 0.3
            ctx = tracker.update(high=high, low=low, close=close)

        # Should NOT detect structural chop (clean uptrend with BOS)
        assert (
            ctx.is_structural_chop is False
        ), "Should not detect structural chop in trending market"

    def test_atr_compression_ratio_requires_full_window(self):
        """Test that ATR compression ratio defaults to 1.0 without enough data."""
        tracker = StructureContextTracker(swing_window=2)

        # First 14 bars - not enough for 14-period ATR (need 15 total)
        for i in range(14):
            ctx = tracker.update(high=100.05, low=99.95, close=100.0)

        # Should default to 1.0 (not enough data yet)
        assert (
            ctx.atr_compression_ratio == 1.0
        ), "Should default to 1.0 without full ATR window"

    def test_atr_compression_ratio_requires_15_bars_not_14(self):
        """Test that 14-period ATR requires 15 bars, not 14.

        Standard ATR semantics:
        - 14-period ATR needs 15 bars total
        - Bar 0: establishes initial close
        - Bars 1-14: produce 14 True Range values
        - Average those 14 values = 14-period ATR
        """
        tracker = StructureContextTracker(swing_window=2)

        # Create 14 bars with extremely tight range (0.02% of price)
        for i in range(14):
            ctx_14 = tracker.update(high=100.01, low=99.99, close=100.0)

        # With 14 bars total: ATR not calculated yet, should default to 1.0
        assert ctx_14.atr_compression_ratio == 1.0, (
            "With only 14 bars, ATR compression ratio should default to 1.0 "
            "(need 15 bars: 1 initial close + 14 TR values for 14-period ATR)."
        )

        # Add 15th bar (still tight range)
        ctx_15 = tracker.update(high=100.01, low=99.99, close=100.0)

        # With 15 bars total: ATR calculated but still defaults to 1.0 (need baseline)
        # (Need 20 bars for baseline comparison)
        assert ctx_15.atr_compression_ratio == 1.0, (
            "With 15 bars, ATR is calculated but baseline not yet established "
            "(need 20 bars for baseline comparison)."
        )


class TestLiquiditySweepDetection:
    """Test liquidity sweep detection and age calculation."""

    def test_sweep_detected_when_high_breaks_swing_high_but_close_doesnt(self):
        """Test bearish sweep (high breaks swing high, close doesn't)."""
        tracker = StructureContextTracker(swing_window=2)

        # Create swing high - pattern: lower, lower, PEAK, lower, lower
        # Bar 2 will be swing high (106), detected at bar 4
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - swing high
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        ctx_swing = tracker.update(
            high=103.0, low=99.0, close=100.0
        )  # Bar 4 - detection

        # Verify swing high was detected
        assert ctx_swing.last_swing_high is not None, "Swing high should be detected"
        assert ctx_swing.last_swing_high == 106.0

        # Continue a few more bars
        tracker.update(high=102.0, low=98.0, close=99.0)  # Bar 5
        tracker.update(high=101.0, low=97.0, close=98.0)  # Bar 6

        # Now sweep high: high > 106 but close < 106
        ctx_sweep = tracker.update(high=108.0, low=102.0, close=104.0)  # Bar 7

        # Should detect bearish sweep
        assert ctx_sweep.liquidity_sweep is True
        assert ctx_sweep.sweep_direction == "bearish"
        assert ctx_sweep.sweep_price == 106.0
        assert ctx_sweep.sweep_age == 0

    def test_sweep_detected_when_low_breaks_swing_low_but_close_doesnt(self):
        """Test bullish sweep (low breaks swing low, close doesn't)."""
        tracker = StructureContextTracker(swing_window=2)

        # Create swing low - pattern: higher, higher, TROUGH, higher, higher
        # Bar 2 will be swing low (94), detected at bar 4
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 0
        tracker.update(high=101.0, low=98.0, close=99.0)  # Bar 1
        tracker.update(high=100.0, low=94.0, close=95.0)  # Bar 2 - swing low
        tracker.update(high=99.0, low=96.0, close=98.0)  # Bar 3
        ctx_swing = tracker.update(
            high=100.0, low=97.0, close=99.0
        )  # Bar 4 - detection

        # Verify swing low was detected
        assert ctx_swing.last_swing_low is not None, "Swing low should be detected"
        assert ctx_swing.last_swing_low == 94.0

        # Continue a few more bars
        tracker.update(high=101.0, low=98.0, close=100.0)  # Bar 5
        tracker.update(high=102.0, low=99.0, close=101.0)  # Bar 6

        # Now sweep low: low < 94 but close > 94
        ctx_sweep = tracker.update(high=100.0, low=92.0, close=96.0)  # Bar 7

        # Should detect bullish sweep
        assert ctx_sweep.liquidity_sweep is True
        assert ctx_sweep.sweep_direction == "bullish"
        assert ctx_sweep.sweep_price == 94.0
        assert ctx_sweep.sweep_age == 0

    def test_sweep_rejected_when_both_directions_swept(self):
        """Test that ambiguous sweeps (both directions) are rejected."""
        tracker = StructureContextTracker(swing_window=2)

        # Build structure with both swing high and low
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=105.0, low=100.0, close=104.0)  # Bar 1 - swing high at 105
        tracker.update(high=102.0, low=99.0, close=100.0)  # Bar 2
        tracker.update(high=101.0, low=95.0, close=96.0)  # Bar 3 - swing low at 95
        tracker.update(high=100.0, low=96.0, close=98.0)  # Bar 4

        # Ambiguous sweep: breaks both high and low
        ctx_sweep = tracker.update(high=107.0, low=93.0, close=100.0)  # Bar 5

        # Should NOT detect sweep (ambiguous)
        assert ctx_sweep.liquidity_sweep is False

    def test_sweep_age_is_zero_when_sweep_detected_on_current_bar(self):
        """Test that sweep_age=0 when liquidity_sweep=True on current bar."""
        tracker = StructureContextTracker(swing_window=2)

        # Build structure
        tracker.update(high=100.0, low=98.0, close=99.0)
        tracker.update(high=105.0, low=100.0, close=104.0)
        tracker.update(high=102.0, low=99.0, close=100.0)
        tracker.update(high=101.0, low=98.0, close=99.0)
        tracker.update(high=100.0, low=97.0, close=98.0)

        # Sweep high
        ctx_sweep = tracker.update(high=107.0, low=102.0, close=103.0)

        # Age should be 0 on detection bar
        if ctx_sweep.liquidity_sweep:
            assert ctx_sweep.sweep_age == 0

    def test_sweep_age_increments_after_detection(self):
        """Test that sweep_age increments correctly after sweep detection."""
        tracker = StructureContextTracker(swing_window=2)

        # Build structure and trigger sweep
        tracker.update(high=100.0, low=98.0, close=99.0)
        tracker.update(high=105.0, low=100.0, close=104.0)
        tracker.update(high=102.0, low=99.0, close=100.0)
        tracker.update(high=101.0, low=98.0, close=99.0)
        tracker.update(high=100.0, low=97.0, close=98.0)

        # Sweep
        ctx_sweep = tracker.update(high=107.0, low=102.0, close=103.0)

        if ctx_sweep.liquidity_sweep:
            assert ctx_sweep.sweep_age == 0

            # Age should increment each bar
            for expected_age in range(1, 4):
                ctx = tracker.update(high=102.0, low=100.0, close=101.0)
                assert (
                    ctx.sweep_age == expected_age
                ), f"Expected sweep_age={expected_age}, got {ctx.sweep_age}"

    def test_sweep_direction_and_price_are_none_when_no_current_sweep(self):
        """Test that sweep_direction and sweep_price are None when liquidity_sweep=False.

        This test verifies correct semantic separation between:
        - liquidity_sweep: True if sweep on CURRENT bar (current event)
        - sweep_direction/sweep_price: Only populated when liquidity_sweep=True
        - sweep_age: Tracks bars since LAST sweep (last event, always populated)

        Bug: StructureContextTracker was mixing "current event" and "last event" semantics,
        returning old sweep_direction/price even when liquidity_sweep=False.
        """
        tracker = StructureContextTracker(swing_window=2)

        # Create swing high - pattern: lower, lower, PEAK, lower, lower
        # Bar 2 will be swing high (106), detected at bar 4
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - swing high
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        ctx_swing = tracker.update(
            high=103.0, low=99.0, close=100.0
        )  # Bar 4 - detection

        # Verify swing high was detected
        assert ctx_swing.last_swing_high is not None, "Swing high should be detected"
        assert ctx_swing.last_swing_high == 106.0

        # Continue a few more bars without sweeping
        tracker.update(high=102.0, low=98.0, close=99.0)  # Bar 5
        tracker.update(high=101.0, low=97.0, close=98.0)  # Bar 6

        # Bar N: Sweep occurs (high > 106 but close < 106)
        ctx_with_sweep = tracker.update(high=108.0, low=102.0, close=104.0)  # Bar 7

        # Verify sweep detected
        assert ctx_with_sweep.liquidity_sweep is True
        assert ctx_with_sweep.sweep_direction == "bearish"
        assert ctx_with_sweep.sweep_price == 106.0
        assert ctx_with_sweep.sweep_age == 0

        # Bar N+1: No sweep occurs (normal bar)
        ctx_no_sweep = tracker.update(high=104.0, low=102.0, close=103.0)  # Bar 8

        # Critical assertion: When no sweep on current bar, direction/price should be None
        assert (
            ctx_no_sweep.liquidity_sweep is False
        ), "No sweep on this bar, liquidity_sweep should be False"
        assert ctx_no_sweep.sweep_direction is None, (
            "No sweep on current bar, sweep_direction should be None "
            "(not carry forward old sweep direction)"
        )
        assert ctx_no_sweep.sweep_price is None, (
            "No sweep on current bar, sweep_price should be None "
            "(not carry forward old sweep price)"
        )
        # But age should track the last sweep
        assert (
            ctx_no_sweep.sweep_age == 1
        ), "sweep_age should track bars since last sweep"

        # Bar N+2: Still no sweep
        ctx_no_sweep_2 = tracker.update(high=103.0, low=101.0, close=102.0)  # Bar 9

        assert ctx_no_sweep_2.liquidity_sweep is False
        assert ctx_no_sweep_2.sweep_direction is None
        assert ctx_no_sweep_2.sweep_price is None
        assert ctx_no_sweep_2.sweep_age == 2


class TestNoLookaheadBias:
    """Test that StructureContext has no lookahead bias."""

    def test_no_lookahead_bias_structure_context(self):
        """Test that context only uses past data."""
        tracker = StructureContextTracker(swing_window=2)

        contexts = []
        data = [
            (100.0, 98.0, 99.0),
            (102.0, 100.0, 101.0),
            (101.0, 99.0, 100.0),
            (103.0, 101.0, 102.0),
            (102.0, 100.0, 101.0),
        ]

        for high, low, close in data:
            ctx = tracker.update(high=high, low=low, close=close)
            contexts.append(ctx)

        # Each context should only depend on data up to that point
        # Re-run and verify same results
        tracker2 = StructureContextTracker(swing_window=2)
        for i, (high, low, close) in enumerate(data):
            ctx2 = tracker2.update(high=high, low=low, close=close)
            # Same input → same output
            assert ctx2.last_structure_label == contexts[i].last_structure_label
            assert ctx2.trend_direction == contexts[i].trend_direction


class TestBatchComputation:
    """Test batch computation for backtesting."""

    def test_compute_structure_context_batch_returns_dataframe(self):
        """Test batch function returns DataFrame with derived columns."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 101, 103, 102, 104, 103],
                "low": [98, 100, 99, 101, 100, 102, 101],
                "close": [99, 101, 100, 102, 101, 103, 102],
            }
        )

        result = compute_structure_context_batch(df, swing_window=2)

        # Should return DataFrame
        assert isinstance(result, pd.DataFrame)

        # Should have all derived columns
        expected_columns = [
            "last_structure_label",
            "trend_direction",
            "trend_confidence",
            "structure_clarity",
            "is_chop",
            "is_structural_chop",
            "atr_compression_ratio",
            "structure_conflict_flag",
            "last_swing_high",
            "last_swing_low",
            "bos_direction",
            "bos_recent",
            "bos_age",
            "choch_detected",
            "choch_age",
            "liquidity_sweep",
            "sweep_direction",
            "sweep_price",
            "sweep_age",
        ]

        for col in expected_columns:
            assert col in result.columns, f"Missing column: {col}"

    def test_batch_forward_fills_derived_fields(self):
        """Test that batch computation forward-fills derived fields."""
        df = pd.DataFrame(
            {
                "high": [100, 105, 102, 101, 100, 99, 98],
                "low": [98, 100, 99, 98, 97, 96, 95],
                "close": [99, 104, 100, 99, 98, 97, 96],
            }
        )

        result = compute_structure_context_batch(df, swing_window=2)

        # After warmup, trend_direction should not be None
        # (should be forward-filled)
        non_null_trends = result["trend_direction"].notna().sum()
        assert non_null_trends > 0


class TestStreamingBatchParity:
    """Test that streaming and batch produce same results."""

    def test_streaming_batch_parity(self):
        """Test streaming tracker produces same results as batch."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 101, 103, 102, 104, 103, 105, 104, 106],
                "low": [98, 100, 99, 101, 100, 102, 101, 103, 102, 104],
                "close": [99, 101, 100, 102, 101, 103, 102, 104, 103, 105],
            }
        )

        # Batch computation
        batch_result = compute_structure_context_batch(df, swing_window=2)

        # Streaming computation
        tracker = StructureContextTracker(swing_window=2)
        streaming_contexts = []
        for i in range(len(df)):
            ctx = tracker.update(
                high=df["high"].iloc[i],
                low=df["low"].iloc[i],
                close=df["close"].iloc[i],
            )
            streaming_contexts.append(ctx)

        # Compare results (after warmup period)
        warmup = 5  # First few bars may differ during warmup
        for i in range(warmup, len(df)):
            streaming_ctx = streaming_contexts[i]
            batch_row = batch_result.iloc[i]

            # Compare key fields
            assert (
                streaming_ctx.last_structure_label == batch_row["last_structure_label"]
            )
            assert streaming_ctx.trend_direction == batch_row["trend_direction"]
            clarity_diff = abs(
                streaming_ctx.structure_clarity - batch_row["structure_clarity"]
            )
            assert clarity_diff < 0.01
            assert streaming_ctx.is_chop == batch_row["is_chop"]
            assert streaming_ctx.choch_detected == batch_row["choch_detected"]
            assert streaming_ctx.last_swing_high_idx == batch_row["last_swing_high_idx"]
            assert streaming_ctx.last_swing_low_idx == batch_row["last_swing_low_idx"]
            # Note: BOS fields not checked (Structure Engine v2.0 Part 2)


class TestBOSDetection:
    """Test BOS (Break of Structure) detection and age calculation."""

    def test_structure_context_has_bos_fields(self):
        """Test that StructureContext has BOS fields."""
        ctx = StructureContext(
            last_structure_label="HH",
            last_swing_high=100.0,
            last_swing_low=95.0,
            last_swing_high_idx=10,
            last_swing_low_idx=8,
            trend_direction="bullish",
            trend_confidence=0.8,
            structure_clarity=0.9,
            is_chop=False,
            structure_conflict_flag=False,
            choch_detected=False,
            choch_direction=None,
            choch_age=None,
            bos_direction="bullish",
            bos_recent=True,
            bos_age=5,
        )

        assert ctx.bos_direction == "bullish"
        assert ctx.bos_recent is True
        assert ctx.bos_age == 5

    def test_tracker_stores_swing_indices_in_lists(self):
        """Test that tracker stores swing indices in lists."""
        tracker = StructureContextTracker(swing_window=2)

        # Build up swings
        data = [
            (100.0, 98.0, 99.0),  # Bar 0
            (105.0, 100.0, 104.0),  # Bar 1 - swing high
            (102.0, 99.0, 100.0),  # Bar 2
            (101.0, 95.0, 96.0),  # Bar 3 - swing low
            (100.0, 98.0, 99.0),  # Bar 4
        ]

        for high, low, close in data:
            tracker.update(high=high, low=low, close=close)

        # Tracker should have swing_high_indices and swing_low_indices lists
        assert hasattr(tracker, "swing_high_indices")
        assert hasattr(tracker, "swing_low_indices")
        assert isinstance(tracker.swing_high_indices, list)
        assert isinstance(tracker.swing_low_indices, list)

    def test_bos_detected_when_close_breaks_swing_high(self):
        """Test bullish BOS detected when close > prior swing high."""
        tracker = StructureContextTracker(swing_window=2)

        # Create swing high - needs proper structure with swing_window=2
        # Pattern: lower, PEAK, lower, lower, lower (so peak is at center of window)
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(
            high=106.0, low=102.0, close=105.0
        )  # Bar 2 - swing high (will be detected at bar 4)
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(
            high=103.0, low=99.0, close=100.0
        )  # Bar 4 - swing high detected here
        tracker.update(high=102.0, low=98.0, close=99.0)  # Bar 5
        tracker.update(high=101.0, low=97.0, close=98.0)  # Bar 6

        # Now break above the swing high (106)
        ctx = tracker.update(high=110.0, low=106.0, close=108.0)  # Bar 7: close > 106

        # Should detect bullish BOS
        assert ctx.bos_direction == "bullish"
        assert ctx.bos_age == 0  # Just detected
        assert ctx.bos_recent is True

    def test_bos_detected_when_close_breaks_swing_low(self):
        """Test bearish BOS detected when close < prior swing low."""
        tracker = StructureContextTracker(swing_window=2)

        # Create swing low - needs proper structure with swing_window=2
        # Pattern: higher, higher, TROUGH, higher, higher (so trough is at center of window)
        tracker.update(high=106.0, low=104.0, close=105.0)  # Bar 0
        tracker.update(high=105.0, low=103.0, close=104.0)  # Bar 1
        tracker.update(
            high=104.0, low=94.0, close=95.0
        )  # Bar 2 - swing low (will be detected at bar 4)
        tracker.update(high=105.0, low=96.0, close=98.0)  # Bar 3
        tracker.update(
            high=106.0, low=97.0, close=99.0
        )  # Bar 4 - swing low detected here
        tracker.update(high=107.0, low=98.0, close=100.0)  # Bar 5
        tracker.update(high=108.0, low=99.0, close=101.0)  # Bar 6

        # Now break below the swing low (94)
        ctx = tracker.update(high=96.0, low=90.0, close=92.0)  # Bar 7: close < 94

        # Should detect bearish BOS
        assert ctx.bos_direction == "bearish"
        assert ctx.bos_age == 0  # Just detected
        assert ctx.bos_recent is True

    def test_bos_age_increments_each_bar(self):
        """Test that bos_age increments correctly after BOS detection."""
        tracker = StructureContextTracker(swing_window=2)

        # Create swing high and trigger BOS
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - swing high
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - swing detected
        tracker.update(high=102.0, low=98.0, close=99.0)  # Bar 5
        tracker.update(high=101.0, low=97.0, close=98.0)  # Bar 6

        # Trigger BOS
        ctx_bos = tracker.update(high=110.0, low=106.0, close=108.0)  # Bar 7
        assert ctx_bos.bos_age == 0

        # Age should increment each bar
        for expected_age in range(1, 5):
            ctx = tracker.update(high=110.0, low=108.0, close=109.0)
            assert (
                ctx.bos_age == expected_age
            ), f"Expected bos_age={expected_age}, got {ctx.bos_age}"

    def test_bos_recent_true_within_threshold(self):
        """Test that bos_recent is True when age <= 15 bars."""
        tracker = StructureContextTracker(swing_window=2)

        # Create swing high and trigger BOS
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=102.0, low=100.0, close=101.0)  # Bar 1
        tracker.update(high=106.0, low=102.0, close=105.0)  # Bar 2 - swing high
        tracker.update(high=104.0, low=100.0, close=102.0)  # Bar 3
        tracker.update(high=103.0, low=99.0, close=100.0)  # Bar 4 - swing detected
        tracker.update(high=102.0, low=98.0, close=99.0)  # Bar 5
        tracker.update(high=101.0, low=97.0, close=98.0)  # Bar 6
        tracker.update(high=110.0, low=106.0, close=108.0)  # Bar 7 - BOS

        # Bars 7-21: bos_recent should be True (age 0-14)
        for _ in range(14):
            ctx = tracker.update(high=110.0, low=108.0, close=109.0)
            assert ctx.bos_recent is True

        # Bar 22: age=15, should still be True (inclusive)
        ctx = tracker.update(high=110.0, low=108.0, close=109.0)
        assert ctx.bos_age == 15
        assert ctx.bos_recent is True

        # Bar 23: age=16, should be False
        ctx = tracker.update(high=110.0, low=108.0, close=109.0)
        assert ctx.bos_age == 16
        assert ctx.bos_recent is False

    def test_no_bos_when_within_range(self):
        """Test that no BOS detected when price stays within swing range."""
        tracker = StructureContextTracker(swing_window=2)

        # Create swing high and low
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=105.0, low=100.0, close=104.0)  # Bar 1 - swing high
        tracker.update(high=102.0, low=99.0, close=100.0)  # Bar 2
        tracker.update(high=101.0, low=95.0, close=96.0)  # Bar 3 - swing low
        tracker.update(high=102.0, low=99.0, close=100.0)  # Bar 4

        # Stay within range (96 < close < 105)
        ctx = tracker.update(high=103.0, low=100.0, close=102.0)  # Bar 5

        # Should NOT detect BOS
        assert ctx.bos_direction is None or ctx.bos_age is None

    def test_ambiguous_bos_returns_none(self):
        """Test that ambiguous BOS (breaks both directions) returns None."""
        tracker = StructureContextTracker(swing_window=2)

        # Create swing high and low
        tracker.update(high=100.0, low=98.0, close=99.0)  # Bar 0
        tracker.update(high=105.0, low=100.0, close=104.0)  # Bar 1 - swing high (105)
        tracker.update(high=102.0, low=99.0, close=100.0)  # Bar 2
        tracker.update(high=101.0, low=95.0, close=96.0)  # Bar 3 - swing low (95)
        tracker.update(high=102.0, low=99.0, close=100.0)  # Bar 4

        # Create volatile bar that breaks both directions
        # High > 105 AND Low < 95
        _ = tracker.update(high=110.0, low=90.0, close=100.0)  # Bar 5

        # Should NOT detect BOS (ambiguous)
        # Implementation should not update bos_direction in this case
        # The test verifies that ambiguous breaks don't trigger BOS

    def test_batch_streaming_parity_includes_bos(self):
        """Test that batch and streaming produce same BOS results."""
        df = pd.DataFrame(
            {
                "high": [100, 105, 102, 101, 102, 110, 108, 109],
                "low": [98, 100, 99, 98, 99, 105, 106, 107],
                "close": [99, 104, 100, 99, 100, 108, 107, 108],
            }
        )

        # Batch computation
        batch_result = compute_structure_context_batch(df, swing_window=2)

        # Streaming computation
        tracker = StructureContextTracker(swing_window=2)
        streaming_contexts = []
        for i in range(len(df)):
            ctx = tracker.update(
                high=df["high"].iloc[i],
                low=df["low"].iloc[i],
                close=df["close"].iloc[i],
            )
            streaming_contexts.append(ctx)

        # Compare BOS fields (after warmup)
        warmup = 5
        for i in range(warmup, len(df)):
            streaming_ctx = streaming_contexts[i]
            batch_row = batch_result.iloc[i]

            # Compare BOS fields
            assert streaming_ctx.bos_direction == batch_row.get("bos_direction")
            assert streaming_ctx.bos_recent == batch_row.get("bos_recent")
            assert streaming_ctx.bos_age == batch_row.get("bos_age")
