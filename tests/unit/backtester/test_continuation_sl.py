"""Tests for DXY_CONTINUATION stop-loss padding."""

import pytest
from datetime import datetime, timezone

from backtester.entry_model import EntryExecution
from backtester.trade import calculate_stop_loss, MIN_SL_TICKS_DXY_CONTINUATION
from common.types import Candle
from rule_engine.signal import Signal


class TestContinuationSLPadding:
    """Test DXY_CONTINUATION stop-loss padding logic."""

    def test_continuation_sl_padding_long(self):
        """Test that DXY_CONTINUATION SL is padded to minimum 25 ticks for longs (PATCH PART 4)."""
        # Create signal with DXY_CONTINUATION setup
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test continuation",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Confirmation candle with tight SL (only 0.5 = 5 ticks from entry)
        confirmation_candle = Candle(
            timestamp=signal.timestamp,
            open=2650.0,
            high=2651.0,
            low=2649.5,  # Only 0.5 below entry
            close=2650.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        config = {"assets": {"tick_sizes": {"GC": 0.1}}}

        sl, rationale, _ = calculate_stop_loss(
            entry_execution, "long", confirmation_candle, None, config
        )

        # PATCH PART 4: Should be padded to 25 ticks below entry (was 15)
        expected_sl = 2650.0 - (MIN_SL_TICKS_DXY_CONTINUATION * 0.1)
        assert abs(sl - expected_sl) < 0.01
        assert "25-tick minimum" in rationale

    def test_continuation_sl_no_padding_when_sufficient(self):
        """Test that SL is not padded when already >= 25 ticks (PATCH PART 4)."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test continuation",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # PATCH PART 4: Confirmation candle with wide SL (3.0 = 30 ticks, > 25 minimum)
        confirmation_candle = Candle(
            timestamp=signal.timestamp,
            open=2647.0,
            high=2651.0,
            low=2647.0,  # 3.0 below entry = 30 ticks (> 25 minimum)
            close=2650.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        config = {"assets": {"tick_sizes": {"GC": 0.1}}}

        sl, rationale, _ = calculate_stop_loss(
            entry_execution, "long", confirmation_candle, None, config
        )

        # Should use confirmation low directly (no padding needed)
        assert abs(sl - 2647.0) < 0.01
        assert "structure-based" in rationale

    def test_continuation_sl_padding_short(self):
        """Test that DXY_CONTINUATION SL is padded to minimum 25 ticks for shorts (PATCH PART 4)."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="DXY_CONTINUATION",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test continuation",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Confirmation candle with tight SL (only 0.5 = 5 ticks from entry)
        confirmation_candle = Candle(
            timestamp=signal.timestamp,
            open=2650.0,
            high=2650.5,  # Only 0.5 above entry
            low=2649.0,
            close=2649.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        config = {"assets": {"tick_sizes": {"GC": 0.1}}}

        sl, rationale, _ = calculate_stop_loss(
            entry_execution, "short", confirmation_candle, None, config
        )

        # PATCH PART 4: Should be padded to 25 ticks above entry (was 15)
        expected_sl = 2650.0 + (MIN_SL_TICKS_DXY_CONTINUATION * 0.1)
        assert abs(sl - expected_sl) < 0.01
        assert "25-tick minimum" in rationale

    def test_vwap_reclaim_now_uses_20_ticks(self):
        """Test that VWAP_RECLAIM now uses 20-tick minimum."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test reclaim",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        confirmation_candle = Candle(
            timestamp=signal.timestamp,
            open=2650.0,
            high=2651.0,
            low=2649.5,
            close=2650.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        config = {"assets": {"tick_sizes": {"GC": 0.1}}}

        sl, rationale, _ = calculate_stop_loss(
            entry_execution, "long", confirmation_candle, None, config
        )

        # Should use 20-tick minimum for VWAP_RECLAIM
        from backtester.trade import MIN_SL_TICKS_VWAP_RECLAIM
        expected_sl = 2650.0 - (MIN_SL_TICKS_VWAP_RECLAIM * 0.1)
        assert abs(sl - expected_sl) < 0.01
        assert "20-tick minimum" in rationale or "padded" in rationale.lower()
