"""Unit tests for VWAP hold confirmation (SOP Section 3.6)."""

import pytest
from datetime import datetime, timezone
from scp_shared.common.types import Candle
from scp_shared.execution import InvalidationChecker
from scp_shared.execution.types import TradeRecord


@pytest.fixture
def base_trade():
    """Base VWAP_RECLAIM trade for testing."""
    return TradeRecord(
        trade_id="test_trade_001",
        signal_id="signal_001",
        symbol="GC",
        direction="long",
        setup_type="VWAP_RECLAIM",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2670.0,
        risk_amount=10.0,
        reward_amount=20.0,
        quantity=1,
        entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        entry_bar_idx=0,
        reached_1r=False,
    )


def make_candle(close: float, timestamp: datetime | None = None) -> Candle:
    """Helper to create candle with specific close price.

    Args:
        close: Close price
        timestamp: Optional timestamp (defaults to 2025-01-15 10:01)

    Returns:
        Candle instance
    """
    if timestamp is None:
        timestamp = datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc)

    return Candle(
        timestamp=timestamp,
        open=2650.0,
        high=max(2652.0, close),  # Ensure high >= close
        low=min(2648.0, close),  # Ensure low <= close
        close=close,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )


class TestVWAPHoldConfirmation:
    """Test VWAP hold confirmation logic (SOP Section 3.6 'Hold' definition)."""

    def test_single_bar_below_vwap_does_not_invalidate(self, base_trade):
        """Single bar below VWAP should NOT trigger invalidation."""
        checker = InvalidationChecker(vwap_hold_confirm_bars=2)

        # First bar: close below VWAP
        candle = make_candle(close=2644.0)  # Below VWAP at 2645.0
        features = {"vwap": 2645.0}

        is_invalid, reason = checker.check_vwap_invalidation(
            base_trade, candle, features
        )

        assert not is_invalid, "Single bar should not invalidate"
        assert reason is None

    def test_two_consecutive_bars_below_vwap_invalidates(self, base_trade):
        """Two consecutive bars below VWAP should trigger invalidation."""
        checker = InvalidationChecker(vwap_hold_confirm_bars=2)

        features = {"vwap": 2645.0}

        # First bar: close below VWAP
        candle1 = make_candle(close=2644.0)
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle1, features)
        assert not is_invalid

        # Second bar: still below VWAP
        candle2 = make_candle(
            close=2643.0, timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc)
        )
        is_invalid, reason = checker.check_vwap_invalidation(
            base_trade, candle2, features
        )

        assert is_invalid, "Two consecutive bars should invalidate"
        assert "2-bar confirmed" in reason
        assert "VWAP invalidation" in reason

    def test_counter_resets_on_non_invalidating_bar(self, base_trade):
        """Counter should reset when price returns above VWAP."""
        checker = InvalidationChecker(vwap_hold_confirm_bars=2)

        features = {"vwap": 2645.0}

        # First bar: close below VWAP
        candle1 = make_candle(close=2644.0)
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle1, features)
        assert not is_invalid

        # Second bar: close ABOVE VWAP (resets counter)
        candle2 = make_candle(
            close=2646.0, timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc)
        )
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle2, features)
        assert not is_invalid

        # Third bar: close below VWAP again (counter starts from 1)
        candle3 = make_candle(
            close=2644.0, timestamp=datetime(2025, 1, 15, 10, 3, tzinfo=timezone.utc)
        )
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle3, features)
        assert not is_invalid, "Counter should have reset, only 1 bar below"

    def test_short_trade_requires_consecutive_bars_above_vwap(self, base_trade):
        """Short trade invalidation requires consecutive bars ABOVE VWAP."""
        checker = InvalidationChecker(vwap_hold_confirm_bars=2)

        # Short trade
        base_trade.direction = "short"
        base_trade.entry_price = 2640.0
        base_trade.sl_price = 2650.0
        base_trade.tp_price = 2620.0

        features = {"vwap": 2645.0}

        # First bar: close above VWAP
        candle1 = make_candle(close=2646.0)
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle1, features)
        assert not is_invalid

        # Second bar: still above VWAP
        candle2 = make_candle(
            close=2647.0, timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc)
        )
        is_invalid, reason = checker.check_vwap_invalidation(
            base_trade, candle2, features
        )

        assert is_invalid, "Two consecutive bars above should invalidate short"
        assert "2-bar confirmed" in reason

    def test_configurable_n_bars_3_bars(self, base_trade):
        """Test configurable N-bar confirmation (3 bars)."""
        checker = InvalidationChecker(vwap_hold_confirm_bars=3)

        features = {"vwap": 2645.0}

        # First bar: below VWAP
        candle1 = make_candle(close=2644.0)
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle1, features)
        assert not is_invalid

        # Second bar: still below VWAP
        candle2 = make_candle(
            close=2643.0, timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc)
        )
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle2, features)
        assert not is_invalid, "Only 2 bars, need 3"

        # Third bar: still below VWAP
        candle3 = make_candle(
            close=2642.0, timestamp=datetime(2025, 1, 15, 10, 3, tzinfo=timezone.utc)
        )
        is_invalid, reason = checker.check_vwap_invalidation(
            base_trade, candle3, features
        )

        assert is_invalid, "Three consecutive bars should invalidate"
        assert "3-bar confirmed" in reason

    def test_vwap_fade_still_uses_2_bar_confirmation(self, base_trade):
        """VWAP_FADE should still use its own 2-bar logic (unchanged)."""
        checker = InvalidationChecker(vwap_hold_confirm_bars=3)  # RECLAIM uses 3

        # Change to FADE setup
        base_trade.setup_type = "VWAP_FADE"

        features = {"vwap": 2645.0, "vwap_slope": 0.5}  # Positive slope

        # First bar: close above VWAP (reclaim)
        candle1 = make_candle(close=2646.0)
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle1, features)
        assert not is_invalid

        # Second bar: still above VWAP
        candle2 = make_candle(
            close=2647.0, timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc)
        )
        is_invalid, reason = checker.check_vwap_invalidation(
            base_trade, candle2, features
        )

        # FADE uses 2-bar confirmation (hardcoded), not affected by vwap_hold_confirm_bars
        assert is_invalid, "FADE should use 2-bar confirmation"
        assert "2-bar confirmed" in reason

    def test_counter_cleared_after_invalidation(self, base_trade):
        """Counter should be cleared after invalidation triggers."""
        checker = InvalidationChecker(vwap_hold_confirm_bars=2)

        features = {"vwap": 2645.0}

        # Trigger invalidation
        candle1 = make_candle(close=2644.0)
        checker.check_vwap_invalidation(base_trade, candle1, features)

        candle2 = make_candle(
            close=2643.0, timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc)
        )
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle2, features)
        assert is_invalid

        # Counter should be cleared now
        # If we check again, it shouldn't immediately invalidate
        candle3 = make_candle(
            close=2642.0, timestamp=datetime(2025, 1, 15, 10, 3, tzinfo=timezone.utc)
        )
        is_invalid, _ = checker.check_vwap_invalidation(base_trade, candle3, features)
        assert not is_invalid, "Counter should reset after invalidation"

    def test_no_invalidation_when_vwap_missing(self, base_trade):
        """No invalidation when VWAP data is missing."""
        checker = InvalidationChecker(vwap_hold_confirm_bars=2)

        features = {"vwap": None}  # Missing VWAP

        candle = make_candle(close=2644.0)
        is_invalid, reason = checker.check_vwap_invalidation(
            base_trade, candle, features
        )

        assert not is_invalid
        assert reason is None
