"""Tests for HTF structural target computation for VWAP_RECLAIM TP selection.

This module tests the functions that identify HTF price targets (range boundaries,
untouched liquidity, FVGs) and obstacles (opposing FVGs) as specified in SOP 4.3.

TDD Approach: Write tests first (RED), then implement (GREEN), then refactor.
"""

from __future__ import annotations

import pandas as pd

from scp_shared.rule_engine.htf.structure.targets import (
    compute_htf_range,
    compute_untouched_liquidity,
    find_nearest_fvg_targets,
    find_opposing_fvgs,
)


class TestComputeHTFRange:
    """Test HTF range boundary computation.
    
    HTF Range Valid When:
    - HTF structure intact (not broken/accepted through)
    - Formed after most recent BOS
    - Clear swing high and low exist
    """

    def test_bullish_range_intact_returns_high_low(self) -> None:
        """Test range detection with intact bullish structure.
        
        Setup: Price trending up with clear range boundaries
        Expected: Returns (range_high, range_low) tuple
        """
        # Create bullish range: swing low at 2000, swing high at 2100
        # bos_index=0 means consider entire dataframe
        df = pd.DataFrame({
            "high": [2010, 2030, 2050, 2070, 2100, 2090, 2080, 2070],
            "low": [2000, 2020, 2040, 2060, 2090, 2080, 2070, 2060],
            "close": [2005, 2025, 2045, 2065, 2095, 2085, 2075, 2065],
        })
        current_price = 2065.0
        bos_index = 0  # Range formed from this BOS onwards

        range_high, range_low = compute_htf_range(df, current_price, bos_index)

        assert range_high == 2100.0  # Highest high since BOS
        assert range_low == 2000.0   # Lowest low since BOS

    def test_bearish_range_intact_returns_high_low(self) -> None:
        """Test range detection with intact bearish structure.
        
        Setup: Price trending down with clear range boundaries
        Expected: Returns (range_high, range_low) tuple
        """
        # Create bearish range: swing high at 2100, swing low at 2000
        # bos_index=0 means consider entire dataframe
        df = pd.DataFrame({
            "high": [2100, 2080, 2060, 2040, 2020, 2030, 2040, 2050],
            "low": [2090, 2070, 2050, 2030, 2000, 2020, 2030, 2040],
            "close": [2095, 2075, 2055, 2035, 2005, 2025, 2035, 2045],
        })
        current_price = 2045.0
        bos_index = 0  # Range formed from this BOS onwards

        range_high, range_low = compute_htf_range(df, current_price, bos_index)

        assert range_high == 2100.0
        assert range_low == 2000.0

    def test_range_broken_above_returns_none_for_high(self) -> None:
        """Test range invalidation when upper boundary broken.
        
        Setup: Price broke above prior range high with acceptance (close > max high)
        Expected: Returns (None, range_low) - high invalidated
        """
        # Range high at 2100 (index 2), then price closes above it at the end
        # bos_index=0 to consider entire dataframe
        df = pd.DataFrame({
            "high": [2010, 2050, 2100, 2090, 2080, 2090, 2095],
            "low": [2000, 2040, 2090, 2080, 2070, 2080, 2085],
            # Last close (2105) above max high (2100)
            "close": [2005, 2045, 2095, 2085, 2075, 2085, 2105],
        })
        current_price = 2105.0
        bos_index = 0  # Consider entire dataframe

        range_high, range_low = compute_htf_range(df, current_price, bos_index)

        # High is broken (last close 2105 > max high 2100)
        assert range_high is None
        assert range_low == 2000.0

    def test_range_broken_below_returns_none_for_low(self) -> None:
        """Test range invalidation when lower boundary broken.
        
        Setup: Price broke below prior range low with acceptance (close < min low)
        Expected: Returns (range_high, None) - low invalidated
        """
        # Range low at 2000 (index 4), then price closes below it at the end
        # bos_index=0 to consider entire dataframe
        df = pd.DataFrame({
            "high": [2100, 2080, 2060, 2040, 2020, 2010, 2005],
            "low": [2090, 2070, 2050, 2030, 2000, 2005, 2002],
            # Last close (1995) below min low (2000)
            "close": [2095, 2075, 2055, 2035, 2005, 2002, 1995],
        })
        current_price = 1995.0
        bos_index = 0  # Consider entire dataframe

        range_high, range_low = compute_htf_range(df, current_price, bos_index)

        assert range_high == 2100.0
        # Low is broken (last close 1995 < min low 2000)
        assert range_low is None

    def test_range_scoped_to_post_bos(self) -> None:
        """Test range calculation scoped to bars after BOS.
        
        Setup: Data before and after BOS index
        Expected: Only considers bars after BOS index
        """
        # BOS at index 3, range should only consider bars 4+
        df = pd.DataFrame({
            "high": [1900, 1950, 2200, 2050, 2100, 2090, 2080],  # 2200 pre-BOS
            "low": [1890, 1940, 2190, 2040, 2090, 2080, 2070],
            "close": [1895, 1945, 2195, 2045, 2095, 2085, 2075],
        })
        current_price = 2075.0
        bos_index = 3  # BOS at index 3

        range_high, range_low = compute_htf_range(df, current_price, bos_index)

        # Should NOT include 2200 (index 2, before BOS)
        assert range_high == 2100.0  # Max after BOS (index 4)
        assert range_low == 2040.0   # Min after BOS (index 3)

    def test_no_swings_returns_none_none(self) -> None:
        """Test behavior with insufficient data for range detection.
        
        Setup: Empty DataFrame or single bar
        Expected: Returns (None, None)
        """
        df = pd.DataFrame({
            "high": [2050],
            "low": [2040],
            "close": [2045],
        })
        current_price = 2045.0
        bos_index = None

        range_high, range_low = compute_htf_range(df, current_price, bos_index)

        assert range_high is None
        assert range_low is None

    def test_no_bos_uses_entire_dataframe(self) -> None:
        """Test range calculation when no BOS specified.
        
        Setup: bos_index is None
        Expected: Considers entire DataFrame for range
        """
        df = pd.DataFrame({
            "high": [2010, 2030, 2100, 2070, 2060],
            "low": [2000, 2020, 2090, 2060, 2050],
            "close": [2005, 2025, 2095, 2065, 2055],
        })
        current_price = 2055.0
        bos_index = None

        range_high, range_low = compute_htf_range(df, current_price, bos_index)

        assert range_high == 2100.0
        assert range_low == 2000.0

    def test_wick_touch_vs_body_acceptance(self) -> None:
        """Test that wicks touching boundary don't invalidate, but closes do.
        
        Setup: Wick touches above max high but closes inside
        Expected: Range high still valid (wick doesn't count as acceptance)
        """
        # Max high at 2100 (index 2), last bar wicks to 2105 but closes at 2095
        # bos_index=0 to consider entire dataframe
        df = pd.DataFrame({
            "high": [2010, 2050, 2100, 2090, 2105],  # Last bar wicks above max
            "low": [2000, 2040, 2090, 2080, 2090],
            "close": [2005, 2045, 2095, 2085, 2095],  # Close inside range
        })
        current_price = 2095.0
        bos_index = 0  # Consider entire dataframe

        range_high, range_low = compute_htf_range(df, current_price, bos_index)

        # Wick touch shouldn't invalidate - max high is 2105 (last bar's wick)
        # No subsequent bar closes above 2105, so range_high = 2105
        assert range_high == 2105  # Max high in dataframe
        assert range_low == 2000.0


class TestComputeUntouchedLiquidity:
    """Test untouched liquidity identification.
    
    Untouched Liquidity Valid When:
    - No wick or body interaction with the level
    - Clearly visible swing high/low
    - Not in swept_levels set
    """

    def test_unswept_high_above_price(self) -> None:
        """Test identification of unswept swing high above current price.
        
        Setup: Clear swing high at 2100, current price at 2050
        Expected: Returns (2100.0, None)
        """
        df = pd.DataFrame({
            "high": [2010, 2050, 2100, 2090, 2080, 2070, 2060],
            "low": [2000, 2040, 2090, 2080, 2070, 2060, 2050],
            "close": [2005, 2045, 2095, 2085, 2075, 2065, 2055],
        })
        current_price = 2055.0
        swept_levels = set()  # No swept levels

        liq_high, liq_low = compute_untouched_liquidity(df, current_price, swept_levels)

        assert liq_high == 2100.0
        assert liq_low is None  # No swing low above current price

    def test_unswept_low_below_price(self) -> None:
        """Test identification of unswept swing low below current price.
        
        Setup: Clear swing low at 2000, current price at 2050
        Expected: Returns (None, 2000.0)
        """
        df = pd.DataFrame({
            "high": [2100, 2080, 2060, 2040, 2020, 2030, 2050],
            "low": [2090, 2070, 2050, 2030, 2000, 2020, 2040],
            "close": [2095, 2075, 2055, 2035, 2005, 2025, 2045],
        })
        current_price = 2045.0
        swept_levels = set()

        liq_high, liq_low = compute_untouched_liquidity(df, current_price, swept_levels)

        assert liq_high is None  # No swing high below current price
        assert liq_low == 2000.0

    def test_swept_level_excluded(self) -> None:
        """Test that swept levels are excluded from liquidity targets.
        
        Setup: Swing high at 2100 that has been swept
        Expected: Returns (None, None) - swept level ignored
        """
        df = pd.DataFrame({
            "high": [2010, 2050, 2100, 2090, 2080],
            "low": [2000, 2040, 2090, 2080, 2070],
            "close": [2005, 2045, 2095, 2085, 2075],
        })
        current_price = 2075.0
        swept_levels = {2100.0}  # This level was swept

        liq_high, liq_low = compute_untouched_liquidity(df, current_price, swept_levels)

        # Swept level should be excluded
        assert liq_high is None
        assert liq_low is None

    def test_no_valid_levels_returns_none(self) -> None:
        """Test behavior when no valid untouched liquidity exists.
        
        Setup: All swing levels have been swept
        Expected: Returns (None, None)
        """
        df = pd.DataFrame({
            "high": [2010, 2050, 2100],
            "low": [2000, 2040, 2090],
            "close": [2005, 2045, 2095],
        })
        current_price = 2095.0
        swept_levels = {2100.0, 2050.0, 2010.0}  # All swept

        liq_high, liq_low = compute_untouched_liquidity(df, current_price, swept_levels)

        assert liq_high is None
        assert liq_low is None

    def test_returns_nearest_valid_level(self) -> None:
        """Test that function returns nearest valid level, not furthest.
        
        Setup: Multiple swing highs, one swept
        Expected: Returns nearest unswept level
        """
        df = pd.DataFrame({
            "high": [2010, 2050, 2100, 2080, 2070, 2060, 2120, 2110],
            "low": [2000, 2040, 2090, 2070, 2060, 2050, 2110, 2100],
            "close": [2005, 2045, 2095, 2075, 2065, 2055, 2115, 2105],
        })
        current_price = 2105.0
        swept_levels = {2100.0}  # First high swept

        liq_high, liq_low = compute_untouched_liquidity(df, current_price, swept_levels)

        # Should return 2120 (next valid high), not 2050 or lower
        assert liq_high == 2120.0


class TestFindNearestFVGTargets:
    """Test nearest FVG target identification for directional trades.
    
    FVG Valid When:
    - FVG is in trade direction
    - FVG is not fully filled
    - HTF structure supports continuation
    """

    def test_nearest_bullish_fvg_above(self) -> None:
        """Test finding nearest bullish FVG above current price for longs.
        
        Setup: Bullish FVG at 2100-2110, current price at 2050
        Expected: Returns (2110.0, 2100.0) - FVG boundaries
        """
        # Create FVG DataFrame (structure from detect_fvg output)
        fvg_df = pd.DataFrame({
            "fvg_index": [5, 8],
            "fvg_type": ["bullish", "bullish"],
            "fvg_high": [2110.0, 2150.0],
            "fvg_low": [2100.0, 2140.0],
            "filled": [False, False],
        })
        current_price = 2050.0
        direction = "long"

        fvg_high, fvg_low = find_nearest_fvg_targets(fvg_df, current_price, direction)

        # Should return nearest bullish FVG above price
        assert fvg_high == 2110.0
        assert fvg_low == 2100.0

    def test_nearest_bearish_fvg_below(self) -> None:
        """Test finding nearest bearish FVG below current price for shorts.
        
        Setup: Bearish FVG at 2000-1990, current price at 2050
        Expected: Returns (2000.0, 1990.0) - FVG boundaries
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [3, 6],
            "fvg_type": ["bearish", "bearish"],
            "fvg_high": [2000.0, 1950.0],
            "fvg_low": [1990.0, 1940.0],
            "filled": [False, False],
        })
        current_price = 2050.0
        direction = "short"

        fvg_high, fvg_low = find_nearest_fvg_targets(fvg_df, current_price, direction)

        # Should return nearest bearish FVG below price
        assert fvg_high == 2000.0
        assert fvg_low == 1990.0

    def test_filled_fvg_excluded(self) -> None:
        """Test that filled FVGs are excluded from targets.
        
        Setup: Nearest FVG is filled, next one is unfilled
        Expected: Returns unfilled FVG, skips filled one
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [5, 8],
            "fvg_type": ["bullish", "bullish"],
            "fvg_high": [2110.0, 2150.0],
            "fvg_low": [2100.0, 2140.0],
            "filled": [True, False],  # First is filled
        })
        current_price = 2050.0
        direction = "long"

        fvg_high, fvg_low = find_nearest_fvg_targets(fvg_df, current_price, direction)

        # Should skip filled FVG and return next valid one
        assert fvg_high == 2150.0
        assert fvg_low == 2140.0

    def test_no_fvgs_returns_none(self) -> None:
        """Test behavior when no FVGs exist in trade direction.
        
        Setup: Empty FVG DataFrame or all filled
        Expected: Returns (None, None)
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [],
            "fvg_type": [],
            "fvg_high": [],
            "fvg_low": [],
            "filled": [],
        })
        current_price = 2050.0
        direction = "long"

        fvg_high, fvg_low = find_nearest_fvg_targets(fvg_df, current_price, direction)

        assert fvg_high is None
        assert fvg_low is None

    def test_wrong_direction_fvg_ignored(self) -> None:
        """Test that FVGs in wrong direction are ignored.
        
        Setup: Only bearish FVGs exist, but direction is long
        Expected: Returns (None, None)
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [5],
            "fvg_type": ["bearish"],
            "fvg_high": [2110.0],
            "fvg_low": [2100.0],
            "filled": [False],
        })
        current_price = 2050.0
        direction = "long"  # Looking for bullish FVGs

        fvg_high, fvg_low = find_nearest_fvg_targets(fvg_df, current_price, direction)

        assert fvg_high is None
        assert fvg_low is None


class TestFindOpposingFVGs:
    """Test opposing FVG detection for TP path validation.
    
    Opposing FVG Blocks TP When:
    - Located between entry and TP
    - FVG type opposes trade direction
    - FVG is unfilled
    """

    def test_bearish_fvg_blocks_long_tp(self) -> None:
        """Test detection of bearish FVG blocking long TP.
        
        Setup: Bearish FVG at 2080-2070 between entry (2050) and TP (2100)
        Expected: Returns dict with opposing_fvg_high/low populated
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [5],
            "fvg_type": ["bearish"],
            "fvg_high": [2080.0],
            "fvg_low": [2070.0],
            "filled": [False],
        })
        current_price = 2050.0
        tp_price = 2100.0
        direction = "long"

        result = find_opposing_fvgs(fvg_df, current_price, tp_price, direction)

        # Should detect bearish FVG blocking long path
        assert result["opposing_fvg_high"] == 2080.0
        assert result["opposing_fvg_low"] == 2070.0
        assert result["opposing_fvg_bullish_high"] is None
        assert result["opposing_fvg_bullish_low"] is None

    def test_bullish_fvg_blocks_short_tp(self) -> None:
        """Test detection of bullish FVG blocking short TP.
        
        Setup: Bullish FVG at 2030-2040 between entry (2050) and TP (2000)
        Expected: Returns dict with opposing_fvg_bullish_high/low populated
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [5],
            "fvg_type": ["bullish"],
            "fvg_high": [2040.0],
            "fvg_low": [2030.0],
            "filled": [False],
        })
        current_price = 2050.0
        tp_price = 2000.0
        direction = "short"

        result = find_opposing_fvgs(fvg_df, current_price, tp_price, direction)

        # Should detect bullish FVG blocking short path
        assert result["opposing_fvg_bullish_high"] == 2040.0
        assert result["opposing_fvg_bullish_low"] == 2030.0
        assert result["opposing_fvg_high"] is None
        assert result["opposing_fvg_low"] is None

    def test_fvg_beyond_tp_not_blocking(self) -> None:
        """Test that FVGs beyond TP don't block (not in path).
        
        Setup: Bearish FVG at 2110-2120, TP at 2100 (FVG is beyond)
        Expected: Returns all None (no blocking FVG)
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [5],
            "fvg_type": ["bearish"],
            "fvg_high": [2120.0],
            "fvg_low": [2110.0],
            "filled": [False],
        })
        current_price = 2050.0
        tp_price = 2100.0
        direction = "long"

        result = find_opposing_fvgs(fvg_df, current_price, tp_price, direction)

        # FVG beyond TP shouldn't block
        assert result["opposing_fvg_high"] is None
        assert result["opposing_fvg_low"] is None

    def test_no_opposing_fvg_returns_none(self) -> None:
        """Test behavior when no opposing FVG exists in path.
        
        Setup: No FVGs or only same-direction FVGs
        Expected: Returns dict with all None values
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [5],
            "fvg_type": ["bullish"],  # Same direction as trade
            "fvg_high": [2080.0],
            "fvg_low": [2070.0],
            "filled": [False],
        })
        current_price = 2050.0
        tp_price = 2100.0
        direction = "long"  # Same direction as FVG

        result = find_opposing_fvgs(fvg_df, current_price, tp_price, direction)

        # No opposing FVG (same direction)
        assert result["opposing_fvg_high"] is None
        assert result["opposing_fvg_low"] is None
        assert result["opposing_fvg_bullish_high"] is None
        assert result["opposing_fvg_bullish_low"] is None

    def test_filled_opposing_fvg_not_blocking(self) -> None:
        """Test that filled opposing FVGs don't block.
        
        Setup: Opposing FVG in path but already filled
        Expected: Returns None (filled FVG not an obstacle)
        """
        fvg_df = pd.DataFrame({
            "fvg_index": [5],
            "fvg_type": ["bearish"],
            "fvg_high": [2080.0],
            "fvg_low": [2070.0],
            "filled": [True],  # Already filled
        })
        current_price = 2050.0
        tp_price = 2100.0
        direction = "long"

        result = find_opposing_fvgs(fvg_df, current_price, tp_price, direction)

        # Filled FVG shouldn't block
        assert result["opposing_fvg_high"] is None
        assert result["opposing_fvg_low"] is None
