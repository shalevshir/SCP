"""Tests for relaxed VWAP_RECLAIM context validation (safety gates only).

This module tests that validate_reclaim_context now only enforces safety gates
and returns quality flags for penalty calculation instead of hard rejection.
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.htf.vwap.reclaim import validate_reclaim_context


def _make_htf_bias(**kwargs):
    """Helper to create HTFBias with required fields."""
    defaults = {
        "bias": "bullish",
        "direction": "long",
        "score": 7.0,
        "confidence": "high",
    }
    defaults.update(kwargs)
    return HTFBias(**defaults)


class TestRelaxedReclaimContext:
    """Test suite for relaxed VWAP_RECLAIM context validation."""

    def test_safety_gate_direction_mismatch_rejects(self):
        """Direction mismatch with BOS/CHoCH should still hard reject (SAFETY)."""
        features = pd.Series({
            "liquidity_sweep": True,
            "structure_clarity": 0.8,
            "bos_recent": True,
            "bos_direction": "bearish",  # Mismatch with long direction
            "choch_detected": False,
            "structure_conflict_flag": False,
        })
        htf_bias = _make_htf_bias(
            structure_clarity=0.8,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=5,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        assert result.context_valid is False
        assert "SAFETY" in result.reason
        assert "bullish BOS/CHoCH" in result.reason

    def test_safety_gate_structure_conflict_rejects(self):
        """Structure conflict flag should still hard reject (SAFETY)."""
        features = pd.Series({
            "liquidity_sweep": True,
            "structure_clarity": 0.8,
            "bos_recent": True,
            "bos_direction": "bullish",
            "choch_detected": False,
            "structure_conflict_flag": True,  # SAFETY issue
        })
        htf_bias = _make_htf_bias(
            structure_clarity=0.8,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=5,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        assert result.context_valid is False
        assert "SAFETY" in result.reason
        assert "conflict" in result.reason.lower()

    def test_no_sweep_returns_quality_flag_not_rejection(self):
        """No liquidity sweep should return quality flag, not hard reject."""
        features = pd.Series({
            "liquidity_sweep": False,  # Quality issue, not safety
            "structure_clarity": 0.8,
            "bos_recent": True,
            "bos_direction": "bullish",
            "choch_detected": False,
            "structure_conflict_flag": False,
        })
        htf_bias = _make_htf_bias(
            structure_clarity=0.8,
            liquidity_sweep_detected=False,
            bos_detected=True,
            bars_since_bos=5,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should pass safety gates
        assert result.context_valid is True
        assert result.reason is None
        
        # Should have quality flag
        assert result.quality_flags["no_sweep"] is True
        assert result.quality_flags["low_clarity"] is False
        assert result.quality_flags["no_bos"] is False

    def test_low_clarity_returns_quality_flag_not_rejection(self):
        """Low structure clarity should return quality flag, not hard reject."""
        features = pd.Series({
            "liquidity_sweep": True,
            "structure_clarity": 0.3,  # Quality issue, not safety
            "bos_recent": True,
            "bos_direction": "bullish",
            "choch_detected": False,
            "structure_conflict_flag": False,
        })
        htf_bias = _make_htf_bias(
            structure_clarity=0.3,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=5,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should pass safety gates
        assert result.context_valid is True
        assert result.reason is None
        
        # Should have quality flag
        assert result.quality_flags["no_sweep"] is False
        assert result.quality_flags["low_clarity"] is True
        assert result.quality_flags["no_bos"] is False

    def test_no_bos_returns_quality_flag_not_rejection(self):
        """No BOS detected should return quality flag, not hard reject."""
        features = pd.Series({
            "liquidity_sweep": True,
            "structure_clarity": 0.8,
            "bos_recent": False,  # Quality issue, not safety
            "bos_direction": None,
            "choch_detected": True,
            "choch_direction": "bullish",  # Has CHoCH, so direction check passes
            "structure_conflict_flag": False,
        })
        htf_bias = _make_htf_bias(
            structure_clarity=0.8,
            liquidity_sweep_detected=True,
            bos_detected=False,
            bars_since_bos=None,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should pass safety gates (CHoCH provides direction alignment)
        assert result.context_valid is True
        assert result.reason is None
        
        # Should have quality flag
        assert result.quality_flags["no_sweep"] is False
        assert result.quality_flags["low_clarity"] is False
        assert result.quality_flags["no_bos"] is True

    def test_bos_stale_flag_set_correctly(self):
        """BOS staleness flag should be set based on age threshold."""
        features = pd.Series({
            "liquidity_sweep": True,
            "structure_clarity": 0.8,
            "bos_recent": True,
            "bos_direction": "bullish",
            "bos_age": 20,  # Stale (> 15)
            "choch_detected": False,
            "structure_conflict_flag": False,
        })
        htf_bias = _make_htf_bias(
            structure_clarity=0.8,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=20,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should pass safety gates
        assert result.context_valid is True
        
        # Should have bos_stale flag
        assert result.quality_flags["bos_stale"] is True

    def test_multiple_quality_issues_all_flagged(self):
        """Multiple quality issues should all be flagged, not rejected."""
        features = pd.Series({
            "liquidity_sweep": False,  # Quality issue 1
            "structure_clarity": 0.3,  # Quality issue 2
            "bos_recent": False,  # Quality issue 3
            "bos_direction": None,
            "choch_detected": True,
            "choch_direction": "bullish",  # Has CHoCH for direction safety
            "structure_conflict_flag": False,
        })
        htf_bias = _make_htf_bias(
            structure_clarity=0.3,
            liquidity_sweep_detected=False,
            bos_detected=False,
            bars_since_bos=None,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should pass safety gates
        assert result.context_valid is True
        assert result.reason is None
        
        # Should have all quality flags
        assert result.quality_flags["no_sweep"] is True
        assert result.quality_flags["low_clarity"] is True
        assert result.quality_flags["no_bos"] is True

    def test_perfect_quality_no_flags(self):
        """Perfect quality should result in all flags False."""
        features = pd.Series({
            "liquidity_sweep": True,
            "structure_clarity": 0.8,
            "bos_recent": True,
            "bos_direction": "bullish",
            "bos_age": 5,  # Fresh BOS
            "choch_detected": False,
            "structure_conflict_flag": False,
        })
        htf_bias = _make_htf_bias(
            structure_clarity=0.8,
            liquidity_sweep_detected=True,
            bos_detected=True,
            bars_since_bos=5,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should pass safety gates
        assert result.context_valid is True
        assert result.reason is None
        
        # Should have no quality flags
        assert result.quality_flags["no_sweep"] is False
        assert result.quality_flags["low_clarity"] is False
        assert result.quality_flags["no_bos"] is False
        assert result.quality_flags["bos_stale"] is False

    def test_choch_can_substitute_for_bos_direction(self):
        """CHoCH can provide direction alignment when BOS is missing."""
        features = pd.Series({
            "liquidity_sweep": True,
            "structure_clarity": 0.8,
            "bos_recent": False,
            "bos_direction": None,
            "choch_detected": True,
            "choch_direction": "bearish",  # Aligns with short direction
            "structure_conflict_flag": False,
        })
        htf_bias = _make_htf_bias(
            bias="bearish",
            direction="short",
            structure_clarity=0.8,
            liquidity_sweep_detected=True,
            bos_detected=False,
            bars_since_bos=None,
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should pass safety gates (CHoCH provides direction)
        assert result.context_valid is True
        assert result.reason is None
        
        # Should have no_bos quality flag
        assert result.quality_flags["no_bos"] is True

