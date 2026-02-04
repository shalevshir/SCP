"""Tests for strict structure scoring logic.

Tests the new structure quality requirements that prevent micro-chop entries
from scoring high on structure alignment alone.
"""

import pandas as pd
import pytest
from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.scoring import calculate_structure_alignment


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
        """Test that chop detection still allows partial structure score.

        Per 2024-02 optimization: DXY_CONTINUATION uses relaxed scoring:
        - BOS recency, clarity, chop are SCORING-ONLY factors, not hard rejections
        - This allows continuation setups in regimes where BOS is older (mean ~542 bars)
        - Chop is handled via chop_penalty applied separately, not in structure_alignment
        """
        # Arrange: Good clarity and recent BOS, but chop detected
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            structure_clarity=0.8,  # Clean - gives +20% bonus
            bars_since_bos=12,  # Recent (10-20 range) - gives +10% bonus
            chop_detected=True,  # CHOP! (but no longer a hard rejection)
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

        # Assert: Chop detected still scores with relaxed DXY_CONTINUATION scoring
        # Base 40% + 20% clarity + 10% BOS recency = 70% = 1.75
        assert score == pytest.approx(1.75, rel=0.01)

    def test_stale_bos_returns_partial_points(self):
        """Test that stale BOS (>30 bars ago) gets base score without recency bonus.

        Per 2024-02 optimization: DXY_CONTINUATION uses relaxed scoring:
        - BOS recency, clarity are SCORING-ONLY factors, not hard rejections
        - This allows continuation setups in regimes where BOS is older (mean ~542 bars)
        - Base score is 40% of max_points even with stale BOS
        """
        # Arrange: Clean structure but stale BOS
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="medium",
            structure_clarity=0.9,  # Clean - gives +20% bonus
            bars_since_bos=40,  # Very stale - no BOS recency bonus
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

        # Assert: Base 40% + 20% clarity bonus = 60% = 1.5 (no BOS recency bonus, no sweep)
        assert score == pytest.approx(1.5, rel=0.01)

    def test_poor_clarity_returns_low_score(self):
        """Test that poor structure clarity gets base score without clarity bonus.

        Per 2024-02 optimization: DXY_CONTINUATION uses relaxed scoring:
        - Clarity is a SCORING-ONLY factor, not hard rejection
        - Poor clarity (< 0.5) doesn't get clarity bonus but still gets base score
        """
        # Arrange: Poor clarity despite recent BOS
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=6.0,
            confidence="low",
            structure_clarity=0.3,  # Poor - no clarity bonus
            bars_since_bos=10,  # Recent BOS - gets +20% bonus
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

        # Assert: Base 40% + 20% BOS recency bonus = 60% = 1.5 (no clarity bonus, no sweep)
        assert score == pytest.approx(1.5, rel=0.01)

    def test_micro_chop_conditions_return_base_score(self):
        """Test that micro-chop conditions return base score (relaxed scoring).

        Per 2024-02 optimization: DXY_CONTINUATION uses relaxed scoring:
        - BOS recency, clarity, chop are SCORING-ONLY factors, not hard rejections
        - Base score is 40% of max_points even with poor conditions
        - Chop penalty is applied separately in the main scoring flow
        """
        # Arrange: Classic micro-chop: poor clarity, old BOS, chop detected
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=5.0,
            confidence="low",
            structure_clarity=0.2,  # Very poor - no bonus
            bars_since_bos=50,  # Very stale - no bonus
            chop_detected=True,  # Chop! (no longer hard rejection)
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

        # Assert: Base 40% score (no bonuses for poor conditions)
        assert score == pytest.approx(1.0, rel=0.01)

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
        """Test that moderate clarity (0.5-0.7) gets partial clarity bonus.

        Per 2024-02 optimization: DXY_CONTINUATION uses relaxed scoring:
        - Moderate clarity (0.5-0.7) gets +10% bonus
        - BOS recency <= 10 gets +20% bonus
        """
        # Arrange: Moderate clarity
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            structure_clarity=0.5,  # Moderate - gets +10% clarity bonus
            bars_since_bos=10,  # Recent BOS - gets +20% bonus
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

        # Assert: Base 40% + 10% moderate clarity + 20% BOS recency = 70% = 1.75
        assert score == pytest.approx(1.75, rel=0.01)

    def test_moderate_bos_age_gets_partial_credit(self):
        """Test that BOS between 15-30 bars gets base score without full BOS bonus.

        Per 2024-02 optimization: DXY_CONTINUATION uses relaxed scoring:
        - BOS age 10-20 gets +10% bonus (moderately recent)
        - BOS age > 20 gets no BOS bonus
        - High clarity (>= 0.7) gets +20% bonus
        """
        # Arrange: BOS 25 bars ago (within grace window)
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="medium",
            structure_clarity=0.9,  # High clarity - gets +20% bonus
            bars_since_bos=25,  # Moderately stale - no BOS bonus (> 20)
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

        # Assert: Base 40% + 20% high clarity = 60% = 1.5 (no BOS bonus, no sweep)
        assert score == pytest.approx(1.5, rel=0.01)
