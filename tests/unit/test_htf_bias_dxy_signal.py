"""Test for DXY correlation signal in HTF bias computation.

This test verifies that DXY correlation (Signal 4) properly influences
the HTF bias calculation when correlation is strong (< -0.6).
"""

import pandas as pd
import pytest

from validation.context_builder import ValidationContextBuilder
from validation.schema import HTFBias


class TestDXYSignalInHTFBias:
    """Test that DXY correlation acts as Signal 4 in HTF bias."""

    def test_dxy_correlation_acts_as_tiebreaker_for_bullish(self) -> None:
        """Test that strong DXY correlation confirms bullish bias.
        
        When we have only 1 bullish signal vs 0 bearish (not enough for bias),
        strong DXY correlation should act as confirmation to push it to BULLISH.
        """
        builder = ValidationContextBuilder()
        
        # Only 1 bullish signal (structure), not enough alone
        features = pd.Series({
            "structure_type": "HH",  # 1 bullish signal
            "ema_9": 2645.0,
            "ema_20": 2645.0,
            "ema_50": 2645.0,  # Flat EMAs (no signal)
            "close": 2645.0,
            "vwap": 2645.0,  # At VWAP (no signal)
            "dxy_corr": -0.75,  # Strong correlation should add confirmation
        })
        
        bias = builder._compute_htf_bias(features)
        # With DXY signal, should be BULLISH (2 signals: structure + DXY)
        assert bias == HTFBias.BULLISH

    def test_dxy_correlation_acts_as_tiebreaker_for_bearish(self) -> None:
        """Test that strong DXY correlation confirms bearish bias.
        
        When we have only 1 bearish signal vs 0 bullish (not enough for bias),
        strong DXY correlation should act as confirmation to push it to BEARISH.
        """
        builder = ValidationContextBuilder()
        
        # Only 1 bearish signal (structure), not enough alone
        features = pd.Series({
            "structure_type": "LL",  # 1 bearish signal
            "ema_9": 2645.0,
            "ema_20": 2645.0,
            "ema_50": 2645.0,  # Flat EMAs (no signal)
            "close": 2645.0,
            "vwap": 2645.0,  # At VWAP (no signal)
            "dxy_corr": -0.75,  # Strong correlation should add confirmation
        })
        
        bias = builder._compute_htf_bias(features)
        # With DXY signal, should be BEARISH (2 signals: structure + DXY)
        assert bias == HTFBias.BEARISH

    def test_weak_dxy_correlation_does_not_influence_bias(self) -> None:
        """Test that weak DXY correlation doesn't add to signal count."""
        builder = ValidationContextBuilder()
        
        # Only 1 bullish signal, weak correlation
        features = pd.Series({
            "structure_type": "HH",  # 1 bullish signal
            "ema_9": 2645.0,
            "ema_20": 2645.0,
            "ema_50": 2645.0,  # Flat EMAs
            "close": 2645.0,
            "vwap": 2645.0,  # At VWAP
            "dxy_corr": -0.4,  # Weak correlation (not < -0.6)
        })
        
        bias = builder._compute_htf_bias(features)
        # Only 1 signal, not enough for bias
        assert bias == HTFBias.NEUTRAL

    def test_missing_dxy_correlation_does_not_influence_bias(self) -> None:
        """Test that missing DXY data doesn't affect bias calculation."""
        builder = ValidationContextBuilder()
        
        # Only 1 bullish signal, no DXY data
        features = pd.Series({
            "structure_type": "HH",  # 1 bullish signal
            "ema_9": 2645.0,
            "ema_20": 2645.0,
            "ema_50": 2645.0,  # Flat EMAs
            "close": 2645.0,
            "vwap": 2645.0,  # At VWAP
            "dxy_corr": None,  # Missing DXY
        })
        
        bias = builder._compute_htf_bias(features)
        # Only 1 signal, not enough for bias
        assert bias == HTFBias.NEUTRAL

    def test_dxy_signal_strengthens_existing_majority(self) -> None:
        """Test DXY signal adds to the currently leading direction.
        
        When signals are 2 bullish vs 1 bearish, DXY should strengthen
        the bullish bias by adding another bullish signal.
        """
        builder = ValidationContextBuilder()
        
        # 2 bullish (structure + EMA), 1 bearish (price below VWAP)
        features = pd.Series({
            "structure_type": "HH",  # 1 bullish
            "ema_9": 2650.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,  # 1 bullish (ascending)
            "close": 2635.0,
            "vwap": 2645.0,  # 1 bearish (below VWAP)
            "dxy_corr": -0.75,  # Strong correlation
        })
        
        bias = builder._compute_htf_bias(features)
        # With DXY confirmation, should remain BULLISH (3 bullish vs 1 bearish)
        assert bias == HTFBias.BULLISH

