"""Test that enhanced VWAP_RECLAIM validation is actually executed in scoring.py.

This test verifies the fix for the dead code issue where validate_reclaim_prerequisites
was not receiving the features parameter.
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.scoring import determine_setup_type


class TestVWAPReclaimEnhancedValidation:
    """Test that enhanced validation checks are executed."""

    def test_bos_direction_mismatch_rejects_long_reclaim(self) -> None:
        """Test that BOS direction mismatch rejects long VWAP_RECLAIM setup.

        This verifies the enhanced validation in validate_reclaim_prerequisites
        is actually being called with features parameter.
        """
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "dxy_corr": -0.75,
                # Structure fields - BOS direction mismatches trade direction
                "bos_direction": "bearish",  # Wrong direction for long setup
                "choch_detected": False,
                "structure_conflict_flag": False,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bos_detected=True,
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            chop_detected=False,
        )

        setup_type = determine_setup_type(features, htf_bias)

        # Should reject due to BOS direction mismatch
        assert setup_type == "REJECTED"

    def test_bos_direction_match_accepts_long_reclaim(self) -> None:
        """Test that BOS direction match accepts long VWAP_RECLAIM setup."""
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "dxy_corr": -0.75,
                "structure_label": "HH",  # Required for validation
                # Structure fields - BOS direction matches trade direction
                "bos_direction": "bullish",  # Correct direction for long setup
                "choch_detected": False,
                "structure_conflict_flag": False,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            bos_detected=True,
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            chop_detected=False,
        )

        setup_type = determine_setup_type(features, htf_bias)

        # Should accept as VWAP_RECLAIM
        assert setup_type == "VWAP_RECLAIM"

    def test_choch_direction_can_substitute_for_bos(self) -> None:
        """Test that CHoCH direction can substitute for BOS direction."""
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "dxy_corr": -0.75,
                "structure_label": "HH",  # Required for validation
                # Structure fields - CHoCH direction matches, BOS doesn't
                "bos_direction": None,  # No BOS direction
                "choch_detected": True,
                "choch_direction": "bullish",  # CHoCH matches trade direction
                "structure_conflict_flag": False,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            bos_detected=True,
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            chop_detected=False,
        )

        setup_type = determine_setup_type(features, htf_bias)

        # Should accept as VWAP_RECLAIM (CHoCH substitutes for BOS)
        assert setup_type == "VWAP_RECLAIM"

    def test_structure_conflict_rejects_reclaim(self) -> None:
        """Test that structure conflict flag rejects VWAP_RECLAIM setup."""
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "dxy_corr": -0.75,
                # Structure fields - conflict detected
                "bos_direction": "bullish",
                "choch_detected": False,
                "structure_conflict_flag": True,  # Conflict should reject
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bos_detected=True,
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            chop_detected=False,
        )

        setup_type = determine_setup_type(features, htf_bias)

        # Should reject due to structure conflict
        assert setup_type == "REJECTED"

    def test_bos_direction_mismatch_rejects_short_reclaim(self) -> None:
        """Test that BOS direction mismatch rejects short VWAP_RECLAIM setup."""
        features = pd.Series(
            {
                "close": 2640.0,
                "vwap": 2645.0,
                "rsi": 45.0,
                "dxy_corr": -0.75,
                # Structure fields - BOS direction mismatches trade direction
                "bos_direction": "bullish",  # Wrong direction for short setup
                "choch_detected": False,
                "structure_conflict_flag": False,
            }
        )

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=8.0,
            confidence="high",
            bos_detected=True,
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            chop_detected=False,
        )

        setup_type = determine_setup_type(features, htf_bias)

        # Should reject due to BOS direction mismatch
        assert setup_type == "REJECTED"

    def test_bos_direction_match_accepts_short_reclaim(self) -> None:
        """Test that BOS direction match accepts short VWAP_RECLAIM setup."""
        features = pd.Series(
            {
                "close": 2640.0,
                "vwap": 2645.0,
                "rsi": 45.0,
                "dxy_corr": -0.75,
                "structure_label": "LL",  # Required for validation - bearish for short
                # Structure fields - BOS direction matches trade direction
                "bos_direction": "bearish",  # Correct direction for short setup
                "choch_detected": False,
                "structure_conflict_flag": False,
            }
        )

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=8.0,
            confidence="high",
            structure_1h="LL",  # Required for validation
            bos_detected=True,
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            chop_detected=False,
        )

        setup_type = determine_setup_type(features, htf_bias)

        # Should accept as VWAP_RECLAIM
        assert setup_type == "VWAP_RECLAIM"

    def test_choch_overrides_conflicting_bos_direction(self) -> None:
        """Test that CHoCH direction can override conflicting BOS direction.

        This specifically tests the bug fix where choch_direction was missing
        from streaming features, making CHoCH validation always fail.
        """
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "dxy_corr": -0.75,
                "structure_label": "HH",  # Required for validation
                # Structure fields - BOS conflicts but CHoCH is correct
                "bos_direction": "bearish",  # Wrong direction
                "choch_detected": True,
                "choch_direction": "bullish",  # Correct direction - should override BOS
                "structure_conflict_flag": False,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            bos_detected=True,
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            chop_detected=False,
        )

        setup_type = determine_setup_type(features, htf_bias)

        # Should accept as VWAP_RECLAIM (CHoCH direction overrides BOS)
        assert setup_type == "VWAP_RECLAIM"

