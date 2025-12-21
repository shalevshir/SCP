"""Integration test for VWAP_RECLAIM symmetry fixes.

This test verifies that the symmetry fixes allow SHORT trades to be generated
and that all the safety gates work correctly.
"""

from __future__ import annotations

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.htf.vwap.reclaim import detect_vwap_reclaim, validate_reclaim_context
from rule_engine.htf.vwap.sentinel import reclaim_sentinel


class TestVWAPReclaimSymmetryIntegration:
    """Integration tests for VWAP_RECLAIM symmetry fixes."""

    def test_short_reclaim_end_to_end(self):
        """Test that SHORT reclaim can be detected end-to-end."""
        # Create realistic data: 35 bars above VWAP, then cross below
        df = pd.DataFrame(
            {
                "open": [2020.0] * 35 + [2019.0, 2018.0],
                "high": [2021.0] * 35 + [2019.5, 2018.5],
                "low": [2019.5] * 35 + [2018.5, 2017.5],
                "close": [2020.0] * 35 + [2018.5, 2017.5],  # Crosses below at index 35
                "vwap": [2019.0] * 37,  # VWAP constant at 2019
            }
        )

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=7.5,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
            structure_1h="LL",  # Required: bearish 1H structure for short reclaim
        )

        # Step 1: detect_vwap_reclaim should pass
        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)
        assert is_reclaim is True, "SHORT reclaim detection should pass"
        assert state.started_on_dwell_side is True
        assert state.reclaim_confirmed is True

        # Step 2: sentinel should pass
        price_history = df.iloc[-5:]
        vwap_history = df["vwap"].iloc[-5:]
        features = pd.Series({"close": 2017.5, "vwap": 2019.0})

        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap_history, price_history, lookback=5
        )
        assert is_valid is True, f"SHORT sentinel should pass, got: {reason}"

        # Step 3: validate_reclaim_context should pass with aligned structure
        features_full = pd.Series(
            {
                "close": 2017.5,
                "vwap": 2019.0,
                "vwap_deviation": -0.20,  # 0.20% below VWAP (must be >= 0.15%)
                "structure_clarity": 0.85,
                "structure_label": "LL",  # Bearish structure for SHORT
                "bos_direction": "bearish",  # Required: BOS alignment for short
            }
        )

        result = validate_reclaim_context(htf_bias, features_full)
        assert result.context_valid is True, f"Context validation should pass, got: {result.reason}"

    def test_long_reclaim_end_to_end(self):
        """Test that LONG reclaim still works correctly."""
        # Create realistic data: 35 bars below VWAP, then cross above
        df = pd.DataFrame(
            {
                "open": [2018.0] * 35 + [2019.0, 2020.0],
                "high": [2018.5] * 35 + [2019.5, 2021.0],
                "low": [2017.5] * 35 + [2018.5, 2019.5],
                "close": [2018.0] * 35 + [2019.5, 2020.5],  # Crosses above at index 35
                "vwap": [2019.0] * 37,  # VWAP constant at 2019
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
            structure_1h="HH",  # Required: bullish 1H structure for long reclaim
        )

        # Step 1: detect_vwap_reclaim should pass
        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)
        assert is_reclaim is True, "LONG reclaim detection should pass"
        assert state.started_on_dwell_side is True
        assert state.reclaim_confirmed is True

        # Step 2: sentinel should pass
        price_history = df.iloc[-5:]
        vwap_history = df["vwap"].iloc[-5:]
        features = pd.Series({"close": 2020.5, "vwap": 2019.0})

        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap_history, price_history, lookback=5
        )
        assert is_valid is True, f"LONG sentinel should pass, got: {reason}"

        # Step 3: validate_reclaim_context should pass with aligned structure
        features_full = pd.Series(
            {
                "close": 2020.5,
                "vwap": 2019.0,
                "vwap_deviation": 0.20,  # 0.20% above VWAP (must be >= 0.15%)
                "structure_clarity": 0.85,
                "structure_label": "HH",  # Bullish structure for LONG
                "bos_direction": "bullish",  # Required: BOS alignment for long
            }
        )

        result = validate_reclaim_context(htf_bias, features_full)
        assert result.context_valid is True, f"Context validation should pass, got: {result.reason}"

    def test_dwell_gate_rejects_insufficient_time(self):
        """Test that dwell gate rejects reclaims with insufficient dwell time."""
        # Create data: only 15 bars below VWAP (insufficient), then cross above
        df = pd.DataFrame(
            {
                "open": [2020.0] * 20 + [2018.0] * 15 + [2019.0, 2020.0],
                "high": [2021.0] * 20 + [2018.5] * 15 + [2019.5, 2021.0],
                "low": [2019.5] * 20 + [2017.5] * 15 + [2018.5, 2019.5],
                "close": [2020.0] * 20 + [2018.0] * 15 + [2019.5, 2020.5],
                "vwap": [2019.0] * 37,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)
        assert is_reclaim is False, "Should reject due to insufficient dwell time (< 30 bars)"

    def test_structure_label_mandatory_check(self):
        """Test that missing structure_label causes rejection."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
            structure_1h="HH",  # Required: 1H structure must be present
        )

        # Features without structure_label
        features = pd.Series(
            {
                "close": 2020.5,
                "vwap": 2019.0,
                "vwap_deviation": 0.08,
                "structure_clarity": 0.85,
                # structure_label is missing
            }
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should reject due to missing structure_label OR missing BOS/CHoCH
        assert result.context_valid is False
        assert "No structure label" in result.reason or "No bullish BOS/CHoCH" in result.reason

    def test_wrong_direction_structure_rejected(self):
        """Test that wrong-direction structure_label causes rejection."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
            structure_1h="HH",  # Required: 1H structure must be present
        )

        # Features with bearish structure for LONG trade
        features = pd.Series(
            {
                "close": 2020.5,
                "vwap": 2019.0,
                "vwap_deviation": 0.08,
                "structure_clarity": 0.85,
                "structure_label": "LL",  # Bearish structure for LONG trade (wrong direction)
                "bos_direction": "bullish",  # BOS aligned, but structure_label conflicts
            }
        )

        result = validate_reclaim_context(htf_bias, features)
        
        # Should reject due to structure mismatch
        assert result.context_valid is False
        assert "Bearish" in result.reason or "conflicts" in result.reason

