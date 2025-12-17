"""Unit tests for Task 6: Diagnostic Coverage Upgrade.

Tests verify that:
1. Rejected signals log primary_rejection_reason
2. secondary_factors lists contributing penalties
3. would_pass_if suggests what relaxation would help
4. Passing signals have passed=True
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.scoring import score_signal


class TestRejectionDiagnostics:
    """Test suite for rejection diagnostic coverage."""

    def test_rejected_signal_has_primary_reason(self):
        """Rejected signal should have primary_rejection_reason in diagnostics."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650,
            "vwap": 2645,
            "rsi": 55,
            "ema_9": 2648,
            "ema_20": 2645,
            "ema_50": 2640,
            "dxy_corr": -0.75,
            # Heavy structure penalty
            "is_structural_chop": True,
            "atr_compression_ratio": 0.3,
            "structure_clarity": 0.2,
            "bos_age": 30,
            "bos_direction": "bullish",
            "bos_recent": False,
            "choch_detected": False,
            "liquidity_sweep": False,
            "expansion_detected": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=6.0,
            confidence="low",
            structure_clarity=0.2,
            bars_since_bos=30,
            liquidity_sweep_detected=False,
            bos_detected=False,
        )
        
        context = {"session_ok": True, "enforcer_tier": "EarlyMild"}
        
        signal = score_signal(features, htf_bias, context)
        
        # Should be rejected
        assert signal.confidence != "A+", "Signal should be rejected"
        
        # Should have rejection analysis in diagnostics
        assert "rejection_analysis" in signal.diagnostics, \
            "Diagnostics should contain rejection_analysis"
        
        rejection = signal.diagnostics["rejection_analysis"]
        assert "primary_rejection_reason" in rejection, \
            "Should have primary_rejection_reason"
        assert rejection["primary_rejection_reason"] is not None, \
            "Primary reason should not be None"

    def test_rejected_signal_has_secondary_factors(self):
        """Rejected signal should list secondary contributing factors."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2660,
            "vwap": 2645,
            "rsi": 55,
            "ema_9": 2648,
            "ema_20": 2645,
            "ema_50": 2640,
            "dxy_corr": -0.75,
            # Multiple penalties
            "is_structural_chop": True,
            "atr_compression_ratio": 0.3,
            "structure_clarity": 0.3,
            "bos_age": 25,
            "bos_direction": "bullish",
            "bos_recent": False,
            "choch_detected": True,
            "choch_direction": "bearish",
            "liquidity_sweep": False,
            "expansion_detected": False,
        })
        
        htf_bias = HTFBias(
            bias="neutral",
            direction="neutral",
            score=4.0,
            confidence="low",
            structure_clarity=0.3,
            bars_since_bos=25,
            liquidity_sweep_detected=False,
            bos_detected=False,
        )
        
        context = {"session_ok": True, "enforcer_tier": "Conservative"}
        
        signal = score_signal(features, htf_bias, context)
        
        # Should have rejection analysis
        rejection = signal.diagnostics.get("rejection_analysis", {})
        assert "secondary_factors" in rejection, \
            "Should have secondary_factors"
        assert isinstance(rejection["secondary_factors"], list), \
            "Secondary factors should be a list"

    def test_rejected_signal_has_would_pass_if(self):
        """Rejected signal should suggest what would make it pass."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650,
            "vwap": 2645,
            "rsi": 55,
            "ema_9": 2648,
            "ema_20": 2645,
            "ema_50": 2640,
            "dxy_corr": -0.75,
            # Single large penalty
            "is_structural_chop": False,
            "atr_compression_ratio": 1.0,
            "structure_clarity": 0.2,  # Low clarity -> heavy penalty
            "bos_age": 30,
            "bos_direction": "bullish",
            "bos_recent": False,
            "choch_detected": False,
            "liquidity_sweep": False,
            "expansion_detected": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            structure_clarity=0.2,
            bars_since_bos=30,
            liquidity_sweep_detected=False,
            bos_detected=False,
        )
        
        context = {"session_ok": True, "enforcer_tier": "EarlyMild"}
        
        signal = score_signal(features, htf_bias, context)
        
        # Should have rejection analysis
        rejection = signal.diagnostics.get("rejection_analysis", {})
        assert "would_pass_if" in rejection, \
            "Should have would_pass_if"
        assert isinstance(rejection["would_pass_if"], list), \
            "would_pass_if should be a list"

    def test_passing_signal_has_passed_true(self):
        """Passing signal should have passed=True in rejection_analysis."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650,
            "vwap": 2645,
            "rsi": 55,
            "ema_9": 2650,
            "ema_20": 2645,
            "ema_50": 2640,
            "dxy_corr": -0.75,
            # Strong structure
            "is_structural_chop": False,
            "atr_compression_ratio": 1.0,
            "structure_clarity": 0.8,
            "bos_age": 5,
            "bos_direction": "bullish",
            "bos_recent": True,
            "choch_detected": False,
            "liquidity_sweep": True,
            "expansion_detected": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            bos_detected=True,
        )
        
        context = {"session_ok": True, "enforcer_tier": "EarlyMild"}
        
        signal = score_signal(features, htf_bias, context)
        
        # Should pass
        assert signal.confidence == "A+", f"Signal should pass, got {signal.confidence}"
        
        # Should have rejection analysis with passed=True
        rejection = signal.diagnostics.get("rejection_analysis", {})
        assert rejection.get("passed") is True, \
            "Passing signal should have passed=True"

    def test_score_gap_calculated(self):
        """Rejected signal should show score gap to minimum."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650,  # Above VWAP (VWAP_RECLAIM condition)
            "vwap": 2645,
            "rsi": 55,
            "ema_9": 2650,  # Proper EMA stack for bullish
            "ema_20": 2645,
            "ema_50": 2640,
            "dxy_corr": -0.75,
            "is_structural_chop": True,  # Penalty
            "atr_compression_ratio": 0.3,  # Penalty
            "structure_clarity": 0.4,  # Borderline
            "bos_age": 20,
            "bos_recent": False,
            "bos_direction": "bullish",
            "choch_detected": False,
            "liquidity_sweep": False,
            "expansion_detected": True,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=6.5,
            confidence="low",
            structure_clarity=0.4,
            bars_since_bos=20,
            liquidity_sweep_detected=False,
            bos_detected=True,
        )
        
        context = {"session_ok": True, "enforcer_tier": "EarlyMild"}
        
        signal = score_signal(features, htf_bias, context)
        
        # Should have score_gap if rejected
        rejection = signal.diagnostics.get("rejection_analysis", {})
        if not rejection.get("passed", False):
            assert "score_gap" in rejection, "Should have score_gap"
            assert isinstance(rejection["score_gap"], (int, float)), \
                "score_gap should be numeric"
            assert rejection["score_gap"] > 0, "score_gap should be positive"

