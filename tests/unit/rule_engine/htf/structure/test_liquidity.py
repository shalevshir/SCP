"""Unit tests for liquidity sweep detection.

Tests the detect_liquidity_sweeps function which identifies when price wicks
through prior swing levels but closes back inside (taking liquidity without
confirming breakout).
"""

from __future__ import annotations

import pandas as pd
import pytest

from rule_engine.htf.structure.liquidity import detect_liquidity_sweeps


class TestDetectLiquiditySweeps:
    """Test suite for liquidity sweep detection."""

    # ========================================================================
    # Core Functionality Tests
    # ========================================================================

    def test_detects_sweep_high(self):
        """Test detection of liquidity sweep high.
        
        Sweep high occurs when:
        - high > prior swing high (wick breaks level)
        - close < prior swing high (body doesn't break)
        """
        # Create uptrend with swing high at index 2, then sweep at index 4
        df = pd.DataFrame({
            'high': [100, 102, 105, 103, 107],  # Index 4: high breaks 105
            'low': [98, 99, 102, 100, 101],
            'close': [99, 101, 104, 102, 103]   # Index 4: close < 105 (sweep!)
        })
        
        swing_highs = [2]  # Swing high at 105
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Should detect sweep_high at index 4
        assert sweep_events.iloc[4] == "sweep_high"
        assert pd.isna(sweep_events.iloc[0])
        assert pd.isna(sweep_events.iloc[1])
        assert pd.isna(sweep_events.iloc[2])
        assert pd.isna(sweep_events.iloc[3])

    def test_detects_sweep_low(self):
        """Test detection of liquidity sweep low.
        
        Sweep low occurs when:
        - low < prior swing low (wick breaks level)
        - close > prior swing low (body doesn't break)
        """
        # Create downtrend with swing low at index 2, then sweep at index 4
        df = pd.DataFrame({
            'high': [100, 98, 95, 97, 99],
            'low': [98, 96, 93, 95, 91],    # Index 4: low breaks 93
            'close': [99, 97, 94, 96, 95]   # Index 4: close > 93 (sweep!)
        })
        
        swing_highs = []
        swing_lows = [2]  # Swing low at 93
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Should detect sweep_low at index 4
        assert sweep_events.iloc[4] == "sweep_low"
        assert pd.isna(sweep_events.iloc[0])
        assert pd.isna(sweep_events.iloc[1])
        assert pd.isna(sweep_events.iloc[2])
        assert pd.isna(sweep_events.iloc[3])

    def test_no_sweep_when_no_prior_swings(self):
        """Test that no sweep is detected without prior swings."""
        df = pd.DataFrame({
            'high': [100, 102, 105, 103, 107],
            'low': [98, 99, 102, 100, 101],
            'close': [99, 101, 104, 102, 103]
        })
        
        swing_highs = []
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # No sweeps should be detected
        assert sweep_events.isna().all()
        assert sweep_success.isna().all()

    def test_multiple_sweeps_detected(self):
        """Test detection of multiple sweep events in dataset."""
        df = pd.DataFrame({
            'high': [100, 105, 103, 108, 104, 102, 106, 101],
            'low': [98, 102, 100, 105, 101, 98, 103, 97],
            'close': [99, 104, 102, 106, 103, 100, 105, 99]
        })
        
        # Swing high at index 1 (105)
        # Index 3: high=108 > 105, close=106 > 105 → BOS, not sweep
        # Index 6: high=106 > 105, close=105 = 105 → equality, not sweep
        # Let's make index 3 a sweep: high breaks but close doesn't
        df.loc[3, 'close'] = 104  # Now: high=108 > 105, close=104 < 105 → sweep!
        
        swing_highs = [1]  # Swing high at 105
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Should detect sweep at index 3
        assert sweep_events.iloc[3] == "sweep_high"

    # ========================================================================
    # Success Tracking Tests
    # ========================================================================

    def test_failed_sweep_high(self):
        """Test failed sweep high (next bar closes below swept level).
        
        Failed sweep indicates reversal - price fails to follow through.
        """
        df = pd.DataFrame({
            'high': [100, 105, 103, 108, 102],  # Index 3: sweep high
            'low': [98, 102, 100, 103, 98],
            'close': [99, 104, 102, 104, 100]   # Index 3: close=104 < 105
                                                 # Index 4: close=100 < 105 → failed
        })
        
        swing_highs = [1]  # Swing high at 105
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        assert sweep_events.iloc[3] == "sweep_high"
        assert sweep_success.iloc[3] == False  # Failed - next bar didn't break through

    def test_successful_sweep_high(self):
        """Test successful sweep high (next bar closes above swept level).
        
        Successful sweep indicates breakout confirmed after initial wick.
        """
        df = pd.DataFrame({
            'high': [100, 105, 103, 108, 110],  # Index 3: sweep high
            'low': [98, 102, 100, 103, 105],
            'close': [99, 104, 102, 104, 107]   # Index 3: close=104 < 105
                                                 # Index 4: close=107 > 105 → success!
        })
        
        swing_highs = [1]  # Swing high at 105
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        assert sweep_events.iloc[3] == "sweep_high"
        assert sweep_success.iloc[3] == True  # Success - next bar broke through

    def test_failed_sweep_low(self):
        """Test failed sweep low (next bar closes above swept level).
        
        Failed sweep indicates reversal - price fails to follow through.
        """
        df = pd.DataFrame({
            'high': [100, 98, 95, 97, 99, 102],
            'low': [98, 96, 93, 95, 91, 98],   # Index 4: sweep low
            'close': [99, 97, 94, 96, 95, 101] # Index 4: close=95 > 93
                                                # Index 5: close=101 > 93 → failed
        })
        
        swing_highs = []
        swing_lows = [2]  # Swing low at 93
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        assert sweep_events.iloc[4] == "sweep_low"
        assert sweep_success.iloc[4] == False  # Failed - next bar didn't break down

    def test_successful_sweep_low(self):
        """Test successful sweep low (next bar closes below swept level).
        
        Successful sweep indicates breakdown confirmed after initial wick.
        """
        df = pd.DataFrame({
            'high': [100, 98, 95, 97, 99, 96],
            'low': [98, 96, 93, 95, 91, 90],   # Index 4: sweep low
            'close': [99, 97, 94, 96, 95, 92]  # Index 4: close=95 > 93
                                                # Index 5: close=92 < 93 → success!
        })
        
        swing_highs = []
        swing_lows = [2]  # Swing low at 93
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        assert sweep_events.iloc[4] == "sweep_low"
        assert sweep_success.iloc[4] == True  # Success - next bar broke down

    def test_last_bar_sweep_success_is_none(self):
        """Test that last bar sweep has None for success (no next bar)."""
        df = pd.DataFrame({
            'high': [100, 105, 103, 108],  # Index 3: sweep high, last bar
            'low': [98, 102, 100, 103],
            'close': [99, 104, 102, 104]   # Index 3: close=104 < 105, no next bar
        })
        
        swing_highs = [1]  # Swing high at 105
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        assert sweep_events.iloc[3] == "sweep_high"
        assert pd.isna(sweep_success.iloc[3])  # Cannot determine success yet

    # ========================================================================
    # Critical Edge Cases
    # ========================================================================

    def test_ambiguous_sweep_rejected(self):
        """Test that sweeping both high and low is rejected (ambiguous).
        
        If a candle sweeps both directions, it's likely whipsaw/chop.
        """
        df = pd.DataFrame({
            'high': [100, 105, 103, 100, 110],  # Index 4: high breaks prior high
            'low': [98, 102, 100, 95, 93],      # Index 4: low breaks prior low
            'close': [99, 104, 102, 97, 101]    # Index 4: close between both
        })
        
        swing_highs = [1]  # Swing high at 105
        swing_lows = [3]   # Swing low at 95
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Index 4 sweeps both → should be None (ambiguous)
        assert pd.isna(sweep_events.iloc[4])
        assert pd.isna(sweep_success.iloc[4])

    def test_equality_not_sweep(self):
        """Test that high/low equal to swing level does NOT trigger sweep.
        
        Strict inequality required: > and <, not >= or <=
        """
        # Test high equality
        df = pd.DataFrame({
            'high': [100, 105, 103, 105],  # Index 3: high=105, equal to swing
            'low': [98, 102, 100, 102],
            'close': [99, 104, 102, 103]   # Index 3: close < 105
        })
        
        swing_highs = [1]  # Swing high at 105
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Equality should NOT trigger sweep
        assert pd.isna(sweep_events.iloc[3])

    def test_close_breaks_is_not_sweep(self):
        """Test that when close also breaks level, it's BOS not sweep.
        
        Sweep requires wick to break but close to NOT break.
        """
        df = pd.DataFrame({
            'high': [100, 105, 103, 108],  # Index 3: high breaks
            'low': [98, 102, 100, 105],
            'close': [99, 104, 102, 107]   # Index 3: close also breaks → BOS!
        })
        
        swing_highs = [1]  # Swing high at 105
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # When close also breaks, it's not a sweep
        assert pd.isna(sweep_events.iloc[3])

    def test_empty_swing_lists(self):
        """Test handling of empty swing lists."""
        df = pd.DataFrame({
            'high': [100, 105, 103, 108],
            'low': [98, 102, 100, 103],
            'close': [99, 104, 102, 104]
        })
        
        swing_highs = []
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # No sweeps without swings
        assert sweep_events.isna().all()
        assert sweep_success.isna().all()

    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        df = pd.DataFrame({
            'high': [],
            'low': [],
            'close': []
        })
        
        swing_highs = []
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        assert len(sweep_events) == 0
        assert len(sweep_success) == 0

    # ========================================================================
    # Validation Tests
    # ========================================================================

    def test_missing_high_column_raises(self):
        """Test that missing 'high' column raises ValueError."""
        df = pd.DataFrame({
            'low': [98, 96, 93],
            'close': [99, 97, 94]
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            detect_liquidity_sweeps(df, [], [])

    def test_missing_low_column_raises(self):
        """Test that missing 'low' column raises ValueError."""
        df = pd.DataFrame({
            'high': [100, 105, 103],
            'close': [99, 104, 102]
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            detect_liquidity_sweeps(df, [], [])

    def test_missing_close_column_raises(self):
        """Test that missing 'close' column raises ValueError."""
        df = pd.DataFrame({
            'high': [100, 105, 103],
            'low': [98, 102, 100]
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            detect_liquidity_sweeps(df, [], [])

    def test_invalid_swing_highs_type_raises(self):
        """Test that non-list swing_highs raises ValueError."""
        df = pd.DataFrame({
            'high': [100, 105],
            'low': [98, 102],
            'close': [99, 104]
        })
        
        with pytest.raises(ValueError, match="must be lists"):
            detect_liquidity_sweeps(df, "not a list", [])

    def test_invalid_swing_lows_type_raises(self):
        """Test that non-list swing_lows raises ValueError."""
        df = pd.DataFrame({
            'high': [100, 105],
            'low': [98, 102],
            'close': [99, 104]
        })
        
        with pytest.raises(ValueError, match="must be lists"):
            detect_liquidity_sweeps(df, [], {"not": "a list"})

    def test_uses_most_recent_swing_only(self):
        """Test that only most recent swing is checked, not all prior swings.
        
        Important: We should check only the most recent swing high/low
        before the current bar, not all historical swings.
        """
        df = pd.DataFrame({
            'high': [100, 105, 103, 110, 108, 113],  # Multiple swing highs
            'low': [98, 102, 100, 107, 105, 110],
            'close': [99, 104, 102, 109, 107, 112]
        })
        
        # Two swing highs: 105 at index 1, 110 at index 3
        swing_highs = [1, 3]
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Index 4: high=108 < 110 (most recent), so no sweep
        # (Even though 108 > 105, we only check most recent swing at 110)
        assert pd.isna(sweep_events.iloc[4])
        
        # Index 5: high=113 > 110 (most recent), close=112 > 110, so BOS not sweep
        assert pd.isna(sweep_events.iloc[5])

    def test_prior_swings_only(self):
        """Test that only swings BEFORE current bar are considered.
        
        Swing at same index or after should not affect current bar.
        """
        df = pd.DataFrame({
            'high': [100, 105, 103, 108],
            'low': [98, 102, 100, 103],
            'close': [99, 104, 102, 104]
        })
        
        # Swing high at index 3 (same as potential sweep bar)
        swing_highs = [3]
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Index 3: no prior swings, so no sweep
        assert pd.isna(sweep_events.iloc[3])

    # ========================================================================
    # Integration Tests
    # ========================================================================

    def test_integration_with_detect_swings(self):
        """Test integration with real swing detection output."""
        from rule_engine.htf.structure.swings import detect_swings
        
        df = pd.DataFrame({
            'high': [100, 102, 105, 103, 101, 99, 97, 95, 93, 91, 98, 103, 108, 104],
            'low': [98, 99, 102, 100, 98, 96, 94, 92, 90, 88, 95, 100, 105, 101],
            'close': [99, 101, 104, 102, 100, 98, 96, 94, 92, 90, 97, 102, 106, 103]
        })
        
        # Detect swings with lookback=2
        swing_highs, swing_lows = detect_swings(df, lookback=2)
        
        # Now modify last bar to create a sweep
        df.loc[13, 'high'] = 110  # Breaks prior swing high
        df.loc[13, 'close'] = 103  # But close doesn't break → sweep!
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Should detect some structure
        assert isinstance(sweep_events, pd.Series)
        assert isinstance(sweep_success, pd.Series)
        assert len(sweep_events) == len(df)

    def test_custom_dataframe_index(self):
        """Test that function works with custom DataFrame index."""
        df = pd.DataFrame({
            'high': [100, 105, 103, 108],
            'low': [98, 102, 100, 103],
            'close': [99, 104, 102, 104]
        }, index=[10, 20, 30, 40])  # Custom index
        
        swing_highs = [1]  # Index position, not label
        swing_lows = []
        
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Result should have same index as input
        assert list(sweep_events.index) == [10, 20, 30, 40]
        assert list(sweep_success.index) == [10, 20, 30, 40]

    def test_large_dataset_efficiency(self):
        """Test efficiency with large dataset (1000+ bars)."""
        import numpy as np
        
        # Create large dataset
        n = 1000
        df = pd.DataFrame({
            'high': np.random.uniform(100, 110, n),
            'low': np.random.uniform(90, 100, n),
            'close': np.random.uniform(95, 105, n)
        })
        
        swing_highs = [10, 50, 100, 200, 500]
        swing_lows = [25, 75, 150, 300, 600]
        
        # Should complete without error
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        assert len(sweep_events) == n
        assert len(sweep_success) == n

    def test_complementary_to_bos(self):
        """Test that sweep and BOS are mutually exclusive conditions.
        
        When close breaks level → BOS
        When wick breaks but close doesn't → Sweep
        These conditions should never overlap.
        """
        from rule_engine.htf.structure.bos import detect_bos
        
        df = pd.DataFrame({
            'high': [100, 105, 103, 108, 106, 110],
            'low': [98, 102, 100, 103, 101, 105],
            'close': [99, 104, 102, 107, 103, 109]  # Index 3: BOS, Index 4: maybe sweep
        })
        
        # Modify index 4 to be a sweep
        df.loc[4, 'high'] = 108  # Breaks prior swing high at 105
        df.loc[4, 'close'] = 103  # Close doesn't break → sweep
        
        swing_highs = [1]  # Swing high at 105
        swing_lows = []
        
        bos = detect_bos(df, swing_highs, swing_lows)
        sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
        
        # Index 3: BOS (close=107 > 105)
        assert bos.iloc[3] == "bullish_bos"
        assert pd.isna(sweep_events.iloc[3])
        
        # Index 4: Sweep (high=108 > 105, close=103 < 105)
        assert pd.isna(bos.iloc[4])
        assert sweep_events.iloc[4] == "sweep_high"

