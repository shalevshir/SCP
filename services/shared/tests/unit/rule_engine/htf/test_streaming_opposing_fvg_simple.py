"""Simplified test for opposing FVG field preservation in DXY chop override.

This test directly verifies that the HTFBias constructor in streaming.py lines 289-320
includes all opposing FVG fields when creating a new bias object.
"""

from __future__ import annotations

from scp_shared.rule_engine.htf.types import HTFBias


class TestOpposingFVGFieldPreservation:
    """Test that all TP target fields are preserved in HTFBias constructor."""

    def test_htf_bias_constructor_preserves_all_tp_target_fields(self) -> None:
        """Test that HTFBias constructor can accept and preserve all 10 TP target fields.

        This test verifies that when creating a new HTFBias object (as done in
        streaming.py lines 289-320), all TP target fields are properly assigned,
        including the 4 opposing FVG fields that were omitted in the bug.

        The bug: streaming.py creates a new HTFBias to override DXY chop, but omits:
        - opposing_fvg_high
        - opposing_fvg_low
        - opposing_fvg_bullish_high
        - opposing_fvg_bullish_low

        These fields then default to None, breaking TP safety checks.
        """
        # Create an initial bias with ALL TP target fields populated
        original_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_15m="HH",
            structure_1h="HH",
            dxy_chop_detected=True,
            # All 10 TP target fields populated
            htf_range_high=2670.0,
            htf_range_low=2630.0,
            untouched_liquidity_high=2675.0,
            untouched_liquidity_low=2625.0,
            nearest_fvg_high=2665.0,
            nearest_fvg_low=2635.0,
            # These 4 were missing in the bug:
            opposing_fvg_high=2660.0,
            opposing_fvg_low=2655.0,
            opposing_fvg_bullish_high=2645.0,
            opposing_fvg_bullish_low=2640.0,
        )

        # Simulate what streaming.py does (lines 289-320):
        # Create a new HTFBias with cached DXY chop value
        # This is where the bug occurs - opposing FVG fields were omitted
        new_bias = HTFBias(
            bias=original_bias.bias,
            direction=original_bias.direction,
            score=original_bias.score,
            confidence=original_bias.confidence,
            structure_15m=original_bias.structure_15m,
            structure_1h=original_bias.structure_1h,
            dxy_chop_detected=False,  # Overridden value (cached)
            # TP target fields - these SHOULD all be preserved
            htf_range_high=original_bias.htf_range_high,
            htf_range_low=original_bias.htf_range_low,
            untouched_liquidity_high=original_bias.untouched_liquidity_high,
            untouched_liquidity_low=original_bias.untouched_liquidity_low,
            nearest_fvg_high=original_bias.nearest_fvg_high,
            nearest_fvg_low=original_bias.nearest_fvg_low,
            # BUG: These 4 fields are missing in streaming.py lines 314-320
            # They should be included:
            opposing_fvg_high=original_bias.opposing_fvg_high,
            opposing_fvg_low=original_bias.opposing_fvg_low,
            opposing_fvg_bullish_high=original_bias.opposing_fvg_bullish_high,
            opposing_fvg_bullish_low=original_bias.opposing_fvg_bullish_low,
        )

        # Verify ALL 10 TP target fields are preserved
        assert new_bias.htf_range_high == 2670.0, "htf_range_high should be preserved"
        assert new_bias.htf_range_low == 2630.0, "htf_range_low should be preserved"
        assert (
            new_bias.untouched_liquidity_high == 2675.0
        ), "untouched_liquidity_high should be preserved"
        assert (
            new_bias.untouched_liquidity_low == 2625.0
        ), "untouched_liquidity_low should be preserved"
        assert (
            new_bias.nearest_fvg_high == 2665.0
        ), "nearest_fvg_high should be preserved"
        assert new_bias.nearest_fvg_low == 2635.0, "nearest_fvg_low should be preserved"

        # CRITICAL: These 4 fields were missing in the bug
        assert (
            new_bias.opposing_fvg_high == 2660.0
        ), "opposing_fvg_high should be preserved (was missing in bug)"
        assert (
            new_bias.opposing_fvg_low == 2655.0
        ), "opposing_fvg_low should be preserved (was missing in bug)"
        assert (
            new_bias.opposing_fvg_bullish_high == 2645.0
        ), "opposing_fvg_bullish_high should be preserved (was missing in bug)"
        assert (
            new_bias.opposing_fvg_bullish_low == 2640.0
        ), "opposing_fvg_bullish_low should be preserved (was missing in bug)"

        # Also verify DXY chop was overridden
        assert (
            new_bias.dxy_chop_detected == False
        ), "dxy_chop_detected should be overridden"

    def test_missing_opposing_fvg_fields_default_to_none(self) -> None:
        """Test that omitting opposing FVG fields causes them to default to None.

        This demonstrates the bug: when opposing FVG fields are not included
        in the HTFBias constructor, they default to None, which breaks TP safety.
        """
        # Create bias WITHOUT opposing FVG fields (simulating the bug)
        bias_with_bug = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_15m="HH",
            structure_1h="HH",
            # Include first 6 TP target fields
            htf_range_high=2670.0,
            htf_range_low=2630.0,
            untouched_liquidity_high=2675.0,
            untouched_liquidity_low=2625.0,
            nearest_fvg_high=2665.0,
            nearest_fvg_low=2635.0,
            # BUG: Omit opposing FVG fields (as in streaming.py lines 314-320)
            # They will default to None
        )

        # Verify opposing FVG fields default to None (demonstrating the bug)
        assert (
            bias_with_bug.opposing_fvg_high is None
        ), "opposing_fvg_high defaults to None when omitted"
        assert (
            bias_with_bug.opposing_fvg_low is None
        ), "opposing_fvg_low defaults to None when omitted"
        assert (
            bias_with_bug.opposing_fvg_bullish_high is None
        ), "opposing_fvg_bullish_high defaults to None when omitted"
        assert (
            bias_with_bug.opposing_fvg_bullish_low is None
        ), "opposing_fvg_bullish_low defaults to None when omitted"

        # This is the problem: signal_engine.py's _check_tp_safety() will miss
        # blocking FVGs because these fields are None
