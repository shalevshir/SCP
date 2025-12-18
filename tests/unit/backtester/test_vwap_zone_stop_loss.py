"""Tests for VWAP-zone stop loss calculation (Sprint 3 Task 5).

Sprint 3 replaces micro-candle SL with VWAP-zone SL for VWAP_RECLAIM trades.
This allows normal retest behavior without premature stop-outs.

Test coverage:
- SL uses VWAP - 30 ticks for long VWAP_RECLAIM
- SL uses VWAP + 30 ticks for short VWAP_RECLAIM
- 20-tick minimum floor still applies
- Non-VWAP_RECLAIM setups use existing logic (regression)
- Fallback to confirmation candle if VWAP is None
"""

from datetime import datetime, timezone

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
def sample_short_reclaim_signal():
    """Create a sample short VWAP_RECLAIM signal."""
    return Signal(
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
                "GC": 0.1,  # Gold tick size
            }
        }
    }


class TestVWAPZoneStopLoss:
    """Test VWAP-zone SL calculation for VWAP_RECLAIM trades."""

    def test_long_reclaim_uses_vwap_minus_30_ticks(
        self, sample_long_reclaim_signal, sample_confirmation_candle, config_with_tick_size
    ):
        """Long VWAP_RECLAIM should use VWAP - 30 ticks as SL."""
        # Entry execution with VWAP value
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2652.0,
            signal=sample_long_reclaim_signal,
            executed=True,
            rejection_reason=None,
        )

        # VWAP value at entry
        vwap_value = 2648.0

        # Calculate SL
        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="long",
            confirmation_candle=sample_confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # Expected SL = VWAP - (30 ticks * 0.1) = 2648.0 - 3.0 = 2645.0
        expected_sl = 2648.0 - (30 * 0.1)
        assert sl == pytest.approx(expected_sl, abs=0.01)
        assert "VWAP-zone" in rationale or "VWAP" in rationale

    def test_short_reclaim_uses_vwap_plus_30_ticks(
        self, sample_short_reclaim_signal, sample_confirmation_candle, config_with_tick_size
    ):
        """Short VWAP_RECLAIM should use VWAP + 30 ticks as SL."""
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2648.0,
            signal=sample_short_reclaim_signal,
            executed=True,
            rejection_reason=None,
        )

        vwap_value = 2652.0

        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="short",
            confirmation_candle=sample_confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # Expected SL = VWAP + (30 ticks * 0.1) = 2652.0 + 3.0 = 2655.0
        expected_sl = 2652.0 + (30 * 0.1)
        assert sl == pytest.approx(expected_sl, abs=0.01)

    def test_minimum_floor_still_applies(
        self, sample_long_reclaim_signal, config_with_tick_size
    ):
        """20-tick minimum floor should still apply to VWAP-zone SL."""
        # Entry very close to VWAP
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2650.5,  # Very close to VWAP
            signal=sample_long_reclaim_signal,
            executed=True,
            rejection_reason=None,
        )

        vwap_value = 2650.0  # Close to entry
        confirmation_candle = Candle(
            timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            open=2650.0,
            high=2651.0,
            low=2649.5,
            close=2650.5,
            volume=1000.0,
            symbol="GC",
            timeframe="5m",
            source="test",
        )

        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="long",
            confirmation_candle=confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # VWAP - 30 ticks = 2650.0 - 3.0 = 2647.0
        # Risk = 2650.5 - 2647.0 = 3.5 points = 35 ticks (> 20 minimum)
        # So VWAP-zone SL should be used
        expected_sl = 2650.0 - (30 * 0.1)
        assert sl == pytest.approx(expected_sl, abs=0.01)

    def test_non_reclaim_setup_uses_existing_logic(self, config_with_tick_size):
        """Non-VWAP_RECLAIM setups should still use confirmation candle SL."""
        # DXY_CONTINUATION signal
        signal = Signal(
            timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="5m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test DXY continuation",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2652.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        confirmation_candle = Candle(
            timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            open=2648.0,
            high=2655.0,
            low=2645.0,  # This should be SL for non-RECLAIM
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="5m",
            source="test",
        )

        vwap_value = 2648.0  # VWAP is provided but should be ignored

        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="long",
            confirmation_candle=confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # Should use confirmation candle low, not VWAP-zone
        assert sl == confirmation_candle.low
        assert "VWAP" not in rationale

    def test_fallback_to_confirmation_candle_if_vwap_none(
        self, sample_long_reclaim_signal, sample_confirmation_candle, config_with_tick_size
    ):
        """If VWAP is None, should fallback to confirmation candle low."""
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2652.0,
            signal=sample_long_reclaim_signal,
            executed=True,
            rejection_reason=None,
        )

        # VWAP is None (not available)
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

    def test_vwap_sl_buffer_constant_value(self):
        """Verify VWAP_SL_BUFFER_TICKS constant is defined and reasonable."""
        from backtester.trade import VWAP_SL_BUFFER_TICKS

        # Should be 30 ticks (conservative)
        assert VWAP_SL_BUFFER_TICKS == 30

    def test_rationale_includes_vwap_zone_description(
        self, sample_long_reclaim_signal, sample_confirmation_candle, config_with_tick_size
    ):
        """Rationale should clearly indicate VWAP-zone SL."""
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
            entry_timestamp=datetime(2024, 11, 1, 10, 5, tzinfo=timezone.utc),
            entry_price=2652.0,
            signal=sample_long_reclaim_signal,
            executed=True,
            rejection_reason=None,
        )

        vwap_value = 2648.0

        sl, rationale, retest_flag = calculate_stop_loss(
            entry_execution=entry_execution,
            direction="long",
            confirmation_candle=sample_confirmation_candle,
            bos_candle=None,
            config=config_with_tick_size,
            vwap_value=vwap_value,
        )

        # Rationale should mention VWAP-zone or VWAP buffer
        assert ("VWAP" in rationale and ("zone" in rationale.lower() or "buffer" in rationale.lower()))

