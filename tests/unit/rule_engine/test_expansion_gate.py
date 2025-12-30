"""Tests for ExpansionGate evaluation logic.

Following TDD: Tests written before implementation of ExpansionGate.
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.htf.vwap.reclaim import ExpansionGate, evaluate_expansion_gate


class TestExpansionGate:
    """Test ExpansionGate evaluation logic."""

    def test_expansion_gate_passes_with_recent_bos(self):
        """Test that expansion gate passes with recent BOS."""
        features = pd.Series({
            "bos_age": 5,
            "bos_recent": True,
            "close": 2650.0,
            "high": 2651.0,
            "low": 2649.0,
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
        
        gate = evaluate_expansion_gate(features, htf_bias, config)
        
        assert gate.passed is True
        assert gate.recent_bos is True
        assert "recent_bos" in gate.reasons

    def test_expansion_gate_passes_with_expansion_signals(self):
        """Test that expansion gate passes with expansion signals from features."""
        features = pd.Series({
            "bos_age": 15,  # Stale BOS
            "bos_recent": False,
            "close": 2650.0,
            "high": 2651.0,
            "low": 2649.0,
            # Expansion signals will come from StructureContext
            "expansion_detected": True,
            "expansion_reasons": ["range_expansion", "atr_expansion"],
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
        
        gate = evaluate_expansion_gate(features, htf_bias, config)
        
        assert gate.passed is True
        assert gate.range_expansion is True
        assert gate.atr_expansion is True
        assert "range_expansion" in gate.reasons
        assert "atr_expansion" in gate.reasons

    def test_expansion_gate_fails_without_expansion(self):
        """Test that expansion gate fails without any expansion signals."""
        features = pd.Series({
            "bos_age": 20,  # Stale BOS
            "bos_recent": False,
            "close": 2650.0,
            "high": 2651.0,
            "low": 2649.0,
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
        
        gate = evaluate_expansion_gate(features, htf_bias, config)
        
        assert gate.passed is False
        assert len(gate.reasons) == 0

    def test_expansion_gate_with_multiple_signals(self):
        """Test that expansion gate captures multiple expansion signals."""
        features = pd.Series({
            "bos_age": 3,
            "bos_recent": True,
            "close": 2650.0,
            "high": 2651.0,
            "low": 2649.0,
            "expansion_detected": True,
            "expansion_reasons": ["range_expansion", "displacement_candle"],
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bos_detected=True,
            bars_since_bos=3,
        )
        
        config = {
            "bos_recency_threshold": 10,
            "range_expansion_ratio": 1.5,
            "atr_expansion_threshold": 0.7,
            "displacement_body_ratio": 2.0,
        }
        
        gate = evaluate_expansion_gate(features, htf_bias, config)
        
        assert gate.passed is True
        assert gate.recent_bos is True
        assert gate.range_expansion is True
        assert gate.displacement_candle is True
        # Should have all three reasons
        assert len(gate.reasons) >= 3








