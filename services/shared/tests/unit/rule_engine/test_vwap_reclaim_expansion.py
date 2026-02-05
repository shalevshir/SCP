"""Integration tests for VWAP_RECLAIM expansion gate system.

Tests the complete flow: context validation -> entry readiness -> scoring penalties.
"""

import pandas as pd
import pytest

from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.htf.vwap.reclaim import (
    evaluate_entry_readiness,
    evaluate_expansion_gate,
    validate_reclaim_context,
)
from scp_shared.rule_engine.scoring import (
    build_diagnostics,
    calculate_late_reclaim_penalty,
    determine_setup_type,
    score_signal,
)


class TestVWAPReclaimExpansionIntegration:
    """Integration tests for VWAP_RECLAIM expansion gate system."""

    def test_valid_context_with_expansion_produces_high_score(self):
        """Test that valid context + expansion produces high-quality signal."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,  # Changed from 2649.0 to give 0.19% deviation (> 0.15%)
                "vwap_deviation_normalized": 1.5,  # Required for vwap_reclaim_distance
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
                "structure_label": "HH",  # Required for validation
                # Context prerequisites
                "structure_clarity": 0.6,
                "liquidity_sweep": True,
                "bos_recent": False,  # Changed to False to pass no_late_reclaim constraint
                "bos_age": 25,  # Changed to 25 (>20) to pass bos_reclaim_gate constraint
                "bos_direction": "bullish",
                "choch_detected": False,
                "structure_conflict_flag": False,
                "conflict_detected": False,  # Required for constraints
                # Expansion signals
                "expansion_detected": True,
                "expansion_reasons": ["recent_bos", "range_expansion"],
                # Required fields for new constraints
                "reclaim_candle_close": 2650.0,
                "vwap_trend_confirmed": True,
            }
        )

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
            vwap_trend_confirmed=True,
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        # Step 1: Context validation should pass
        context_result = validate_reclaim_context(htf_bias, features)
        assert context_result.context_valid is True

        # Step 2: Setup type should be VWAP_RECLAIM
        setup_type = determine_setup_type(features, htf_bias)
        assert setup_type == "VWAP_RECLAIM"

        # Step 3: Entry readiness should be satisfied
        config = {
            "bos_recency_threshold": 10,
            "range_expansion_ratio": 1.5,
            "atr_expansion_threshold": 0.7,
            "displacement_body_ratio": 2.0,
        }
        readiness = evaluate_entry_readiness(features, htf_bias, config)
        assert readiness.entry_ready is True
        assert readiness.expansion_satisfied is True

        # Step 4: Score should be high (no penalties)
        signal = score_signal(features, htf_bias, context)
        assert signal.setup_type == "VWAP_RECLAIM"
        assert signal.score >= 7.0  # High score expected
        assert (
            "late_reclaim_penalty" not in signal.factors
            or signal.factors.get("late_reclaim_penalty", 0) == 0
        )

    def test_valid_context_without_expansion_produces_penalized_signal(self):
        """Test that valid context without expansion still produces signal but with penalty.

        Note: The late_reclaim_penalty is only applied for no-expansion (-0.5).
        BOS age penalty only applies if BOS is INVALID (counter-CHoCH or low clarity).
        With high base confluence, the signal can still score >= 8.0.
        The key assertion is that the penalty IS applied when expansion is missing.
        """
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,  # 0.19% deviation (>= 0.15% threshold)
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
                "structure_label": "HH",  # Required for validation
                # Context prerequisites (valid)
                "structure_clarity": 0.6,
                "liquidity_sweep": True,
                "bos_recent": False,  # Stale
                "bos_age": 18,  # Old BOS
                "bos_direction": "bullish",
                "choch_detected": False,
                "structure_conflict_flag": False,
                # No expansion signals
                "expansion_detected": False,
                "expansion_reasons": [],
                # Required fields for new constraints
                "reclaim_candle_close": 2650.0,
                "vwap_trend_confirmed": True,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=18,
            vwap_trend_confirmed=True,
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        # Context should still be valid
        context_result = validate_reclaim_context(htf_bias, features)
        assert context_result.context_valid is True

        # Setup type should be VWAP_RECLAIM (context is valid)
        setup_type = determine_setup_type(features, htf_bias)
        assert setup_type == "VWAP_RECLAIM"

        # Entry readiness should be NOT ready (no expansion)
        config = {
            "bos_recency_threshold": 10,
            "range_expansion_ratio": 1.5,
            "atr_expansion_threshold": 0.7,
            "displacement_body_ratio": 2.0,
        }
        readiness = evaluate_entry_readiness(features, htf_bias, config)
        assert readiness.entry_ready is False
        assert readiness.expansion_satisfied is False

        # Signal should still be generated but with expansion penalty
        signal = score_signal(features, htf_bias, context)
        assert signal.setup_type == "VWAP_RECLAIM"

        # Should have late_reclaim_penalty for missing expansion (-0.5)
        # Note: BOS age penalty only applies if BOS is invalid (counter-CHoCH or clarity < 0.4)
        # Since clarity=0.6 and no counter-CHoCH, BOS is still valid - no age penalty
        assert "late_reclaim_penalty" in signal.factors
        assert signal.factors["late_reclaim_penalty"] < 0  # -0.5 for no expansion

    def test_invalid_context_rejects_signal(self):
        """Test that invalid context rejects signal entirely."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,  # 0.19% deviation (>= 0.15% threshold)
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.5,  # Weak correlation - fails DXY_CONTINUATION threshold (-0.6)
                # Invalid context (no sweep)
                "structure_clarity": 0.6,
                "liquidity_sweep": False,  # Missing sweep
                "bos_recent": True,
                "bos_age": 5,
                "expansion_detected": True,
                "expansion_reasons": ["recent_bos"],
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=False,  # No sweep
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=5,
        )

        # Context validation should fail
        context_result = validate_reclaim_context(htf_bias, features)
        assert context_result.context_valid is False

        # Setup type should be REJECTED
        setup_type = determine_setup_type(features, htf_bias)
        assert setup_type == "REJECTED"

    def test_diagnostics_include_expansion_fields(self):
        """Test that diagnostics include expansion gate information."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,  # 0.19% deviation (>= 0.15% threshold)
                "rsi": 55.0,
                "structure_clarity": 0.6,
                "liquidity_sweep": True,
                "bos_age": 5,
                "expansion_detected": True,
                "expansion_reasons": ["recent_bos", "displacement_candle"],
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )

        diagnostics = build_diagnostics(features, htf_bias)

        # Should include expansion fields
        assert "expansion_detected" in diagnostics
        assert diagnostics["expansion_detected"] is True
        assert "expansion_reasons" in diagnostics
        assert len(diagnostics["expansion_reasons"]) == 2
        assert "recent_bos" in diagnostics["expansion_reasons"]
        assert "displacement_candle" in diagnostics["expansion_reasons"]

    def test_late_bos_with_expansion_still_executes_with_penalty(self):
        """Test that late BOS with expansion executes and evaluate_entry_readiness tracks penalty.

        Note: calculate_late_reclaim_penalty only applies BOS age penalty if BOS is INVALID
        (counter-CHoCH or clarity < 0.4). This test has valid BOS (clarity=0.6, no CHoCH),
        so the score_signal won't show late_reclaim_penalty for BOS age.

        The key behavior tested:
        1. evaluate_entry_readiness tracks late_bos penalty for its own purposes
        2. score_signal generates valid signal (expansion present = entry ready)
        """
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,  # 0.19% deviation (>= 0.15% threshold)
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
                "structure_label": "HH",  # Required for validation
                # Valid context
                "structure_clarity": 0.6,
                "liquidity_sweep": True,
                "bos_recent": False,
                "bos_age": 12,  # Late but not ancient
                "bos_direction": "bullish",
                "choch_detected": False,
                "structure_conflict_flag": False,
                # Has expansion (so entry is ready)
                "expansion_detected": True,
                "expansion_reasons": ["range_expansion", "atr_expansion"],
                # Required fields for new constraints
                "reclaim_candle_close": 2650.0,
                "vwap_trend_confirmed": True,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=12,
            vwap_trend_confirmed=True,
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        # Setup type should be VWAP_RECLAIM
        setup_type = determine_setup_type(features, htf_bias)
        assert setup_type == "VWAP_RECLAIM"

        # Entry should be ready (has expansion)
        config = {
            "bos_recency_threshold": 10,
            "range_expansion_ratio": 1.5,
            "atr_expansion_threshold": 0.7,
            "displacement_body_ratio": 2.0,
        }
        readiness = evaluate_entry_readiness(features, htf_bias, config)
        assert readiness.entry_ready is True
        assert readiness.expansion_satisfied is True

        # evaluate_entry_readiness tracks late BOS penalty (for its own internal purposes)
        assert "late_bos" in readiness.penalties
        assert readiness.penalties["late_bos"] == -0.5

        # Signal should be generated - it's a valid VWAP_RECLAIM setup
        signal = score_signal(features, htf_bias, context)
        assert signal.setup_type == "VWAP_RECLAIM"
        # Note: late_reclaim_penalty only applies for invalid BOS (CHoCH or low clarity)
        # or for missing expansion. Here BOS is valid and expansion present, so no penalty.

    def test_noise_and_late_penalties_stack(self):
        """Test that multiple penalties stack correctly.

        Tests both noise_penalty and late_reclaim_penalty:
        - noise_penalty: -1.5 for structural chop + -0.5 for ATR compression = -2.0
        - late_reclaim_penalty: Only applies if BOS invalid (which we set up here)

        To trigger BOS age penalty, we need BOS to be INVALID (counter-CHoCH or clarity < 0.4).
        We use choch_detected=True with opposite direction to invalidate BOS.
        """
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,  # 0.19% deviation (>= 0.15% threshold)
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
                "structure_label": "HH",  # Required for validation
                # Valid context but problematic quality
                "structure_clarity": 0.35,  # LOW clarity to invalidate BOS
                "liquidity_sweep": True,
                "bos_age": 18,  # Late BOS + invalid = -1.0 penalty
                "bos_direction": "bullish",
                "choch_detected": False,
                "structure_conflict_flag": False,
                "is_structural_chop": True,  # Noise (-1.5 penalty for RECLAIM)
                "atr_compression_ratio": 0.3,  # Severe compression (-0.5 more)
                # Has expansion (so not blocked entirely)
                "expansion_detected": True,
                "expansion_reasons": ["displacement_candle"],
                # Required fields for new constraints
                "reclaim_candle_close": 2650.0,
                "vwap_trend_confirmed": True,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            structure_1h="HH",  # Required for validation
            liquidity_sweep_detected=True,
            structure_clarity=0.35,  # Match features - LOW to invalidate BOS
            bos_detected=True,
            bars_since_bos=18,
            vwap_trend_confirmed=True,
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, htf_bias, context)

        # Should have noise penalty (structural chop + ATR compression)
        assert "noise_penalty" in signal.factors
        assert signal.factors["noise_penalty"] < 0

        # late_reclaim_penalty should be present (BOS invalid due to low clarity)
        # -1.0 for age 16-20 with invalid BOS
        assert "late_reclaim_penalty" in signal.factors
        assert signal.factors["late_reclaim_penalty"] < 0

        # Final score should be reduced by penalties
        # With multiple penalties stacking, score should be lower than 8.0
        assert signal.score < 8.0
