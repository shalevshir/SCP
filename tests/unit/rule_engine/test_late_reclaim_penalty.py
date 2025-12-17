"""Tests for calculate_late_reclaim_penalty function.

Following TDD: Tests written before implementation.
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.scoring import calculate_late_reclaim_penalty


class TestLateReclaimPenalty:
    """Test late reclaim penalty calculation."""

    def test_no_penalty_for_fresh_entry(self):
        """Test that no penalty is applied for fresh entry with good timing."""
        features = pd.Series({
            "bos_age": 5,
            "close": 2650.0,
            "vwap": 2649.0,  # Close above VWAP by 0.04%
            "expansion_detected": True,
            "expansion_reasons": ["recent_bos"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=5,
        )

        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")

        assert penalty == 0.0

    def test_penalty_for_stale_bos_11_to_15_bars(self):
        """Test penalty for BOS age 11-15 bars."""
        features = pd.Series({
            "bos_age": 12,
            "close": 2650.0,
            "vwap": 2649.0,
            "expansion_detected": True,
            "expansion_reasons": ["range_expansion"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=12,
        )

        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")

        assert penalty == -0.5

    def test_penalty_for_stale_bos_16_to_20_bars(self):
        """Test penalty for BOS age 16-20 bars."""
        features = pd.Series({
            "bos_age": 18,
            "close": 2650.0,
            "vwap": 2649.0,
            "expansion_detected": True,
            "expansion_reasons": ["atr_expansion"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=18,
        )

        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")

        assert penalty == -1.0

    def test_penalty_for_very_stale_bos_over_20_bars(self):
        """Test penalty for BOS age > 20 bars."""
        features = pd.Series({
            "bos_age": 25,
            "close": 2650.0,
            "vwap": 2649.0,
            "expansion_detected": True,
            "expansion_reasons": ["displacement_candle"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=25,
        )

        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")

        assert penalty == -1.5

    def test_penalty_for_large_vwap_distance(self):
        """Test penalty for VWAP distance > 0.3%."""
        features = pd.Series({
            "bos_age": 5,
            "close": 2660.0,  # 0.38% above VWAP
            "vwap": 2650.0,
            "expansion_detected": True,
            "expansion_reasons": ["recent_bos"],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=5,
        )

        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")

        assert penalty == -0.3

    def test_penalty_for_no_expansion(self):
        """Test penalty for lack of expansion signal."""
        features = pd.Series({
            "bos_age": 8,
            "close": 2650.0,
            "vwap": 2649.5,
            "expansion_detected": False,
            "expansion_reasons": [],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=8,
        )

        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")

        assert penalty == -0.5

    def test_cumulative_penalties(self):
        """Test that multiple penalties stack correctly."""
        features = pd.Series({
            "bos_age": 18,  # -1.0 penalty
            "close": 2660.0,  # 0.38% above VWAP -> -0.3 penalty
            "vwap": 2650.0,
            "expansion_detected": False,  # -0.5 penalty
            "expansion_reasons": [],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=18,
        )

        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")

        # Total: -1.0 (BOS) -0.3 (VWAP) -0.5 (no expansion) = -1.8
        assert penalty == -1.8

    def test_no_penalty_for_non_reclaim_setup(self):
        """Test that penalty only applies to VWAP_RECLAIM."""
        features = pd.Series({
            "bos_age": 25,
            "close": 2660.0,
            "vwap": 2650.0,
            "expansion_detected": False,
            "expansion_reasons": [],
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=25,
        )

        penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_FADE")

        assert penalty == 0.0


