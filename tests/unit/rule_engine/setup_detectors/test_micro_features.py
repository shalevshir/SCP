"""Tests for micro feature computations."""

import pandas as pd
import pytest

from rule_engine.setup_detectors.micro_features import (
    calculate_bars_since_pullback,
    calculate_displacement_strength,
    detect_micro_pullback,
)


class TestMicroPullbackDetection:
    """Test micro pullback structure detection."""

    def test_detect_hl_pullback_long(self):
        """Test HL pullback detection for longs."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 103],
                "low": [98, 100, 101],  # Ascending lows = HL (101 > 100)
            }
        )

        result = detect_micro_pullback(df, "long")
        assert result == "HL"

    def test_detect_lh_pullback_short(self):
        """Test LH pullback detection for shorts."""
        df = pd.DataFrame(
            {
                "high": [102, 100, 99],  # Descending highs = LH
                "low": [98, 96, 95],
            }
        )

        result = detect_micro_pullback(df, "short")
        assert result == "LH"

    def test_no_pullback_detected_long(self):
        """Test no pullback when lows are descending."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 101],
                "low": [98, 97, 96],  # Descending lows = no HL
            }
        )

        result = detect_micro_pullback(df, "long")
        assert result is None

    def test_no_pullback_detected_short(self):
        """Test no pullback when highs are ascending."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 104],  # Ascending highs = no LH
                "low": [98, 100, 102],
            }
        )

        result = detect_micro_pullback(df, "short")
        assert result is None

    def test_insufficient_data(self):
        """Test that insufficient data returns None."""
        df = pd.DataFrame(
            {
                "high": [100],
                "low": [98],
            }
        )

        result = detect_micro_pullback(df, "long")
        assert result is None


class TestDisplacementStrength:
    """Test displacement strength calculation."""

    def test_strong_displacement(self):
        """Test strong displacement candle."""
        # Body = 105 - 100 = 5, ATR = 3, ratio = 5/3 = 1.67
        displacement = calculate_displacement_strength(
            candle_open=100.0,
            candle_close=105.0,
            candle_high=105.5,
            candle_low=99.5,
            atr=3.0,
        )

        assert displacement > 1.2
        assert abs(displacement - 1.67) < 0.01

    def test_weak_displacement(self):
        """Test weak displacement candle."""
        # Body = 101 - 100 = 1, ATR = 3, ratio = 1/3 = 0.33
        displacement = calculate_displacement_strength(
            candle_open=100.0,
            candle_close=101.0,
            candle_high=102.0,
            candle_low=99.0,
            atr=3.0,
        )

        assert displacement < 1.2
        assert abs(displacement - 0.33) < 0.01

    def test_bearish_displacement(self):
        """Test bearish displacement (absolute value)."""
        # Body = abs(95 - 100) = 5, ATR = 3, ratio = 5/3 = 1.67
        displacement = calculate_displacement_strength(
            candle_open=100.0,
            candle_close=95.0,
            candle_high=101.0,
            candle_low=94.5,
            atr=3.0,
        )

        assert displacement > 1.2
        assert abs(displacement - 1.67) < 0.01

    def test_zero_atr_returns_zero(self):
        """Test that zero ATR returns 0.0."""
        displacement = calculate_displacement_strength(
            candle_open=100.0,
            candle_close=105.0,
            candle_high=105.5,
            candle_low=99.5,
            atr=0.0,
        )

        assert displacement == 0.0


class TestBarsSincePullback:
    """Test bars since pullback calculation."""

    def test_recent_pullback_long(self):
        """Test recent pullback for longs."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 103, 104],
                "low": [98, 100, 101, 102],  # HL at index 2 (2 bars ago)
            }
        )

        bars = calculate_bars_since_pullback(df, "long")
        assert bars == 1  # Most recent low (index 3) is 1 bar from pullback at index 2

    def test_recent_pullback_short(self):
        """Test recent pullback for shorts."""
        df = pd.DataFrame(
            {
                "high": [104, 102, 101, 100],  # LH at index 2 (1 bar ago)
                "low": [102, 100, 99, 98],
            }
        )

        bars = calculate_bars_since_pullback(df, "short")
        assert bars == 1

    def test_no_recent_pullback(self):
        """Test no recent pullback found."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 104, 106],
                "low": [98, 97, 96, 95],  # No HL pattern
            }
        )

        bars = calculate_bars_since_pullback(df, "long")
        assert bars is None

    def test_insufficient_data(self):
        """Test insufficient data returns None."""
        df = pd.DataFrame(
            {
                "high": [100],
                "low": [98],
            }
        )

        bars = calculate_bars_since_pullback(df, "long")
        assert bars is None




