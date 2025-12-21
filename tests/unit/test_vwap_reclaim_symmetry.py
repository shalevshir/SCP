"""Unit tests for VWAP_RECLAIM symmetry fixes (Issues 1-5).

Tests cover:
- Issue 1: SHORT reclaim detection (direction-aware logic)
- Issue 2: Sentinel gate SHORT support
- Issue 3: VWAPReclaimState backward compatibility
- Issue 4: VWAP dwell gate (30 bar minimum)
- Issue 5: Structure label mandatory check
"""

from __future__ import annotations

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.htf.vwap.reclaim import (
    VWAPReclaimState,
    detect_vwap_reclaim,
    validate_reclaim_context,
)
from rule_engine.htf.vwap.sentinel import reclaim_sentinel


class TestVWAPReclaimDirectionAware:
    """Test Issue 1: detect_vwap_reclaim() supports SHORT direction."""

    def test_long_reclaim_detection(self):
        """Test LONG reclaim: price crosses from below to above VWAP."""
        # Create sample data: price below VWAP, then crosses above
        df = pd.DataFrame(
            {
                "open": [100.0] * 10 + [101.0, 102.0],
                "high": [100.5] * 10 + [101.5, 103.0],
                "low": [99.5] * 10 + [100.5, 101.5],
                "close": [100.0] * 10 + [101.5, 102.5],  # Crosses above at index 10
                "vwap": [101.0] * 12,  # VWAP constant at 101
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        assert is_reclaim is True
        assert state.started_on_dwell_side is True
        assert state.sweep_detected is True
        assert state.displacement_detected is True
        assert state.reclaim_confirmed is True

    def test_short_reclaim_detection(self):
        """Test SHORT reclaim: price crosses from above to below VWAP."""
        # Create sample data: price above VWAP, then crosses below
        df = pd.DataFrame(
            {
                "open": [102.0] * 10 + [101.0, 100.0],
                "high": [102.5] * 10 + [101.5, 100.5],
                "low": [101.5] * 10 + [100.5, 99.5],
                "close": [102.0] * 10 + [100.5, 99.5],  # Crosses below at index 10
                "vwap": [101.0] * 12,  # VWAP constant at 101
            }
        )

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        assert is_reclaim is True
        assert state.started_on_dwell_side is True
        assert state.sweep_detected is True
        assert state.displacement_detected is True
        assert state.reclaim_confirmed is True

    def test_long_direction_rejects_short_pattern(self):
        """Test that LONG direction rejects SHORT pattern (above to below)."""
        # Create SHORT pattern data
        df = pd.DataFrame(
            {
                "open": [102.0] * 10 + [101.0, 100.0],
                "high": [102.5] * 10 + [101.5, 100.5],
                "low": [101.5] * 10 + [100.5, 99.5],
                "close": [102.0] * 10 + [100.5, 99.5],
                "vwap": [101.0] * 12,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",  # LONG direction with SHORT pattern
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        # Should reject because price was above VWAP, not below
        assert is_reclaim is False

    def test_short_direction_rejects_long_pattern(self):
        """Test that SHORT direction rejects LONG pattern (below to above)."""
        # Create LONG pattern data
        df = pd.DataFrame(
            {
                "open": [100.0] * 10 + [101.0, 102.0],
                "high": [100.5] * 10 + [101.5, 103.0],
                "low": [99.5] * 10 + [100.5, 101.5],
                "close": [100.0] * 10 + [101.5, 102.5],
                "vwap": [101.0] * 12,
            }
        )

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",  # SHORT direction with LONG pattern
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        # Should reject because price was below VWAP, not above
        assert is_reclaim is False


class TestSentinelDirectionAware:
    """Test Issue 2: reclaim_sentinel() supports SHORT direction."""

    def test_sentinel_long_cross_detection(self):
        """Test sentinel detects LONG cross (below to above)."""
        price_history = pd.DataFrame(
            {
                "open": [100.0] * 3 + [101.0, 102.0],
                "high": [100.5] * 3 + [101.5, 103.0],
                "low": [99.5] * 3 + [100.5, 101.5],
                "close": [100.0] * 3 + [101.5, 102.5],
            }
        )
        vwap_history = pd.Series([101.0] * 5)
        features = pd.Series({"close": 102.5, "vwap": 101.0})

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap_history, price_history, lookback=5
        )

        assert is_valid is True
        assert reason is None

    def test_sentinel_short_cross_detection(self):
        """Test sentinel detects SHORT cross (above to below)."""
        price_history = pd.DataFrame(
            {
                "open": [102.0] * 3 + [101.0, 100.0],
                "high": [102.5] * 3 + [101.5, 100.5],
                "low": [101.5] * 3 + [100.5, 99.5],
                "close": [102.0] * 3 + [100.5, 99.5],
            }
        )
        vwap_history = pd.Series([101.0] * 5)
        features = pd.Series({"close": 99.5, "vwap": 101.0})

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap_history, price_history, lookback=5
        )

        assert is_valid is True
        assert reason is None

    def test_sentinel_rejects_wrong_direction_cross(self):
        """Test sentinel rejects cross in wrong direction."""
        # SHORT pattern (above to below)
        price_history = pd.DataFrame(
            {
                "open": [102.0] * 3 + [101.0, 100.0],
                "high": [102.5] * 3 + [101.5, 100.5],
                "low": [101.5] * 3 + [100.5, 99.5],
                "close": [102.0] * 3 + [100.5, 99.5],
            }
        )
        vwap_history = pd.Series([101.0] * 5)
        features = pd.Series({"close": 99.5, "vwap": 101.0})

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",  # LONG direction with SHORT pattern
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_valid, reason = reclaim_sentinel(
            features, htf_bias, vwap_history, price_history, lookback=5
        )

        assert is_valid is False
        assert "from below" in reason


class TestVWAPReclaimStateBackwardCompatibility:
    """Test Issue 3: VWAPReclaimState backward compatibility."""

    def test_started_on_dwell_side_field(self):
        """Test new field name works correctly."""
        state = VWAPReclaimState()
        state.started_on_dwell_side = True

        assert state.started_on_dwell_side is True

    def test_started_below_property_getter(self):
        """Test backward-compatible property getter."""
        state = VWAPReclaimState()
        state.started_on_dwell_side = True

        # Old code using started_below should still work
        assert state.started_below is True

    def test_started_below_property_setter(self):
        """Test backward-compatible property setter."""
        state = VWAPReclaimState()
        # Old code setting started_below should update started_on_dwell_side
        state.started_below = True

        assert state.started_on_dwell_side is True
        assert state.started_below is True


class TestVWAPDwellGate:
    """Test Issue 4: VWAP dwell gate (30 bar minimum)."""

    def test_dwell_gate_passes_with_sufficient_bars(self):
        """Test reclaim passes when price dwells 30+ bars on dwell side."""
        # Create data: 35 bars below VWAP, then cross above
        df = pd.DataFrame(
            {
                "open": [100.0] * 35 + [101.0, 102.0],
                "high": [100.5] * 35 + [101.5, 103.0],
                "low": [99.5] * 35 + [100.5, 101.5],
                "close": [100.0] * 35 + [101.5, 102.5],
                "vwap": [101.0] * 37,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        assert is_reclaim is True

    def test_dwell_gate_rejects_insufficient_bars(self):
        """Test reclaim rejects when price dwells < 30 bars on dwell side."""
        # Create data: only 10 bars below VWAP, then cross above
        df = pd.DataFrame(
            {
                "open": [102.0] * 25 + [100.0] * 10 + [101.0, 102.0],
                "high": [102.5] * 25 + [100.5] * 10 + [101.5, 103.0],
                "low": [101.5] * 25 + [99.5] * 10 + [100.5, 101.5],
                "close": [102.0] * 25 + [100.0] * 10 + [101.5, 102.5],
                "vwap": [101.0] * 37,
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        # Should reject due to insufficient dwell time
        assert is_reclaim is False

    def test_dwell_gate_short_direction(self):
        """Test dwell gate works for SHORT direction (above VWAP)."""
        # Create data: 35 bars above VWAP, then cross below
        df = pd.DataFrame(
            {
                "open": [102.0] * 35 + [101.0, 100.0],
                "high": [102.5] * 35 + [101.5, 100.5],
                "low": [101.5] * 35 + [100.5, 99.5],
                "close": [102.0] * 35 + [100.5, 99.5],
                "vwap": [101.0] * 37,
            }
        )

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        assert is_reclaim is True


class TestStructureLabelMandatory:
    """Test Issue 5: Structure label check is mandatory."""

    def test_rejects_missing_structure_label(self):
        """Test that missing structure_label causes rejection."""
        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                "structure_clarity": 0.8,
                # structure_label is missing
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
            structure_1h="HH",  # Required to pass structure_1h check
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is False
        assert "No structure label available" in result.reason

    def test_rejects_nan_structure_label(self):
        """Test that NaN structure_label causes rejection."""
        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                "structure_clarity": 0.8,
                "structure_label": pd.NA,  # NaN value
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
            structure_1h="HH",  # Required to pass structure_1h check
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is False
        assert "No structure label available" in result.reason

    def test_rejects_conflicting_structure_label_long(self):
        """Test that bearish structure_label rejects LONG trade."""
        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                "structure_clarity": 0.8,
                "structure_label": "LL",  # Bearish label for LONG trade
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
            structure_1h="HH",  # Required to pass structure_1h check
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is False
        assert "Bearish micro structure" in result.reason

    def test_rejects_conflicting_structure_label_short(self):
        """Test that bullish structure_label rejects SHORT trade."""
        features = pd.Series(
            {
                "close": 100.0,
                "vwap": 101.0,
                "vwap_deviation": -1.0,
                "structure_clarity": 0.8,
                "structure_label": "HH",  # Bullish label for SHORT trade
            }
        )

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
            structure_1h="LL",  # Required to pass structure_1h check
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is False
        assert "Bullish micro structure" in result.reason

    def test_accepts_aligned_structure_label_long(self):
        """Test that bullish structure_label accepts LONG trade."""
        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                "structure_clarity": 0.8,
                "structure_label": "HH",  # Bullish label for LONG trade
                "bos_direction": "bullish",  # Required for BOS/CHoCH alignment check
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
            structure_1h="HH",  # Required to pass structure_1h check
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is True

    def test_accepts_aligned_structure_label_short(self):
        """Test that bearish structure_label accepts SHORT trade."""
        features = pd.Series(
            {
                "close": 100.0,
                "vwap": 101.0,
                "vwap_deviation": -1.0,
                "structure_clarity": 0.8,
                "structure_label": "LL",  # Bearish label for SHORT trade
                "bos_direction": "bearish",  # Required for BOS/CHoCH alignment check
            }
        )

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=7.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            chop_detected=False,
            structure_1h="LL",  # Required to pass structure_1h check
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is True

