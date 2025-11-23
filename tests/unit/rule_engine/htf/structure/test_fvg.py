"""Unit tests for Fair Value Gap (FVG) detection.

Tests the detect_fvg and check_fvg_filled functions which identify 3-candle
price imbalances indicating institutional order flow and potential
support/resistance zones.
"""

from __future__ import annotations

import pandas as pd
import pytest

from rule_engine.htf.structure.fvg import check_fvg_filled, detect_fvg


class TestDetectFVG:
    """Test suite for FVG detection."""

    # ========================================================================
    # Core Detection Tests
    # ========================================================================

    def test_detects_bullish_fvg(self):
        """Test detection of bullish FVG (gap up).
        
        Bullish FVG occurs when:
        - candle_1.high < candle_3.low (gap exists)
        - candle_2.high < candle_3.low (candle 2 doesn't fill)
        - candle_2.low > candle_1.high (candle 2 doesn't fill)
        """
        df = pd.DataFrame({
            'high': [100, 101, 105, 107],    # Candle 1: 100, Candle 3: 105
            'low': [98, 100.5, 103, 105]      # Gap: 100 to 103
        })
        
        fvg_df = detect_fvg(df)
        
        assert len(fvg_df) == 1
        assert fvg_df.iloc[0]['fvg_index'] == 2
        assert fvg_df.iloc[0]['fvg_type'] == 'bullish'
        assert fvg_df.iloc[0]['fvg_high'] == 103  # candle_3.low
        assert fvg_df.iloc[0]['fvg_low'] == 100   # candle_1.high
        assert fvg_df.iloc[0]['filled'] == False
        assert pd.isna(fvg_df.iloc[0]['fill_index'])

    def test_detects_bearish_fvg(self):
        """Test detection of bearish FVG (gap down).
        
        Bearish FVG occurs when:
        - candle_1.low > candle_3.high (gap exists)
        - candle_2.low > candle_3.high (candle 2 doesn't fill)
        - candle_2.high < candle_1.low (candle 2 doesn't fill)
        """
        df = pd.DataFrame({
            'high': [102, 99.5, 97, 96],      # Gap: 97 to 100
            'low': [100, 97.5, 95, 94]        # Candle 1: 100, Candle 3: 97
        })
        
        fvg_df = detect_fvg(df)
        
        assert len(fvg_df) == 1
        assert fvg_df.iloc[0]['fvg_index'] == 2
        assert fvg_df.iloc[0]['fvg_type'] == 'bearish'
        assert fvg_df.iloc[0]['fvg_high'] == 100  # candle_1.low
        assert fvg_df.iloc[0]['fvg_low'] == 97    # candle_3.high
        assert fvg_df.iloc[0]['filled'] == False
        assert pd.isna(fvg_df.iloc[0]['fill_index'])

    def test_no_fvg_when_candle_2_fills_gap(self):
        """Test that no FVG is detected when candle 2 overlaps the gap."""
        # Bullish case - candle 2 enters the gap
        df = pd.DataFrame({
            'high': [100, 103, 105],   # Candle 2 high enters the gap
            'low': [98, 100, 103]      # Would be gap 100-103, but candle 2 fills it
        })
        
        fvg_df = detect_fvg(df)
        assert len(fvg_df) == 0

    def test_multiple_fvgs_detected(self):
        """Test detection of multiple FVGs in dataset."""
        df = pd.DataFrame({
            'high': [100, 101, 105, 107, 108, 107, 106],
            'low': [98, 100.5, 103, 105, 105.5, 104, 103]
        })
        
        fvg_df = detect_fvg(df)
        
        # Should detect at least one FVG at index 2
        assert len(fvg_df) >= 1
        assert any(fvg_df['fvg_type'] == 'bullish')

    def test_minimum_3_candles_required(self):
        """Test that less than 3 candles returns empty DataFrame."""
        # 2 candles
        df = pd.DataFrame({
            'high': [100, 105],
            'low': [98, 103]
        })
        
        fvg_df = detect_fvg(df)
        
        assert len(fvg_df) == 0
        assert list(fvg_df.columns) == ['fvg_index', 'fvg_type', 'fvg_high', 'fvg_low', 'filled', 'fill_index']

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_exact_equality_no_fvg(self):
        """Test that exact equality at boundary does NOT create FVG.
        
        Strict inequality required: candle_1.high < candle_3.low
        """
        df = pd.DataFrame({
            'high': [100, 101, 105],
            'low': [98, 100, 100]  # candle_3.low == candle_1.high (equality)
        })
        
        fvg_df = detect_fvg(df)
        assert len(fvg_df) == 0

    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        df = pd.DataFrame({
            'high': [],
            'low': []
        })
        
        fvg_df = detect_fvg(df)
        
        assert len(fvg_df) == 0
        assert list(fvg_df.columns) == ['fvg_index', 'fvg_type', 'fvg_high', 'fvg_low', 'filled', 'fill_index']

    def test_two_candles_only(self):
        """Test that exactly 2 candles returns empty result."""
        df = pd.DataFrame({
            'high': [100, 105],
            'low': [98, 103]
        })
        
        fvg_df = detect_fvg(df)
        assert len(fvg_df) == 0

    def test_missing_high_column_raises(self):
        """Test that missing 'high' column raises ValueError."""
        df = pd.DataFrame({
            'low': [98, 100, 103]
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            detect_fvg(df)

    def test_missing_low_column_raises(self):
        """Test that missing 'low' column raises ValueError."""
        df = pd.DataFrame({
            'high': [100, 101, 105]
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            detect_fvg(df)

    def test_custom_dataframe_index(self):
        """Test that function works with custom DataFrame index."""
        df = pd.DataFrame({
            'high': [100, 101, 105, 107],
            'low': [98, 100.5, 103, 105]
        }, index=[10, 20, 30, 40])
        
        fvg_df = detect_fvg(df)
        
        assert len(fvg_df) == 1
        # fvg_index should be the positional index (2), not the label (30)
        assert fvg_df.iloc[0]['fvg_index'] == 2

    def test_all_increasing_no_gaps(self):
        """Test continuous uptrend with no gaps produces no FVGs."""
        df = pd.DataFrame({
            'high': [100, 102, 104, 106, 108],
            'low': [99, 100, 102, 104, 106]  # Overlapping candles, no gaps
        })
        
        fvg_df = detect_fvg(df)
        assert len(fvg_df) == 0

    def test_all_decreasing_no_gaps(self):
        """Test continuous downtrend with no gaps produces no FVGs."""
        df = pd.DataFrame({
            'high': [108, 106, 104, 102, 100],
            'low': [106, 104, 102, 100, 98]  # Overlapping candles, no gaps
        })
        
        fvg_df = detect_fvg(df)
        assert len(fvg_df) == 0

    # ========================================================================
    # Bullish FVG Edge Cases
    # ========================================================================

    def test_bullish_fvg_candle_2_low_touches_candle_1_high(self):
        """Test that candle 2 low touching candle 1 high prevents FVG."""
        df = pd.DataFrame({
            'high': [100, 101, 105],
            'low': [98, 100, 103]  # candle_2.low == candle_1.high (equality)
        })
        
        fvg_df = detect_fvg(df)
        # Should not detect FVG due to equality (not strict >)
        assert len(fvg_df) == 0

    def test_bullish_fvg_candle_2_high_touches_candle_3_low(self):
        """Test that candle 2 high touching candle 3 low prevents FVG."""
        df = pd.DataFrame({
            'high': [100, 103, 105],  # candle_2.high == candle_3.low (equality)
            'low': [98, 100.5, 103]
        })
        
        fvg_df = detect_fvg(df)
        # Should not detect FVG due to equality (not strict <)
        assert len(fvg_df) == 0

    # ========================================================================
    # Bearish FVG Edge Cases
    # ========================================================================

    def test_bearish_fvg_candle_2_high_touches_candle_1_low(self):
        """Test that candle 2 high touching candle 1 low prevents FVG."""
        df = pd.DataFrame({
            'high': [102, 100, 98],  # candle_2.high == candle_1.low (equality)
            'low': [100, 98, 95]
        })
        
        fvg_df = detect_fvg(df)
        # Should not detect FVG due to equality (not strict <)
        assert len(fvg_df) == 0

    def test_bearish_fvg_candle_2_low_touches_candle_3_high(self):
        """Test that candle 2 low touching candle 3 high prevents FVG."""
        df = pd.DataFrame({
            'high': [102, 99.5, 98],
            'low': [100, 98, 95]  # candle_2.low == candle_3.high (equality)
        })
        
        fvg_df = detect_fvg(df)
        # Should not detect FVG due to equality (not strict >)
        assert len(fvg_df) == 0

    # ========================================================================
    # Integration Tests
    # ========================================================================

    def test_integration_with_detect_swings(self):
        """Test that FVGs can be detected near swing points."""
        from rule_engine.htf.structure.swings import detect_swings
        
        df = pd.DataFrame({
            'high': [100, 102, 105, 103, 101, 99, 97, 95, 98, 103],
            'low': [98, 99, 102, 100, 98, 96, 94, 92, 95, 100]
        })
        
        # Detect swings
        swing_highs, swing_lows = detect_swings(df, lookback=2)
        
        # Detect FVGs
        fvg_df = detect_fvg(df)
        
        # Should work without errors
        assert isinstance(fvg_df, pd.DataFrame)
        assert len(fvg_df.columns) == 6

    def test_integration_with_bos(self):
        """Test that FVGs can coexist with BOS detection."""
        from rule_engine.htf.structure.bos import detect_bos
        from rule_engine.htf.structure.swings import detect_swings
        
        df = pd.DataFrame({
            'high': [100, 102, 105, 103, 108, 110],
            'low': [98, 99, 102, 100, 105, 107],
            'close': [99, 101, 104, 102, 107, 109]
        })
        
        swing_highs, swing_lows = detect_swings(df, lookback=1)
        bos = detect_bos(df, swing_highs, swing_lows)
        fvg_df = detect_fvg(df)
        
        # Should work without errors
        assert isinstance(fvg_df, pd.DataFrame)
        assert isinstance(bos, pd.Series)

    def test_large_dataset(self):
        """Test efficiency with large dataset (1000+ candles)."""
        import numpy as np
        
        # Create large dataset with some gaps
        n = 1000
        highs = []
        lows = []
        
        for i in range(n):
            if i % 100 == 50:  # Introduce gaps periodically
                highs.append(highs[-1] + 5 if highs else 100)
                lows.append(lows[-1] + 3 if lows else 98)
            else:
                highs.append((highs[-1] + np.random.uniform(0, 1)) if highs else 100)
                lows.append((lows[-1] + np.random.uniform(0, 1)) if lows else 98)
        
        df = pd.DataFrame({
            'high': highs,
            'low': lows
        })
        
        fvg_df = detect_fvg(df)
        
        # Should complete without error
        assert isinstance(fvg_df, pd.DataFrame)
        assert len(fvg_df) >= 0


class TestCheckFVGFilled:
    """Test suite for FVG fill tracking."""

    def test_bullish_fvg_filled(self):
        """Test that bullish FVG is marked as filled when price returns."""
        df = pd.DataFrame({
            'high': [100, 101, 105, 107, 106, 102, 104],
            'low': [98, 100.5, 103, 105, 104, 99, 102]  # Index 5: low=99 < 100 (filled!)
        })
        
        fvg_df = detect_fvg(df)
        assert len(fvg_df) == 1
        
        fvg_df = check_fvg_filled(df, fvg_df)
        
        assert fvg_df.iloc[0]['filled'] == True
        assert fvg_df.iloc[0]['fill_index'] == 5

    def test_bearish_fvg_filled(self):
        """Test that bearish FVG is marked as filled when price returns."""
        df = pd.DataFrame({
            'high': [102, 99.5, 97, 96, 97, 101, 99],
            'low': [100, 97.5, 95, 94, 95, 99, 97]  # Index 5: high=101 > 100 (filled!)
        })
        
        fvg_df = detect_fvg(df)
        assert len(fvg_df) == 1
        
        fvg_df = check_fvg_filled(df, fvg_df)
        
        assert fvg_df.iloc[0]['filled'] == True
        assert fvg_df.iloc[0]['fill_index'] == 5

    def test_fvg_remains_unfilled(self):
        """Test that FVG remains unfilled when price doesn't return."""
        df = pd.DataFrame({
            'high': [100, 101, 105, 107, 110, 112],
            'low': [98, 100.5, 103, 105, 108, 110]
        })
        
        fvg_df = detect_fvg(df)
        assert len(fvg_df) == 1
        
        fvg_df = check_fvg_filled(df, fvg_df)
        
        assert fvg_df.iloc[0]['filled'] == False
        assert pd.isna(fvg_df.iloc[0]['fill_index'])

    def test_partial_fill_counts_as_filled(self):
        """Test that touching the gap boundary counts as filled."""
        df = pd.DataFrame({
            'high': [100, 101, 105, 107, 104],
            'low': [98, 100.5, 103, 105, 100]  # Index 4: low=100 (touches boundary)
        })
        
        fvg_df = detect_fvg(df)
        fvg_df = check_fvg_filled(df, fvg_df)
        
        # Should be filled (low <= fvg_low)
        assert fvg_df.iloc[0]['filled'] == True
        assert fvg_df.iloc[0]['fill_index'] == 4

    def test_first_fill_recorded(self):
        """Test that first fill is recorded, not subsequent touches."""
        df = pd.DataFrame({
            'high': [100, 101, 105, 107, 102, 103, 102],
            'low': [98, 100.5, 103, 105, 99, 101, 99]  # Fills at index 4 and 6
        })
        
        fvg_df = detect_fvg(df)
        fvg_df = check_fvg_filled(df, fvg_df)
        
        # Should record first fill only
        assert fvg_df.iloc[0]['filled'] == True
        assert fvg_df.iloc[0]['fill_index'] == 4  # First fill, not 6

    def test_empty_fvg_dataframe(self):
        """Test handling of empty FVG DataFrame."""
        df = pd.DataFrame({
            'high': [100, 102, 104],
            'low': [99, 100, 102]  # Overlapping, no gaps
        })
        
        fvg_df = detect_fvg(df)  # No FVGs
        assert len(fvg_df) == 0
        
        fvg_df = check_fvg_filled(df, fvg_df)
        
        assert len(fvg_df) == 0

    def test_multiple_fvgs_fill_tracking(self):
        """Test fill tracking with multiple FVGs."""
        df = pd.DataFrame({
            'high': [100, 101, 105, 107, 108, 107, 103, 109, 110],
            'low': [98, 100.5, 103, 105, 105.5, 104, 99, 107, 108]
        })
        
        fvg_df = detect_fvg(df)
        fvg_df = check_fvg_filled(df, fvg_df)
        
        # Should track fills for all FVGs
        assert len(fvg_df) >= 1
        assert 'filled' in fvg_df.columns
        assert 'fill_index' in fvg_df.columns

    def test_no_subsequent_candles(self):
        """Test FVG at end of data (no candles to fill it)."""
        df = pd.DataFrame({
            'high': [100, 101, 105],
            'low': [98, 100.5, 103]
        })
        
        fvg_df = detect_fvg(df)
        fvg_df = check_fvg_filled(df, fvg_df)
        
        # Should remain unfilled (no data after formation)
        assert fvg_df.iloc[0]['filled'] == False
        assert pd.isna(fvg_df.iloc[0]['fill_index'])

