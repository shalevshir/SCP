"""Unit tests for VWAP reclaim sentinel module."""

import pytest
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Literal, Optional

from scp_shared.rule_engine.htf.vwap.sentinel import (
    reclaim_sentinel,
    detect_displacement_candle,
)
from scp_shared.rule_engine.htf.types import HTFBias


def create_htf_bias(
    direction: Literal["long", "short", "neutral"] = "long",
    structure_clarity: float = 0.8,
    liquidity_sweep_detected: bool = True,
    chop_detected: bool = False,
) -> HTFBias:
    """Helper to create HTFBias for testing."""
    bias: Literal["bullish", "bearish", "neutral"] = "bullish" if direction == "long" else "bearish" if direction == "short" else "neutral"
    return HTFBias(
        bias=bias,
        direction=direction,
        score=7.5,
        confidence="high",
        structure_clarity=structure_clarity,
        liquidity_sweep_detected=liquidity_sweep_detected,
        chop_detected=chop_detected,
        dxy_alignment=True,
        structure_15m="HL",
        structure_1h="HL",
    )


def create_price_history(
    num_bars: int = 10,
    base_price: float = 100.0,
    base_vwap: float = 99.0,
    include_cross_below_to_above: bool = False,
    include_cross_above_to_below: bool = False,
    cross_bar: int = 7,  # Set to be in last 5 bars (lookback=5 checks last 5 bars)
) -> tuple[pd.DataFrame, pd.Series]:
    """Create price history and VWAP for testing.
    
    Args:
        num_bars: Number of bars to create
        base_price: Base price level
        base_vwap: Base VWAP level
        include_cross_below_to_above: If True, create a cross from below to above VWAP
        include_cross_above_to_below: If True, create a cross from above to below VWAP  
        cross_bar: Bar index where cross occurs (should be >= num_bars - lookback)
    """
    closes = [base_price + i * 0.1 for i in range(num_bars)]
    opens = [c - 0.5 for c in closes]
    highs = [c + 0.5 for c in closes]
    lows = [c - 1.0 for c in closes]
    
    vwap_values = [base_vwap + i * 0.05 for i in range(num_bars)]
    
    if include_cross_below_to_above:
        # Price below VWAP before cross, above after
        for i in range(cross_bar):
            closes[i] = vwap_values[i] - 1.0
            opens[i] = closes[i] - 0.5
            highs[i] = opens[i] + 0.5
            lows[i] = closes[i] - 1.5
        for i in range(cross_bar, num_bars):
            closes[i] = vwap_values[i] + 1.0
            opens[i] = closes[i] - 0.5
            highs[i] = closes[i] + 0.5
            lows[i] = opens[i] - 0.5
    
    if include_cross_above_to_below:
        # Price above VWAP before cross, below after
        for i in range(cross_bar):
            closes[i] = vwap_values[i] + 1.0
            opens[i] = closes[i] + 0.5
            highs[i] = opens[i] + 0.5
            lows[i] = closes[i] - 0.5
        for i in range(cross_bar, num_bars):
            closes[i] = vwap_values[i] - 1.0
            opens[i] = closes[i] + 0.5
            highs[i] = opens[i] + 0.5
            lows[i] = closes[i] - 0.5
    
    price_df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    })
    
    vwap_series = pd.Series(vwap_values)
    
    return price_df, vwap_series


class TestDetectDisplacementCandle:
    """Tests for detect_displacement_candle function."""

    def test_detects_displacement_when_body_larger_than_avg(self) -> None:
        """Returns True when reclaim bar body > average body size."""
        # Create bars with small bodies, then a large body
        opens = [100, 100.1, 100.2, 100.3, 100.4]
        closes = [100.1, 100.2, 100.3, 100.4, 101.0]  # Last one has large body
        
        df = pd.DataFrame({
            "open": opens,
            "high": [o + 0.5 for o in opens],
            "low": [o - 0.2 for o in opens],
            "close": closes,
        })
        
        result = detect_displacement_candle(df, reclaim_bar_idx=4, lookback=4)
        
        assert result == True

    def test_rejects_when_body_smaller_than_avg(self) -> None:
        """Returns False when reclaim bar body <= average body size."""
        # Create bars with similar-sized bodies
        opens = [100, 100.1, 100.2, 100.3, 100.4]
        closes = [100.1, 100.2, 100.3, 100.4, 100.45]  # Last one has small body
        
        df = pd.DataFrame({
            "open": opens,
            "high": [o + 0.5 for o in opens],
            "low": [o - 0.2 for o in opens],
            "close": closes,
        })
        
        result = detect_displacement_candle(df, reclaim_bar_idx=4, lookback=4)
        
        assert result == False

    def test_returns_false_for_invalid_index(self) -> None:
        """Returns False for out-of-bounds index."""
        df = pd.DataFrame({
            "open": [100, 101],
            "high": [101, 102],
            "low": [99, 100],
            "close": [100.5, 101.5],
        })
        
        assert detect_displacement_candle(df, reclaim_bar_idx=-1, lookback=1) == False
        assert detect_displacement_candle(df, reclaim_bar_idx=10, lookback=1) == False

    def test_returns_false_when_no_previous_bars(self) -> None:
        """Returns False when no previous bars for comparison."""
        df = pd.DataFrame({
            "open": [100],
            "high": [101],
            "low": [99],
            "close": [100.5],
        })
        
        result = detect_displacement_candle(df, reclaim_bar_idx=0, lookback=5)
        
        assert result == False


class TestReclaimSentinel:
    """Tests for reclaim_sentinel function."""

    def test_rejects_insufficient_history(self) -> None:
        """Rejects when insufficient price/VWAP history."""
        features = pd.Series({"close": 100, "vwap": 99})
        htf_bias = create_htf_bias()
        
        # Only 2 bars, needs 5
        price_df = pd.DataFrame({
            "open": [99, 100],
            "high": [101, 102],
            "low": [98, 99],
            "close": [100, 101],
        })
        vwap = pd.Series([99, 99.5])
        
        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap, price_df, lookback=5
        )
        
        assert is_valid == False
        assert reason is not None and "Insufficient" in reason

    def test_rejects_long_without_vwap_cross_from_below(self) -> None:
        """Rejects long when price didn't cross VWAP from below."""
        features = pd.Series({"close": 100, "vwap": 99})
        htf_bias = create_htf_bias(direction="long")
        
        # Price always above VWAP
        price_df, vwap = create_price_history(
            num_bars=10, base_price=100, base_vwap=95
        )
        
        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap, price_df, lookback=5
        )
        
        assert is_valid == False
        assert reason is not None and "hasn't crossed VWAP from below" in reason

    def test_rejects_short_without_vwap_cross_from_above(self) -> None:
        """Rejects short when price didn't cross VWAP from above."""
        features = pd.Series({"close": 100, "vwap": 99})
        htf_bias = create_htf_bias(direction="short")
        
        # Price always below VWAP
        price_df, vwap = create_price_history(
            num_bars=10, base_price=95, base_vwap=100
        )
        
        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap, price_df, lookback=5
        )
        
        assert is_valid == False
        assert reason is not None and "hasn't crossed VWAP from above" in reason

    def test_rejects_without_liquidity_sweep(self) -> None:
        """Rejects when no liquidity sweep detected."""
        features = pd.Series({"close": 100, "vwap": 99})
        htf_bias = create_htf_bias(
            direction="long", 
            liquidity_sweep_detected=False
        )
        
        # Cross at bar 7 so it's within last 5 bars
        price_df, vwap = create_price_history(
            num_bars=10, include_cross_below_to_above=True, cross_bar=7
        )
        
        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap, price_df, lookback=5
        )
        
        assert is_valid == False
        assert reason is not None and "liquidity sweep" in reason

    def test_rejects_low_structure_clarity(self) -> None:
        """Rejects when structure clarity too low."""
        features = pd.Series({"close": 100, "vwap": 99})
        htf_bias = create_htf_bias(
            direction="long",
            structure_clarity=0.5,
        )
        
        # Cross at bar 7 so it's within last 5 bars (7 is bar 2 in the lookback window)
        price_df, vwap = create_price_history(
            num_bars=10, include_cross_below_to_above=True, cross_bar=7
        )
        # Override reclaim bar (bar 7, which is index 2 in lookback) to create displacement
        price_df.loc[7, "close"] = price_df.loc[7, "open"] + 5.0
        
        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap, price_df, lookback=5
        )
        
        assert is_valid == False
        assert reason is not None and "Structure clarity too low" in reason

    def test_rejects_choppy_structure(self) -> None:
        """Rejects when choppy structure detected."""
        features = pd.Series({"close": 100, "vwap": 99})
        htf_bias = create_htf_bias(
            direction="long",
            chop_detected=True,
        )
        
        # Cross at bar 7 so it's within last 5 bars
        price_df, vwap = create_price_history(
            num_bars=10, include_cross_below_to_above=True, cross_bar=7
        )
        # Override reclaim bar (bar 7, which is index 2 in lookback) to create displacement
        price_df.loc[7, "close"] = price_df.loc[7, "open"] + 5.0
        
        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap, price_df, lookback=5
        )
        
        assert is_valid == False
        assert reason is not None and "Choppy" in reason
