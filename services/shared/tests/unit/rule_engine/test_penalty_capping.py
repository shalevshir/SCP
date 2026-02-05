"""Unit tests for Task 5: Scoring Floor Protection.

Tests verify that:
1. Structure penalties capped at -2.5
2. Timing penalties capped at -1.5
3. HTF penalties capped at -1.0
4. Total penalties capped at -4.0
5. Strong confluence still surfaces >= 8.0 scores
"""

import pandas as pd
import pytest

from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.scoring import score_signal


class TestPenaltyCapping:
    """Test suite for penalty capping logic."""

    def test_structure_penalties_capped(self):
        """Structure penalties (noise + structure_quality) should be capped at -2.5."""
        features = pd.Series(
            {
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
                # Extreme structure penalties
                "is_structural_chop": True,
                "atr_compression_ratio": 0.3,  # Compressed
                "structure_clarity": 0.2,  # Very low
                "bos_age": 30,
                "bos_direction": "bullish",
                "bos_recent": False,
                "choch_detected": False,
                "liquidity_sweep": False,
                "expansion_detected": True,
            }
        )

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

        # Extract structure penalties
        noise_penalty = signal.factors.get("noise_penalty", 0)
        structure_quality_penalty = signal.factors.get("structure_quality_penalty", 0)
        structure_total = noise_penalty + structure_quality_penalty

        # Should be capped at -2.5
        assert (
            structure_total >= -2.5
        ), f"Structure penalties should be capped at -2.5, got {structure_total}"

    def test_timing_penalties_capped(self):
        """Timing penalties (late_reclaim) should be capped at -1.5."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2660,  # Far from VWAP
                "vwap": 2645,
                "rsi": 55,
                "ema_9": 2648,
                "ema_20": 2645,
                "ema_50": 2640,
                "dxy_corr": -0.75,
                # Extreme timing penalties
                "bos_age": 30,  # Very old
                "bos_direction": "bullish",
                "bos_recent": False,
                "choch_detected": True,  # Counter-CHoCH
                "choch_direction": "bearish",
                "structure_clarity": 0.3,  # Poor
                "expansion_detected": False,  # No expansion
                "is_structural_chop": False,
                "liquidity_sweep": True,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            structure_clarity=0.6,
            bars_since_bos=30,
            liquidity_sweep_detected=True,
            bos_detected=True,
        )

        context = {"session_ok": True, "enforcer_tier": "EarlyMild"}

        signal = score_signal(features, htf_bias, context)

        # Extract timing penalty
        late_reclaim_penalty = signal.factors.get("late_reclaim_penalty", 0)

        # Should be capped at -1.5
        assert (
            late_reclaim_penalty >= -1.5
        ), f"Timing penalties should be capped at -1.5, got {late_reclaim_penalty}"

    def test_htf_penalties_capped(self):
        """HTF penalties should be capped at -1.0."""
        features = pd.Series(
            {
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
                "bos_age": 5,
                "bos_recent": True,
                "structure_clarity": 0.7,
                "is_structural_chop": False,
                "liquidity_sweep": True,
                "expansion_detected": True,
            }
        )

        # Weak HTF bias
        htf_bias = HTFBias(
            bias="neutral",
            direction="neutral",
            score=3.0,
            confidence="low",
            structure_clarity=0.4,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            bos_detected=True,
        )

        context = {"session_ok": True, "enforcer_tier": "Conservative"}

        signal = score_signal(features, htf_bias, context)

        # Extract HTF penalty
        htf_weak_bias = signal.factors.get("htf_weak_bias", 0)

        # Should be capped at -1.0
        assert (
            htf_weak_bias >= -1.0
        ), f"HTF penalties should be capped at -1.0, got {htf_weak_bias}"

    def test_total_penalties_capped(self):
        """Total penalties should be capped at -4.0."""
        features = pd.Series(
            {
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
                # Extreme penalties across all domains
                "is_structural_chop": True,
                "atr_compression_ratio": 0.3,
                "structure_clarity": 0.2,
                "bos_age": 30,
                "bos_direction": "bullish",
                "bos_recent": False,
                "choch_detected": True,
                "choch_direction": "bearish",
                "liquidity_sweep": False,
                "expansion_detected": False,
            }
        )

        htf_bias = HTFBias(
            bias="neutral",
            direction="neutral",
            score=3.0,
            confidence="low",
            structure_clarity=0.2,
            bars_since_bos=30,
            liquidity_sweep_detected=False,
            bos_detected=False,
        )

        context = {"session_ok": True, "enforcer_tier": "Conservative"}

        signal = score_signal(features, htf_bias, context)

        # Calculate total penalties
        penalties = {k: v for k, v in signal.factors.items() if v < 0}
        total_penalties = sum(penalties.values())

        # Should be capped at -4.0
        assert total_penalties >= -4.0, (
            f"Total penalties should be capped at -4.0, got {total_penalties} "
            f"(penalties: {penalties})"
        )

    def test_strong_confluence_still_surfaces(self):
        """Strong confluence should still achieve >= 8.0 scores."""
        features = pd.Series(
            {
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
                "structure_label": "HH",  # Required for validation
                "direction": "long",  # Required for valid_direction
                # Strong structure
                "is_structural_chop": False,
                "atr_compression_ratio": 1.0,
                "structure_clarity": 0.8,
                "bos_age": 25,  # >= 20 to satisfy no_late_reclaim
                "bos_direction": "long",  # Must match direction format
                "bos_recent": False,  # False to avoid no_late_reclaim rejection
                "choch_detected": False,
                "structure_conflict_flag": False,
                "conflict_detected": False,  # Required for no_structure_conflict
                "liquidity_sweep": True,
                "expansion_detected": True,
                "near_vwap_count_last_20": 5,  # Required for min_vwap_acceptance
                "reclaim_candle_close": 2650,  # Required for VWAP_RECLAIM
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            structure_1h="HH",  # Required for validation
            structure_clarity=0.8,
            bars_since_bos=25,
            liquidity_sweep_detected=True,
            bos_detected=True,
            vwap_trend_confirmed=True,  # Required for VWAP_RECLAIM
        )

        context = {"session_ok": True, "enforcer_tier": "EarlyMild"}

        signal = score_signal(features, htf_bias, context)

        # Should achieve A+ score
        assert (
            signal.score >= 8.0
        ), f"Strong confluence should achieve >= 8.0, got {signal.score}"
        assert (
            signal.confidence == "A+"
        ), f"Strong confluence should be A+, got {signal.confidence}"
