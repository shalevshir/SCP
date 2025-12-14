"""Unit tests for HTF structure invalidation logic.

Tests proper structure break detection that should flip HTF bias:
- HH -> LL (bullish to bearish)
- HL -> LL (bullish to bearish)
- LH -> HH (bearish to bullish)
- LL -> HH (bearish to bullish)

NOT invalidations (micro volatility):
- HL -> LH (single step)
- LH -> HL (single step)

Following TDD: These tests will fail until implementation is complete.
"""

import pytest

from rule_engine.htf.conflicts import detect_structure_invalidation


class TestStructureInvalidation:
    """Test HTF structure invalidation detection."""

    def test_bullish_hh_to_ll_invalidates(self):
        """Test HH -> LL invalidates bullish bias."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="HH",
            curr_structure="LL",
            bias="bullish",
        )

        assert is_invalidated is True
        assert "HH" in reason and "LL" in reason

    def test_bullish_hl_to_ll_invalidates(self):
        """Test HL -> LL invalidates bullish bias."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="HL",
            curr_structure="LL",
            bias="bullish",
        )

        assert is_invalidated is True
        assert "HL" in reason and "LL" in reason

    def test_bearish_lh_to_hh_invalidates(self):
        """Test LH -> HH invalidates bearish bias."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="LH",
            curr_structure="HH",
            bias="bearish",
        )

        assert is_invalidated is True
        assert "LH" in reason and "HH" in reason

    def test_bearish_ll_to_hh_invalidates(self):
        """Test LL -> HH invalidates bearish bias."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="LL",
            curr_structure="HH",
            bias="bearish",
        )

        assert is_invalidated is True
        assert "LL" in reason and "HH" in reason

    def test_hl_to_lh_does_not_invalidate(self):
        """Test HL -> LH does NOT invalidate (micro volatility)."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="HL",
            curr_structure="LH",
            bias="bullish",
        )

        assert is_invalidated is False
        assert reason is None

    def test_lh_to_hl_does_not_invalidate(self):
        """Test LH -> HL does NOT invalidate (micro volatility)."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="LH",
            curr_structure="HL",
            bias="bearish",
        )

        assert is_invalidated is False
        assert reason is None

    def test_hh_to_hh_does_not_invalidate(self):
        """Test same structure label does not invalidate."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="HH",
            curr_structure="HH",
            bias="bullish",
        )

        assert is_invalidated is False
        assert reason is None

    def test_neutral_bias_not_invalidated(self):
        """Test neutral bias cannot be invalidated."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="HH",
            curr_structure="LL",
            bias="neutral",
        )

        assert is_invalidated is False
        assert reason is None

    def test_none_structure_does_not_invalidate(self):
        """Test None structure values don't trigger invalidation."""
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure=None,
            curr_structure="LL",
            bias="bullish",
        )

        assert is_invalidated is False
        assert reason is None

        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="HH",
            curr_structure=None,
            bias="bullish",
        )

        assert is_invalidated is False
        assert reason is None

    def test_bullish_with_bearish_continuation_not_invalidated(self):
        """Test bullish bias with bearish structure continuation doesn't invalidate."""
        # LH -> LL is bearish continuation, but if bias is already bullish,
        # this shouldn't trigger invalidation (bias was wrong to begin with)
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="LH",
            curr_structure="LL",
            bias="bullish",
        )

        assert is_invalidated is False
        assert reason is None

    def test_bearish_with_bullish_continuation_not_invalidated(self):
        """Test bearish bias with bullish structure continuation doesn't invalidate."""
        # HH -> HL is bullish continuation, but if bias is already bearish,
        # this shouldn't trigger invalidation (bias was wrong to begin with)
        is_invalidated, reason = detect_structure_invalidation(
            prev_structure="HH",
            curr_structure="HL",
            bias="bearish",
        )

        assert is_invalidated is False
        assert reason is None
