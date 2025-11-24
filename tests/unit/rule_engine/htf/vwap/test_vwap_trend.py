"""Unit tests for VWAP trend validation.

Tests the validate_vwap_trend() function which confirms trend validity
when price stays above/below VWAP for N consecutive candles.
"""

import numpy as np
import pandas as pd
import pytest

from rule_engine.htf.vwap.trend import validate_vwap_trend


class TestVWAPTrendValidation:
    """Test suite for VWAP trend confirmation logic."""

    # =========================================================================
    # Core Functionality Tests (5 tests)
    # =========================================================================

    def test_bullish_trend_confirmed(self):
        """Test that bullish trend is confirmed after N consecutive closes above VWAP."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2655, 2660, 2665],
            'vwap':  [2640, 2642, 2645, 2648, 2650]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # First 2 bars: insufficient history → False
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        
        # Bar 2 onwards: 3 consecutive closes above VWAP → True
        assert result.iloc[2] == True
        assert result.iloc[3] == True
        assert result.iloc[4] == True

    def test_bearish_trend_confirmed(self):
        """Test that bearish trend is confirmed after N consecutive closes below VWAP."""
        df = pd.DataFrame({
            'close': [2635, 2630, 2625, 2620, 2615],
            'vwap':  [2640, 2640, 2640, 2640, 2640]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # First 2 bars: insufficient history → False
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        
        # Bar 2 onwards: 3 consecutive closes below VWAP → True
        assert result.iloc[2] == True
        assert result.iloc[3] == True
        assert result.iloc[4] == True

    def test_mixed_no_confirmation(self):
        """Test that crosses within window prevent confirmation."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2640, 2655, 2660],
            'vwap':  [2642, 2642, 2642, 2642, 2642]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # All bars: price crosses VWAP at index 2 → False throughout
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        assert result.iloc[2] == False  # Cross here
        assert result.iloc[3] == False  # Within 3-bar window of cross
        assert result.iloc[4] == False  # Within 3-bar window of cross

    def test_exact_threshold_confirms(self):
        """Test that exactly min_candles consecutive triggers confirmation."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2655],  # Exactly 3 candles
            'vwap':  [2640, 2642, 2645]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # First 2 bars: insufficient history
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        
        # Bar 2: exactly 3 consecutive above → True
        assert result.iloc[2] == True

    def test_just_under_threshold_no_confirmation(self):
        """Test that min_candles-1 consecutive does not trigger confirmation."""
        df = pd.DataFrame({
            'close': [2645, 2650],  # Only 2 candles
            'vwap':  [2640, 2642]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # All bars: only 2 candles, need 3 → False
        assert result.iloc[0] == False
        assert result.iloc[1] == False

    # =========================================================================
    # Edge Cases Tests (6 tests)
    # =========================================================================

    def test_empty_dataframe(self):
        """Test that empty DataFrame returns empty Series."""
        df = pd.DataFrame({'close': [], 'vwap': []})
        
        result = validate_vwap_trend(df, min_candles=3)
        
        assert len(result) == 0
        assert isinstance(result, pd.Series)

    def test_dataframe_shorter_than_min_candles(self):
        """Test that DataFrame with fewer rows than min_candles returns all False."""
        df = pd.DataFrame({
            'close': [2645],
            'vwap':  [2640]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        assert len(result) == 1
        assert result.iloc[0] == False

    def test_min_candles_one_immediate_confirmation(self):
        """Test that min_candles=1 gives immediate confirmation."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2640, 2655],
            'vwap':  [2640, 2642, 2642, 2642]
        })
        
        result = validate_vwap_trend(df, min_candles=1)
        
        # Every bar where close != vwap should be confirmed
        assert result.iloc[0] == True   # Above VWAP → confirmed
        assert result.iloc[1] == True   # Above VWAP → confirmed
        assert result.iloc[2] == True   # Below VWAP → confirmed (bearish)
        assert result.iloc[3] == True   # Above VWAP → confirmed

    def test_invalid_min_candles_zero(self):
        """Test that min_candles=0 raises ValueError."""
        df = pd.DataFrame({
            'close': [2645, 2650],
            'vwap':  [2640, 2642]
        })
        
        with pytest.raises(ValueError, match="min_candles must be >= 1"):
            validate_vwap_trend(df, min_candles=0)

    def test_invalid_min_candles_negative(self):
        """Test that negative min_candles raises ValueError."""
        df = pd.DataFrame({
            'close': [2645, 2650],
            'vwap':  [2640, 2642]
        })
        
        with pytest.raises(ValueError, match="min_candles must be >= 1"):
            validate_vwap_trend(df, min_candles=-5)

    def test_missing_close_column(self):
        """Test that missing 'close' column raises ValueError."""
        df = pd.DataFrame({
            'vwap': [2640, 2642, 2645]
        })
        
        with pytest.raises(ValueError, match="Missing required columns.*close"):
            validate_vwap_trend(df, min_candles=3)

    def test_missing_vwap_column(self):
        """Test that missing 'vwap' column raises ValueError."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2655]
        })
        
        with pytest.raises(ValueError, match="Missing required columns.*vwap"):
            validate_vwap_trend(df, min_candles=3)

    # =========================================================================
    # NaN Handling Tests (3 tests)
    # =========================================================================

    def test_nan_in_vwap_column(self):
        """Test that NaN in VWAP column results in False for those rows."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2655, 2660, 2665],
            'vwap':  [np.nan, 2642, 2645, 2648, 2650]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # First bar has NaN VWAP, affects rolling window
        # Bars 0-2: NaN in window → False
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        assert result.iloc[2] == False
        
        # Bar 3: rolling window [1,2,3] all valid and above → True
        assert result.iloc[3] == True
        assert result.iloc[4] == True

    def test_nan_in_close_column(self):
        """Test that NaN in close column results in False for those rows."""
        df = pd.DataFrame({
            'close': [2645, np.nan, 2655, 2660, 2665],
            'vwap':  [2640, 2642, 2645, 2648, 2650]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # Bars with NaN in rolling window → False
        assert result.iloc[0] == False  # Insufficient history
        assert result.iloc[1] == False  # NaN close
        assert result.iloc[2] == False  # NaN in window
        
        # Bar 3: rolling window [1,2,3] has NaN at index 1 → False
        assert result.iloc[3] == False
        
        # Bar 4: rolling window [2,3,4] no NaN, all above VWAP → True
        assert result.iloc[4] == True

    def test_all_nan_returns_all_false(self):
        """Test that all NaN values result in all False."""
        df = pd.DataFrame({
            'close': [np.nan, np.nan, np.nan],
            'vwap':  [np.nan, np.nan, np.nan]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # All NaN → all False
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        assert result.iloc[2] == False

    # =========================================================================
    # Validation Tests (3 tests)
    # =========================================================================

    def test_configurable_min_candles_three(self):
        """Test that min_candles=3 requires 3 consecutive candles."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2655, 2660],
            'vwap':  [2640, 2642, 2645, 2648]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # First 2 bars: insufficient
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        
        # Bar 2 onwards: 3 consecutive → True
        assert result.iloc[2] == True
        assert result.iloc[3] == True

    def test_configurable_min_candles_five(self):
        """Test that min_candles=5 requires 5 consecutive candles."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2655, 2660, 2665, 2670],
            'vwap':  [2640, 2642, 2645, 2648, 2650, 2655]
        })
        
        result = validate_vwap_trend(df, min_candles=5)
        
        # First 4 bars: insufficient
        assert result.iloc[0] == False
        assert result.iloc[1] == False
        assert result.iloc[2] == False
        assert result.iloc[3] == False
        
        # Bar 4 onwards: 5 consecutive → True
        assert result.iloc[4] == True
        assert result.iloc[5] == True

    def test_index_preservation(self):
        """Test that output Series index matches input DataFrame index."""
        custom_index = pd.date_range('2025-01-01', periods=5, freq='1h')
        df = pd.DataFrame({
            'close': [2645, 2650, 2655, 2660, 2665],
            'vwap':  [2640, 2642, 2645, 2648, 2650]
        }, index=custom_index)
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # Index should match exactly
        assert result.index.equals(df.index)
        assert len(result) == len(df)

    # =========================================================================
    # Additional Scenarios (3 tests)
    # =========================================================================

    def test_trend_break_resets_confirmation(self):
        """Test that breaking trend resets confirmation requirement."""
        df = pd.DataFrame({
            'close': [2645, 2650, 2655, 2640, 2645, 2650, 2655],
            'vwap':  [2640, 2642, 2645, 2642, 2642, 2642, 2642]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # Bars 0-2: 3 consecutive above → True at bar 2
        assert result.iloc[2] == True
        
        # Bar 3: breaks below → False (cross in window)
        assert result.iloc[3] == False
        
        # Bar 4: still has cross in window → False
        assert result.iloc[4] == False
        
        # Bar 5: window [3,4,5] has cross at 3 → False
        assert result.iloc[5] == False
        
        # Bar 6: window [4,5,6] all above → True
        assert result.iloc[6] == True

    def test_equal_to_vwap_not_confirmed(self):
        """Test that close == vwap does not count as above or below."""
        df = pd.DataFrame({
            'close': [2645, 2642, 2655, 2660],
            'vwap':  [2640, 2642, 2645, 2648]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # Bar 1: close == vwap, breaks streak
        # Bar 2: window [0,1,2] has equality at index 1 → False
        assert result.iloc[2] == False
        
        # Bar 3: window [1,2,3] has equality at index 1 → False
        assert result.iloc[3] == False

    def test_alternating_bullish_bearish(self):
        """Test that alternating above/below never confirms."""
        df = pd.DataFrame({
            'close': [2645, 2640, 2645, 2640, 2645],
            'vwap':  [2642, 2642, 2642, 2642, 2642]
        })
        
        result = validate_vwap_trend(df, min_candles=3)
        
        # All bars: alternating, never 3 consecutive in same direction → all False
        for i in range(len(result)):
            assert result.iloc[i] == False

