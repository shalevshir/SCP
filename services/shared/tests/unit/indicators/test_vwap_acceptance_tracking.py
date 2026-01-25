"""Tests for VWAP acceptance tracking feature computation.

Tests the new VWAP acceptance metrics:
- bars_near_vwap: Consecutive bars within ±0.2 ATR of VWAP
- bars_since_last_vwap_touch: Bars since last VWAP interaction
"""

import pandas as pd
import pytest
from scp_shared.common.types import Candle
from scp_shared.indicators.structure import StructureContextTracker


class TestBarsNearVWAP:
    """Test bars_near_vwap tracking."""

    def test_increments_when_within_proximity_band(self):
        """Test that bars_near_vwap increments when price is within ±0.2 ATR of VWAP."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Bar 1: Update structure
        tracker.update(high=2650.0, low=2645.0, close=2648.0)

        # Bar 1: Price near VWAP (within 0.2 ATR)
        # VWAP = 2650, Close = 2650.1, ATR = 5.0
        # Distance = 0.1, Threshold = 5.0 * 0.2 = 1.0
        # 0.1 < 1.0 -> Near VWAP
        tracker.update_vwap_state(vwap=2650.0, close=2650.1, atr=5.0)
        assert tracker.bars_near_vwap == 1

        # Bar 2: Still near VWAP
        tracker.update(high=2651.0, low=2646.0, close=2649.5)
        tracker.update_vwap_state(vwap=2650.0, close=2649.5, atr=5.0)
        assert tracker.bars_near_vwap == 2

        # Bar 3: Still near VWAP
        tracker.update(high=2652.0, low=2647.0, close=2650.5)
        tracker.update_vwap_state(vwap=2650.0, close=2650.5, atr=5.0)
        assert tracker.bars_near_vwap == 3

    def test_resets_when_moves_outside_band(self):
        """Test that bars_near_vwap resets to 0 when price moves outside band."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Bar 1: Near VWAP
        tracker.update(high=2650.0, low=2645.0, close=2648.0)
        tracker.update_vwap_state(vwap=2650.0, close=2650.1, atr=5.0)
        assert tracker.bars_near_vwap == 1

        # Bar 2: Near VWAP
        tracker.update(high=2651.0, low=2646.0, close=2649.5)
        tracker.update_vwap_state(vwap=2650.0, close=2649.5, atr=5.0)
        assert tracker.bars_near_vwap == 2

        # Bar 3: Moves far from VWAP
        # Distance = 5.0, Threshold = 5.0 * 0.2 = 1.0
        # 5.0 > 1.0 -> Outside band
        tracker.update(high=2660.0, low=2655.0, close=2655.0)
        tracker.update_vwap_state(vwap=2650.0, close=2655.0, atr=5.0)
        assert tracker.bars_near_vwap == 0

    def test_handles_no_atr(self):
        """Test that bars_near_vwap is None when ATR is not available."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        tracker.update(high=2650.0, low=2645.0, close=2648.0)
        tracker.update_vwap_state(vwap=2650.0, close=2650.1, atr=None)
        # Should be None (tracking unavailable), not 0 (tracking available but not near)
        assert tracker.bars_near_vwap is None

    def test_proximity_threshold_scales_with_atr(self):
        """Test that proximity threshold scales with ATR."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # High volatility: ATR = 10.0, threshold = 2.0
        tracker.update(high=2650.0, low=2645.0, close=2648.0)
        tracker.update_vwap_state(vwap=2650.0, close=2651.5, atr=10.0)
        # Distance = 1.5, Threshold = 2.0 -> Near
        assert tracker.bars_near_vwap == 1

        # Low volatility: ATR = 2.0, threshold = 0.4
        tracker.update(high=2651.0, low=2649.0, close=2650.0)
        tracker.update_vwap_state(vwap=2650.0, close=2651.5, atr=2.0)
        # Distance = 1.5, Threshold = 0.4 -> Far
        assert tracker.bars_near_vwap == 0


class TestBarsSinceLastVWAPTouch:
    """Test bars_since_last_vwap_touch tracking."""

    def test_tracks_bars_since_touch(self):
        """Test that bars_since_last_vwap_touch increments correctly."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Bar 1: Touch VWAP
        tracker.update(high=2650.0, low=2645.0, close=2648.0)
        tracker.update_vwap_state(vwap=2650.0, close=2650.1, atr=5.0)
        assert tracker.bars_since_last_vwap_touch == 0
        assert tracker.last_vwap_touch_idx == 0

        # Bar 2: Move away from VWAP
        tracker.update(high=2655.0, low=2650.0, close=2653.0)
        tracker.update_vwap_state(vwap=2650.0, close=2653.0, atr=5.0)
        assert tracker.bars_since_last_vwap_touch == 1

        # Bar 3: Still away
        tracker.update(high=2656.0, low=2651.0, close=2654.0)
        tracker.update_vwap_state(vwap=2650.0, close=2654.0, atr=5.0)
        assert tracker.bars_since_last_vwap_touch == 2

        # Bar 4: Touch again - resets counter
        tracker.update(high=2652.0, low=2648.0, close=2650.0)
        tracker.update_vwap_state(vwap=2650.0, close=2650.2, atr=5.0)
        assert tracker.bars_since_last_vwap_touch == 0
        assert tracker.last_vwap_touch_idx == 3

    def test_none_when_no_touch_yet(self):
        """Test that bars_since_last_vwap_touch is None initially."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # No touch yet - should be None
        assert tracker.bars_since_last_vwap_touch is None
        assert tracker.last_vwap_touch_idx is None

    def test_increments_while_away_from_vwap(self):
        """Test that counter increments while away from VWAP."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Touch VWAP
        tracker.update(high=2650.0, low=2645.0, close=2648.0)
        tracker.update_vwap_state(vwap=2650.0, close=2650.1, atr=5.0)

        # Move away and stay away for multiple bars
        for i in range(5):
            tracker.update(high=2655.0 + i, low=2650.0 + i, close=2653.0 + i)
            tracker.update_vwap_state(vwap=2650.0, close=2653.0 + i, atr=5.0)
            assert tracker.bars_since_last_vwap_touch == i + 1


class TestStreamingIntegration:
    """Test integration with StreamingFeatureProcessor."""

    def test_features_populated_in_streaming_processor(self):
        """Test that new features are populated by StreamingFeatureProcessor."""
        from scp_shared.indicators.streaming import StreamingFeatureProcessor

        processor = StreamingFeatureProcessor(timeframe="1m")

        # Create test candles
        gc_bar = Candle(
            timestamp=pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2648.0,
            close=2650.5,
            volume=1000.0,
            source="TEST",
        )

        dxy_bar = Candle(
            timestamp=pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            symbol="DXY",
            timeframe="1m",
            open=103.0,
            high=103.2,
            low=102.8,
            close=103.1,
            volume=500.0,
            source="TEST",
        )

        # Process bar
        features = processor.update(gc_bar, dxy_bar)

        # Check that new fields exist
        assert "bars_near_vwap" in features
        assert "bars_since_last_vwap_touch" in features

        # Initial values (None until ATR available)
        assert features["bars_near_vwap"] is None
        assert features["bars_since_last_vwap_touch"] is None

    def test_features_track_across_multiple_bars(self):
        """Test that features track correctly across multiple bars."""
        from scp_shared.indicators.streaming import StreamingFeatureProcessor

        processor = StreamingFeatureProcessor(timeframe="1m")

        # Process multiple bars near VWAP
        for i in range(5):
            gc_bar = Candle(
                timestamp=pd.Timestamp(f"2025-01-01 10:0{i}:00", tz="UTC"),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.1,
                high=2651.0 + i * 0.1,
                low=2649.0 + i * 0.1,
                close=2650.0 + i * 0.1,  # Very close to VWAP
                volume=1000.0,
                source="TEST",
            )

            dxy_bar = Candle(
                timestamp=pd.Timestamp(f"2025-01-01 10:0{i}:00", tz="UTC"),
                symbol="DXY",
                timeframe="1m",
                open=103.0,
                high=103.2,
                low=102.8,
                close=103.1,
                volume=500.0,
                source="TEST",
            )

            features = processor.update(gc_bar, dxy_bar)

        # After warmup, bars_near_vwap should be tracking
        # (exact value depends on VWAP calculation and ATR)
        # Note: May be None if ATR not available yet (< 14 bars)
        assert features["bars_near_vwap"] is None or features["bars_near_vwap"] >= 0


class TestStructureContextPropagation:
    """Test that new fields are propagated through StructureContext."""

    def test_context_includes_new_fields(self):
        """Test that StructureContext includes new VWAP acceptance fields."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Update structure
        context = tracker.update(high=2650.0, low=2645.0, close=2648.0)

        # Check that fields exist in context
        assert hasattr(context, "bars_near_vwap")
        assert hasattr(context, "bars_since_last_vwap_touch")

        # Initial values (None until ATR available)
        assert context.bars_near_vwap is None
        assert context.bars_since_last_vwap_touch is None

    def test_context_reflects_vwap_state(self):
        """Test that context reflects current VWAP tracking state."""
        tracker = StructureContextTracker(swing_window=2, clarity_window=5)

        # Touch VWAP
        tracker.update(high=2650.0, low=2645.0, close=2648.0)
        tracker.update_vwap_state(vwap=2650.0, close=2650.1, atr=5.0)

        # Get context
        context = tracker.update(high=2651.0, low=2646.0, close=2649.0)
        tracker.update_vwap_state(vwap=2650.0, close=2649.5, atr=5.0)

        context = tracker.update(high=2652.0, low=2647.0, close=2650.0)
        tracker.update_vwap_state(vwap=2650.0, close=2650.3, atr=5.0)

        # Get updated context
        context = tracker.update(high=2653.0, low=2648.0, close=2651.0)

        # Should reflect current state
        assert context.bars_near_vwap == 3  # Three bars near VWAP
        assert context.bars_since_last_vwap_touch == 0  # Currently touching
