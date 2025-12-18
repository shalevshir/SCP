"""Unit tests for single-bar trade exit checker.

Following TDD principles: tests written first to define behavior.
Tests the new check_trade_exit_single_bar() function that checks
a single candle against an active trade (instead of all future candles).
"""

from datetime import UTC, datetime

import pytest
from backtester.entry_model import EntryExecution
from backtester.simulator import check_trade_exit_single_bar
from backtester.trade import Trade
from common.types import Candle
from rule_engine.signal import Signal


def make_candle(
    timestamp: datetime,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100,
    symbol: str = "GC",
    timeframe: str = "1m",
    source: str = "TEST",
) -> Candle:
    """Helper to create test candles with default values."""
    return Candle(
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        symbol=symbol,
        timeframe=timeframe,
        source=source,
    )


def make_trade(
    direction: str = "long",
    setup_type: str = "VWAP_RECLAIM",
    entry_price: float = 2650.0,
    stop_loss: float = 2645.0,
    take_profit: float = 2665.0,
) -> Trade:
    """Helper to create test trades."""
    signal = Signal(
        timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction=direction,
        setup_type=setup_type,
        htf_bias="bullish" if direction == "long" else "bearish",
        score=9.0,
        confidence="A+",
        factors={},
        rationale="Test",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )
    entry_execution = EntryExecution(
        signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
        entry_price=entry_price,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )
    return Trade(
        trade_id="test-001",
        symbol="GC",
        timeframe="1m",
        entry_execution=entry_execution,
        entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
        entry_price=entry_price,
        direction=direction,
        setup_type=setup_type,
        stop_loss=stop_loss,
        take_profit=take_profit,
        sl_rationale="Test SL",
        tp_rationale="Test TP",
        risk_amount=abs(entry_price - stop_loss),
        reward_amount=abs(take_profit - entry_price),
        r_multiple=3.0,
        contracts=1,
        exit_timestamp=None,
        exit_price=None,
        exit_reason=None,
        pnl=None,
        pnl_percent=None,
        r_realized=None,
        pnl_dollars=None,
        pnl_net=None,
        slippage_cost=None,
        commission_cost=None,
        status="OPEN",
        duration_bars=None,
        invalidation_triggered=False,
        ignore_first_retest_bar=False,
    )


class TestSingleBarChecker:
    """Tests for check_trade_exit_single_bar() function."""

    def test_long_trade_tp_hit(self):
        """Test long trade exits when TP is hit on current candle."""
        trade = make_trade(direction="long", entry_price=2650.0, take_profit=2665.0)
        
        # Candle that hits TP (high >= 2665.0)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2660.0,
            high=2666.0,  # Hits TP
            low=2659.0,
            close=2665.0,
        )
        
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=3,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        assert closed_trade.status != "OPEN"
        assert closed_trade.exit_reason == "tp"
        assert closed_trade.exit_timestamp == candle.timestamp

    def test_long_trade_sl_hit(self):
        """Test long trade exits when SL is hit on current candle."""
        trade = make_trade(direction="long", entry_price=2650.0, stop_loss=2645.0)
        
        # Candle that hits SL (low <= 2645.0)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2644.0,  # Hits SL
            close=2646.0,
        )
        
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=3,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        assert closed_trade.status != "OPEN"
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.exit_timestamp == candle.timestamp

    def test_short_trade_tp_hit(self):
        """Test short trade exits when TP is hit on current candle."""
        trade = make_trade(
            direction="short",
            entry_price=2650.0,
            stop_loss=2655.0,
            take_profit=2635.0,
        )
        
        # Candle that hits TP (low <= 2635.0)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2640.0,
            high=2641.0,
            low=2634.0,  # Hits TP
            close=2636.0,
        )
        
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=3,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        assert closed_trade.status != "OPEN"
        assert closed_trade.exit_reason == "tp"

    def test_short_trade_sl_hit(self):
        """Test short trade exits when SL is hit on current candle."""
        trade = make_trade(
            direction="short",
            entry_price=2650.0,
            stop_loss=2655.0,
            take_profit=2635.0,
        )
        
        # Candle that hits SL (high >= 2655.0)
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2652.0,
            high=2656.0,  # Hits SL
            low=2651.0,
            close=2653.0,
        )
        
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=3,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        assert closed_trade.status != "OPEN"
        assert closed_trade.exit_reason == "sl"

    def test_sl_priority_over_tp(self):
        """Test that SL takes priority when both are hit in same candle."""
        trade = make_trade(direction="long", entry_price=2650.0, stop_loss=2645.0, take_profit=2665.0)
        
        # Candle that hits both SL and TP
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2650.0,
            high=2666.0,  # Hits TP
            low=2644.0,  # Hits SL
            close=2660.0,
        )
        
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=3,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        # SL should take priority per SOP
        assert closed_trade.exit_reason == "sl"

    def test_no_exit_trade_stays_open(self):
        """Test trade stays open when no exit condition is met."""
        trade = make_trade(direction="long", entry_price=2650.0, stop_loss=2645.0, take_profit=2665.0)
        
        # Normal candle that doesn't hit SL or TP
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2651.0,
            high=2652.0,
            low=2650.5,
            close=2651.5,
        )
        
        result_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=3,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        # Trade should still be open (returns original trade)
        assert result_trade.status == "OPEN"
        assert result_trade.exit_timestamp is None

    def test_continuation_grace_period_skips_sl_tp(self):
        """Test CONTINUATION grace period (6 bars) skips SL/TP checks."""
        trade = make_trade(
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2665.0,
        )
        
        # Candle that would normally hit SL
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2644.0,  # Hits SL
            close=2646.0,
        )
        
        # Within grace period (bar 3 of 6)
        result_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=3,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        # Trade should still be open due to grace period
        assert result_trade.status == "OPEN"

    def test_fade_no_grace_for_sl_tp(self):
        """Test FADE setup has no grace period for SL/TP (immediate enforcement)."""
        trade = make_trade(
            direction="long",
            setup_type="VWAP_FADE",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2665.0,
        )
        
        # Candle that hits SL on bar 1
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2644.0,  # Hits SL
            close=2646.0,
        )
        
        # Bar 1 - FADE uses close-based SL
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=1,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        # Should check close-based SL (close=2646.0 > SL=2645.0, so still open)
        # Actually, for bar 1 fade, close=2646.0 is NOT <= 2645.0, so stays open
        assert closed_trade.status == "OPEN"
        
        # But wick-based after bar 1 should close it
        closed_trade_bar2 = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=2,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        assert closed_trade_bar2.exit_reason == "sl"

    def test_reclaim_grace_period_2_bars(self):
        """Test RECLAIM grace period (2 bars) skips SL/TP checks."""
        trade = make_trade(
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2665.0,
        )
        
        # Candle that would hit SL
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2644.0,  # Hits SL
            close=2646.0,
        )
        
        # Bar 2 - within grace period
        result_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=2,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        assert result_trade.status == "OPEN"
        
        # Bar 3 - outside grace period
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=3,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        assert closed_trade.exit_reason == "sl"

    def test_timeout_continuation(self):
        """Test timeout after 20 bars for CONTINUATION setup."""
        trade = make_trade(
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2665.0,
        )
        
        # Normal candle that doesn't hit SL or TP
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 25, tzinfo=UTC),
            open=2651.0,
            high=2652.0,
            low=2650.5,
            close=2651.5,
        )
        
        # Bar 20 - timeout
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=20,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        assert closed_trade.exit_reason == "timeout"

    def test_timeout_fade(self):
        """Test timeout after 10 bars for FADE setup."""
        trade = make_trade(
            direction="long",
            setup_type="VWAP_FADE",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2665.0,
        )
        
        # Normal candle
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 15, tzinfo=UTC),
            open=2651.0,
            high=2652.0,
            low=2650.5,
            close=2651.5,
        )
        
        # Bar 10 - timeout for fade
        closed_trade = check_trade_exit_single_bar(
            trade=trade,
            candle=candle,
            bars_elapsed=10,
            invalidation_checker=None,
            config=None,
            candle_features=None,
        )
        
        assert closed_trade.exit_reason == "timeout"


