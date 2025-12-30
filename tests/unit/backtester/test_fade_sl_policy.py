"""Regression tests for FADE close-based SL policy.

This test file verifies the FADE-specific SL behavior:
1. FADE bar 1 uses close-based SL (not wick-based)
2. FADE SL can only hit on bar 1 if candle.close breaches SL
3. FADE bar 2+ uses normal wick-based SL
4. CONTINUATION and RECLAIM behavior unchanged

Following TDD principles: tests define expected behavior.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from backtester.entry_model import EntryExecution
from backtester.invalidations import InvalidationChecker
from backtester.simulator import simulate_trade_outcome
from backtester.trade import Trade
from common.types import Candle
from rule_engine.signal import Signal


def make_signal(
    timestamp: datetime,
    setup_type: str,
    direction: str = "long",
) -> Signal:
    """Helper to create test signals."""
    return Signal(
        timestamp=timestamp,
        symbol="GC",
        timeframe="1m",
        direction=direction,
        setup_type=setup_type,
        htf_bias="bullish" if direction == "long" else "bearish",
        score=9.0,
        confidence="A+",
        factors={},
        rationale="Test signal",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )


def make_entry_execution(
    signal: Signal,
    entry_timestamp: datetime,
    entry_price: float,
) -> EntryExecution:
    """Helper to create test entry executions."""
    return EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=entry_timestamp,
        entry_price=entry_price,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )


def make_trade(
    setup_type: str,
    direction: str = "long",
    entry_price: float = 2650.0,
    stop_loss: float = 2645.0,
    take_profit: float = 2665.0,
    entry_timestamp: datetime | None = None,
    ignore_first_retest_bar: bool = False,
) -> Trade:
    """Helper to create test trades."""
    if entry_timestamp is None:
        entry_timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)

    signal = make_signal(entry_timestamp, setup_type, direction)
    entry_execution = make_entry_execution(signal, entry_timestamp, entry_price)

    return Trade(
        trade_id="test-001",
        symbol="GC",
        timeframe="1m",
        entry_execution=entry_execution,
        entry_timestamp=entry_timestamp,
        entry_price=entry_price,
        direction=direction,
        setup_type=setup_type,
        stop_loss=stop_loss,
        take_profit=take_profit,
        sl_rationale="Structure-based",
        tp_rationale="R-multiple based",
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
        ignore_first_retest_bar=ignore_first_retest_bar,
    )


def make_candle(
    timestamp: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    """Helper to create test candles."""
    return Candle(
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )


class TestFadeBar1UsesCloseBasedSL:
    """Test that FADE on bar 1 uses close-based SL, not wick-based."""

    def test_fade_bar1_survives_wick_touching_sl(self):
        """FADE bar 1 should NOT exit if wick touches SL but close is above SL."""
        # Long FADE: entry=2650, SL=2645
        trade = make_trade(
            setup_type="VWAP_FADE",
            direction="long",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2670.0,
        )

        # Bar 1: wick touches SL (low=2644), but close above SL (close=2651)
        candle = make_candle(
            timestamp=trade.entry_timestamp + timedelta(minutes=1),
            open_price=2650.0,
            high=2652.0,
            low=2644.0,  # Wick touches SL
            close=2651.0,  # Close ABOVE SL
        )

        future_candles = pd.DataFrame(
            [
                {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            ],
            index=[candle.timestamp],
        )

        result = simulate_trade_outcome(trade, future_candles)

        # Should NOT hit SL (either remains OPEN or closes for other reasons, but NOT sl)
        assert result.exit_reason != "sl", (
            f"FADE bar 1 should not hit SL when wick touches SL but close is above. "
            f"Got status={result.status}, exit_reason={result.exit_reason}"
        )

    def test_fade_bar1_short_survives_wick_touching_sl(self):
        """FADE short bar 1 should NOT exit if wick touches SL but close is below SL."""
        # Short FADE: entry=2650, SL=2655
        trade = make_trade(
            setup_type="VWAP_FADE",
            direction="short",
            entry_price=2650.0,
            stop_loss=2655.0,
            take_profit=2635.0,
        )

        # Bar 1: wick touches SL (high=2656), but close below SL (close=2649)
        candle = make_candle(
            timestamp=trade.entry_timestamp + timedelta(minutes=1),
            open_price=2650.0,
            high=2656.0,  # Wick touches SL
            low=2648.0,
            close=2649.0,  # Close BELOW SL
        )

        future_candles = pd.DataFrame(
            [
                {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            ],
            index=[candle.timestamp],
        )

        result = simulate_trade_outcome(trade, future_candles)

        # Should NOT hit SL (either remains OPEN or closes for other reasons, but NOT sl)
        assert result.exit_reason != "sl", (
            f"FADE short bar 1 should not hit SL when wick touches SL but close is below. "
            f"Got status={result.status}, exit_reason={result.exit_reason}"
        )


class TestFadeBar1SLHitOnlyOnCloseBreach:
    """Test that FADE SL can only hit on bar 1 if candle.close breaches SL."""

    def test_fade_bar1_sl_hit_when_close_breaches(self):
        """FADE bar 1 SHOULD exit if close breaches SL."""
        # Long FADE: entry=2650, SL=2645
        trade = make_trade(
            setup_type="VWAP_FADE",
            direction="long",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2670.0,
        )

        # Bar 1: close breaches SL (close=2644)
        candle = make_candle(
            timestamp=trade.entry_timestamp + timedelta(minutes=1),
            open_price=2650.0,
            high=2651.0,
            low=2643.0,
            close=2644.0,  # Close BELOW SL
        )

        future_candles = pd.DataFrame(
            [
                {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            ],
            index=[candle.timestamp],
        )

        result = simulate_trade_outcome(trade, future_candles)

        # Should hit SL
        assert result.exit_reason == "sl", (
            f"FADE bar 1 should hit SL when close breaches SL. "
            f"Got status={result.status}, exit_reason={result.exit_reason}"
        )

    def test_fade_bar1_short_sl_hit_when_close_breaches(self):
        """FADE short bar 1 SHOULD exit if close breaches SL."""
        # Short FADE: entry=2650, SL=2655
        trade = make_trade(
            setup_type="VWAP_FADE",
            direction="short",
            entry_price=2650.0,
            stop_loss=2655.0,
            take_profit=2635.0,
        )

        # Bar 1: close breaches SL (close=2656)
        candle = make_candle(
            timestamp=trade.entry_timestamp + timedelta(minutes=1),
            open_price=2650.0,
            high=2657.0,
            low=2649.0,
            close=2656.0,  # Close ABOVE SL
        )

        future_candles = pd.DataFrame(
            [
                {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            ],
            index=[candle.timestamp],
        )

        result = simulate_trade_outcome(trade, future_candles)

        # Should hit SL
        assert result.exit_reason == "sl", (
            f"FADE short bar 1 should hit SL when close breaches SL. "
            f"Got status={result.status}, exit_reason={result.exit_reason}"
        )


class TestFadeBar2UsesWickBasedSL:
    """Test that FADE bar 2+ uses normal wick-based SL."""

    def test_fade_bar2_uses_wick_sl(self):
        """FADE bar 2 should use wick-based SL (normal behavior)."""
        # Long FADE: entry=2650, SL=2645
        trade = make_trade(
            setup_type="VWAP_FADE",
            direction="long",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2670.0,
        )

        # Bar 1: safe (close above SL)
        bar1 = make_candle(
            timestamp=trade.entry_timestamp + timedelta(minutes=1),
            open_price=2650.0,
            high=2651.0,
            low=2649.0,
            close=2651.0,
        )

        # Bar 2: wick touches SL (low=2644), close above SL (close=2652)
        bar2 = make_candle(
            timestamp=trade.entry_timestamp + timedelta(minutes=2),
            open_price=2651.0,
            high=2653.0,
            low=2644.0,  # Wick touches SL
            close=2652.0,  # Close ABOVE SL
        )

        future_candles = pd.DataFrame(
            [
                {
                    "open": bar1.open,
                    "high": bar1.high,
                    "low": bar1.low,
                    "close": bar1.close,
                    "volume": bar1.volume,
                },
                {
                    "open": bar2.open,
                    "high": bar2.high,
                    "low": bar2.low,
                    "close": bar2.close,
                    "volume": bar2.volume,
                },
            ],
            index=[bar1.timestamp, bar2.timestamp],
        )

        result = simulate_trade_outcome(trade, future_candles)

        # Should hit SL on bar 2 (wick-based)
        assert result.exit_reason == "sl", (
            f"FADE bar 2 should use wick-based SL and hit on wick. "
            f"Got status={result.status}, exit_reason={result.exit_reason}"
        )
        assert (
            result.duration_bars == 2
        ), f"Expected exit on bar 2, got bar {result.duration_bars}"


class TestContinuationSLUnchanged:
    """Verify CONTINUATION still skips SL for 6 bars."""

    def test_continuation_skips_sl_for_6_bars(self):
        """CONTINUATION should skip SL checks for first 6 bars."""
        # Long CONTINUATION: entry=2650, SL=2645
        trade = make_trade(
            setup_type="DXY_CONTINUATION",
            direction="long",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2675.0,
        )

        # Create 6 bars, all with wick touching SL
        future_candles_data = []
        for i in range(6):
            timestamp = trade.entry_timestamp + timedelta(minutes=i + 1)
            future_candles_data.append(
                {
                    "open": 2650.0,
                    "high": 2651.0,
                    "low": 2644.0,  # Wick touches SL every bar
                    "close": 2650.0,
                    "volume": 1000,
                }
            )

        future_candles = pd.DataFrame(
            future_candles_data,
            index=[trade.entry_timestamp + timedelta(minutes=i + 1) for i in range(6)],
        )

        result = simulate_trade_outcome(trade, future_candles)

        # Should NOT hit SL during first 5 bars (bars_elapsed < 6)
        # Bar 6 is allowed to hit SL (bars_elapsed == 6, skip_sl_tp = 6 < 6 = False)
        if result.duration_bars < 6:
            assert result.exit_reason != "sl", (
                f"CONTINUATION should skip SL for first 5 bars (bars_elapsed < 6). "
                f"Got exit_reason={result.exit_reason} on bar {result.duration_bars}"
            )


class TestReclaimSLUnchanged:
    """Verify RECLAIM still uses retest protection."""

    def test_reclaim_skips_sl_on_bar1_with_retest_protection(self):
        """RECLAIM with retest protection should skip SL on bar 1."""
        # Long RECLAIM: entry=2650, SL=2645
        trade = make_trade(
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=2650.0,
            stop_loss=2645.0,
            take_profit=2665.0,
            ignore_first_retest_bar=True,  # Retest protection enabled
        )

        # Bar 1: wick touches SL
        candle = make_candle(
            timestamp=trade.entry_timestamp + timedelta(minutes=1),
            open_price=2650.0,
            high=2651.0,
            low=2644.0,  # Wick touches SL
            close=2650.0,
        )

        future_candles = pd.DataFrame(
            [
                {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            ],
            index=[candle.timestamp],
        )

        result = simulate_trade_outcome(trade, future_candles)

        # Should NOT hit SL on bar 1 due to retest protection
        assert result.exit_reason != "sl", (
            f"RECLAIM with retest protection should skip SL on bar 1. "
            f"Got status={result.status}, exit_reason={result.exit_reason}"
        )








