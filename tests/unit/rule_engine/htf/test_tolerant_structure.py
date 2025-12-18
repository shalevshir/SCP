"""Tests for tolerant structure chop detection.

Verifies that the new structure chop logic:
- Allows retracements in trends (HL/HH in uptrend, LH/LL in downtrend)
- Only marks chop on 2+ consecutive alternations
- Filters noise swings based on ATR
"""

import pytest

from rule_engine.htf.calculator import detect_structure_chop, is_structural_chop


class TestStructuralChopDensityFilter:
    """Test is_structural_chop() density-based detection."""

    def test_rapid_alternations_detected_as_chop(self):
        """Test that 2+ consecutive alternations mark as chop."""
        # HH -> LL -> HH -> LL (3 alternations)
        labels = ["HH", "LL", "HH", "LL"]

        assert is_structural_chop(labels, min_alternations=2) is True

    def test_trend_with_retracements_not_chop(self):
        """Test that normal retracements don't trigger chop."""
        # HH -> HL -> HH -> HL (no alternations, all bullish)
        labels = ["HH", "HL", "HH", "HL", "HH"]

        assert is_structural_chop(labels, min_alternations=2) is False

    def test_bearish_trend_with_retracements_not_chop(self):
        """Test bearish trend with retracements not marked as chop."""
        # LL -> LH -> LL -> LH (no alternations, all bearish)
        labels = ["LL", "LH", "LL", "LH", "LL"]

        assert is_structural_chop(labels, min_alternations=2) is False

    def test_single_alternation_not_chop(self):
        """Test that single alternation doesn't trigger chop."""
        # HH -> HL -> LL (only 1 alternation at HL->LL)
        labels = ["HH", "HL", "LL"]

        assert is_structural_chop(labels, min_alternations=2) is False

    def test_insufficient_data_returns_false(self):
        """Test that insufficient labels return False."""
        labels = ["HH"]

        assert is_structural_chop(labels, min_alternations=2) is False

    def test_alternations_followed_by_trend_not_chop(self):
        """Test that alternations followed by trend continuation should reset and not be chop.

        Bug reproduction: After reaching threshold, counter never resets on non-alternation.
        Labels: ["LH", "HH", "LL", "HH", "HL", "HH"]
        - LH→HH: non-alternation (H→H), count=0
        - HH→LL: alternation, count=1
        - LL→HH: alternation, count=2 (threshold reached)
        - HH→HL: non-alternation (H→H), should reset count to 0
        - HL→HH: non-alternation (H→H), count stays 0
        Result: Should be False (not chop) because trend continuation breaks alternation pattern.
        """
        labels = ["LH", "HH", "LL", "HH", "HL", "HH"]

        # Should NOT be chop because trend continuation (HH→HL→HH) breaks alternation pattern
        assert is_structural_chop(labels, min_alternations=2) is False


class TestTolerantChopDetection:
    """Test detect_structure_chop() with tolerant logic."""

    def test_uptrend_with_retracements_not_chop(self):
        """Test uptrend with HL retracements is not marked as chop."""
        # HH, HL, HH, HL = uptrend with healthy pullbacks
        labels = ["HH", "HL", "HH", "HL", "HH"]

        result = detect_structure_chop(labels, lookback=5)
        assert result is False

    def test_downtrend_with_retracements_not_chop(self):
        """Test downtrend with LH retracements is not marked as chop."""
        # LL, LH, LL, LH = downtrend with healthy pullbacks
        labels = ["LL", "LH", "LL", "LH", "LL"]

        result = detect_structure_chop(labels, lookback=5)
        assert result is False

    def test_rapid_alternations_detected_as_chop(self):
        """Test rapid H/L alternations detected as chop."""
        # HH -> LL -> HH -> LL = rapid alternations
        labels = ["HH", "LL", "HH", "LL", "HH"]

        result = detect_structure_chop(labels, lookback=5)
        assert result is True

    def test_mixed_trend_without_alternations_marked_chop(self):
        """Test mixed labels without clear trend = chop."""
        # 2 bullish, 2 bearish in last 3 = no clear majority
        labels = ["HH", "LL", "HL"]

        result = detect_structure_chop(labels, lookback=3)
        assert result is True

    def test_noise_swings_detected_with_atr(self):
        """Test that small swings relative to ATR are marked as noise/chop."""
        labels = ["HH", "HL", "HH"]
        swing_prices = [2650.0, 2650.2, 2650.4]  # Only 0.2 and 0.4 moves
        atr = 2.0  # 0.2 < 0.25 * 2.0 = 0.5

        result = detect_structure_chop(
            labels, lookback=3, atr=atr, swing_prices=swing_prices, max_noise_ratio=0.25
        )
        assert result is True

    def test_significant_swings_not_noise(self):
        """Test that large swings relative to ATR are not marked as noise."""
        labels = ["HH", "HL", "HH"]
        swing_prices = [2650.0, 2648.0, 2651.0]  # 2.0 and 3.0 moves
        atr = 2.0  # 2.0 >= 0.25 * 2.0 = 0.5

        result = detect_structure_chop(
            labels, lookback=3, atr=atr, swing_prices=swing_prices, max_noise_ratio=0.25
        )
        # Not noise, and 3 consecutive bullish labels = trend
        assert result is False

    def test_two_out_of_three_agreement_not_chop(self):
        """Test that 2/3 labels agreeing indicates trend, not chop."""
        # HH, HL, LL = 2 bullish, 1 bearish (trend with reversal)
        labels = ["HH", "HL", "LL"]

        result = detect_structure_chop(labels, lookback=3)
        # 2/3 bullish in last 3 = trend (not chop)
        assert result is False



