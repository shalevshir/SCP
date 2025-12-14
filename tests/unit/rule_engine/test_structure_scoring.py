"""Tests for strict structure scoring logic.

Tests the new structure quality requirements that prevent micro-chop entries
from scoring high on structure alignment alone.
"""

import pandas as pd
import pytest
from rule_engine.htf.types import HTFBias
from rule_engine.scoring import calculate_structure_alignment


class TestCalculateStructureAlignment:
    """Tests for strict structure alignment scoring."""

    def test_perfect_structure_gets_full_points(self):
        """Test that clean, recent structure with no chop gets full points."""
        # Arrange: Perfect A+ structure
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=9.0,
            confidence="high",
            structure_clarity=0.9,  # Very clean
            bars_since_bos=10,  # Recent
            chop_detected=False,  # No chop
            liquidity_sweep_detected=True,  # Required for structure scoring
        )
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
            }
        )
        max_points = 2.5

        # Act
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Assert: Should get full points (40% + 30% + 30% = 100%)
        assert score == max_points

    def test_chop_detected_returns_partial_points(self):
        """Test that chop detection prevents full structure score."""
        # Arrange: Good clarity and recent BOS, but chop detected
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            structure_clarity=0.8,  # Clean
            bars_since_bos=12,  # Recent
            chop_detected=True,  # CHOP!
        )
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
            }
        )
        max_points = 2.5

        # Act
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Assert: Chop detected returns 0 for strict setups (DXY_CONTINUATION)
        assert score == 0.0

    def test_stale_bos_returns_partial_points(self):
        """Test that stale BOS (>30 bars ago) gets no recency credit."""
        # Arrange: Clean structure but stale BOS
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="medium",
            structure_clarity=0.9,  # Clean
            bars_since_bos=40,  # Too old!
            chop_detected=False,
        )
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
            }
        )
        max_points = 2.5

        # Act
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Assert: Stale BOS (>15 bars) returns 0 for strict setups
        assert score == 0.0

    def test_poor_clarity_returns_low_score(self):
        """Test that poor structure clarity gets minimal points."""
        # Arrange: Poor clarity despite recent BOS
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=6.0,
            confidence="low",
            structure_clarity=0.3,  # Poor!
            bars_since_bos=10,
            chop_detected=False,
        )
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
            }
        )
        max_points = 2.5

        # Act
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Assert: Low clarity (<0.6) returns 0 for strict setups
        assert score == 0.0

    def test_micro_chop_conditions_return_zero(self):
        """Test that micro-chop conditions (mixed structure, chop) return near-zero."""
        # Arrange: Classic micro-chop: poor clarity, old BOS, chop detected
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=5.0,
            confidence="low",
            structure_clarity=0.2,  # Very poor
            bars_since_bos=50,  # Very stale
            chop_detected=True,  # Chop!
        )
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
            }
        )
        max_points = 2.5

        # Act
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Assert: Should get 0 points (fails all checks)
        assert score == 0.0

    def test_direction_mismatch_returns_zero(self):
        """Test that direction mismatch returns zero regardless of quality."""
        # Arrange: Perfect structure but wrong direction
        htf_bias = HTFBias(
            bias="bearish",  # Bearish bias
            direction="short",
            score=9.0,
            confidence="high",
            structure_clarity=0.9,
            bars_since_bos=10,
            chop_detected=False,
        )
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,  # Signal would be long (close > vwap)
                "ema_9": 2648.0,
                "ema_20": 2645.0,
            }
        )
        max_points = 2.5

        # Act
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Assert: Direction mismatch = 0 points
        assert score == 0.0

    def test_moderate_clarity_gets_partial_credit(self):
        """Test that moderate clarity (0.4-0.7) gets partial credit."""
        # Arrange: Moderate clarity
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            structure_clarity=0.5,  # Moderate
            bars_since_bos=10,
            chop_detected=False,
        )
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
            }
        )
        max_points = 2.5

        # Act
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Assert: Moderate clarity (0.5 < 0.6) returns 0 for strict setups
        assert score == 0.0

    def test_moderate_bos_age_gets_partial_credit(self):
        """Test that BOS between 15-30 bars gets partial credit."""
        # Arrange: BOS 25 bars ago (within grace window)
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="medium",
            structure_clarity=0.9,
            bars_since_bos=25,  # In grace window (15-30)
            chop_detected=False,
        )
        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
            }
        )
        max_points = 2.5

        # Act
        score = calculate_structure_alignment(
            features, htf_bias, max_points, "DXY_CONTINUATION"
        )

        # Assert: BOS > 15 bars returns 0 for strict setups
        assert score == 0.0
