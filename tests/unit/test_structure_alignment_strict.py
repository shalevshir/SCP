"""Unit tests for stricter structure alignment scoring.

Tests that calculate_structure_alignment() applies hard rejections for:
- Choppy structure (chop_detected=True)
- No recent BOS (bars_since_bos > 15 or None)
- Low structure clarity (< 0.6)
- No liquidity sweep

Following TDD: These tests will fail until implementation is complete.
"""

import pandas as pd
import pytest

from rule_engine.scoring import calculate_structure_alignment
from rule_engine.htf.types import HTFBias


class TestStructureAlignmentStrict:
    """Test stricter structure alignment scoring with hard rejections."""

    def test_perfect_structure_gets_full_score(self):
        """Test perfect structure alignment gets full points."""
        features = pd.Series(
            {
                "close": 2655.0,
                "vwap": 2650.0,
                "ema_9": 2652.0,
                "ema_20": 2650.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            structure_clarity=0.9,  # High clarity
            bars_since_bos=10,  # Recent BOS
            chop_detected=False,  # No chop
            liquidity_sweep_detected=True,  # Sweep present
            liquidity_sweep_type="bullish",
        )

        max_points = 2.5
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Should get full points for perfect structure
        assert score == max_points

    def test_reject_choppy_structure(self):
        """Test rejection when chop_detected is True."""
        features = pd.Series(
            {
                "close": 2655.0,
                "vwap": 2650.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_clarity=0.8,
            bars_since_bos=10,
            chop_detected=True,  # CHOP DETECTED - should reject
            liquidity_sweep_detected=True,
        )

        max_points = 2.5
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        assert score == 0.0  # Hard rejection

    def test_reject_no_recent_bos(self):
        """Test rejection when no BOS detected."""
        features = pd.Series(
            {
                "close": 2655.0,
                "vwap": 2650.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_clarity=0.8,
            bars_since_bos=None,  # NO BOS - should reject
            chop_detected=False,
            liquidity_sweep_detected=True,
        )

        max_points = 2.5
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        assert score == 0.0  # Hard rejection

    def test_reject_stale_bos(self):
        """Test rejection when BOS is too old (>15 bars)."""
        features = pd.Series(
            {
                "close": 2655.0,
                "vwap": 2650.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_clarity=0.8,
            bars_since_bos=20,  # STALE BOS (>15) - should reject
            chop_detected=False,
            liquidity_sweep_detected=True,
        )

        max_points = 2.5
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        assert score == 0.0  # Hard rejection

    def test_reject_low_structure_clarity(self):
        """Test rejection when structure clarity is low (<0.6)."""
        features = pd.Series(
            {
                "close": 2655.0,
                "vwap": 2650.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_clarity=0.3,  # LOW CLARITY (<0.6) - should reject
            bars_since_bos=10,
            chop_detected=False,
            liquidity_sweep_detected=True,
        )

        max_points = 2.5
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        assert score == 0.0  # Hard rejection

    def test_reject_no_liquidity_sweep(self):
        """Test rejection when no liquidity sweep detected."""
        features = pd.Series(
            {
                "close": 2655.0,
                "vwap": 2650.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_clarity=0.8,
            bars_since_bos=10,
            chop_detected=False,
            liquidity_sweep_detected=False,  # NO SWEEP - should reject
        )

        max_points = 2.5
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        assert score == 0.0  # Hard rejection

    def test_direction_mismatch_still_rejects(self):
        """Test rejection when direction doesn't match HTF bias."""
        features = pd.Series(
            {
                "close": 2645.0,  # Below VWAP
                "vwap": 2650.0,
                "ema_9": 2648.0,
                "ema_20": 2650.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",  # Wants long but features suggest short
            score=8.0,
            confidence="high",
            structure_clarity=0.8,
            bars_since_bos=10,
            chop_detected=False,
            liquidity_sweep_detected=True,
        )

        max_points = 2.5
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        assert score == 0.0  # Direction mismatch rejects

    def test_moderate_structure_gets_partial_score(self):
        """Test moderate structure quality gets partial points."""
        features = pd.Series(
            {
                "close": 2655.0,
                "vwap": 2650.0,
                "ema_9": 2652.0,
                "ema_20": 2650.0,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_clarity=0.65,  # Moderate clarity (>0.6 but <0.7)
            bars_since_bos=14,  # Recent but not super recent
            chop_detected=False,
            liquidity_sweep_detected=True,
            liquidity_sweep_type="bullish",
        )

        max_points = 2.5
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Should get partial points (not 0, not max)
        assert 0 < score < max_points
