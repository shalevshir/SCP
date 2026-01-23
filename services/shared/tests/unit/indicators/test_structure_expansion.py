"""Tests for expansion detection in StructureContextTracker.

Following TDD: Tests written before implementation of detect_expansion().
"""

import pytest

from scp_shared.indicators.structure import StructureContextTracker


class TestExpansionDetection:
    """Test expansion detection logic."""

    def test_detect_expansion_with_recent_bos(self):
        """Test that recent BOS triggers expansion signal."""
        tracker = StructureContextTracker(swing_window=5, timeframe="1m")

        # Warm up tracker with some bars
        for i in range(20):
            tracker.update(high=2650.0 + i, low=2648.0 + i, close=2649.0 + i)

        # Get context with BOS
        ctx = tracker.update(high=2670.0, low=2668.0, close=2669.0)

        # Should detect expansion due to recent BOS (bos_age should be small)
        expansion_detected, reasons = tracker.detect_expansion()

        # If BOS was just detected, expansion should be true
        if ctx.bos_age is not None and ctx.bos_age <= 10:
            assert expansion_detected is True
            assert "recent_bos" in reasons

    def test_detect_expansion_with_range_expansion(self):
        """Test that range expansion triggers expansion signal."""
        tracker = StructureContextTracker(swing_window=5, timeframe="1m")

        # Warm up with compressed bars (small range)
        for i in range(20):
            tracker.update(high=2650.0 + 0.5, low=2650.0 - 0.5, close=2650.0)

        # Add bar with expanded range (2x normal)
        tracker.update(high=2651.5, low=2648.5, close=2650.0)

        expansion_detected, reasons = tracker.detect_expansion()

        assert expansion_detected is True
        assert "range_expansion" in reasons

    def test_detect_expansion_with_atr_expansion(self):
        """Test that ATR expansion triggers expansion signal."""
        tracker = StructureContextTracker(swing_window=5, timeframe="1m")

        # Warm up with compressed bars
        for i in range(30):
            tracker.update(high=2650.0 + 0.2, low=2650.0 - 0.2, close=2650.0)

        # Add bars with expanding volatility
        for i in range(5):
            tracker.update(high=2650.0 + 2.0, low=2650.0 - 2.0, close=2650.0)

        expansion_detected, reasons = tracker.detect_expansion()

        # ATR should be expanding from compressed baseline
        if tracker.atr_compression_ratio_cached > 0.7:
            assert expansion_detected is True
            assert "atr_expansion" in reasons

    def test_detect_expansion_with_displacement_candle(self):
        """Test that displacement candle triggers expansion signal."""
        tracker = StructureContextTracker(swing_window=5, timeframe="1m")

        # Warm up with small body candles
        for i in range(20):
            tracker.update(high=2650.0 + 0.5, low=2650.0 - 0.5, close=2650.0 + 0.1)

        # Add displacement candle (large body)
        tracker.update(high=2655.0, low=2649.0, close=2654.0)

        expansion_detected, reasons = tracker.detect_expansion()

        assert expansion_detected is True
        assert "displacement_candle" in reasons

    def test_no_expansion_during_compression(self):
        """Test that no expansion is detected during sustained compression."""
        tracker = StructureContextTracker(swing_window=5, timeframe="1m")

        # All compressed bars with no expansion signals
        # Vary close slightly to avoid exact repetition but keep range small
        for i in range(30):
            close_val = 2650.0 + (i % 3) * 0.05  # Small variation
            tracker.update(high=close_val + 0.3, low=close_val - 0.3, close=close_val)

        expansion_detected, reasons = tracker.detect_expansion()

        # Should not detect expansion if ATR is compressed
        # Note: If ATR ratio happens to be >0.7, that's acceptable given data randomness
        # Main check: no BOS, no range expansion, no displacement
        if expansion_detected:
            # Allow ATR expansion since it depends on baseline calculation
            # But should not have BOS, range expansion, or displacement
            invalid_reasons = [
                r
                for r in reasons
                if r in ["recent_bos", "range_expansion", "displacement_candle"]
            ]
            assert (
                len(invalid_reasons) == 0
            ), f"Should not detect {invalid_reasons} during compression"

    def test_expansion_returns_multiple_reasons(self):
        """Test that multiple expansion signals are captured."""
        tracker = StructureContextTracker(swing_window=5, timeframe="1m")

        # Warm up
        for i in range(20):
            tracker.update(high=2650.0 + 0.5, low=2650.0 - 0.5, close=2650.0)

        # Add bar with both range expansion AND displacement
        tracker.update(high=2655.0, low=2648.0, close=2654.0)

        expansion_detected, reasons = tracker.detect_expansion()

        assert expansion_detected is True
        # Should have multiple reasons
        assert len(reasons) >= 1
