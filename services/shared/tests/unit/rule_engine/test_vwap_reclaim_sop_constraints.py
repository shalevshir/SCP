"""Tests for VWAP_RECLAIM SOP alignment constraints.

Tests the new config constraints added for SOP alignment:
- vwap_reclaim_distance: Rejects chase reclaims (> 3 ATR from VWAP)
- no_late_reclaim: Blocks entries immediately after BOS
- min_vwap_acceptance: Requires >= 3 bars near VWAP
- reclaim_timing_gate: Requires reclaim within 10 bars of VWAP touch
"""

import pandas as pd
import pytest
from scp_shared.rule_engine.setup_validator import SetupValidator


class TestVWAPReclaimDistanceConstraint:
    """Test vwap_reclaim_distance constraint (max 3.0 ATR)."""

    def test_accepts_reclaim_within_range(self):
        """Test that reclaims within 0.5-3.0 ATR pass."""
        validator = SetupValidator()

        # Test at 1.5 ATR (ideal range)
        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_chase_reclaim_above_3_atr(self):
        """Test that reclaims > 3.0 ATR are rejected (chase entry)."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 4.5,  # Too far from VWAP
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "late/chase reclaim" in result.reject_reason.lower()

    def test_accepts_at_upper_boundary(self):
        """Test that exactly 3.0 ATR passes."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 3.0,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_below_minimum_threshold(self):
        """Test that reclaims < 0.5 ATR are rejected (too close, micro-fakeout)."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 0.3,  # Too close
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid


class TestNoLateReclaimConstraint:
    """Test no_late_reclaim constraint (blocks BOS age < 20)."""

    def test_accepts_reclaim_after_bos_cooled_off(self):
        """Test that reclaims with BOS age >= 20 pass."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": "bullish",  # Required for bos_reclaim_gate
            "bos_recent": True,  # Recent BOS flag
            "bos_age": 25,  # But old enough
            "conflict_detected": False,
            "choch_detected": False,  # Required for direction_bos_alignment
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_late_reclaim_bos_age_15(self):
        """Test that reclaims with recent BOS (age < 20) are rejected."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": "bullish",
            "bos_recent": True,
            "bos_age": 15,  # Too recent
            "conflict_detected": False,
            "choch_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "late" in result.reject_reason.lower()

    def test_accepts_when_bos_not_recent(self):
        """Test that reclaims pass when bos_recent is False."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 5,  # Age doesn't matter if not recent
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_accepts_at_boundary(self):
        """Test that BOS age exactly 20 passes."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": "bullish",
            "bos_recent": True,
            "bos_age": 20,  # Boundary
            "conflict_detected": False,
            "choch_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid


class TestBOSReclaimGateConstraint:
    """Test bos_reclaim_gate constraint (blocks BOS direction conflicts)."""

    def test_accepts_when_bos_direction_matches(self):
        """Test that reclaims pass when BOS direction matches trade direction."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": "bullish",  # Matches long
            "bos_recent": False,
            "bos_age": 18,  # Recent but matches direction
            "conflict_detected": False,
            "choch_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_when_bos_direction_conflicts(self):
        """Test that reclaims are rejected when BOS direction conflicts."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": "bearish",  # Conflicts with long
            "bos_recent": False,
            "bos_age": 18,  # Age < 20 and direction conflicts
            "conflict_detected": False,
            "choch_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "BOS direction conflicts" in result.reject_reason

    def test_accepts_old_bos_despite_direction_conflict(self):
        """Test that old BOS (age >= 20) is ignored even if direction conflicts."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": "bearish",  # Conflicts
            "bos_recent": False,
            "bos_age": 25,  # But old enough to ignore
            "conflict_detected": False,
            "choch_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_accepts_when_no_bos_exists(self):
        """Test that reclaims pass when no BOS exists."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": None,  # No BOS
            "bos_recent": False,
            "bos_age": None,
            "conflict_detected": False,
            "choch_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid


class TestMinVWAPAcceptanceConstraint:
    """Test min_vwap_acceptance constraint (>= 3 bars near VWAP)."""

    def test_accepts_with_sufficient_acceptance(self):
        """Test that reclaims with >= 3 bars near VWAP pass."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,  # Good acceptance
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_drive_by_reclaim(self):
        """Test that drive-by reclaims (< 3 bars near VWAP) are rejected."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 1,  # Drive-by
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "drive-by" in result.reject_reason.lower()

    def test_accepts_at_minimum_threshold(self):
        """Test that exactly 3 bars near VWAP passes."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 3,  # Boundary
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_accepts_when_bars_near_vwap_is_none(self):
        """Test that None values pass (ATR unavailable, tracking not possible)."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": "bullish",
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "choch_detected": False,
            "bars_near_vwap": None,  # ATR unavailable
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_when_bars_near_vwap_is_zero(self):
        """Test that 0 fails (tracking available, price not near VWAP)."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_direction": "bullish",
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "choch_detected": False,
            "bars_near_vwap": 0,  # ATR available but price not near VWAP
            "bars_since_last_vwap_touch": 2,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "drive-by" in result.reject_reason.lower()


class TestReclaimTimingGateConstraint:
    """Test reclaim_timing_gate constraint (<= 10 bars since VWAP touch)."""

    def test_accepts_timely_reclaim(self):
        """Test that reclaims within 10 bars of VWAP touch pass."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 5,  # Timely
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_delayed_reclaim(self):
        """Test that delayed reclaims (> 10 bars) are rejected."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 15,  # Too delayed
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "delayed" in result.reject_reason.lower()

    def test_accepts_at_boundary(self):
        """Test that exactly 10 bars passes."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": 10,  # Boundary
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_accepts_when_timing_is_none(self):
        """Test that None values pass (no VWAP touch detected yet)."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.5,
            "bos_recent": False,
            "bos_age": 25,
            "conflict_detected": False,
            "bars_near_vwap": 5,
            "bars_since_last_vwap_touch": None,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid


class TestCombinedConstraints:
    """Test that all constraints work together."""

    def test_perfect_reclaim_passes_all_constraints(self):
        """Test that an ideal reclaim passes all SOP constraints."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 1.2,  # Ideal distance
            "bos_recent": False,
            "bos_age": 30,  # Well past expansion
            "conflict_detected": False,
            "bars_near_vwap": 4,  # Good acceptance
            "bars_since_last_vwap_touch": 3,  # Timely
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid
        # Should pass all constraints
        assert len(result.evaluated_constraints) > 5

    def test_fails_if_any_constraint_violated(self):
        """Test that violating any constraint causes rejection."""
        validator = SetupValidator()

        # Good on all except VWAP distance
        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "vwap_deviation_normalized": 5.0,  # FAIL: too far
            "bos_recent": False,
            "bos_age": 30,
            "conflict_detected": False,
            "bars_near_vwap": 4,
            "bars_since_last_vwap_touch": 3,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
