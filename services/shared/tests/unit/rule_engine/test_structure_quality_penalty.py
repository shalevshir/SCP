"""Tests for structure quality penalty calculation (moved from hard rejection).

This module tests the calculate_structure_quality_penalty function which applies
penalties for quality issues that were previously hard rejections.
"""

import pandas as pd
import pytest

from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.scoring import calculate_structure_quality_penalty


class TestStructureQualityPenalty:
    """Test suite for structure quality penalty calculation."""

    def test_no_penalty_for_non_reclaim_setups(self):
        """VWAP_FADE and DXY_CONTINUATION should not get structure quality penalties."""
        features = pd.Series({"liquidity_sweep": False, "bos_recent": False})
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.3,
            liquidity_sweep_detected=False,
            bos_detected=False,
            bars_since_bos=None,
        )

        # VWAP_FADE should get 0 penalty
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_FADE", None
        )
        assert penalty == 0.0

        # DXY_CONTINUATION should get 0 penalty
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "DXY_CONTINUATION", None
        )
        assert penalty == 0.0

    def test_no_sweep_penalty(self):
        """No liquidity sweep should apply -1.5 penalty."""
        features = pd.Series({"liquidity_sweep": False, "bos_recent": True})
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.6,
            liquidity_sweep_detected=False,
            bos_detected=True,
            bars_since_bos=10,
        )

        quality_flags = {
            "no_sweep": True,
            "low_clarity": False,
            "no_bos": False,
            "bos_stale": False,
        }

        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        assert penalty == -1.5

    def test_low_clarity_graduated_penalty(self):
        """Low structure clarity should apply graduated penalties."""
        features = pd.Series({"liquidity_sweep": True, "bos_recent": True})

        # Very low clarity (< 0.3): -1.5
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.25,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=10,
        )
        quality_flags = {
            "no_sweep": False,
            "low_clarity": True,
            "no_bos": False,
            "bos_stale": False,
        }
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        assert penalty == -1.5

        # Low clarity (0.3-0.4): -1.0
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.35,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=10,
        )
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        assert penalty == -1.0

        # Moderate clarity (0.4-0.6): -0.5
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.5,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=10,
        )
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        assert penalty == -0.5

    def test_no_bos_penalty(self):
        """No BOS detected should apply -2.0 penalty."""
        features = pd.Series({"liquidity_sweep": True, "bos_recent": False})
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.6,
            liquidity_sweep_detected=True,
            bos_detected=False,
            bars_since_bos=None,
        )

        quality_flags = {
            "no_sweep": False,
            "low_clarity": False,
            "no_bos": True,
            "bos_stale": False,
        }

        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        assert penalty == -2.0

    def test_bos_stale_graduated_penalty(self):
        """Stale BOS should apply graduated penalties based on age."""
        features_base = pd.Series({"liquidity_sweep": True, "bos_recent": True})
        htf_bias_base = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.6,
            liquidity_sweep_detected=True,
            bos_detected=True,
        )

        quality_flags_base = {
            "no_sweep": False,
            "low_clarity": False,
            "no_bos": False,
            "bos_stale": True,
        }

        # BOS age 16-20: -0.5
        features = features_base.copy()
        features["bos_age"] = 18
        htf_bias = htf_bias_base
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags_base
        )
        assert penalty == -0.5

        # BOS age 21-25: -1.0
        features["bos_age"] = 23
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags_base
        )
        assert penalty == -1.0

        # BOS age > 25: -1.5
        features["bos_age"] = 30
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags_base
        )
        assert penalty == -1.5

    def test_cumulative_penalties(self):
        """Multiple quality issues should accumulate penalties."""
        features = pd.Series({"liquidity_sweep": False, "bos_recent": False, "bos_age": 30})
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.25,
            liquidity_sweep_detected=False,
            bos_detected=False,
            bars_since_bos=30,
        )

        quality_flags = {
            "no_sweep": True,  # -1.5
            "low_clarity": True,  # -1.5 (very low)
            "no_bos": True,  # -2.0
            "bos_stale": True,  # -1.5 (age > 25)
        }

        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        # Total: -1.5 - 1.5 - 2.0 - 1.5 = -6.5
        assert penalty == -6.5

    def test_quality_flags_auto_extraction(self):
        """Should auto-extract quality flags from features/htf_bias if not provided."""
        features = pd.Series({
            "liquidity_sweep": False,
            "bos_recent": False,
            "bos_age": 20,
        })
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.35,
            liquidity_sweep_detected=False,
            bos_detected=False,
            bars_since_bos=20,
        )

        # quality_flags=None should trigger auto-extraction
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", None
        )
        # Expected: no_sweep (-1.5) + low_clarity (-1.0) + no_bos (-2.0) + bos_stale (-0.5 for age 16-20)
        # Total: -5.0
        assert penalty == -5.0

    def test_perfect_quality_no_penalty(self):
        """Perfect quality (all flags False) should result in 0 penalty."""
        features = pd.Series({
            "liquidity_sweep": True,
            "bos_recent": True,
            "bos_age": 5,
        })
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            structure_clarity=0.8,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=5,
        )

        quality_flags = {
            "no_sweep": False,
            "low_clarity": False,
            "no_bos": False,
            "bos_stale": False,
        }

        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        assert penalty == 0.0

