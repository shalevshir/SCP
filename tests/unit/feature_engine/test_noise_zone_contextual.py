"""Unit tests for ATR compression ratio and structural chop detection.

Tests verify that:
1. ATR compression is tracked as a ratio (supporting filter), not a hard gate
2. Structural chop is based on structure (overlapping swings, failed follow-through)
3. Low ATR alone does NOT trigger structural chop
"""

import pytest

from feature_engine.structure import StructureContextTracker


class TestATRCompressionRatio:
    """Test suite for ATR compression ratio (supporting filter, not primary gate)."""

    def test_normal_volatility_ratio_near_one(self):
        """Normal volatility should yield compression ratio near 1.0."""
        tracker = StructureContextTracker()

        # Simulate 70 bars of normal volatility (ATR stays consistent around 5 points)
        for i in range(70):
            high = 2650.0 + (i % 10)  # Range of 10 points
            low = 2645.0 + (i % 10)
            close = 2647.0 + (i % 10)
            context = tracker.update(high, low, close)

        # Last bar should have compression ratio near 1.0 (normal volatility)
        assert 0.8 <= context.atr_compression_ratio <= 1.2, \
            f"Normal volatility should have ratio ~1.0, got {context.atr_compression_ratio}"

    def test_compression_ratio_reflects_volatility_drop(self):
        """Significant volatility compression should yield low compression ratio."""
        tracker = StructureContextTracker()

        # Build baseline with normal volatility (ATR ~5 points)
        for i in range(50):
            high = 2650.0 + (i % 10)
            low = 2645.0 + (i % 10)
            close = 2647.0 + (i % 10)
            tracker.update(high, low, close)

        # Now compress volatility significantly (ATR ~1 point, < 40% of baseline)
        for i in range(20):
            high = 2648.0 + (i % 2) * 0.5  # Tight range
            low = 2647.0 + (i % 2) * 0.5
            close = 2647.5 + (i % 2) * 0.5
            context = tracker.update(high, low, close)

        # Last bar should have low compression ratio (ATR compressed to ~20% of baseline)
        assert context.atr_compression_ratio < 0.4, \
            f"Compressed volatility should have ratio < 0.4, got {context.atr_compression_ratio}"

    def test_compression_ratio_requires_baseline_history(self):
        """Compression ratio should default to 1.0 without sufficient baseline."""
        tracker = StructureContextTracker()

        # First 19 bars should default to 1.0 (insufficient baseline)
        for i in range(19):
            high = 2648.0
            low = 2647.0
            close = 2647.5
            context = tracker.update(high, low, close)
            assert context.atr_compression_ratio == 1.0

    def test_compression_ratio_recovers_after_expansion(self):
        """Compression ratio should increase when volatility expands back."""
        tracker = StructureContextTracker()

        # Build baseline with normal volatility
        for i in range(50):
            high = 2650.0 + (i % 10)
            low = 2645.0 + (i % 10)
            close = 2647.0 + (i % 10)
            tracker.update(high, low, close)

        # Compress volatility
        for i in range(15):
            high = 2648.0 + (i % 2) * 0.5
            low = 2647.0 + (i % 2) * 0.5
            close = 2647.5 + (i % 2) * 0.5
            context = tracker.update(high, low, close)

        # Should have low compression ratio
        assert context.atr_compression_ratio < 0.4

        # Expand volatility back to normal
        for i in range(10):
            high = 2650.0 + (i % 10)
            low = 2645.0 + (i % 10)
            close = 2647.0 + (i % 10)
            context = tracker.update(high, low, close)

        # Should recover to near 1.0
        assert context.atr_compression_ratio > 0.6

    def test_no_false_positives_for_normal_intraday_ranges(self):
        """Normal Gold intraday ranges (2-5 points ATR) should have ratio ~1.0.
        
        Key: ATR is contextual, not absolute. Normal intraday volatility
        should not be flagged as compressed.
        """
        tracker = StructureContextTracker()

        # Simulate realistic Gold 1M intraday volatility (2-5 point ATR)
        for i in range(70):
            # Vary between 2-5 point ranges (normal intraday)
            range_size = 2 + (i % 4)
            high = 2650.0 + range_size
            low = 2650.0
            close = 2650.0 + range_size / 2
            context = tracker.update(high, low, close)

        # Should have normal compression ratio (not compressed)
        assert context.atr_compression_ratio > 0.7, \
            f"Normal intraday should not show compression, got {context.atr_compression_ratio}"


class TestStructuralChopDetection:
    """Test that structural chop is based on structure, not ATR."""

    def test_low_atr_alone_does_not_trigger_structural_chop(self):
        """Low ATR without structural disorder should NOT trigger structural chop."""
        tracker = StructureContextTracker()

        # Build baseline
        for i in range(50):
            high = 2650.0 + (i % 10)
            low = 2645.0 + (i % 10)
            close = 2647.0 + (i % 10)
            tracker.update(high, low, close)

        # Compress ATR but maintain clean structure (no alternations)
        for i in range(20):
            high = 2648.0 + (i % 2) * 0.5
            low = 2647.0 + (i % 2) * 0.5
            close = 2647.5 + (i % 2) * 0.5
            context = tracker.update(high, low, close)

        # ATR should be compressed
        assert context.atr_compression_ratio < 0.4
        # But structural chop should be FALSE (no structural disorder)
        assert context.is_structural_chop is False, \
            "Low ATR alone should not trigger structural chop"


class TestChopPenaltyIntegration:
    """Test that chop penalty uses structural chop + ATR as modifier."""

    def test_structural_chop_penalty_for_vwap_fade(self):
        """VWAP_FADE should get -0.5 penalty for structural chop."""
        from rule_engine.scoring import calculate_noise_penalty
        import pandas as pd

        features = pd.Series({"is_structural_chop": True, "atr_compression_ratio": 1.0})
        penalty = calculate_noise_penalty(features, "VWAP_FADE")
        assert penalty == -0.5

    def test_structural_chop_penalty_for_vwap_reclaim(self):
        """VWAP_RECLAIM should get -1.5 penalty for structural chop."""
        from rule_engine.scoring import calculate_noise_penalty
        import pandas as pd

        features = pd.Series({"is_structural_chop": True, "atr_compression_ratio": 1.0})
        penalty = calculate_noise_penalty(features, "VWAP_RECLAIM")
        assert penalty == -1.5

    def test_structural_chop_penalty_for_dxy_continuation(self):
        """DXY_CONTINUATION should get -1.5 penalty for structural chop."""
        from rule_engine.scoring import calculate_noise_penalty
        import pandas as pd

        features = pd.Series({"is_structural_chop": True, "atr_compression_ratio": 1.0})
        penalty = calculate_noise_penalty(features, "DXY_CONTINUATION")
        assert penalty == -1.5

    def test_atr_compression_amplifies_structural_chop_penalty(self):
        """ATR compression should amplify structural chop penalty by -0.5."""
        from rule_engine.scoring import calculate_noise_penalty
        import pandas as pd

        # Structural chop + ATR compression
        features = pd.Series({"is_structural_chop": True, "atr_compression_ratio": 0.3})
        penalty = calculate_noise_penalty(features, "VWAP_RECLAIM")
        # Base -1.5 + ATR amplifier -0.5 = -2.0
        assert penalty == -2.0

    def test_atr_compression_alone_gives_small_penalty(self):
        """ATR compression without structural chop should give small penalty only."""
        from rule_engine.scoring import calculate_noise_penalty
        import pandas as pd

        # ATR compression but NO structural chop
        features = pd.Series({"is_structural_chop": False, "atr_compression_ratio": 0.3})
        penalty = calculate_noise_penalty(features, "VWAP_RECLAIM")
        # ATR modifier only: -0.2
        assert penalty == -0.2

    def test_no_penalty_when_no_chop_and_normal_atr(self):
        """No penalty when no structural chop and normal ATR."""
        from rule_engine.scoring import calculate_noise_penalty
        import pandas as pd

        features = pd.Series({"is_structural_chop": False, "atr_compression_ratio": 1.0})
        penalty = calculate_noise_penalty(features, "VWAP_FADE")
        assert penalty == 0.0

        penalty = calculate_noise_penalty(features, "VWAP_RECLAIM")
        assert penalty == 0.0

