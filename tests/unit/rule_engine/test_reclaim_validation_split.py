"""Tests for split VWAP_RECLAIM validation (context vs entry readiness).

Following TDD: Tests written before refactoring validate_reclaim_prerequisites().
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.htf.vwap.reclaim import (
    EntryReadinessResult,
    ReclaimContextResult,
    evaluate_entry_readiness,
    validate_reclaim_context,
)


class TestContextValidation:
    """Test context validity checks (prerequisite for any signal)."""

    def test_valid_context_with_all_prerequisites(self):
        """Test that valid context passes with sweep + clarity + BOS direction."""
        features = pd.Series({
            "structure_clarity": 0.6,
            "structure_label": "HH",  # Required for validation
            "liquidity_sweep": True,
            "bos_recent": True,
            "bos_age": 5,
            "bos_direction": "bullish",  # Must match HTF direction
            "choch_detected": False,
            "structure_conflict_flag": False,
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=5,
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is True
        assert result.reason is None
        assert result.sweep_detected is True
        assert result.structure_clarity >= 0.4

    def test_invalid_context_no_sweep(self):
        """Test that context fails without liquidity sweep - returns quality flag not safety rejection.

        Note: validate_reclaim_context now only hard-rejects on SAFETY gates
        (BOS/CHoCH direction mismatch, structure conflict). Missing sweep is tracked
        as a quality flag for penalty calculation, not a hard rejection.
        """
        features = pd.Series({
            "structure_clarity": 0.6,
            "structure_label": "HH",  # Required for validation
            "liquidity_sweep": False,
            "bos_recent": True,
            "bos_direction": "bullish",  # Required for long direction
            "choch_detected": False,
            "structure_conflict_flag": False,
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            liquidity_sweep_detected=False,
            structure_clarity=0.6,
        )

        result = validate_reclaim_context(htf_bias, features)

        # Context is VALID (safety gates passed), but quality_flags indicate issues
        assert result.context_valid is True
        assert result.quality_flags.get("no_sweep") is True

    def test_invalid_context_low_clarity(self):
        """Test that context tracks low clarity as quality flag, not hard rejection.

        Note: validate_reclaim_context now only hard-rejects on SAFETY gates
        (BOS/CHoCH direction mismatch, structure conflict). Low clarity is tracked
        as a quality flag for penalty calculation, not a hard rejection.
        """
        features = pd.Series({
            "structure_clarity": 0.3,
            "structure_label": "HH",  # Required for validation
            "liquidity_sweep": True,
            "bos_recent": True,
            "bos_direction": "bullish",  # Required for long direction
            "choch_detected": False,
            "structure_conflict_flag": False,
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            liquidity_sweep_detected=True,
            structure_clarity=0.3,
        )

        result = validate_reclaim_context(htf_bias, features)

        # Context is VALID (safety gates passed), but quality_flags indicate issues
        assert result.context_valid is True
        assert result.quality_flags.get("low_clarity") is True


class TestEntryReadiness:
    """Test entry readiness evaluation (timing gate for execution)."""

    def test_entry_ready_with_recent_bos_and_expansion(self):
        """Test that entry is ready with recent BOS and expansion."""
        features = pd.Series({
            "bos_age": 5,
            "bos_recent": True,
            "expansion_detected": True,
            "expansion_reasons": ["recent_bos", "range_expansion"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bos_detected=True,
            bars_since_bos=5,
        )

        config = {
            "bos_recency_threshold": 10,
            "range_expansion_ratio": 1.5,
            "atr_expansion_threshold": 0.7,
            "displacement_body_ratio": 2.0,
        }

        result = evaluate_entry_readiness(features, htf_bias, config)

        assert result.entry_ready is True
        assert result.expansion_satisfied is True
        assert len(result.expansion_reasons) >= 2

    def test_entry_not_ready_stale_bos_no_expansion(self):
        """Test that entry is not ready with stale BOS and no expansion."""
        features = pd.Series({
            "bos_age": 20,
            "bos_recent": False,
            "expansion_detected": False,
            "expansion_reasons": [],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bos_detected=True,
            bars_since_bos=20,
        )

        config = {
            "bos_recency_threshold": 10,
            "range_expansion_ratio": 1.5,
            "atr_expansion_threshold": 0.7,
            "displacement_body_ratio": 2.0,
        }

        result = evaluate_entry_readiness(features, htf_bias, config)

        assert result.entry_ready is False
        assert result.expansion_satisfied is False

    def test_entry_ready_with_expansion_despite_stale_bos(self):
        """Test that entry can be ready with expansion even if BOS is old."""
        features = pd.Series({
            "bos_age": 15,
            "bos_recent": False,
            "expansion_detected": True,
            "expansion_reasons": ["range_expansion", "displacement_candle"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bos_detected=True,
            bars_since_bos=15,
        )

        config = {
            "bos_recency_threshold": 10,
            "range_expansion_ratio": 1.5,
            "atr_expansion_threshold": 0.7,
            "displacement_body_ratio": 2.0,
        }

        result = evaluate_entry_readiness(features, htf_bias, config)

        # Even with stale BOS, expansion should make entry ready
        assert result.entry_ready is True
        assert result.expansion_satisfied is True

    def test_penalties_applied_for_stale_bos(self):
        """Test that penalties are tracked for late entries."""
        features = pd.Series({
            "bos_age": 18,
            "bos_recent": False,
            "expansion_detected": True,
            "expansion_reasons": ["atr_expansion"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bos_detected=True,
            bars_since_bos=18,
        )

        config = {
            "bos_recency_threshold": 10,
            "range_expansion_ratio": 1.5,
            "atr_expansion_threshold": 0.7,
            "displacement_body_ratio": 2.0,
        }

        result = evaluate_entry_readiness(features, htf_bias, config)

        assert result.entry_ready is True  # Still ready due to expansion
        assert "late_bos" in result.penalties  # But penalized
        assert result.penalties["late_bos"] < 0  # Negative penalty

