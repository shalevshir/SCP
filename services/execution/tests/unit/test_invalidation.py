"""Unit tests for invalidation checker."""

from datetime import datetime, timezone

import pytest

from scp_shared.common.types import Candle
from scp_shared.execution import InvalidationChecker
from scp_shared.execution.types import TradeRecord


def make_trade(
    direction: str = "long",
    setup_type: str = "VWAP_RECLAIM",
    entry_price: float = 2650.0,
    sl_price: float = 2645.0,
    tp_price: float = 2662.0,
) -> TradeRecord:
    """Helper to create test trade."""
    if direction == "long":
        risk_amount = entry_price - sl_price
        reward_amount = tp_price - entry_price
    else:
        risk_amount = sl_price - entry_price
        reward_amount = entry_price - tp_price

    return TradeRecord(
        trade_id="test-trade-1",
        signal_id="test-signal-1",
        symbol="GC",
        direction=direction,
        setup_type=setup_type,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        quantity=1,
        risk_amount=risk_amount,
        reward_amount=reward_amount,
        entry_timestamp=datetime.now(timezone.utc),
    )


def make_candle(
    high: float = 2655.0,
    low: float = 2645.0,
    close: float = 2650.0,
) -> Candle:
    """Helper to create test candle."""
    return Candle(
        timestamp=datetime.now(timezone.utc),
        open=2650.0,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )


class TestInvalidationChecker:
    """Test invalidation checker."""

    def test_check_sl_hit_long(self) -> None:
        """Test stop-loss hit for long trade."""
        checker = InvalidationChecker()
        trade = make_trade(direction="long", entry_price=2650.0, sl_price=2645.0)
        candle = make_candle(low=2644.0)  # Hits SL

        # Pass bars_elapsed=10 to exceed grace period (VWAP_RECLAIM grace is 8)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=10)

        assert should_exit is True
        assert "SL_HIT" in reason

    def test_check_tp_hit_long(self) -> None:
        """Test take-profit hit for long trade."""
        checker = InvalidationChecker()
        trade = make_trade(
            direction="long", entry_price=2650.0, sl_price=2645.0, tp_price=2662.0
        )
        candle = make_candle(low=2646.0, high=2663.0)  # Hits TP, not SL

        # Pass bars_elapsed=10 to exceed grace period (VWAP_RECLAIM grace is 8)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=10)

        assert should_exit is True
        assert "TP_HIT" in reason

    def test_check_sl_hit_short(self) -> None:
        """Test stop-loss hit for short trade."""
        checker = InvalidationChecker()
        trade = make_trade(direction="short", entry_price=2650.0, sl_price=2655.0)
        candle = make_candle(high=2656.0)  # Hits SL

        # Pass bars_elapsed=10 to exceed grace period (VWAP_RECLAIM grace is 8)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=10)

        assert should_exit is True
        assert "SL_HIT" in reason

    def test_check_tp_hit_short(self) -> None:
        """Test take-profit hit for short trade."""
        checker = InvalidationChecker()
        trade = make_trade(
            direction="short", entry_price=2650.0, sl_price=2655.0, tp_price=2638.0
        )
        candle = make_candle(low=2637.0, high=2654.0)  # Hits TP, not SL

        # Pass bars_elapsed=10 to exceed grace period (VWAP_RECLAIM grace is 8)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=10)

        assert should_exit is True
        assert "TP_HIT" in reason

    def test_no_exit_when_within_range(self) -> None:
        """Test no exit when price stays within SL/TP range."""
        checker = InvalidationChecker()
        trade = make_trade(
            direction="long", entry_price=2650.0, sl_price=2645.0, tp_price=2662.0
        )
        candle = make_candle(low=2646.0, high=2660.0)  # Within range

        should_exit, reason = checker.check_sl_tp(trade, candle)

        assert should_exit is False
        assert reason is None

    def test_update_state_tracks_1r_reached_long(self) -> None:
        """Test that state tracking detects +1R for long trade."""
        checker = InvalidationChecker()
        trade = make_trade(direction="long", entry_price=2650.0, sl_price=2645.0)
        # +1R = 2650 + 5 = 2655
        candle = make_candle(high=2656.0)

        checker.update_state(trade, candle)

        state = checker._get_trade_state(trade.trade_id)
        assert state["reached_1r"] is True

    def test_check_no_1r_reached_invalidates_after_time_limit(self) -> None:
        """Test invalidation when +1R not reached within time limit."""
        checker = InvalidationChecker()
        trade = make_trade(setup_type="VWAP_FADE")  # 10 bar limit

        # Simulate 10 bars without reaching +1R
        for _ in range(10):
            candle = make_candle(high=2654.0)  # Below +1R
            checker.update_state(trade, candle)

        # Check at bar 10
        is_invalid, reason, _ = checker.check_no_1r_reached(trade, bars_elapsed=10)

        assert is_invalid is True
        assert "+1R not reached" in reason

    def test_check_vwap_invalidation_reclaim_long(self) -> None:
        """Test VWAP invalidation for VWAP_RECLAIM long trade requires 2-bar confirmation."""
        checker = InvalidationChecker()
        trade = make_trade(direction="long", setup_type="VWAP_RECLAIM")
        features = {"vwap": 2650.0}  # Close below VWAP

        # First bar below VWAP
        candle1 = make_candle(close=2649.0)
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle1, features)
        assert is_invalid is False  # Not yet - need 2 bars

        # Second bar below VWAP - now invalidated
        candle2 = make_candle(close=2648.0)
        is_invalid, reason = checker.check_vwap_invalidation(trade, candle2, features)
        assert is_invalid is True
        assert "VWAP invalidation" in reason
        assert "2-bar confirmed" in reason

    def test_check_vwap_invalidation_fade_requires_2_bars(self) -> None:
        """Test VWAP_FADE invalidation requires 2 consecutive bars."""
        checker = InvalidationChecker()
        trade = make_trade(direction="long", setup_type="VWAP_FADE")
        # For FADE invalidation, we need positive slope (for long) to confirm VWAP reclaim
        features = {"vwap": 2649.0, "vwap_slope": 0.5}

        # First bar above VWAP with positive slope
        candle1 = make_candle(close=2651.0)
        is_invalid, _ = checker.check_vwap_invalidation(trade, candle1, features)
        assert is_invalid is False  # Not yet

        # Second bar above VWAP with positive slope
        candle2 = make_candle(close=2652.0)
        is_invalid, reason = checker.check_vwap_invalidation(trade, candle2, features)
        assert is_invalid is True  # Now invalidated
        assert "2-bar confirmed" in reason
