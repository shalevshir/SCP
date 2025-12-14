"""Unit tests for RECLAIM_SENTINEL validation.

Tests the final gatekeeper that rejects invalid reclaim signals.

Following TDD: These tests will fail until implementation is complete.
"""

import pandas as pd
import pytest
from datetime import datetime, timezone

from rule_engine.htf.vwap.sentinel import (
    reclaim_sentinel,
    detect_displacement_candle,
)
from rule_engine.htf.types import HTFBias


class TestReclaimSentinel:
    """Test the RECLAIM_SENTINEL gatekeeper."""

    def test_valid_reclaim_passes_sentinel(self):
        """Test valid reclaim passes all sentinel checks."""
        # Create valid reclaim scenario
        price_history = pd.DataFrame(
            {
                "open": [2645.0, 2646.0, 2647.0, 2648.0, 2653.0],
                "high": [2646.0, 2647.0, 2648.0, 2649.0, 2655.0],
                "low": [2644.0, 2645.0, 2646.0, 2647.0, 2651.0],
                "close": [
                    2645.5,
                    2646.5,
                    2647.5,
                    2648.5,
                    2654.0,
                ],  # Last bar is displacement
            }
        )
        vwap_history = pd.Series([2650.0, 2650.0, 2650.0, 2650.0, 2650.0])

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            liquidity_sweep_detected=True,
            liquidity_sweep_type="bullish",
            structure_clarity=0.8,
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=False,
        )

        features = pd.Series(
            {
                "close": 2654.0,
                "vwap": 2650.0,
            }
        )

        is_valid, reason = reclaim_sentinel(
            features=features,
            htf_bias=htf_bias,
            vwap_history=vwap_history,
            price_history=price_history,
            lookback=5,
        )

        assert is_valid is True
        assert reason is None

    def test_reject_no_vwap_cross_from_below(self):
        """Test rejection when price never crossed VWAP from below."""
        # Price always above VWAP
        price_history = pd.DataFrame(
            {
                "open": [2655.0, 2656.0, 2657.0, 2658.0, 2659.0],
                "high": [2656.0, 2657.0, 2658.0, 2659.0, 2660.0],
                "low": [2654.0, 2655.0, 2656.0, 2657.0, 2658.0],
                "close": [2655.5, 2656.5, 2657.5, 2658.5, 2659.5],
            }
        )
        vwap_history = pd.Series([2650.0, 2650.0, 2650.0, 2650.0, 2650.0])

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
        )

        features = pd.Series(
            {
                "close": 2659.5,
                "vwap": 2650.0,
            }
        )

        is_valid, reason = reclaim_sentinel(
            features=features,
            htf_bias=htf_bias,
            vwap_history=vwap_history,
            price_history=price_history,
            lookback=5,
        )

        assert is_valid is False
        assert "crossed" in reason.lower() or "below" in reason.lower()

    def test_reject_no_sweep(self):
        """Test rejection when no liquidity sweep detected."""
        price_history = pd.DataFrame(
            {
                "open": [2645.0, 2646.0, 2647.0, 2648.0, 2653.0],
                "high": [2646.0, 2647.0, 2648.0, 2649.0, 2655.0],
                "low": [2644.0, 2645.0, 2646.0, 2647.0, 2651.0],
                "close": [2645.5, 2646.5, 2647.5, 2648.5, 2654.0],
            }
        )
        vwap_history = pd.Series([2650.0, 2650.0, 2650.0, 2650.0, 2650.0])

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=False,  # No sweep
            structure_clarity=0.8,
        )

        features = pd.Series(
            {
                "close": 2654.0,
                "vwap": 2650.0,
            }
        )

        is_valid, reason = reclaim_sentinel(
            features=features,
            htf_bias=htf_bias,
            vwap_history=vwap_history,
            price_history=price_history,
            lookback=5,
        )

        assert is_valid is False
        assert "sweep" in reason.lower()

    def test_reject_no_displacement_candle(self):
        """Test rejection when no displacement candle present."""
        # Small body candles - no displacement
        price_history = pd.DataFrame(
            {
                "open": [2645.0, 2646.0, 2647.0, 2650.0, 2651.0],
                "high": [2646.0, 2647.0, 2648.0, 2651.0, 2652.0],
                "low": [2644.0, 2645.0, 2646.0, 2649.0, 2650.0],
                "close": [2645.5, 2646.5, 2647.5, 2650.5, 2651.5],  # Small bodies
            }
        )
        vwap_history = pd.Series([2650.0, 2650.0, 2650.0, 2650.0, 2650.0])

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
        )

        features = pd.Series(
            {
                "close": 2651.5,
                "vwap": 2650.0,
            }
        )

        is_valid, reason = reclaim_sentinel(
            features=features,
            htf_bias=htf_bias,
            vwap_history=vwap_history,
            price_history=price_history,
            lookback=5,
        )

        assert is_valid is False
        assert "displacement" in reason.lower()

    def test_reject_choppy_structure(self):
        """Test rejection with choppy structure."""
        price_history = pd.DataFrame(
            {
                "open": [2645.0, 2646.0, 2647.0, 2648.0, 2653.0],
                "high": [2646.0, 2647.0, 2648.0, 2649.0, 2655.0],
                "low": [2644.0, 2645.0, 2646.0, 2647.0, 2651.0],
                "close": [2645.5, 2646.5, 2647.5, 2648.5, 2654.0],
            }
        )
        vwap_history = pd.Series([2650.0, 2650.0, 2650.0, 2650.0, 2650.0])

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.3,  # Low clarity
            chop_detected=True,  # Chop detected
        )

        features = pd.Series(
            {
                "close": 2654.0,
                "vwap": 2650.0,
            }
        )

        is_valid, reason = reclaim_sentinel(
            features=features,
            htf_bias=htf_bias,
            vwap_history=vwap_history,
            price_history=price_history,
            lookback=5,
        )

        assert is_valid is False
        assert "structure" in reason.lower() or "chop" in reason.lower()


class TestDetectDisplacementCandle:
    """Test displacement candle detection."""

    def test_valid_displacement_candle(self):
        """Test detection of valid displacement candle."""
        df = pd.DataFrame(
            {
                "open": [2645.0, 2646.0, 2647.0, 2648.0, 2649.0, 2650.0],
                "high": [2646.0, 2647.0, 2648.0, 2649.0, 2650.0, 2655.0],
                "low": [2644.0, 2645.0, 2646.0, 2647.0, 2648.0, 2649.0],
                "close": [
                    2645.5,
                    2646.5,
                    2647.5,
                    2648.5,
                    2649.5,
                    2654.0,
                ],  # Last bar: body=4.0
            }
        )
        # Average body of first 5 bars: (0.5+0.5+0.5+0.5+0.5)/5 = 0.5
        # Last bar body: 4.0 > 0.5 -> True

        reclaim_bar_idx = 5
        is_displacement = detect_displacement_candle(df, reclaim_bar_idx, lookback=5)

        assert is_displacement  # Should be True is True

    def test_no_displacement_small_body(self):
        """Test rejection when candle body is not larger than average."""
        df = pd.DataFrame(
            {
                "open": [2645.0, 2646.0, 2647.0, 2648.0, 2649.0, 2650.0],
                "high": [2646.0, 2647.0, 2648.0, 2649.0, 2650.0, 2651.0],
                "low": [2644.0, 2645.0, 2646.0, 2647.0, 2648.0, 2649.0],
                "close": [
                    2645.5,
                    2646.5,
                    2647.5,
                    2648.5,
                    2649.5,
                    2650.5,
                ],  # Last bar: body=0.5
            }
        )
        # Average body of first 5 bars: (0.5+0.5+0.5+0.5+0.5)/5 = 0.5
        # Last bar body: 0.5 = 0.5 -> False (not greater)

        reclaim_bar_idx = 5
        is_displacement = detect_displacement_candle(df, reclaim_bar_idx, lookback=5)

        assert not is_displacement

    def test_displacement_with_bearish_candle(self):
        """Test displacement detection works for bearish candles too."""
        df = pd.DataFrame(
            {
                "open": [2655.0, 2654.0, 2653.0, 2652.0, 2651.0, 2650.0],
                "high": [2656.0, 2655.0, 2654.0, 2653.0, 2652.0, 2651.0],
                "low": [2654.0, 2653.0, 2652.0, 2651.0, 2650.0, 2645.0],
                "close": [
                    2654.5,
                    2653.5,
                    2652.5,
                    2651.5,
                    2650.5,
                    2646.0,
                ],  # Last bar: body=4.0
            }
        )
        # Average body of first 5 bars: (0.5+0.5+0.5+0.5+0.5)/5 = 0.5
        # Last bar body: abs(2646.0-2650.0) = 4.0 > 0.5 -> True

        reclaim_bar_idx = 5
        is_displacement = detect_displacement_candle(df, reclaim_bar_idx, lookback=5)

        assert is_displacement  # Should be True
