"""Integration tests for VWAP_RECLAIM expansion gate system.

Tests the complete flow: context validation -> entry readiness -> scoring penalties.
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.htf.vwap.reclaim import (
    evaluate_entry_readiness,
    evaluate_expansion_gate,
    validate_reclaim_context,
)
from rule_engine.scoring import (
    build_diagnostics,
    calculate_late_reclaim_penalty,
    determine_setup_type,
    score_signal,
)


class TestVWAPReclaimExpansionIntegration:
    """Integration tests for VWAP_RECLAIM expansion gate system."""

    def test_valid_context_with_expansion_produces_high_score(self):
        """Test that valid context + expansion produces high-quality signal."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
            # Context prerequisites
            "structure_clarity": 0.6,
            "liquidity_sweep": True,
            "bos_recent": True,
            "bos_age": 5,
            "bos_direction": "bullish",
            # Expansion signals
            "expansion_detected": True,
            "expansion_reasons": ["recent_bos", "range_expansion"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=5,
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
        assert "late_reclaim_penalty" not in signal.factors or signal.factors.get("late_reclaim_penalty", 0) == 0

    def test_valid_context_without_expansion_produces_penalized_signal(self):
        """Test that valid context without expansion still produces signal but with penalty."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
            # Context prerequisites (valid)
            "structure_clarity": 0.6,
            "liquidity_sweep": True,
            "bos_recent": False,  # Stale
            "bos_age": 18,  # Old BOS
            "bos_direction": "bullish",
            # No expansion signals
            "expansion_detected": False,
            "expansion_reasons": [],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=18,
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

        # Signal should still be generated but with penalties
        signal = score_signal(features, htf_bias, context)
        assert signal.setup_type == "VWAP_RECLAIM"
        
        # Should have penalties applied
        assert "late_reclaim_penalty" in signal.factors
        assert signal.factors["late_reclaim_penalty"] < 0
        
        # Score should be lower due to penalties
        assert signal.score < 8.0  # Penalized score

    def test_invalid_context_rejects_signal(self):
        """Test that invalid context rejects signal entirely."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
            # Invalid context (no sweep)
            "structure_clarity": 0.6,
            "liquidity_sweep": False,  # Missing sweep
            "bos_recent": True,
            "bos_age": 5,
            "expansion_detected": True,
            "expansion_reasons": ["recent_bos"],
        })

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
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "rsi": 55.0,
            "structure_clarity": 0.6,
            "liquidity_sweep": True,
            "bos_age": 5,
            "expansion_detected": True,
            "expansion_reasons": ["recent_bos", "displacement_candle"],
        })

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
        """Test that late BOS with expansion executes but applies penalty."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
            # Valid context
            "structure_clarity": 0.6,
            "liquidity_sweep": True,
            "bos_recent": False,
            "bos_age": 12,  # Late but not ancient
            "bos_direction": "bullish",
            # Has expansion (so entry is ready)
            "expansion_detected": True,
            "expansion_reasons": ["range_expansion", "atr_expansion"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=12,
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
        
        # But should have late BOS penalty
        assert "late_bos" in readiness.penalties
        assert readiness.penalties["late_bos"] == -0.5

        # Signal should be generated with penalty applied
        signal = score_signal(features, htf_bias, context)
        assert signal.setup_type == "VWAP_RECLAIM"
        assert "late_reclaim_penalty" in signal.factors
        assert signal.factors["late_reclaim_penalty"] < 0

    def test_noise_and_late_penalties_stack(self):
        """Test that multiple penalties stack correctly."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
            # Valid but problematic
            "structure_clarity": 0.6,
            "liquidity_sweep": True,
            "bos_age": 18,  # Late BOS (-1.0 penalty)
            "bos_direction": "bullish",
            "is_structural_chop": True,  # Noise (-1.5 penalty for RECLAIM)
            "atr_compression_ratio": 0.3,  # Severe compression (-0.5 more)
            # Has expansion (so not blocked entirely)
            "expansion_detected": True,
            "expansion_reasons": ["displacement_candle"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=18,
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, htf_bias, context)
        
        # Should have multiple penalties
        assert "late_reclaim_penalty" in signal.factors
        assert "noise_penalty" in signal.factors
        
        # Both should be negative
        assert signal.factors["late_reclaim_penalty"] < 0
        assert signal.factors["noise_penalty"] < 0
        
        # Final score should reflect both penalties
        # Base score might be ~8, with penalties could drop to ~5-6
        assert signal.score < 7.0


