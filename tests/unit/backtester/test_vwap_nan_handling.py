"""Tests for VWAP NaN handling in SL calculation (Bug Fix).

Bug: vwap_value is not None doesn't catch NaN values from DataFrames,
resulting in NaN stop loss when VWAP is NaN (common for early rows).

Test coverage:
- NaN VWAP falls back to confirmation candle SL
- None VWAP falls back to confirmation candle SL
- Valid VWAP uses VWAP-zone SL
"""

from datetime import datetime, timezone

import numpy as np
import pytest

from backtester.entry_model import EntryExecution
from backtester.trade import calculate_stop_loss
from common.types import Candle
from rule_engine.signal import Signal


@pytest.fixture
def sample_long_reclaim_signal():
    """Create a sample long VWAP_RECLAIM signal."""
    return Signal(
        timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="5m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=9.0,
        confidence="A+",
        factors={},
        rationale="Test VWAP reclaim",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )


@pytest.fixture
def sample_confirmation_candle():
    """Create a sample confirmation candle."""
    return Candle(
        timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
        open=2648.0,
        high=2655.0,
        low=2645.0,
        close=2652.0,
        volume=1000.0,
        symbol="GC",
        timeframe="5m",
        source="test",
    )


@pytest.fixture
def config_with_tick_size():
    """Create a config with tick size."""
    return {
        "assets": {
            "tick_sizes": {
                "GC": 0.1,
            }
        }
    }


class TestVWAPNaNHandling:
    """Test that NaN VWAP values are handled correctly."""

    def test_nan_vwap_falls_back_to_confirmation_candle(
        self,
        sample_long_reclaim_signal,
        sample_confirmation_candle,
        config_with_tick_size,
    ):
        """NaN VWAP should fallback to confirmation candle low, not produce NaN SL."""
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2652.0,
            signal=sample_long_reclaim_signal,
            executed=True,
            rejection_reason=None,
        )

        # NaN VWAP (common for early rows in VWAP calculation)
        vwap_value = np.nan

        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="long",
            confirmation_candle=sample_confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # Should fallback to confirmation candle low
        assert sl == sample_confirmation_candle.low
        assert not np.isnan(sl), "Stop loss should not be NaN"
        assert "VWAP not available" in rationale or "confirmation candle" in rationale

    def test_none_vwap_falls_back_to_confirmation_candle(
        self,
        sample_long_reclaim_signal,
        sample_confirmation_candle,
        config_with_tick_size,
    ):
        """None VWAP should fallback to confirmation candle low."""
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2652.0,
            signal=sample_long_reclaim_signal,
            executed=True,
            rejection_reason=None,
        )

        vwap_value = None

        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="long",
            confirmation_candle=sample_confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # Should fallback to confirmation candle low
        assert sl == sample_confirmation_candle.low
        assert not np.isnan(sl), "Stop loss should not be NaN"

    def test_valid_vwap_uses_vwap_zone_sl(
        self,
        sample_long_reclaim_signal,
        sample_confirmation_candle,
        config_with_tick_size,
    ):
        """Valid VWAP should use VWAP-zone SL."""
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2652.0,
            signal=sample_long_reclaim_signal,
            executed=True,
            rejection_reason=None,
        )

        vwap_value = 2648.0  # Valid VWAP

        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="long",
            confirmation_candle=sample_confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # Should use VWAP-zone SL
        expected_sl = 2648.0 - (30 * 0.1)  # VWAP - 30 ticks
        assert sl == pytest.approx(expected_sl, abs=0.01)
        assert not np.isnan(sl), "Stop loss should not be NaN"
        assert "VWAP-zone" in rationale or "VWAP" in rationale

    def test_nan_vwap_short_trade(
        self, sample_confirmation_candle, config_with_tick_size
    ):
        """NaN VWAP for short trade should fallback to confirmation candle high."""
        signal = Signal(
            timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="5m",
            direction="short",
            setup_type="VWAP_RECLAIM",
            htf_bias="bearish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test VWAP reclaim",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2648.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        vwap_value = np.nan

        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="short",
            confirmation_candle=sample_confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # Should fallback to confirmation candle high
        assert sl == sample_confirmation_candle.high
        assert not np.isnan(sl), "Stop loss should not be NaN"
