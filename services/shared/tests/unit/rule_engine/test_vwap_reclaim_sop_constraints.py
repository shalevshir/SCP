"""Tests for VWAP_RECLAIM SOP alignment constraints.

Tests the new config constraints added for SOP alignment:
- vwap_reclaim_distance: Requires prior excursion (0.5-12.0 ATR in last 20 bars)
- vwap_reclaim_current_distance: Rejects chase reclaims (> 3.0 ATR from VWAP)
- no_late_reclaim: Blocks entries immediately after BOS (age < 20)
- min_vwap_acceptance: Requires >= 2 bars near VWAP in last 20 bars
- reclaim_timing_gate: DISABLED (commented out in config)
"""

import pandas as pd
import pytest
from scp_shared.rule_engine.setup_validator import SetupValidator


class TestVWAPReclaimDistanceConstraint:
    """Test vwap_reclaim_distance constraint (prior excursion 0.5-12.0 ATR) and
    vwap_reclaim_current_distance constraint (current distance <= 3.0 ATR)."""

    def test_accepts_reclaim_within_range(self):
        """Test that reclaims with valid prior excursion and current distance pass."""
        validator = SetupValidator()

        # Test with prior excursion at 1.5 ATR (ideal range) and current at 0.8 ATR
        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,  # Prior excursion within 0.5-8.0 ATR
            "vwap_deviation_normalized": 0.8,  # Current distance within 2.0 ATR
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",  # BOS matches direction
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_chase_reclaim_above_3_atr(self):
        """Test that reclaims > 3.0 ATR current distance are rejected (chase entry)."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,  # Valid prior excursion
            "vwap_deviation_normalized": 3.5,  # Too far from VWAP (> 3.0 ATR)
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "too far" in result.reject_reason.lower()

    def test_accepts_at_upper_boundary(self):
        """Test that exactly 3.0 ATR current distance passes."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,  # Valid prior excursion
            "vwap_deviation_normalized": 3.0,  # At boundary
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_below_minimum_threshold(self):
        """Test that no prior excursion (< 0.5 ATR) is rejected."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 0.3,  # No prior excursion (< 0.5 ATR)
            "vwap_deviation_normalized": 0.8,  # Current distance OK
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid


class TestNoLateReclaimConstraint:
    """Test no_late_reclaim constraint (blocks BOS age < 20 when bos_recent is True)."""

    def test_accepts_reclaim_after_bos_cooled_off(self):
        """Test that reclaims with BOS age >= 20 pass."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_direction": "long",  # Must match direction exactly
            "bos_recent": True,  # Recent BOS flag
            "bos_age": 25,  # But old enough (>= 20)
            "conflict_detected": False,
            "choch_detected": False,  # Required for direction_bos_alignment
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_allows_late_reclaim_bos_age_15_with_scoring_penalty(self):
        """Test that reclaims with recent BOS (age < 20) are allowed with scoring penalty.

        Per 2024-02 optimization: BOS constraints moved to SCORING-ONLY:
        - no_late_reclaim constraint removed from config
        - Late reclaims are allowed but get a scoring penalty via calculate_late_reclaim_penalty()
        """
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_direction": "long",
            "bos_recent": True,
            "bos_age": 15,  # Recent BOS (< 20) - now handled via scoring penalty
            "conflict_detected": False,
            "choch_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        # BOS timing is now a scoring penalty, not hard rejection
        assert result.is_valid

    def test_accepts_when_bos_not_recent(self):
        """Test that reclaims pass when bos_recent is False."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 5,  # Age doesn't matter if not recent
            "bos_direction": "long",  # Required for bos_reclaim_gate constraint
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
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
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_direction": "long",
            "bos_recent": True,
            "bos_age": 20,  # Boundary (>= 20)
            "conflict_detected": False,
            "choch_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid


class TestBOSReclaimGateConstraint:
    """Test bos_reclaim_gate constraint (blocks BOS direction conflicts when age < 20)."""

    def test_accepts_when_bos_direction_matches(self):
        """Test that reclaims pass when BOS direction matches trade direction."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_direction": "long",  # Must match direction exactly
            "bos_recent": False,
            "bos_age": 18,  # Recent but matches direction
            "conflict_detected": False,
            "choch_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_allows_bos_direction_conflict_with_scoring_penalty(self):
        """Test that BOS direction conflict is allowed with scoring penalty.

        Per 2024-02 optimization: BOS constraints moved to SCORING-ONLY:
        - bos_reclaim_gate constraint removed from config
        - BOS direction conflicts are handled via calculate_bos_direction_penalty()
        """
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_direction": "short",  # Conflicts with long - now handled via scoring penalty
            "bos_recent": False,
            "bos_age": 18,  # Age < 20 and direction conflicts
            "conflict_detected": False,
            "choch_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        # BOS direction conflict is now a scoring penalty, not hard rejection
        assert result.is_valid

    def test_accepts_old_bos_despite_direction_conflict(self):
        """Test that old BOS (age >= 20) is ignored even if direction conflicts."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_direction": "short",  # Conflicts
            "bos_recent": False,
            "bos_age": 25,  # But old enough to ignore (>= 20)
            "conflict_detected": False,
            "choch_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
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
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_direction": None,  # No BOS
            "bos_recent": False,
            "bos_age": None,
            "conflict_detected": False,
            "choch_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid


class TestMinVWAPAcceptanceConstraint:
    """Test min_vwap_acceptance constraint (>= 2 bars near VWAP in last 20 bars)."""

    def test_accepts_with_sufficient_acceptance(self):
        """Test that reclaims with >= 2 bars near VWAP pass."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,  # Good acceptance
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    def test_rejects_drive_by_reclaim(self):
        """Test that drive-by reclaims (< 2 bars near VWAP) are rejected."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 1,  # Drive-by (< 2)
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "acceptance" in result.reject_reason.lower() or "vwap" in result.reject_reason.lower()

    def test_accepts_at_minimum_threshold(self):
        """Test that exactly 2 bars near VWAP passes."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 2,  # Boundary (>= 2)
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
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
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "choch_detected": False,
            "near_vwap_count_last_20": None,  # ATR unavailable
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
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
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "choch_detected": False,
            "near_vwap_count_last_20": 0,  # No acceptance (< 2)
            "bars_since_last_vwap_touch": 2,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "acceptance" in result.reject_reason.lower() or "vwap" in result.reject_reason.lower()


class TestReclaimTimingGateConstraint:
    """Test reclaim_timing_gate constraint (<= 30 bars since VWAP touch).

    NOTE: This constraint is currently DISABLED in config (commented out).
    Tests are preserved for when/if the constraint is re-enabled.
    """

    def test_accepts_timely_reclaim(self):
        """Test that reclaims within 30 bars of VWAP touch pass."""
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 5,  # Timely
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid

    @pytest.mark.skip(reason="reclaim_timing_gate constraint disabled in config")
    def test_rejects_delayed_reclaim(self):
        """Test that delayed reclaims (> 30 bars) are rejected.

        SKIPPED: reclaim_timing_gate is currently commented out in setups.yaml
        based on EDA showing median bars_since_last_vwap_touch of 130.
        """
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 35,  # Too delayed (> 30)
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
        assert "delayed" in result.reject_reason.lower()

    @pytest.mark.skip(reason="reclaim_timing_gate constraint disabled in config")
    def test_accepts_at_boundary(self):
        """Test that exactly 30 bars passes.

        SKIPPED: reclaim_timing_gate is currently commented out in setups.yaml.
        """
        validator = SetupValidator()

        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": 30,  # Boundary (<= 30)
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
            "max_abs_deviation_last_20": 1.5,
            "vwap_deviation_normalized": 0.8,
            "bos_recent": False,
            "bos_age": 25,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 5,
            "bars_since_last_vwap_touch": None,
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
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
            "max_abs_deviation_last_20": 1.5,  # Valid prior excursion
            "vwap_deviation_normalized": 0.8,  # Within 2.0 ATR
            "bos_recent": False,
            "bos_age": 30,  # Well past expansion
            "bos_direction": "long",  # Required for bos_reclaim_gate constraint
            "conflict_detected": False,
            "near_vwap_count_last_20": 4,  # Good acceptance (>= 2)
            "bars_since_last_vwap_touch": 3,  # Timely (<= 30)
            # Required fields for new constraints
            "vwap_trend_confirmed": True,
            "reclaim_candle_close": 2650.0,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert result.is_valid
        # Should pass all constraints
        assert len(result.evaluated_constraints) > 5

    def test_fails_if_any_constraint_violated(self):
        """Test that violating any constraint causes rejection."""
        validator = SetupValidator()

        # Good on all except current VWAP distance (> 3.0 ATR)
        context = {
            "structure_1h": "HH",
            "structure_label": "HL",
            "direction": "long",
            "max_abs_deviation_last_20": 1.5,  # Valid prior excursion
            "vwap_deviation_normalized": 3.5,  # FAIL: too far (> 3.0 ATR)
            "bos_recent": False,
            "bos_age": 30,
            "bos_direction": "long",
            "conflict_detected": False,
            "near_vwap_count_last_20": 4,
            "bars_since_last_vwap_touch": 3,
        }

        result = validator.validate_setup("VWAP_RECLAIM", context)
        assert not result.is_valid
