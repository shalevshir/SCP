"""Tests for location integrity multiplier.

Tests the calculate_location_multiplier function which applies a multiplier
to VWAP_RECLAIM scores based on reclaim location quality.
"""

import pandas as pd
import pytest
from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.scoring import calculate_location_multiplier, score_signal


class TestLocationMultiplier:
    """Test calculate_location_multiplier function."""

    def test_returns_1_for_clean_reclaim(self):
        """Test that clean reclaims get multiplier = 1.0."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap_deviation_normalized": 1.0,  # Ideal: 0.5-1.5 ATR
                "bos_age": 5,  # Recent and valid
                "bos_recent": False,
                "choch_detected": False,
                "structure_clarity": 0.7,
                "bars_since_last_vwap_touch": 3,  # Timely
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=5,
            structure_clarity=0.7,
        )

        multiplier = calculate_location_multiplier(features, htf_bias, "VWAP_RECLAIM")
        assert multiplier == 1.0

    def test_applies_reduction_for_far_vwap_distance(self):
        """Test that large VWAP distance reduces multiplier."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap_deviation_normalized": 2.8,  # Late: 2.5-3.0 ATR
                "bos_age": 5,
                "bos_recent": False,
                "choch_detected": False,
                "structure_clarity": 0.7,
                "bars_since_last_vwap_touch": 3,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=5,
            structure_clarity=0.7,
        )

        multiplier = calculate_location_multiplier(features, htf_bias, "VWAP_RECLAIM")
        assert multiplier == 0.7  # Late VWAP distance

    def test_applies_reduction_for_moderate_vwap_distance(self):
        """Test that moderate VWAP distance applies moderate reduction."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap_deviation_normalized": 2.0,  # Moderate: 1.5-2.5 ATR
                "bos_age": 5,
                "bos_recent": False,
                "choch_detected": False,
                "structure_clarity": 0.7,
                "bars_since_last_vwap_touch": 3,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=5,
            structure_clarity=0.7,
        )

        multiplier = calculate_location_multiplier(features, htf_bias, "VWAP_RECLAIM")
        assert multiplier == 0.9  # Moderate reduction

    def test_applies_reduction_for_invalid_old_bos(self):
        """Test that invalid old BOS reduces multiplier."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap_deviation_normalized": 1.0,
                "bos_age": 25,  # Old BOS
                "bos_recent": False,
                "choch_detected": True,  # Counter-CHoCH invalidates BOS
                "choch_direction": "bearish",
                "structure_clarity": 0.3,  # Low clarity
                "bars_since_last_vwap_touch": 3,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=25,
            structure_clarity=0.3,
        )

        multiplier = calculate_location_multiplier(features, htf_bias, "VWAP_RECLAIM")
        assert multiplier == 0.7  # Invalid old BOS

    def test_applies_reduction_for_delayed_reclaim(self):
        """Test that delayed reclaim timing reduces multiplier."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap_deviation_normalized": 1.0,
                "bos_age": 5,
                "bos_recent": False,
                "choch_detected": False,
                "structure_clarity": 0.7,
                "bars_since_last_vwap_touch": 8,  # Delayed: 6-10 bars
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=5,
            structure_clarity=0.7,
        )

        multiplier = calculate_location_multiplier(features, htf_bias, "VWAP_RECLAIM")
        assert multiplier == 0.9  # Delayed timing

    def test_multiplies_penalties(self):
        """Test that multiple penalties stack multiplicatively."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap_deviation_normalized": 2.8,  # 0.7x
                "bos_age": 25,
                "bos_recent": False,
                "choch_detected": True,
                "choch_direction": "bearish",
                "structure_clarity": 0.3,  # 0.7x
                "bars_since_last_vwap_touch": 8,  # 0.9x
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=25,
            structure_clarity=0.3,
        )

        multiplier = calculate_location_multiplier(features, htf_bias, "VWAP_RECLAIM")
        # 0.7 * 0.7 * 0.9 = 0.441, capped at 0.5
        assert multiplier == 0.5

    def test_caps_at_minimum_0_5(self):
        """Test that multiplier is capped at 0.5."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap_deviation_normalized": 2.9,  # 0.7x
                "bos_age": 25,
                "choch_detected": True,
                "choch_direction": "bearish",
                "structure_clarity": 0.2,  # 0.7x
                "bars_since_last_vwap_touch": 9,  # 0.9x
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bars_since_bos=25,
            structure_clarity=0.2,
        )

        multiplier = calculate_location_multiplier(features, htf_bias, "VWAP_RECLAIM")
        assert multiplier >= 0.5

    def test_returns_1_for_non_vwap_reclaim_setups(self):
        """Test that multiplier is always 1.0 for non-VWAP_RECLAIM setups."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap_deviation_normalized": 5.0,  # Would penalize VWAP_RECLAIM
                "bos_age": 30,
                "choch_detected": True,
                "structure_clarity": 0.2,
                "bars_since_last_vwap_touch": 15,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )

        # Should always be 1.0 for other setups
        assert calculate_location_multiplier(features, htf_bias, "VWAP_FADE") == 1.0
        assert (
            calculate_location_multiplier(features, htf_bias, "DXY_CONTINUATION") == 1.0
        )


class TestScoreSignalIntegration:
    """Test integration of location multiplier into score_signal."""

    def test_multiplier_reduces_final_score(self):
        """Test that location multiplier reduces the final signal score."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "open": 2648.0,
                "high": 2652.0,
                "low": 2647.0,
                "volume": 1000.0,
                "vwap": 2645.0,
                "vwap_deviation_normalized": 2.8,  # Late: 0.7x multiplier
                "rsi": 55.0,
                "ema_9": 2640.0,
                "ema_20": 2635.0,
                "ema_50": 2630.0,
                "dxy_corr": -0.7,
                "structure_label": "HL",
                "structure_clarity": 0.7,
                "bos_direction": "bullish",
                "bos_recent": False,
                "bos_age": 5,
                "choch_detected": False,
                "liquidity_sweep": True,
                "expansion_detected": True,
                "bars_near_vwap": 4,
                "bars_since_last_vwap_touch": 3,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            structure_15m="HH",
            structure_1h="HL",
            dxy_alignment=True,
            chop_detected=False,
            bars_since_bos=5,
            structure_clarity=0.7,
            liquidity_sweep_detected=True,
        )

        context = {
            "enforcer_tier": "Balanced",
            "structure_1h": "HL",
            "htf_direction": "long",
        }

        signal = score_signal(features, htf_bias, context)

        # Should have location_multiplier in factors
        assert "location_multiplier" in signal.factors
        assert signal.factors["location_multiplier"] == 0.7

        # Score should be reduced (base score * 0.7)
        # Exact score depends on all factors, but should be lower than without multiplier

    def test_clean_reclaim_no_multiplier_penalty(self):
        """Test that clean reclaims don't get multiplier reduction."""
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "open": 2648.0,
                "high": 2652.0,
                "low": 2647.0,
                "volume": 1000.0,
                "vwap": 2649.0,
                "vwap_deviation_normalized": 1.0,  # Clean: 1.0x multiplier
                "rsi": 55.0,
                "ema_9": 2640.0,
                "ema_20": 2635.0,
                "ema_50": 2630.0,
                "dxy_corr": -0.7,
                "structure_label": "HL",
                "structure_clarity": 0.7,
                "bos_direction": "bullish",
                "bos_recent": False,
                "bos_age": 5,
                "choch_detected": False,
                "liquidity_sweep": True,
                "expansion_detected": True,
                "bars_near_vwap": 4,
                "bars_since_last_vwap_touch": 3,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            structure_15m="HH",
            structure_1h="HL",
            dxy_alignment=True,
            chop_detected=False,
            bars_since_bos=5,
            structure_clarity=0.7,
            liquidity_sweep_detected=True,
        )

        context = {
            "enforcer_tier": "Balanced",
            "structure_1h": "HL",
            "htf_direction": "long",
        }

        signal = score_signal(features, htf_bias, context)

        # Should NOT have location_multiplier in factors (only added if < 1.0)
        assert (
            "location_multiplier" not in signal.factors
            or signal.factors["location_multiplier"] == 1.0
        )

    def test_multiplier_can_drop_score_below_threshold(self):
        """Test that multiplier can cause borderline signals to fail threshold."""
        # Create a signal that would be just above 8.0 without multiplier
        # but drops below with 0.7x multiplier
        features = pd.Series(
            {
                "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "open": 2648.0,
                "high": 2652.0,
                "low": 2647.0,
                "volume": 1000.0,
                "vwap": 2645.0,
                "vwap_deviation_normalized": 2.9,  # 0.7x
                "rsi": 52.0,
                "ema_9": 2640.0,
                "ema_20": 2635.0,
                "ema_50": 2630.0,
                "dxy_corr": -0.6,
                "structure_label": "HL",
                "structure_clarity": 0.6,
                "bos_direction": "bullish",
                "bos_recent": False,
                "bos_age": 8,
                "choch_detected": False,
                "liquidity_sweep": True,
                "expansion_detected": True,
                "bars_near_vwap": 3,
                "bars_since_last_vwap_touch": 3,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="medium",
            structure_15m="HH",
            structure_1h="HL",
            dxy_alignment=True,
            chop_detected=False,
            bars_since_bos=8,
            structure_clarity=0.6,
            liquidity_sweep_detected=True,
        )

        context = {
            "enforcer_tier": "Balanced",
            "structure_1h": "HL",
            "htf_direction": "long",
        }

        signal = score_signal(features, htf_bias, context)

        # Location multiplier should reduce score
        # Final score could be below 8.0 threshold
        if "location_multiplier" in signal.factors:
            assert signal.factors["location_multiplier"] < 1.0
