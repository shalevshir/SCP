"""Unit tests for FVG alignment scoring.

Tests the score_fvg_alignment function which adjusts HTF bias score based on
alignment of unfilled Fair Value Gaps with the current trend direction.
"""

from __future__ import annotations

import pandas as pd
import pytest

from rule_engine.htf.vwap.fvg import score_fvg_alignment


class TestScoreFVGAlignment:
    """Test suite for FVG alignment scoring."""

    # ========================================================================
    # Core Functionality Tests
    # ========================================================================

    def test_bullish_bias_with_aligned_bullish_fvgs(self):
        """Test that bullish FVGs increase score for bullish bias."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8],
            'fvg_type': ['bullish', 'bullish', 'bullish'],
            'fvg_high': [103, 108, 112],
            'fvg_low': [100, 105, 110],
            'filled': [False, False, False],
            'fill_index': [None, None, None]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 3 aligned bullish FVGs: 3 * 0.5 = +1.5
        assert score == 1.5

    def test_bearish_bias_with_aligned_bearish_fvgs(self):
        """Test that bearish FVGs increase score for bearish bias."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5],
            'fvg_type': ['bearish', 'bearish'],
            'fvg_high': [100, 98],
            'fvg_low': [97, 95],
            'filled': [False, False],
            'fill_index': [None, None]
        })
        
        score = score_fvg_alignment(fvg_df, "bearish")
        
        # 2 aligned bearish FVGs: 2 * 0.5 = +1.0
        assert score == 1.0

    def test_bullish_bias_with_opposing_bearish_fvgs(self):
        """Test that bearish FVGs decrease score for bullish bias."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8],
            'fvg_type': ['bearish', 'bearish', 'bearish'],
            'fvg_high': [100, 98, 96],
            'fvg_low': [97, 95, 93],
            'filled': [False, False, False],
            'fill_index': [None, None, None]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 3 opposing bearish FVGs: -3 * 0.5 = -1.5
        assert score == -1.5

    def test_bearish_bias_with_opposing_bullish_fvgs(self):
        """Test that bullish FVGs decrease score for bearish bias."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5],
            'fvg_type': ['bullish', 'bullish'],
            'fvg_high': [103, 108],
            'fvg_low': [100, 105],
            'filled': [False, False],
            'fill_index': [None, None]
        })
        
        score = score_fvg_alignment(fvg_df, "bearish")
        
        # 2 opposing bullish FVGs: -2 * 0.5 = -1.0
        assert score == -1.0

    def test_mixed_fvgs_net_score(self):
        """Test that mixed FVGs produce net score."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8, 11],
            'fvg_type': ['bullish', 'bullish', 'bearish', 'bullish'],
            'fvg_high': [103, 108, 107, 112],
            'fvg_low': [100, 105, 104, 110],
            'filled': [False, False, False, False],
            'fill_index': [None, None, None, None]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 3 aligned bullish, 1 opposing bearish: (3 * 0.5) - (1 * 0.5) = +1.0
        assert score == 1.0

    # ========================================================================
    # Filled Status Tests
    # ========================================================================

    def test_filled_fvgs_ignored(self):
        """Test that filled FVGs don't contribute to score."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8],
            'fvg_type': ['bullish', 'bullish', 'bullish'],
            'fvg_high': [103, 108, 112],
            'fvg_low': [100, 105, 110],
            'filled': [True, True, True],  # All filled
            'fill_index': [10, 12, 15]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # All FVGs filled → no score adjustment
        assert score == 0.0

    def test_unfilled_fvgs_count(self):
        """Test that unfilled FVGs contribute to score."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5],
            'fvg_type': ['bullish', 'bullish'],
            'fvg_high': [103, 108],
            'fvg_low': [100, 105],
            'filled': [False, False],
            'fill_index': [None, None]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 2 unfilled aligned FVGs: 2 * 0.5 = +1.0
        assert score == 1.0

    def test_mix_filled_unfilled_only_unfilled_count(self):
        """Test that only unfilled FVGs count in scoring."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8, 11],
            'fvg_type': ['bullish', 'bullish', 'bullish', 'bullish'],
            'fvg_high': [103, 108, 112, 115],
            'fvg_low': [100, 105, 110, 113],
            'filled': [False, True, False, True],  # 2 unfilled, 2 filled
            'fill_index': [None, 12, None, 18]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # Only 2 unfilled bullish FVGs count: 2 * 0.5 = +1.0
        assert score == 1.0

    # ========================================================================
    # Edge Cases Tests
    # ========================================================================

    def test_empty_fvg_dataframe(self):
        """Test that empty FVG DataFrame returns 0.0."""
        fvg_df = pd.DataFrame({
            'fvg_index': [],
            'fvg_type': [],
            'fvg_high': [],
            'fvg_low': [],
            'filled': [],
            'fill_index': []
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        assert score == 0.0

    def test_neutral_bias_returns_zero(self):
        """Test that neutral bias always returns 0.0 regardless of FVGs."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5],
            'fvg_type': ['bullish', 'bullish'],
            'fvg_high': [103, 108],
            'fvg_low': [100, 105],
            'filled': [False, False],
            'fill_index': [None, None]
        })
        
        score = score_fvg_alignment(fvg_df, "neutral")
        
        # Neutral bias always returns 0.0
        assert score == 0.0

    def test_invalid_bias_raises_error(self):
        """Test that invalid bias string raises ValueError."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2],
            'fvg_type': ['bullish'],
            'fvg_high': [103],
            'fvg_low': [100],
            'filled': [False],
            'fill_index': [None]
        })
        
        with pytest.raises(ValueError, match="Invalid bias"):
            score_fvg_alignment(fvg_df, "sideways")
        
        with pytest.raises(ValueError, match="Invalid bias"):
            score_fvg_alignment(fvg_df, "BULLISH")  # Case sensitive
        
        with pytest.raises(ValueError, match="Invalid bias"):
            score_fvg_alignment(fvg_df, "")

    def test_no_unfilled_fvgs_all_filled(self):
        """Test that when all FVGs are filled, score is 0.0."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8],
            'fvg_type': ['bullish', 'bearish', 'bullish'],
            'fvg_high': [103, 100, 108],
            'fvg_low': [100, 97, 105],
            'filled': [True, True, True],  # All filled
            'fill_index': [10, 12, 15]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        assert score == 0.0

    # ========================================================================
    # Scoring Validation Tests
    # ========================================================================

    def test_multiple_aligned_fvgs_correct_multiplication(self):
        """Test that multiple aligned FVGs multiply correctly."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8, 11, 14],
            'fvg_type': ['bullish'] * 5,
            'fvg_high': [103, 108, 112, 115, 120],
            'fvg_low': [100, 105, 110, 113, 118],
            'filled': [False] * 5,
            'fill_index': [None] * 5
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 5 aligned bullish FVGs: 5 * 0.5 = +2.5
        assert score == 2.5

    def test_multiple_opposing_fvgs_correct_subtraction(self):
        """Test that multiple opposing FVGs subtract correctly."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8, 11],
            'fvg_type': ['bearish'] * 4,
            'fvg_high': [100, 98, 96, 94],
            'fvg_low': [97, 95, 93, 91],
            'filled': [False] * 4,
            'fill_index': [None] * 4
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 4 opposing bearish FVGs: -4 * 0.5 = -2.0
        assert score == -2.0

    def test_equal_counts_score_zero(self):
        """Test that equal aligned and opposing FVGs cancel out."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8, 11],
            'fvg_type': ['bullish', 'bullish', 'bearish', 'bearish'],
            'fvg_high': [103, 108, 100, 98],
            'fvg_low': [100, 105, 97, 95],
            'filled': [False] * 4,
            'fill_index': [None] * 4
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 2 aligned, 2 opposing: (2 * 0.5) - (2 * 0.5) = 0.0
        assert score == 0.0

    # ========================================================================
    # Additional Edge Cases
    # ========================================================================

    def test_single_aligned_fvg(self):
        """Test scoring with single aligned FVG."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2],
            'fvg_type': ['bullish'],
            'fvg_high': [103],
            'fvg_low': [100],
            'filled': [False],
            'fill_index': [None]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 1 aligned FVG: 1 * 0.5 = +0.5
        assert score == 0.5

    def test_single_opposing_fvg(self):
        """Test scoring with single opposing FVG."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2],
            'fvg_type': ['bearish'],
            'fvg_high': [100],
            'fvg_low': [97],
            'filled': [False],
            'fill_index': [None]
        })
        
        score = score_fvg_alignment(fvg_df, "bullish")
        
        # 1 opposing FVG: -1 * 0.5 = -0.5
        assert score == -0.5

    def test_bearish_bias_mixed_fvgs(self):
        """Test bearish bias with mixed FVGs."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5, 8],
            'fvg_type': ['bearish', 'bullish', 'bearish'],
            'fvg_high': [100, 108, 98],
            'fvg_low': [97, 105, 95],
            'filled': [False, False, False],
            'fill_index': [None, None, None]
        })
        
        score = score_fvg_alignment(fvg_df, "bearish")
        
        # 2 aligned bearish, 1 opposing bullish: (2 * 0.5) - (1 * 0.5) = +0.5
        assert score == 0.5

    def test_only_filled_bullish_fvgs_with_bearish_bias(self):
        """Test that filled FVGs don't affect score even with opposing bias."""
        fvg_df = pd.DataFrame({
            'fvg_index': [2, 5],
            'fvg_type': ['bullish', 'bullish'],
            'fvg_high': [103, 108],
            'fvg_low': [100, 105],
            'filled': [True, True],  # Both filled
            'fill_index': [10, 12]
        })
        
        score = score_fvg_alignment(fvg_df, "bearish")
        
        # Filled FVGs don't count, even though they oppose
        assert score == 0.0

    def test_neutral_bias_with_empty_dataframe(self):
        """Test neutral bias with empty FVG DataFrame."""
        fvg_df = pd.DataFrame({
            'fvg_index': [],
            'fvg_type': [],
            'fvg_high': [],
            'fvg_low': [],
            'filled': [],
            'fill_index': []
        })
        
        score = score_fvg_alignment(fvg_df, "neutral")
        
        assert score == 0.0

