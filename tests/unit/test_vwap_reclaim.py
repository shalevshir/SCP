"""Unit tests for VWAP reclaim detection.

Tests the complete VWAP reclaim sequence detection:
- Price below VWAP
- Liquidity sweep
- Displacement candle
- Close above VWAP

Following TDD: These tests will fail until implementation is complete.
"""

import pandas as pd
import pytest
from datetime import datetime, timezone

from rule_engine.htf.vwap.reclaim import (
    VWAPReclaimState,
    detect_vwap_reclaim,
    validate_reclaim_prerequisites,
)
from rule_engine.htf.types import HTFBias


class TestVWAPReclaimState:
    """Test the VWAPReclaimState dataclass."""

    def test_initial_state(self):
        """Test initial state is all False/None."""
        state = VWAPReclaimState()
        assert state.started_below is False
        assert state.sweep_detected is False
        assert state.sweep_bar_idx is None
        assert state.displacement_detected is False
        assert state.reclaim_confirmed is False


class TestDetectVWAPReclaim:
    """Test VWAP reclaim detection logic."""

    def test_valid_reclaim_sequence(self):
        """Test detection of valid reclaim sequence."""
        # Create test data: price below VWAP -> sweep -> displacement -> above VWAP
        df = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01 10:00', periods=10, freq='1min', tz='UTC'),
            'open': [2650.0, 2649.0, 2648.0, 2647.0, 2646.0, 2645.0, 2650.0, 2655.0, 2656.0, 2657.0],
            'high': [2651.0, 2650.0, 2649.0, 2648.0, 2647.0, 2646.0, 2654.0, 2656.0, 2657.0, 2658.0],
            'low': [2649.0, 2648.0, 2647.0, 2645.0, 2644.0, 2643.0, 2649.0, 2654.0, 2655.0, 2656.0],
            'close': [2649.5, 2648.5, 2647.5, 2646.5, 2645.5, 2649.0, 2653.0, 2655.5, 2656.5, 2657.5],
            'vwap': [2652.0, 2652.0, 2652.0, 2652.0, 2652.0, 2652.0, 2652.0, 2652.0, 2652.0, 2652.0],
        })
        df.set_index('timestamp', inplace=True)

        # Mock HTF bias with sweep detected
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            liquidity_sweep_detected=True,
            liquidity_sweep_type="bullish",
            structure_clarity=0.8,
        )

        # Check last 5 bars for reclaim
        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        assert is_reclaim is True
        assert state.started_below
        assert state.sweep_detected
        assert state.displacement_detected
        assert state.reclaim_confirmed

    def test_no_reclaim_price_never_below_vwap(self):
        """Test rejection when price never goes below VWAP."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01 10:00', periods=5, freq='1min', tz='UTC'),
            'open': [2655.0, 2656.0, 2657.0, 2658.0, 2659.0],
            'high': [2656.0, 2657.0, 2658.0, 2659.0, 2660.0],
            'low': [2654.0, 2655.0, 2656.0, 2657.0, 2658.0],
            'close': [2655.5, 2656.5, 2657.5, 2658.5, 2659.5],
            'vwap': [2650.0, 2650.0, 2650.0, 2650.0, 2650.0],
        })
        df.set_index('timestamp', inplace=True)

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=False,
            structure_clarity=0.8,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        assert is_reclaim is False
        assert not state.started_below

    def test_no_reclaim_no_sweep(self):
        """Test rejection when no liquidity sweep detected."""
        df = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01 10:00', periods=5, freq='1min', tz='UTC'),
            'open': [2645.0, 2646.0, 2647.0, 2653.0, 2654.0],
            'high': [2646.0, 2647.0, 2648.0, 2654.0, 2655.0],
            'low': [2644.0, 2645.0, 2646.0, 2652.0, 2653.0],
            'close': [2645.5, 2646.5, 2647.5, 2653.5, 2654.5],
            'vwap': [2650.0, 2650.0, 2650.0, 2650.0, 2650.0],
        })
        df.set_index('timestamp', inplace=True)

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=False,  # No sweep
            structure_clarity=0.8,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        assert is_reclaim is False
        assert not state.sweep_detected

    def test_no_reclaim_no_displacement(self):
        """Test rejection when no displacement candle present."""
        # Small body candles - no displacement
        df = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01 10:00', periods=5, freq='1min', tz='UTC'),
            'open': [2645.0, 2646.0, 2647.0, 2651.0, 2651.5],
            'high': [2646.0, 2647.0, 2648.0, 2652.0, 2652.5],
            'low': [2644.0, 2645.0, 2646.0, 2650.0, 2650.5],
            'close': [2645.5, 2646.5, 2647.5, 2651.5, 2652.0],  # Small bodies
            'vwap': [2650.0, 2650.0, 2650.0, 2650.0, 2650.0],
        })
        df.set_index('timestamp', inplace=True)

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            liquidity_sweep_type="bullish",
            structure_clarity=0.8,
        )

        is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)

        assert is_reclaim is False
        assert not state.displacement_detected


class TestValidateReclaimPrerequisites:
    """Test reclaim prerequisite validation."""

    def test_valid_prerequisites(self):
        """Test validation passes with all prerequisites met."""
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

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is True
        assert reason is None

    def test_invalid_no_sweep(self):
        """Test validation fails when no sweep detected."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=False,  # No sweep
            structure_clarity=0.8,
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=False,
        )

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is False
        assert "sweep" in reason.lower()

    def test_invalid_choppy_structure(self):
        """Test validation fails with choppy structure."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            liquidity_sweep_type="bullish",
            structure_clarity=0.3,  # Low clarity
            chop_detected=True,  # Chop detected
            bos_detected=True,
            bars_since_bos=10,
        )

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is False
        assert "structure" in reason.lower() or "chop" in reason.lower()

    def test_invalid_no_bos(self):
        """Test validation fails when no recent BOS."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            liquidity_sweep_type="bullish",
            structure_clarity=0.8,
            bos_detected=False,  # No BOS
            bars_since_bos=None,
            chop_detected=False,
        )

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is False
        assert "bos" in reason.lower()

    def test_invalid_stale_bos(self):
        """Test validation fails when BOS is too old."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            liquidity_sweep_type="bullish",
            structure_clarity=0.8,
            bos_detected=True,
            bars_since_bos=20,  # Too old (>15 bars)
            chop_detected=False,
        )

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is False
        assert "bos" in reason.lower() and "stale" in reason.lower()

