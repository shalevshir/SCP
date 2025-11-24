"""Unit tests for HTF conflict detection rules.

Tests the three conflict detection mechanisms:
1. Structure conflict between 1H and 15M
2. Price chop detection on 15M
3. Liquidity sweep against trend
"""

import pandas as pd
import pytest
from rule_engine.htf.conflicts import (
    detect_structure_conflict,
    detect_price_chop_15m,
    detect_sweep_against_trend,
)


class TestStructureConflictDetection:
    """Test structure conflict detection between 1H and 15M."""

    def test_bullish_1h_bearish_15m_conflict(self) -> None:
        """Test that bullish 1H + bearish 15M triggers conflict."""
        is_conflict, reason = detect_structure_conflict(
            structure_1h="HH",
            structure_15m="LH",
        )
        assert is_conflict is True
        assert reason is not None
        assert "conflict" in reason.lower()

    def test_bearish_1h_bullish_15m_conflict(self) -> None:
        """Test that bearish 1H + bullish 15M triggers conflict."""
        is_conflict, reason = detect_structure_conflict(
            structure_1h="LH",
            structure_15m="HH",
        )
        assert is_conflict is True
        assert reason is not None

    def test_bullish_1h_bullish_15m_no_conflict(self) -> None:
        """Test that both bullish structures don't conflict."""
        is_conflict, reason = detect_structure_conflict(
            structure_1h="HH",
            structure_15m="HL",
        )
        assert is_conflict is False
        assert reason is None

    def test_bearish_1h_bearish_15m_no_conflict(self) -> None:
        """Test that both bearish structures don't conflict."""
        is_conflict, reason = detect_structure_conflict(
            structure_1h="LH",
            structure_15m="LL",
        )
        assert is_conflict is False
        assert reason is None

    def test_none_values_handled_gracefully(self) -> None:
        """Test that None structure labels don't crash."""
        # Both None
        is_conflict, reason = detect_structure_conflict(None, None)
        assert is_conflict is False
        assert reason is None

        # One None
        is_conflict, reason = detect_structure_conflict("HH", None)
        assert is_conflict is False

        is_conflict, reason = detect_structure_conflict(None, "LH")
        assert is_conflict is False

    def test_neutral_structures_no_conflict(self) -> None:
        """Test that neutral/unknown structures don't trigger conflicts."""
        # Empty strings
        is_conflict, reason = detect_structure_conflict("", "")
        assert is_conflict is False

        # Unknown label
        is_conflict, reason = detect_structure_conflict("UNKNOWN", "HH")
        assert is_conflict is False


class TestPriceChopDetection:
    """Test 15M price chop detection."""

    @pytest.fixture
    def chop_data(self) -> pd.DataFrame:
        """Create DataFrame with choppy price action (large wicks)."""
        return pd.DataFrame(
            {
                "high": [2100.0, 2105.0, 2110.0, 2115.0, 2120.0],
                "low": [2080.0, 2085.0, 2090.0, 2095.0, 2100.0],
                "open": [2095.0, 2097.0, 2099.0, 2101.0, 2103.0],
                "close": [2097.0, 2099.0, 2101.0, 2103.0, 2105.0],
                # Large wicks (20 points) vs small bodies (2 points) = 10:1 ratio
            }
        )

    @pytest.fixture
    def trending_data(self) -> pd.DataFrame:
        """Create DataFrame with trending price action (small wicks)."""
        return pd.DataFrame(
            {
                "high": [2100.5, 2105.5, 2110.5, 2115.5, 2120.5],
                "low": [2100.0, 2105.0, 2110.0, 2115.0, 2120.0],
                "open": [2100.0, 2105.0, 2110.0, 2115.0, 2120.0],
                "close": [2100.5, 2105.5, 2110.5, 2115.5, 2120.5],
                # Small wicks (0.5 points) vs large bodies (5 points) = 0.1:1 ratio
            }
        )

    def test_large_wicks_trigger_chop_detection(self, chop_data: pd.DataFrame) -> None:
        """Test that large wicks relative to body trigger chop."""
        is_chop = detect_price_chop_15m(chop_data)
        assert is_chop is True

    def test_small_wicks_no_chop(self, trending_data: pd.DataFrame) -> None:
        """Test that small wicks don't trigger chop."""
        is_chop = detect_price_chop_15m(trending_data)
        assert is_chop is False

    def test_consecutive_candle_requirement(self) -> None:
        """Test that < 3 consecutive chop candles don't trigger."""
        # Only 2 consecutive chop candles
        df = pd.DataFrame(
            {
                "high": [2100.0, 2105.0, 2110.0],
                "low": [2080.0, 2085.0, 2109.0],  # Last candle trending
                "open": [2095.0, 2097.0, 2109.0],
                "close": [2097.0, 2099.0, 2110.0],
            }
        )
        is_chop = detect_price_chop_15m(df, min_chop_candles=3)
        assert is_chop is False

    def test_empty_dataframe_handling(self) -> None:
        """Test that empty DataFrame doesn't crash."""
        empty_df = pd.DataFrame(columns=["high", "low", "open", "close"])
        is_chop = detect_price_chop_15m(empty_df)
        assert is_chop is False

    def test_mixed_chop_trend_candles(self) -> None:
        """Test mixed chop and trend candles."""
        # 2 chop, 1 trend, 3 chop - should detect chop (last 3 consecutive)
        df = pd.DataFrame(
            {
                "high": [2100.0, 2105.0, 2110.0, 2115.0, 2120.0, 2125.0],
                "low": [2080.0, 2085.0, 2109.5, 2095.0, 2100.0, 2105.0],
                "open": [2095.0, 2097.0, 2109.5, 2101.0, 2103.0, 2107.0],
                "close": [2097.0, 2099.0, 2110.0, 2103.0, 2105.0, 2109.0],
            }
        )
        is_chop = detect_price_chop_15m(df, min_chop_candles=3)
        assert is_chop is True


class TestSweepAgainstTrend:
    """Test liquidity sweep against trend detection."""

    @pytest.fixture
    def sweep_high_events(self) -> pd.Series:
        """Create sweep events with a sweep_high at the end."""
        return pd.Series(
            [None, None, None, "sweep_high"],
            index=pd.RangeIndex(4),
        )

    @pytest.fixture
    def sweep_low_events(self) -> pd.Series:
        """Create sweep events with a sweep_low at the end."""
        return pd.Series(
            [None, None, None, "sweep_low"],
            index=pd.RangeIndex(4),
        )

    @pytest.fixture
    def sweep_success(self) -> pd.Series:
        """Create sweep success tracking (successful sweeps)."""
        return pd.Series(
            [None, None, None, True],
            index=pd.RangeIndex(4),
        )

    def test_bullish_trend_sweep_low_conflict(
        self, sweep_low_events: pd.Series, sweep_success: pd.Series
    ) -> None:
        """Test that bullish trend + sweep_low triggers conflict."""
        is_conflict, reason = detect_sweep_against_trend(
            bias="bullish",
            sweep_events=sweep_low_events,
            sweep_success=sweep_success,
        )
        assert is_conflict is True
        assert reason is not None
        assert "sweep" in reason.lower()

    def test_bearish_trend_sweep_high_conflict(
        self, sweep_high_events: pd.Series, sweep_success: pd.Series
    ) -> None:
        """Test that bearish trend + sweep_high triggers conflict."""
        is_conflict, reason = detect_sweep_against_trend(
            bias="bearish",
            sweep_events=sweep_high_events,
            sweep_success=sweep_success,
        )
        assert is_conflict is True
        assert reason is not None

    def test_bullish_trend_sweep_high_no_conflict(
        self, sweep_high_events: pd.Series, sweep_success: pd.Series
    ) -> None:
        """Test that bullish trend + sweep_high is continuation (no conflict)."""
        is_conflict, reason = detect_sweep_against_trend(
            bias="bullish",
            sweep_events=sweep_high_events,
            sweep_success=sweep_success,
        )
        assert is_conflict is False
        assert reason is None

    def test_bearish_trend_sweep_low_no_conflict(
        self, sweep_low_events: pd.Series, sweep_success: pd.Series
    ) -> None:
        """Test that bearish trend + sweep_low is continuation (no conflict)."""
        is_conflict, reason = detect_sweep_against_trend(
            bias="bearish",
            sweep_events=sweep_low_events,
            sweep_success=sweep_success,
        )
        assert is_conflict is False
        assert reason is None

    def test_neutral_bias_no_conflict(self, sweep_low_events: pd.Series) -> None:
        """Test that neutral bias doesn't trigger conflicts."""
        is_conflict, reason = detect_sweep_against_trend(
            bias="neutral",
            sweep_events=sweep_low_events,
        )
        assert is_conflict is False
        assert reason is None

    def test_no_recent_sweeps_no_conflict(self) -> None:
        """Test that no sweeps means no conflict."""
        no_sweeps = pd.Series([None, None, None, None], index=pd.RangeIndex(4))
        is_conflict, reason = detect_sweep_against_trend(
            bias="bullish",
            sweep_events=no_sweeps,
        )
        assert is_conflict is False
        assert reason is None

