"""Unit tests for SL priority system (SOP Section 3.2-3.3)."""

import pytest
from scp_shared.messaging.schemas import FeaturesMessage
from bot_core_svc.signal_engine import calculate_sl_price_vwap_reclaim
from datetime import datetime, timezone


@pytest.fixture
def base_features():
    """Base features message for testing."""
    return FeaturesMessage(
        timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        vwap=2645.0,
    )


class TestSLPrioritySystem:
    """Test SL priority: Structure (HL/LH) -> Reclaim candle -> VWAP zone."""
    
    def test_priority_a_long_uses_hl_swing_low(self, base_features):
        """Priority A: Long SL uses HL swing low when available."""
        base_features.swing_hl_low = 2640.0
        base_features.reclaim_candle_low = 2642.0  # Should be ignored
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="long",
            entry_price=2650.0,
            features=base_features,
            sl_buffer_ticks=30,  # 3.0 points
            min_sl_ticks=20,  # 2.0 points
        )
        
        # SL = HL low - buffer = 2640.0 - 3.0 = 2637.0
        assert sl_price == 2637.0
    
    def test_priority_a_short_uses_lh_swing_high(self, base_features):
        """Priority A: Short SL uses LH swing high when available."""
        base_features.swing_lh_high = 2655.0
        base_features.reclaim_candle_high = 2653.0  # Should be ignored
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="short",
            entry_price=2640.0,
            features=base_features,
            sl_buffer_ticks=30,
            min_sl_ticks=20,
        )
        
        # SL = LH high + buffer = 2655.0 + 3.0 = 2658.0
        assert sl_price == 2658.0
    
    def test_priority_b_long_uses_reclaim_candle_low(self, base_features):
        """Priority B: Long SL uses reclaim candle low when no HL swing."""
        base_features.swing_hl_low = None  # No HL swing
        base_features.reclaim_candle_low = 2642.0
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="long",
            entry_price=2650.0,
            features=base_features,
            sl_buffer_ticks=30,
            min_sl_ticks=20,
        )
        
        # SL = reclaim low - buffer = 2642.0 - 3.0 = 2639.0
        assert sl_price == 2639.0
    
    def test_priority_b_short_uses_reclaim_candle_high(self, base_features):
        """Priority B: Short SL uses reclaim candle high when no LH swing."""
        base_features.swing_lh_high = None  # No LH swing
        base_features.reclaim_candle_high = 2648.0
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="short",
            entry_price=2640.0,
            features=base_features,
            sl_buffer_ticks=30,
            min_sl_ticks=20,
        )
        
        # SL = reclaim high + buffer = 2648.0 + 3.0 = 2651.0
        assert sl_price == 2651.0
    
    def test_priority_c_long_uses_vwap_zone(self, base_features):
        """Priority C: Long SL uses VWAP zone when no structure/reclaim."""
        base_features.swing_hl_low = None
        base_features.reclaim_candle_low = None
        base_features.vwap = 2645.0
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="long",
            entry_price=2650.0,
            features=base_features,
            sl_buffer_ticks=30,
            min_sl_ticks=20,
        )
        
        # SL = VWAP - buffer = 2645.0 - 3.0 = 2642.0
        assert sl_price == 2642.0
    
    def test_priority_c_short_uses_vwap_zone(self, base_features):
        """Priority C: Short SL uses VWAP zone when no structure/reclaim."""
        base_features.swing_lh_high = None
        base_features.reclaim_candle_high = None
        base_features.vwap = 2645.0
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="short",
            entry_price=2640.0,
            features=base_features,
            sl_buffer_ticks=30,
            min_sl_ticks=20,
        )
        
        # SL = VWAP + buffer = 2645.0 + 3.0 = 2648.0
        assert sl_price == 2648.0
    
    def test_minimum_distance_enforced_long(self, base_features):
        """Minimum SL distance enforced when calculated SL too close to entry."""
        # Set SL that would be too close (< 2.0 points)
        base_features.swing_hl_low = 2649.0  # Only 1.0 point from entry at 2650.0
        base_features.reclaim_candle_low = None
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="long",
            entry_price=2650.0,
            features=base_features,
            sl_buffer_ticks=10,  # Small buffer: 1.0 point
            min_sl_ticks=20,  # Minimum distance: 2.0 points
        )
        
        # SL would be 2649.0 - 1.0 = 2648.0 (only 2.0 distance)
        # But min_distance is 2.0, so SL = entry - 2.0 = 2648.0
        assert sl_price == 2648.0
    
    def test_minimum_distance_enforced_short(self, base_features):
        """Minimum SL distance enforced for short when too close."""
        # Set SL that would be too close
        base_features.swing_lh_high = 2641.0  # Only 1.0 point from entry at 2640.0
        base_features.reclaim_candle_high = None
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="short",
            entry_price=2640.0,
            features=base_features,
            sl_buffer_ticks=10,
            min_sl_ticks=20,
        )
        
        # SL would be 2641.0 + 1.0 = 2642.0 (only 2.0 distance)
        # Min_distance is 2.0, so SL = entry + 2.0 = 2642.0
        assert sl_price == 2642.0
    
    def test_fallback_when_no_valid_methods(self, base_features):
        """Fallback to minimum distance when no valid SL method available."""
        base_features.swing_hl_low = None
        base_features.reclaim_candle_low = None
        base_features.vwap = None  # No VWAP either
        
        sl_price = calculate_sl_price_vwap_reclaim(
            direction="long",
            entry_price=2650.0,
            features=base_features,
            sl_buffer_ticks=30,
            min_sl_ticks=20,
        )
        
        # Fallback: SL = entry - min_distance = 2650.0 - 2.0 = 2648.0
        assert sl_price == 2648.0
