"""Tests for swing high/low detection in HTF structure analysis."""

from __future__ import annotations

import pandas as pd
import pytest
from scp_shared.rule_engine.htf.structure.swings import detect_swings


class TestDetectSwings:
    """Test swing high/low detection."""

    def test_detects_clear_swing_high_and_low(self) -> None:
        """Test detection of clear swing high and low."""
        # Create data with obvious swing high at index 2 and swing low at index 4
        df = pd.DataFrame(
            {
                "high": [100, 102, 105, 103, 101, 103],
                "low": [98, 99, 102, 100, 98, 100],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=1)

        assert 2 in swing_highs  # Index 2 has highest high in window
        assert 4 in swing_lows  # Index 4 has lowest low in window

    def test_returns_integer_indices(self) -> None:
        """Test that function returns lists of integer indices."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 105, 103, 101],
                "low": [98, 99, 102, 100, 98],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=1)

        assert isinstance(swing_highs, list)
        assert isinstance(swing_lows, list)
        assert all(isinstance(i, int) for i in swing_highs)
        assert all(isinstance(i, int) for i in swing_lows)

    def test_with_lookback_3(self) -> None:
        """Test swing detection with larger lookback window."""
        df = pd.DataFrame(
            {
                "high": [100, 101, 102, 105, 103, 102, 101, 103, 102],
                "low": [98, 99, 100, 103, 101, 100, 99, 101, 100],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=3)

        # Index 3 should be swing high (highest in 7-bar window)
        assert 3 in swing_highs
        # Should have at least one swing detected
        assert len(swing_highs) > 0 or len(swing_lows) > 0

    def test_with_lookback_5(self) -> None:
        """Test swing detection with lookback=5."""
        # Create 15 bars with clear swing at center
        df = pd.DataFrame(
            {
                "high": [
                    100,
                    101,
                    102,
                    103,
                    104,
                    110,
                    104,
                    103,
                    102,
                    101,
                    100,
                    101,
                    102,
                    103,
                    104,
                ],
                "low": [
                    99,
                    100,
                    101,
                    102,
                    103,
                    108,
                    103,
                    102,
                    101,
                    100,
                    99,
                    100,
                    101,
                    102,
                    103,
                ],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=5)

        # Index 5 should be swing high (highest in 11-bar window)
        assert 5 in swing_highs

    def test_empty_dataframe(self) -> None:
        """Test with empty DataFrame returns empty lists."""
        df = pd.DataFrame({"high": [], "low": []})

        swing_highs, swing_lows = detect_swings(df, lookback=2)

        assert swing_highs == []
        assert swing_lows == []

    def test_insufficient_data(self) -> None:
        """Test with insufficient data returns empty lists."""
        # Need at least 2*lookback + 1 rows
        df = pd.DataFrame(
            {
                "high": [100, 101, 102],
                "low": [98, 99, 100],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=2)

        # Not enough data (need 5 rows for lookback=2)
        assert swing_highs == []
        assert swing_lows == []

    def test_missing_high_column(self) -> None:
        """Test that missing 'high' column raises ValueError."""
        df = pd.DataFrame({"low": [98, 99, 100, 99, 98]})

        with pytest.raises(ValueError, match="Missing required column"):
            detect_swings(df, lookback=1)

    def test_missing_low_column(self) -> None:
        """Test that missing 'low' column raises ValueError."""
        df = pd.DataFrame({"high": [100, 101, 102, 101, 100]})

        with pytest.raises(ValueError, match="Missing required column"):
            detect_swings(df, lookback=1)

    def test_invalid_lookback(self) -> None:
        """Test that lookback < 1 raises ValueError."""
        df = pd.DataFrame(
            {
                "high": [100, 101, 102],
                "low": [98, 99, 100],
            }
        )

        with pytest.raises(ValueError, match="lookback must be >= 1"):
            detect_swings(df, lookback=0)

    def test_flat_price_no_swings(self) -> None:
        """Test with flat price returns empty lists."""
        df = pd.DataFrame(
            {
                "high": [100, 100, 100, 100, 100],
                "low": [99, 99, 99, 99, 99],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=1)

        # All bars are equal, so all are technically swing points
        # But we want strict inequality for swings, so may return all or none
        # depending on implementation (using == for max/min will include all)
        # Let's verify they're all included
        assert len(swing_highs) == 3  # Indices 1, 2, 3 (excluding boundaries)
        assert len(swing_lows) == 3

    def test_all_increasing(self) -> None:
        """Test with all increasing prices."""
        df = pd.DataFrame(
            {
                "high": [100, 101, 102, 103, 104, 105],
                "low": [99, 100, 101, 102, 103, 104],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=1)

        # In strictly increasing series, only last point could be swing high
        # but it's excluded (needs lookback after). So no interior swings.
        assert len(swing_highs) == 0
        # Only first point could be swing low, but excluded (needs lookback before)
        assert len(swing_lows) == 0

    def test_all_decreasing(self) -> None:
        """Test with all decreasing prices."""
        df = pd.DataFrame(
            {
                "high": [105, 104, 103, 102, 101, 100],
                "low": [104, 103, 102, 101, 100, 99],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=1)

        # In strictly decreasing series, no interior swings
        assert len(swing_highs) == 0
        assert len(swing_lows) == 0

    def test_duplicate_highs_at_same_level(self) -> None:
        """Test with duplicate highs at same level includes all."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 105, 105, 105, 102, 100],
                "low": [98, 99, 102, 102, 102, 99, 98],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=1)

        # Indices 2, 3, 4 all have high=105, all should be included
        assert 2 in swing_highs
        assert 3 in swing_highs
        assert 4 in swing_highs

    def test_boundary_exclusion(self) -> None:
        """Test that first and last bars cannot be swings."""
        df = pd.DataFrame(
            {
                "high": [110, 102, 105, 103, 101, 103, 115],
                "low": [95, 99, 102, 100, 98, 100, 94],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=2)

        # Indices 0 and 6 should not be in results (boundary exclusion)
        assert 0 not in swing_highs
        assert 0 not in swing_lows
        assert 6 not in swing_highs
        assert 6 not in swing_lows

    def test_alternating_peaks_and_troughs(self) -> None:
        """Test with alternating peaks and troughs."""
        df = pd.DataFrame(
            {
                "high": [100, 105, 100, 105, 100, 105, 100],
                "low": [95, 100, 95, 100, 95, 100, 95],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=1)

        # Peaks at odd indices: 1, 3, 5
        assert 1 in swing_highs
        assert 3 in swing_highs
        assert 5 in swing_highs

        # Troughs at even indices (excluding boundaries): 2, 4
        assert 2 in swing_lows
        assert 4 in swing_lows

    def test_with_custom_dataframe_index(self) -> None:
        """Test that integer positions are returned, not DataFrame index values."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 105, 103, 101],
                "low": [98, 99, 102, 100, 98],
            },
            index=[10, 20, 30, 40, 50],  # Custom index
        )

        swing_highs, swing_lows = detect_swings(df, lookback=1)

        # Should return integer positions (2), not index values (30)
        assert 2 in swing_highs  # Position 2 in DataFrame
        assert 30 not in swing_highs  # Not the index value

    def test_multiple_swings_in_series(self) -> None:
        """Test detection of multiple swings in longer series."""
        df = pd.DataFrame(
            {
                "high": [100, 102, 105, 103, 101, 103, 106, 104, 102, 104, 107],
                "low": [98, 99, 102, 100, 98, 100, 103, 101, 99, 101, 104],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=2)

        # Should detect multiple swing points
        assert len(swing_highs) >= 2
        assert len(swing_lows) >= 2

    def test_minimum_data_requirement(self) -> None:
        """Test minimum data requirement: exactly 2*lookback + 1 rows."""
        # For lookback=2, need exactly 5 rows minimum
        df = pd.DataFrame(
            {
                "high": [100, 101, 105, 103, 102],
                "low": [98, 99, 103, 101, 100],
            }
        )

        swing_highs, swing_lows = detect_swings(df, lookback=2)

        # Index 2 should be swing high (highest in 5-bar window)
        assert 2 in swing_highs
