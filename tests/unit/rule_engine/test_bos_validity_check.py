"""Unit tests for Task 3: BOS Recency Relaxation.

Tests verify that:
1. BOS age alone does NOT trigger penalty
2. Counter-CHoCH invalidates BOS (triggers penalty)
3. Degraded structure (clarity < 0.4) invalidates BOS
4. Valid BOS (no counter-CHoCH, good clarity) has no age penalty
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.scoring import calculate_late_reclaim_penalty, calculate_structure_quality_penalty


class TestBOSValidityCheck:
    """Test suite for BOS validity-based penalty logic."""

    def test_old_bos_no_penalty_if_valid(self):
        """Old BOS should NOT trigger penalty if structure remains valid."""
        features = pd.Series({
            "bos_age": 25,  # Old BOS
            "bos_direction": "bullish",
            "choch_detected": False,  # No counter-CHoCH
            "choch_direction": None,
            "structure_clarity": 0.7,  # Good clarity
            "close": 2650,
            "vwap": 2645,
            "expansion_detected": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=25,
        )
        
        # Should have NO age-based penalty (BOS still valid)
        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")
        
        # Should only have VWAP distance penalty if any, not BOS age penalty
        assert penalty > -1.0, \
            f"Old but valid BOS should not trigger heavy penalty (got {penalty})"

    def test_counter_choch_invalidates_bos(self):
        """Counter-CHoCH should invalidate BOS and trigger penalty."""
        features = pd.Series({
            "bos_age": 15,
            "bos_direction": "bullish",
            "choch_detected": True,  # Counter-CHoCH detected
            "choch_direction": "bearish",  # Opposite to BOS
            "structure_clarity": 0.6,
            "close": 2650,
            "vwap": 2645,
            "expansion_detected": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            bars_since_bos=15,
        )
        
        # Should trigger penalty (BOS invalidated by counter-CHoCH)
        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")
        
        # Should have penalty for invalidated BOS
        assert penalty < 0, \
            f"Counter-CHoCH should invalidate BOS and trigger penalty (got {penalty})"

    def test_degraded_clarity_invalidates_bos(self):
        """Degraded structure clarity should invalidate BOS."""
        features = pd.Series({
            "bos_age": 20,
            "bos_direction": "bullish",
            "choch_detected": False,
            "choch_direction": None,
            "structure_clarity": 0.3,  # Poor clarity
            "close": 2650,
            "vwap": 2645,
            "expansion_detected": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=6.5,
            confidence="low",
            bars_since_bos=20,
        )
        
        # Should trigger penalty (BOS invalidated by poor structure)
        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")
        
        # Should have penalty for degraded structure
        assert penalty < 0, \
            f"Degraded clarity should invalidate BOS and trigger penalty (got {penalty})"

    def test_recent_bos_no_penalty(self):
        """Recent BOS (< 10 bars) should never trigger penalty."""
        features = pd.Series({
            "bos_age": 5,  # Recent
            "bos_direction": "bullish",
            "choch_detected": False,
            "choch_direction": None,
            "structure_clarity": 0.6,
            "close": 2650,
            "vwap": 2645,
            "expansion_detected": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            bars_since_bos=5,
        )
        
        # Should have NO BOS-related penalty
        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")
        
        # Recent BOS should not penalize
        assert penalty >= -0.5, \
            f"Recent BOS should have minimal/no penalty (got {penalty})"


class TestStructureQualityPenaltyWithBOSValidity:
    """Test structure quality penalty uses BOS validity."""
    
    def test_stale_bos_with_valid_structure_minimal_penalty(self):
        """Stale BOS with valid structure should have minimal penalty."""
        features = pd.Series({
            "bos_age": 30,  # Very stale
            "bos_direction": "bullish",
            "choch_detected": False,  # No counter-CHoCH
            "structure_clarity": 0.6,  # Good clarity
            "liquidity_sweep": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="medium",
            bars_since_bos=30,
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
        )
        
        # Quality flags indicating good structure
        quality_flags = {
            "no_sweep": False,  # Has sweep
            "low_clarity": False,  # Good clarity
            "no_bos": False,  # Has BOS
            "bos_stale": True,  # Stale but valid
        }
        
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        
        # Should have minimal penalty (BOS is stale but structure valid)
        assert penalty > -2.0, \
            f"Stale but valid BOS should have minimal penalty (got {penalty})"

    def test_stale_bos_with_invalid_structure_heavy_penalty(self):
        """Stale BOS with invalid structure should have heavy penalty."""
        features = pd.Series({
            "bos_age": 30,
            "bos_direction": "bullish",
            "choch_detected": True,  # Counter-CHoCH
            "choch_direction": "bearish",
            "structure_clarity": 0.3,  # Poor clarity
            "liquidity_sweep": False,
        })
        
        htf_bias = HTFBias(
            bias="neutral",  # Degraded to neutral
            direction="neutral",
            score=4.0,
            confidence="low",
            bars_since_bos=30,
            liquidity_sweep_detected=False,
            structure_clarity=0.3,
            bos_detected=False,
        )
        
        quality_flags = {
            "no_sweep": True,
            "low_clarity": True,
            "no_bos": True,
            "bos_stale": True,
        }
        
        penalty = calculate_structure_quality_penalty(
            features, htf_bias, "VWAP_RECLAIM", quality_flags
        )
        
        # Should have heavy penalty (BOS invalid + poor structure)
        assert penalty < -2.0, \
            f"Invalid BOS with poor structure should have heavy penalty (got {penalty})"






