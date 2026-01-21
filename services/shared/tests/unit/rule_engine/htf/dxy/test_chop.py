"""Unit tests for DXY chop detection.

Tests the DXY chop (ranging) detection logic which identifies wick-to-wick
behavior in the Dollar Index. When detected, HTF bias should be forced to neutral.

SOP Definition of Chop:
- Wick-to-wick behavior (large wicks relative to body)
- Price containment within a narrow range (ATR-based)
- No directional progression (no HH/HL or LL/LH sequences)
"""

from pathlib import Path

import pandas as pd
import pytest
from scp_shared.rule_engine.htf.dxy.chop import detect_dxy_chop

# Path to project root (8 levels up from services/shared/tests/unit/rule_engine/htf/dxy/ to repository root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent.parent.parent


class TestDXYChopSOPCompliance:
    """Tests for SOP-compliant chop detection.
    
    SOP requires:
    1. Wick threshold >= 1.0 (wicks at least equal to body)
    2. Range constraint (price contained within narrow range)
    3. Directional failure (no HH/HL or LL/LH progression)
    """

    def test_default_wick_threshold_is_1_0(self) -> None:
        """Test that default wick_threshold is 1.0 (SOP requirement).
        
        At threshold 1.0, wicks must be at least equal to body size
        to indicate real indecision, not just pullbacks.
        """
        import inspect
        from scp_shared.rule_engine.htf.dxy.chop import detect_dxy_chop
        
        sig = inspect.signature(detect_dxy_chop)
        default_threshold = sig.parameters["wick_threshold"].default
        
        assert default_threshold == 1.0, (
            f"Default wick_threshold should be 1.0 (SOP), got {default_threshold}"
        )

    def test_trending_with_pullback_wicks_not_chop(self) -> None:
        """Test that trending data with pullback wicks is NOT flagged as chop.
        
        This is the core SOP violation being fixed:
        - A clear uptrend with HH/HL progression
        - Large wicks from pullbacks
        - Should NOT be chop because price is making directional progress
        """
        # Clear uptrend with HH/HL: each candle makes higher high and higher low
        # But with significant wicks (pullbacks during uptrend)
        trending_with_wicks = pd.DataFrame({
            "high":  [101.0, 102.5, 104.0, 105.5, 107.0],  # HH progression
            "low":   [99.0,  100.0, 101.5, 103.0, 104.5],  # HL progression
            "open":  [100.0, 101.0, 102.5, 104.0, 105.5],
            "close": [100.5, 101.5, 103.0, 104.5, 106.0],
            # Body ~0.5, wicks ~1.5 total → ratio ~3.0 (would trigger old logic)
            # But this is NOT chop - it's a healthy uptrend with pullbacks
        })
        
        result = detect_dxy_chop(trending_with_wicks, min_chop_candles=3)
        
        # Should NOT detect chop because there's clear HH/HL progression
        assert not result.any(), (
            "Trending data with HH/HL progression should NOT be flagged as chop, "
            "even with large wicks (pullbacks are not chop)"
        )

    def test_downtrend_with_pullback_wicks_not_chop(self) -> None:
        """Test that downtrending data with pullback wicks is NOT flagged as chop."""
        # Clear downtrend with LL/LH: each candle makes lower low and lower high
        downtrend_with_wicks = pd.DataFrame({
            "high":  [107.0, 105.5, 104.0, 102.5, 101.0],  # LH progression
            "low":   [104.5, 103.0, 101.5, 100.0, 99.0],   # LL progression
            "open":  [106.0, 104.5, 103.0, 101.5, 100.0],
            "close": [105.5, 104.0, 102.5, 101.0, 99.5],
            # Body ~0.5, wicks ~1.5 total → ratio ~3.0
            # But NOT chop - healthy downtrend
        })
        
        result = detect_dxy_chop(downtrend_with_wicks, min_chop_candles=3)
        
        assert not result.any(), (
            "Downtrending data with LL/LH progression should NOT be flagged as chop"
        )

    def test_range_bound_with_wicks_is_chop(self) -> None:
        """Test that range-bound price action with wicks IS flagged as chop.
        
        True chop: overlapping highs/lows, no directional progress,
        price contained in narrow range.
        """
        # Range-bound: highs and lows overlap, no progression
        # Need enough candles for ATR calculation (14+ for reliable ATR)
        # All candles oscillate around 100, with doji-like bodies and large wicks
        range_bound_chop = pd.DataFrame({
            "high":  [100.8] * 20,  # Flat highs (no HH/LH)
            "low":   [99.2] * 20,   # Flat lows (no HL/LL)
            "open":  [100.0] * 20,
            "close": [100.0] * 20,  # Doji candles (zero body) → automatic chop candle
            # Body = 0, wicks = 1.6 total → infinite ratio
            # Price contained in narrow 1.6 point range
            # No directional progress at all
        })
        
        # Use loose range_multiplier to ensure range-bound condition passes
        result = detect_dxy_chop(range_bound_chop, min_chop_candles=3, range_multiplier=3.0)
        
        # Should detect chop: wicks + range-bound + no progression
        assert result.iloc[2:].any(), (
            "Range-bound data with doji candles and no progression should be chop"
        )

    def test_expanding_range_not_chop(self) -> None:
        """Test that expanding range (breakout) is NOT flagged as chop.
        
        Even with wicky candles, if the range is expanding (breakout),
        it's not chop - it's volatility expansion.
        """
        # Range expanding significantly - breakout, not chop
        expanding_range = pd.DataFrame({
            "high":  [101.0, 102.0, 104.0, 107.0, 111.0],  # Expanding highs
            "low":   [99.0,  98.0,  96.0,  93.0,  89.0],   # Expanding lows
            "open":  [100.0, 100.0, 100.0, 100.0, 100.0],
            "close": [100.5, 100.5, 100.5, 100.5, 100.5],
            # Large wicks but range is EXPANDING not contracting
        })
        
        result = detect_dxy_chop(expanding_range, min_chop_candles=3)
        
        assert not result.any(), (
            "Expanding range (breakout) should NOT be flagged as chop"
        )

    def test_alternating_structure_is_chop(self) -> None:
        """Test that alternating/flat structure (no progression) is chop.
        
        This is the directional failure condition:
        - Price oscillates without making sustained highs or lows
        - This indicates indecision, not trend
        """
        # Flat structure with large wicks: no HH/HL or LL/LH
        # Enough candles for ATR calculation
        alternating = pd.DataFrame({
            "high":  [101.0] * 20,  # Flat highs
            "low":   [99.0] * 20,   # Flat lows
            "open":  [100.0] * 20,
            "close": [100.1] * 20,  # Tiny bodies
            # Body = 0.1, wicks = 1.9 total → ratio = 19 (well above 1.0)
            # No directional progress
        })
        
        # Use loose range_multiplier to ensure range-bound condition passes
        result = detect_dxy_chop(alternating, min_chop_candles=3, range_multiplier=3.0)
        
        # No progression = chop
        assert result.iloc[2:].any(), (
            "Flat structure with large wicks and no progression should be chop"
        )

    def test_range_multiplier_parameter(self) -> None:
        """Test that range_multiplier parameter controls range constraint sensitivity."""
        # Moderate range data
        moderate_range = pd.DataFrame({
            "high":  [101.5, 101.5, 101.5, 101.5, 101.5],
            "low":   [99.5,  99.5,  99.5,  99.5,  99.5],
            "open":  [100.5, 100.5, 100.5, 100.5, 100.5],
            "close": [100.4, 100.4, 100.4, 100.4, 100.4],
        })
        
        # With tight range_multiplier, should detect chop
        result_tight = detect_dxy_chop(
            moderate_range, min_chop_candles=3, range_multiplier=2.0
        )
        
        # With loose range_multiplier, might not detect chop
        result_loose = detect_dxy_chop(
            moderate_range, min_chop_candles=3, range_multiplier=0.5
        )
        
        # Tight should be more likely to detect chop than loose
        assert result_tight.sum() >= result_loose.sum(), (
            "Tighter range_multiplier should detect more chop conditions"
        )


class TestDXYChopDetection:
    """Test DXY chop detection with SOP-compliant logic.
    
    SOP chop requires:
    1. Large wicks (wick_threshold >= 1.0)
    2. Range-bound price action
    3. No directional progression (no HH/HL or LL/LH)
    """

    @pytest.fixture
    def simple_chop_data(self) -> pd.DataFrame:
        """Create simple DXY data that is TRUE chop (SOP-compliant).
        
        - Large wicks relative to body
        - Flat/range-bound (no directional progress)
        - Enough candles for ATR calculation
        """
        # All candles oscillate around 100, no directional progress
        return pd.DataFrame(
            {
                "high": [101.0] * 20,   # Flat highs
                "low": [99.0] * 20,     # Flat lows
                "open": [100.0] * 20,
                "close": [100.1] * 20,  # Tiny bodies
                # Body = 0.1, Wicks = 1.9 total, ratio = 19 (well above 1.0)
                # No HH/HL or LL/LH progression
            }
        )

    @pytest.fixture
    def simple_trending_data(self) -> pd.DataFrame:
        """Create simple DXY data with trending candles (NOT chop).
        
        - Small wicks, large bodies
        - Clear HH/HL progression (uptrend)
        """
        return pd.DataFrame(
            {
                "high": [100.5, 101.5, 102.5, 103.5, 104.5],
                "low": [100.0, 101.0, 102.0, 103.0, 104.0],
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                # Body = 0.5, Wicks = 0 total, ratio = 0 (trending)
                # Clear HH/HL progression - NOT chop
            }
        )

    @pytest.fixture
    def mixed_chop_data(self) -> pd.DataFrame:
        """Create DXY data with mix of chop and non-chop candles.
        
        For SOP-compliant testing, we need:
        - Some candles that meet all chop criteria
        - Some candles that break the pattern
        """
        # Start with chop (flat), then trend (breaks pattern), then chop again
        return pd.DataFrame(
            {
                # Candles 0-1: Chop-like (but not enough consecutive)
                # Candle 2: Trending (breaks pattern)
                # Candles 3-6: Mix
                "high": [101.0, 101.0, 102.5, 101.0, 101.0, 101.0, 101.0],
                "low": [99.0, 99.0, 102.0, 99.0, 99.0, 99.0, 99.0],
                "open": [100.0, 100.0, 102.0, 100.0, 100.0, 100.0, 100.0],
                "close": [100.1, 100.1, 102.5, 100.1, 100.1, 100.1, 100.1],
                # Candle 2 is strong trending (breaks chop sequence)
            }
        )

    def test_detect_chop_basic(self, simple_chop_data: pd.DataFrame) -> None:
        """Test basic chop detection with default parameters."""
        # Use range_multiplier=3.0 to ensure range-bound condition passes
        result = detect_dxy_chop(simple_chop_data, range_multiplier=3.0)

        # Should return Series with same length
        assert isinstance(result, pd.Series)
        assert len(result) == len(simple_chop_data)

        # Should be boolean dtype
        assert result.dtype == bool

    def test_detect_chop_three_consecutive_triggers(
        self, simple_chop_data: pd.DataFrame
    ) -> None:
        """Test that 3+ consecutive chop candles trigger chop condition."""
        result = detect_dxy_chop(
            simple_chop_data, wick_threshold=1.0, min_chop_candles=3, range_multiplier=3.0
        )

        # First 2 candles should be False (need 3 consecutive)
        assert not result.iloc[0]
        assert not result.iloc[1]

        # From candle 3 onwards should be True (3+ consecutive chop)
        assert result.iloc[2], "3rd candle should trigger chop"
        assert result.iloc[3], "4th candle should be chop"
        assert result.iloc[4], "5th candle should be chop"

    def test_detect_chop_two_consecutive_not_enough(
        self, simple_chop_data: pd.DataFrame
    ) -> None:
        """Test that 2 consecutive chop candles don't trigger (need 3)."""
        # Take only first 2 candles
        data = simple_chop_data.head(2)
        result = detect_dxy_chop(data, wick_threshold=1.0, min_chop_candles=3, range_multiplier=3.0)

        # Should all be False (need 3 consecutive)
        assert not result.any()

    def test_detect_chop_single_candle_not_enough(
        self, simple_chop_data: pd.DataFrame
    ) -> None:
        """Test that single chop candle doesn't trigger."""
        # Take only first candle
        data = simple_chop_data.head(1)
        result = detect_dxy_chop(data, wick_threshold=1.0, min_chop_candles=3, range_multiplier=3.0)

        # Should be False
        assert not result.iloc[0]

    def test_detect_chop_trending_data_no_trigger(
        self, simple_trending_data: pd.DataFrame
    ) -> None:
        """Test that trending candles (HH/HL progression) don't trigger chop.
        
        Even with large wicks, trending data should NOT be flagged as chop
        because it has directional progress.
        """
        result = detect_dxy_chop(simple_trending_data, wick_threshold=0.5)

        # All should be False (trending data has HH/HL - not chop)
        assert not result.any()

    def test_detect_chop_interrupted_sequence_resets(
        self, mixed_chop_data: pd.DataFrame
    ) -> None:
        """Test that non-chop candle interrupts and resets the count."""
        result = detect_dxy_chop(
            mixed_chop_data, wick_threshold=1.0, min_chop_candles=3, range_multiplier=3.0
        )

        # Candles 0-1: chop but only 2 (not enough)
        assert not result.iloc[0]
        assert not result.iloc[1]

        # Candle 2: trending (resets count) - has large body
        assert not result.iloc[2]

        # After reset, need 3 more consecutive for chop
        # Candles 3-4: only 2 consecutive after reset
        assert not result.iloc[3]
        assert not result.iloc[4]

    def test_detect_chop_custom_threshold(self, simple_chop_data: pd.DataFrame) -> None:
        """Test chop detection with custom wick threshold."""
        # Very high threshold (only extreme wicks trigger)
        # Even with high threshold, simple_chop_data has ratio=19, so it passes
        result_high = detect_dxy_chop(simple_chop_data, wick_threshold=20.0, range_multiplier=3.0)
        assert not result_high.any()  # Ratio=19 < 20, so no candles meet threshold

        # Low threshold (all candles trigger if other conditions met)
        result_low = detect_dxy_chop(simple_chop_data, wick_threshold=1.0, range_multiplier=3.0)
        assert result_low.iloc[2:].all()  # Candles 3+ meet all conditions

    def test_detect_chop_custom_min_candles(
        self, simple_chop_data: pd.DataFrame
    ) -> None:
        """Test chop detection with custom minimum consecutive candles."""
        # Need 5 consecutive chop candles
        result = detect_dxy_chop(simple_chop_data, min_chop_candles=5, range_multiplier=3.0)

        # First 4 should be False (need 5 consecutive)
        assert not result.iloc[:4].any()

        # 5th candle should be True (5 consecutive)
        assert result.iloc[4]

    def test_detect_chop_doji_candles(self) -> None:
        """Test that doji candles (zero body) with no directional progress are chop."""
        # Doji candles in a range-bound pattern (flat highs/lows)
        doji_data = pd.DataFrame(
            {
                "high": [101.0] * 20,   # Flat highs
                "low": [99.0] * 20,     # Flat lows
                "open": [100.0] * 20,
                "close": [100.0] * 20,  # Same as open (doji)
            }
        )

        result = detect_dxy_chop(doji_data, wick_threshold=1.0, min_chop_candles=3, range_multiplier=3.0)

        # All doji should be considered chop (infinite wick ratio)
        # Third candle should trigger (3 consecutive)
        assert result.iloc[2], "Doji candles in range-bound pattern should be chop"

    def test_detect_chop_empty_dataframe(self) -> None:
        """Test chop detection with empty DataFrame."""
        empty_df = pd.DataFrame(columns=["high", "low", "open", "close"])
        result = detect_dxy_chop(empty_df)

        # Should return empty Series
        assert len(result) == 0
        assert isinstance(result, pd.Series)

    def test_detect_chop_insufficient_data(self) -> None:
        """Test chop detection with insufficient data (< min_chop_candles)."""
        small_df = pd.DataFrame(
            {
                "high": [101.0, 101.5],
                "low": [99.0, 99.5],
                "open": [100.0, 100.5],
                "close": [100.2, 100.7],
            }
        )

        result = detect_dxy_chop(small_df, min_chop_candles=3)

        # All should be False (need 3 candles, only have 2)
        assert not result.any()

    def test_detect_chop_missing_high_column(self) -> None:
        """Test that missing 'high' column raises ValueError."""
        invalid_df = pd.DataFrame(
            {
                "low": [99.0, 99.5],
                "open": [100.0, 100.5],
                "close": [100.2, 100.7],
            }
        )

        with pytest.raises(ValueError, match="Missing required column.*high"):
            detect_dxy_chop(invalid_df)

    def test_detect_chop_missing_low_column(self) -> None:
        """Test that missing 'low' column raises ValueError."""
        invalid_df = pd.DataFrame(
            {
                "high": [101.0, 101.5],
                "open": [100.0, 100.5],
                "close": [100.2, 100.7],
            }
        )

        with pytest.raises(ValueError, match="Missing required column.*low"):
            detect_dxy_chop(invalid_df)

    def test_detect_chop_missing_open_column(self) -> None:
        """Test that missing 'open' column raises ValueError."""
        invalid_df = pd.DataFrame(
            {
                "high": [101.0, 101.5],
                "low": [99.0, 99.5],
                "close": [100.2, 100.7],
            }
        )

        with pytest.raises(ValueError, match="Missing required column.*open"):
            detect_dxy_chop(invalid_df)

    def test_detect_chop_missing_close_column(self) -> None:
        """Test that missing 'close' column raises ValueError."""
        invalid_df = pd.DataFrame(
            {
                "high": [101.0, 101.5],
                "low": [99.0, 99.5],
                "open": [100.0, 100.5],
            }
        )

        with pytest.raises(ValueError, match="Missing required column.*close"):
            detect_dxy_chop(invalid_df)

    def test_detect_chop_invalid_threshold(self) -> None:
        """Test that invalid wick_threshold raises ValueError."""
        df = pd.DataFrame(
            {
                "high": [101.0],
                "low": [99.0],
                "open": [100.0],
                "close": [100.2],
            }
        )

        with pytest.raises(ValueError, match="wick_threshold must be > 0"):
            detect_dxy_chop(df, wick_threshold=0)

        with pytest.raises(ValueError, match="wick_threshold must be > 0"):
            detect_dxy_chop(df, wick_threshold=-0.5)

    def test_detect_chop_invalid_min_candles(self) -> None:
        """Test that invalid min_chop_candles raises ValueError."""
        df = pd.DataFrame(
            {
                "high": [101.0],
                "low": [99.0],
                "open": [100.0],
                "close": [100.2],
            }
        )

        with pytest.raises(ValueError, match="min_chop_candles must be >= 1"):
            detect_dxy_chop(df, min_chop_candles=0)

        with pytest.raises(ValueError, match="min_chop_candles must be >= 1"):
            detect_dxy_chop(df, min_chop_candles=-1)

    def test_detect_chop_nan_values(self) -> None:
        """Test chop detection with NaN values in data."""
        nan_data = pd.DataFrame(
            {
                "high": [101.0, float("nan"), 102.0, 102.5, 103.0],
                "low": [99.0, 99.5, 100.0, 100.5, 101.0],
                "open": [100.0, 100.5, 101.0, 101.5, 102.0],
                "close": [100.2, 100.7, 101.2, 101.7, 102.2],
            }
        )

        result = detect_dxy_chop(nan_data, wick_threshold=0.5, min_chop_candles=3)

        # Should handle NaN gracefully
        assert isinstance(result, pd.Series)
        assert len(result) == len(nan_data)

        # NaN row should not be considered chop
        assert not result.iloc[1]

    def test_detect_chop_index_preserved(self, simple_chop_data: pd.DataFrame) -> None:
        """Test that result preserves input DataFrame index."""
        # Set custom index
        simple_chop_data.index = pd.date_range(
            "2025-01-01", periods=len(simple_chop_data), freq="1H"
        )

        result = detect_dxy_chop(simple_chop_data)

        # Index should match input
        assert result.index.equals(simple_chop_data.index)

    def test_detect_chop_return_type(self, simple_chop_data: pd.DataFrame) -> None:
        """Test that result is pd.Series with bool dtype."""
        result = detect_dxy_chop(simple_chop_data)

        assert isinstance(result, pd.Series)
        assert result.dtype == bool
        assert result.name == "dxy_chop"

    def test_detect_chop_wick_ratio_calculation(self) -> None:
        """Test wick ratio calculation logic.
        
        Note: With SOP-compliant logic, a single candle won't trigger chop
        due to range/directional checks. This test verifies the wick ratio
        threshold is respected.
        """
        # Create range-bound data with known wick ratios (all same level)
        # Ratio: body=0.1, wicks=3.9, ratio=39
        high_ratio_data = pd.DataFrame(
            {
                "high": [102.0] * 20,
                "low": [98.0] * 20,
                "open": [100.0] * 20,
                "close": [100.1] * 20,
            }
        )

        # Ratio is 39, threshold 1.0, should trigger chop with range_multiplier
        result = detect_dxy_chop(
            high_ratio_data, wick_threshold=1.0, min_chop_candles=1, range_multiplier=3.0
        )
        assert result.iloc[0], "High wick ratio should trigger chop"

        # Ratio is 39, threshold 50.0, should not trigger chop
        result = detect_dxy_chop(
            high_ratio_data, wick_threshold=50.0, min_chop_candles=1, range_multiplier=3.0
        )
        assert not result.iloc[0], "Threshold above ratio should not trigger"

    def test_detect_chop_consecutive_count_accuracy(self) -> None:
        """Test accurate consecutive counting.
        
        Verifies that:
        1. First 2 candles don't trigger (need min_chop_candles=3)
        2. 3rd consecutive candle triggers chop
        3. Subsequent candles remain flagged as chop
        """
        # All flat, range-bound data - every candle should be chop
        test_data = pd.DataFrame(
            {
                "high": [101.0] * 20,
                "low": [99.0] * 20,
                "open": [100.0] * 20,
                "close": [100.1] * 20,
                # Body = 0.1, wicks = 1.9 total → ratio = 19 (well above 1.0)
                # All flat - no directional progress
            }
        )

        result = detect_dxy_chop(test_data, wick_threshold=1.0, min_chop_candles=3, range_multiplier=3.0)

        # First 2: chop conditions met but not enough consecutive
        assert not result.iloc[0], "1st candle should not trigger (need 3)"
        assert not result.iloc[1], "2nd candle should not trigger (need 3)"

        # 3rd candle onwards should trigger
        assert result.iloc[2], "3rd candle should trigger chop"
        assert result.iloc[3], "4th candle should be chop"
        assert result.iloc[4], "5th candle should be chop"
        
        # All remaining candles should be chop
        assert result.iloc[5:].all(), "All remaining candles should be chop"
