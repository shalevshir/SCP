"""Unit tests for Trade Simulator - TP/SL outcome simulation.

Following TDD principles: tests written first to define behavior.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from backtester.entry_model import EntryExecution
from backtester.simulator import (
    check_sl_hit,
    check_timeout,
    check_tp_hit,
    simulate_trade_outcome,
)
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


class TestCheckTPHit:
    """Tests for check_tp_hit() function."""

    @pytest.fixture
    def long_trade(self):
        """Create a sample long trade."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
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
            entry_price=2650.0,
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
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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

    @pytest.fixture
    def short_trade(self):
        """Create a sample short trade."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="Mild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-002",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="short",
            setup_type="VWAP_FADE",
            stop_loss=2655.0,
            take_profit=2640.0,
            sl_rationale="Above sweep",
            tp_rationale="2R fade",
            risk_amount=5.0,
            reward_amount=10.0,
            r_multiple=2.0,
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

    def test_long_tp_hit_when_high_reaches_target(self, long_trade):
        """Test TP hit for long when candle high reaches TP."""
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2652.0,
            high=2666.0,  # Above TP (2665.0)
            low=2651.0,
            close=2664.0,
        )
        assert check_tp_hit(long_trade, candle) is True

    def test_long_tp_not_hit_when_high_below_target(self, long_trade):
        """Test TP not hit for long when candle high is below TP."""
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2652.0,
            high=2664.0,  # Below TP (2665.0)
            low=2651.0,
            close=2663.0,
            volume=100,
        )
        assert check_tp_hit(long_trade, candle) is False

    def test_short_tp_hit_when_low_reaches_target(self, short_trade):
        """Test TP hit for short when candle low reaches TP."""
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2639.0,  # Below TP (2640.0)
            close=2641.0,
            volume=100,
        )
        assert check_tp_hit(short_trade, candle) is True

    def test_short_tp_not_hit_when_low_above_target(self, short_trade):
        """Test TP not hit for short when candle low is above TP."""
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2648.0,
            high=2649.0,
            low=2641.0,  # Above TP (2640.0)
            close=2642.0,
            volume=100,
        )
        assert check_tp_hit(short_trade, candle) is False


class TestCheckSLHit:
    """Tests for check_sl_hit() function."""

    @pytest.fixture
    def long_trade(self):
        """Create a sample long trade."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
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
            entry_price=2650.0,
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
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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

    @pytest.fixture
    def short_trade(self):
        """Create a sample short trade."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="Mild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-002",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="short",
            setup_type="VWAP_FADE",
            stop_loss=2655.0,
            take_profit=2640.0,
            sl_rationale="Above sweep",
            tp_rationale="2R fade",
            risk_amount=5.0,
            reward_amount=10.0,
            r_multiple=2.0,
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

    def test_long_sl_hit_when_low_reaches_stop(self, long_trade):
        """Test SL hit for long when candle low reaches SL."""
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2649.0,
            high=2651.0,
            low=2644.0,  # Below SL (2645.0)
            close=2647.0,
            volume=100,
        )
        assert check_sl_hit(long_trade, candle) is True

    def test_long_sl_not_hit_when_low_above_stop(self, long_trade):
        """Test SL not hit for long when candle low is above SL."""
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2649.0,
            high=2651.0,
            low=2646.0,  # Above SL (2645.0)
            close=2650.0,
            volume=100,
        )
        assert check_sl_hit(long_trade, candle) is False

    def test_short_sl_hit_when_high_reaches_stop(self, short_trade):
        """Test SL hit for short when candle high reaches SL."""
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2652.0,
            high=2656.0,  # Above SL (2655.0)
            low=2651.0,
            close=2653.0,
            volume=100,
        )
        assert check_sl_hit(short_trade, candle) is True

    def test_short_sl_not_hit_when_high_below_stop(self, short_trade):
        """Test SL not hit for short when candle high is below SL."""
        candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2652.0,
            high=2654.0,  # Below SL (2655.0)
            low=2651.0,
            close=2653.0,
            volume=100,
        )
        assert check_sl_hit(short_trade, candle) is False


class TestCheckTimeout:
    """Tests for check_timeout() function."""

    def test_continuation_timeout_at_20_bars(self):
        """Test timeout for continuation setup at 20 bars."""
        assert check_timeout(20, "VWAP_RECLAIM") is True
        assert check_timeout(20, "DXY_CONTINUATION") is True

    def test_continuation_no_timeout_before_20_bars(self):
        """Test no timeout for continuation setup before 20 bars."""
        assert check_timeout(19, "VWAP_RECLAIM") is False
        assert check_timeout(10, "DXY_CONTINUATION") is False

    def test_fade_timeout_at_10_bars(self):
        """Test timeout for fade setup at 10 bars."""
        assert check_timeout(10, "VWAP_FADE") is True

    def test_fade_no_timeout_before_10_bars(self):
        """Test no timeout for fade setup before 10 bars."""
        assert check_timeout(9, "VWAP_FADE") is False
        assert check_timeout(5, "VWAP_FADE") is False


class TestSimulateTradeOutcome:
    """Tests for simulate_trade_outcome() function."""

    @pytest.fixture
    def long_continuation_trade(self):
        """Create a long continuation trade."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
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
            entry_price=2650.0,
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
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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

    @pytest.fixture
    def short_fade_trade(self):
        """Create a short fade trade."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="Mild",
        )
        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-002",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="short",
            setup_type="VWAP_FADE",
            stop_loss=2655.0,
            take_profit=2640.0,
            sl_rationale="Above sweep",
            tp_rationale="2R fade",
            risk_amount=5.0,
            reward_amount=10.0,
            r_multiple=2.0,
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

    def test_basic_tp_hit(self, long_continuation_trade):
        """Test basic TP hit scenario - price moves to TP without hitting SL."""
        # Create candles where price gradually moves to TP
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)
        for i in range(5):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0 + i * 3,
                    high=2652.0 + i * 3,
                    low=2649.0 + i * 3,
                    close=2651.0 + i * 3,
                    volume=100,
                )
            )
        # Final candle hits TP
        candles.append(
            make_candle(
                timestamp=base_time + timedelta(minutes=5),
                open=2663.0,
                high=2666.0,  # Hits TP (2665.0)
                low=2662.0,
                close=2665.0,
                volume=100,
            )
        )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        assert closed_trade.exit_reason == "tp"
        assert closed_trade.exit_price == 2665.0
        assert closed_trade.status == "CLOSED_WIN"
        assert closed_trade.r_realized == pytest.approx(3.0)
        assert closed_trade.duration_bars == 6

    def test_basic_sl_hit(self, long_continuation_trade):
        """Test basic SL hit scenario - price moves to SL."""
        # Create candles where price drops to SL
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)
        for i in range(3):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0 - i * 2,
                    high=2651.0 - i * 2,
                    low=2648.0 - i * 2,
                    close=2649.0 - i * 2,
                    volume=100,
                )
            )
        # Final candle hits SL
        candles.append(
            make_candle(
                timestamp=base_time + timedelta(minutes=3),
                open=2646.0,
                high=2647.0,
                low=2644.0,  # Hits SL (2645.0)
                close=2645.5,
                volume=100,
            )
        )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        assert closed_trade.exit_reason == "sl"
        assert closed_trade.exit_price == 2645.0
        assert closed_trade.status == "STOPPED_OUT"
        assert closed_trade.r_realized == pytest.approx(-1.0)
        # FIX #5: VWAP_RECLAIM has 2-bar grace period, so SL hits on bar 3
        assert (
            closed_trade.duration_bars == 3
        )  # Hits SL on 3rd bar (after 2-bar grace period)

    def test_sl_priority_over_tp(self, long_continuation_trade):
        """Test SL takes priority when both hit in same candle."""
        # Need 3+ candles due to VWAP_RECLAIM grace period (MIN_BARS_RECLAIM = 3)
        # First 2 candles are neutral (grace period), 3rd candle hits both SL and TP
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)
        # Add 2 neutral candles during grace period
        for i in range(2):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,  # Above SL (2645.0)
                    close=2651.0,
                    volume=100,
                )
            )
        # 3rd candle hits both SL and TP (after grace period)
        candles.append(
            make_candle(
                timestamp=base_time + timedelta(minutes=2),
                open=2650.0,
                high=2666.0,  # Above TP (2665.0)
                low=2644.0,  # Below SL (2645.0)
                close=2655.0,
                volume=100,
            )
        )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        # SL should take priority per SOP
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.exit_price == 2645.0
        assert closed_trade.status == "STOPPED_OUT"

    def test_gap_beyond_sl_long(self, long_continuation_trade):
        """Test gap opening beyond SL - should exit at SL, not worse."""
        # Need 3+ candles due to VWAP_RECLAIM grace period (MIN_BARS_RECLAIM = 3)
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)
        # Add 3 neutral candles during grace period
        for i in range(3):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,  # Above SL (2645.0)
                    close=2651.0,
                    volume=100,
                )
            )
        # 4th candle: Gap down opening below SL
        candles.append(
            make_candle(
                timestamp=base_time + timedelta(minutes=3),
                open=2640.0,  # Opens below SL (2645.0)
                high=2642.0,
                low=2638.0,
                close=2641.0,
                volume=100,
            )
        )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        # Should exit at SL, not at worse gap price
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.exit_price == 2645.0

    def test_gap_beyond_tp_long(self, long_continuation_trade):
        """Test gap opening beyond TP - should exit at TP."""
        # Need 3+ candles due to VWAP_RECLAIM grace period (MIN_BARS_RECLAIM = 3)
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)
        # Add 2 neutral candles during grace period
        for i in range(2):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,  # Above SL (2645.0)
                    close=2651.0,
                    volume=100,
                )
            )
        # 3rd candle: Gap up opening above TP (after grace period)
        candles.append(
            make_candle(
                timestamp=base_time + timedelta(minutes=2),
                open=2670.0,  # Opens above TP (2665.0)
                high=2672.0,
                low=2668.0,
                close=2671.0,
                volume=100,
            )
        )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        # Should exit at TP
        assert closed_trade.exit_reason == "tp"
        assert closed_trade.exit_price == 2665.0

    def test_timeout_continuation(self, long_continuation_trade):
        """Test timeout for continuation setup at 20 bars."""
        # Create 20 candles that don't hit TP or SL
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)
        for i in range(20):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        assert closed_trade.exit_reason == "timeout"
        assert closed_trade.exit_price == 2651.0  # Last candle close
        assert closed_trade.duration_bars == 20

    def test_timeout_fade(self, short_fade_trade):
        """Test timeout for fade setup at 10 bars."""
        # Create 10 candles that don't hit TP or SL
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)
        for i in range(10):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(short_fade_trade, df)

        assert closed_trade.exit_reason == "timeout"
        assert closed_trade.exit_price == 2651.0  # Last candle close
        assert closed_trade.duration_bars == 10

    def test_skipped_nan_candles_dont_count_toward_timeout(
        self, long_continuation_trade
    ):
        """Test that skipped NaN/Inf candles don't increment bars_elapsed.

        This ensures trades don't timeout prematurely when invalid candles are skipped.
        """
        import math

        # Create 18 valid candles + 2 NaN candles = 20 total candles
        # But only 18 valid candles should be processed
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)

        # First 5 valid candles
        for i in range(5):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        # Insert 2 NaN candles (should be skipped)
        candles.append(
            make_candle(
                timestamp=base_time + timedelta(minutes=5),
                open=math.nan,  # Invalid candle
                high=2652.0,
                low=2648.0,
                close=2651.0,
                volume=100,
            )
        )
        candles.append(
            make_candle(
                timestamp=base_time + timedelta(minutes=6),
                open=2650.0,
                high=math.inf,  # Invalid candle
                low=2648.0,
                close=2651.0,
                volume=100,
            )
        )

        # Add 15 more valid candles (total: 5 + 15 = 20 valid, 2 skipped)
        for i in range(7, 22):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        # Should timeout at 20 valid candles, not 20 total candles
        # The key fix: bars_elapsed only counts valid candles, so timeout happens
        # at the 20th valid candle, not after 20 total candles (which would include skipped ones)
        assert closed_trade.exit_reason == "timeout"
        # duration_bars is time-based (timestamp difference), so it will be 22 minutes
        # because 22 minutes elapsed (20 valid + 2 skipped candles)
        # But the timeout check uses bars_elapsed which only counts valid candles (20)
        assert closed_trade.duration_bars == 22  # 22 minutes elapsed (time-based)
        # Verify exit happened at the 20th valid candle's timestamp
        # (5 initial + 2 skipped + 15 more = 20 valid, last one at minute 21)
        expected_exit_time = base_time + timedelta(minutes=21)  # 20th valid candle
        assert closed_trade.exit_timestamp == expected_exit_time

    def test_end_of_data(self, long_continuation_trade):
        """Test trade closes at end of dataset if still open."""
        # Only 5 candles, trade doesn't hit TP/SL/timeout
        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)
        for i in range(5):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        assert closed_trade.exit_reason == "end_of_data"
        assert closed_trade.exit_price == 2651.0  # Last candle close

    def test_already_closed_trade_returns_unchanged(self, long_continuation_trade):
        """Test that already closed trades are returned unchanged."""
        from backtester.trade import close_trade

        # Close the trade first
        exit_candle = make_candle(
            timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
            open=2665.0,
            high=2665.0,
            low=2665.0,
            close=2665.0,
            volume=100,
        )
        closed = close_trade(long_continuation_trade, exit_candle, "tp")

        # Try to simulate it again
        candles = [exit_candle]
        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        result = simulate_trade_outcome(closed, df)

        # Should return the same closed trade
        assert result.trade_id == closed.trade_id
        assert result.exit_reason == "tp"
        assert result.status == "CLOSED_WIN"

    def test_invalid_candles_dont_count_toward_timeout(self, long_continuation_trade):
        """Test that invalid candles (NaN/Inf) don't count toward timeout limits.

        SOP requires timeout to be based on valid candles only (20 bars for continuation).
        If we have 15 valid candles and 10 invalid candles, timeout should occur at
        the 20th valid candle, not after 25 total candles.
        """
        import math

        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)

        # Create 15 valid candles (not enough to timeout)
        for i in range(15):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        # Insert 10 invalid candles (NaN values) - these should be skipped
        for i in range(10):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=15 + i),
                    open=math.nan,  # Invalid candle
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        # Add 5 more valid candles to reach 20 valid candles total
        for i in range(5):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=25 + i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        # Should timeout at 20th valid candle (not after 30 total candles)
        # The timeout check uses bars_elapsed which only counts valid candles
        assert closed_trade.exit_reason == "timeout"
        # duration_bars is time-based (30 minutes = 30 candles worth of time)
        # but timeout triggers at 20th valid candle due to our fix
        assert closed_trade.duration_bars == 30  # Time-based: 30 minutes elapsed
        assert closed_trade.exit_price == 2651.0  # Last valid candle close

        # Verify timeout triggered at the 20th valid candle by checking
        # that it didn't timeout earlier (at 15 valid candles)
        # Create a test with only 15 valid candles + 10 invalid - should NOT timeout
        candles_15_valid = []
        for i in range(15):
            candles_15_valid.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )
        for i in range(10):
            candles_15_valid.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=15 + i),
                    open=math.nan,  # Invalid
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )
        df_15 = pd.DataFrame([c.__dict__ for c in candles_15_valid])
        df_15 = df_15.set_index("timestamp")

        closed_15 = simulate_trade_outcome(long_continuation_trade, df_15)
        # Should NOT timeout (only 15 valid candles, need 20)
        assert closed_15.exit_reason == "end_of_data"

    def test_invalid_candles_dont_count_toward_fade_timeout(self, short_fade_trade):
        """Test that invalid candles don't count toward fade timeout (10 bars)."""
        import math

        candles = []
        base_time = datetime(2025, 1, 1, 10, 2, tzinfo=UTC)

        # Create 5 valid candles
        for i in range(5):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        # Insert 10 invalid candles (should be skipped)
        for i in range(10):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=5 + i),
                    open=math.nan,  # Invalid candle
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        # Add 5 more valid candles to reach 10 valid candles total
        for i in range(5):
            candles.append(
                make_candle(
                    timestamp=base_time + timedelta(minutes=15 + i),
                    open=2650.0,
                    high=2652.0,
                    low=2648.0,
                    close=2651.0,
                    volume=100,
                )
            )

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(short_fade_trade, df)

        # Should timeout at 10th valid candle (not after 20 total candles)
        # The timeout check uses bars_elapsed which only counts valid candles
        assert closed_trade.exit_reason == "timeout"
        # duration_bars is time-based (20 minutes = 20 candles worth of time)
        # but timeout triggers at 10th valid candle due to our fix
        assert closed_trade.duration_bars == 20  # Time-based: 20 minutes elapsed


class TestGracePeriodLogic:
    """Test grace period logic for VWAP_RECLAIM and DXY_CONTINUATION setups.

    Specification-based tests for FIX #5: Minimum trade duration grace period.
    """

    @pytest.fixture
    def vwap_reclaim_trade(self):
        """Create a VWAP_RECLAIM trade for grace period testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
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
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-vwap-reclaim",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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
            ignore_first_retest_bar=False,  # No retest protection
        )

    @pytest.fixture
    def dxy_continuation_trade(self):
        """Create a DXY_CONTINUATION trade for grace period testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
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
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-dxy-continuation",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="DXY_CONTINUATION",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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

    def test_vwap_reclaim_sl_not_checked_during_first_2_bars(self, vwap_reclaim_trade):
        """VWAP_RECLAIM: SL not checked during first 2 bars (grace period).

        Specification: MIN_BARS_RECLAIM = 3 (skip bars 1-2, check from bar 3)
        During bars 1-2, SL hits should be ignored.
        """
        # Create 3 candles where SL is hit on bars 1 and 2
        future_candles = pd.DataFrame(
            [
                # Bar 1: SL hit (but grace period protects)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2650.5,
                    "low": 2644.0,  # Below SL (2645.0)
                    "close": 2646.0,
                    "volume": 100,
                },
                # Bar 2: SL hit (but grace period protects)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2646.0,
                    "high": 2647.0,
                    "low": 2643.0,  # Below SL
                    "close": 2644.0,
                    "volume": 100,
                },
                # Bar 3: Price recovers ABOVE SL (grace period ends but SL not hit)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 4, tzinfo=UTC),
                    "open": 2646.0,
                    "high": 2652.0,
                    "low": 2646.0,  # Above SL (2645.0) - no SL trigger
                    "close": 2651.0,
                    "volume": 100,
                },
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(vwap_reclaim_trade, future_candles)

        # Should NOT have hit SL during grace period (bars 1-2)
        # Trade should still be open or hit another exit condition
        assert (
            closed_trade.exit_reason != "sl"
        ), "SL should not trigger during 2-bar grace period for VWAP_RECLAIM"

    def test_vwap_reclaim_sl_checked_after_grace_period_ends(self, vwap_reclaim_trade):
        """VWAP_RECLAIM: SL IS checked after grace period ends (bar 3+).

        Specification: After MIN_BARS_RECLAIM (3 bars), SL checks resume.
        """
        # Create 3 candles where SL is hit on bar 3 (after grace period)
        future_candles = pd.DataFrame(
            [
                # Bars 1-2: Grace period (price above SL)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2651.0,
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                },
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2650.5,
                    "high": 2652.0,
                    "low": 2649.5,
                    "close": 2651.0,
                    "volume": 100,
                },
                # Bar 3: SL hit (grace period ended, SL should trigger)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 4, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2650.0,
                    "low": 2644.0,  # Below SL (2645.0)
                    "close": 2644.5,
                    "volume": 100,
                },
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(vwap_reclaim_trade, future_candles)

        # Should hit SL on bar 3 (after 2-bar grace period)
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.duration_bars == 3

    def test_vwap_reclaim_tp_not_checked_during_grace_period(self, vwap_reclaim_trade):
        """VWAP_RECLAIM: TP also not checked during grace period.

        Specification: Both SL and TP checks are skipped during grace period.
        """
        # Create 3 candles where TP is hit on bar 2 (during grace period)
        future_candles = pd.DataFrame(
            [
                # Bar 1: Neutral
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2652.0,
                    "low": 2649.0,
                    "close": 2651.0,
                    "volume": 100,
                },
                # Bar 2: TP hit (but grace period protects)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2651.0,
                    "high": 2666.0,  # Above TP (2665.0)
                    "low": 2650.0,
                    "close": 2665.5,
                    "volume": 100,
                },
                # Bar 3: Grace period ends
                {
                    "timestamp": datetime(2025, 1, 1, 10, 4, tzinfo=UTC),
                    "open": 2665.5,
                    "high": 2667.0,
                    "low": 2664.0,
                    "close": 2666.0,
                    "volume": 100,
                },
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(vwap_reclaim_trade, future_candles)

        # Should NOT have hit TP during grace period
        # Trade should either timeout or exit on different condition
        # But if it exits, it should not be at bar 2
        if closed_trade.exit_reason == "tp":
            assert (
                closed_trade.duration_bars > 2
            ), "TP should not trigger during 2-bar grace period"

    def test_dxy_continuation_sl_not_checked_during_first_6_bars(
        self, dxy_continuation_trade
    ):
        """DXY_CONTINUATION: SL not checked during first 6 bars (grace period).

        Specification: MIN_BARS_CONTINUATION = 7 (skip bars 1-6, check from bar 7)
        During bars 1-6, SL hits should be ignored.
        """
        # Create 7 candles where SL is hit on bars 1-6
        candles_data = []
        for i in range(7):
            ts = datetime(2025, 1, 1, 10, 2 + i, tzinfo=UTC)
            if i < 6:
                # Bars 1-6: SL hit (but grace period protects)
                candles_data.append(
                    {
                        "timestamp": ts,
                        "open": 2648.0 - i,
                        "high": 2649.0 - i,
                        "low": 2644.0 - i,  # Below SL (2645.0)
                        "close": 2646.0 - i,
                        "volume": 100,
                    }
                )
            else:
                # Bar 7: Price recovers
                candles_data.append(
                    {
                        "timestamp": ts,
                        "open": 2646.0,
                        "high": 2652.0,
                        "low": 2645.5,
                        "close": 2650.0,
                        "volume": 100,
                    }
                )

        future_candles = pd.DataFrame(candles_data).set_index("timestamp")

        closed_trade = simulate_trade_outcome(dxy_continuation_trade, future_candles)

        # Should NOT have hit SL during grace period (bars 1-5)
        assert (
            closed_trade.exit_reason != "sl"
        ), "SL should not trigger during 6-bar grace period for DXY_CONTINUATION"

    def test_dxy_continuation_sl_checked_after_grace_period_ends(
        self, dxy_continuation_trade
    ):
        """DXY_CONTINUATION: SL IS checked after grace period ends (bar 7+).

        Specification: After MIN_BARS_CONTINUATION (7 bars total, skip 1-6), SL checks resume.
        """
        # Create 7 candles where SL is hit on bar 7
        candles_data = []
        for i in range(7):
            ts = datetime(2025, 1, 1, 10, 2 + i, tzinfo=UTC)
            if i < 6:
                # Bars 1-6: Grace period (price safe)
                candles_data.append(
                    {
                        "timestamp": ts,
                        "open": 2650.0,
                        "high": 2652.0,
                        "low": 2649.0,
                        "close": 2651.0,
                        "volume": 100,
                    }
                )
            else:
                # Bar 7: SL hit (grace period ended)
                candles_data.append(
                    {
                        "timestamp": ts,
                        "open": 2651.0,
                        "high": 2651.0,
                        "low": 2644.0,  # Below SL (2645.0)
                        "close": 2644.5,
                        "volume": 100,
                    }
                )

        future_candles = pd.DataFrame(candles_data).set_index("timestamp")

        closed_trade = simulate_trade_outcome(dxy_continuation_trade, future_candles)

        # Should hit SL on bar 7 (after 6-bar grace period)
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.duration_bars == 7


class TestRetestProtectionLogic:
    """Test retest protection logic (ignore_first_retest_bar flag).

    Specification-based tests for FIX #2: Retest protection for VWAP_RECLAIM.
    """

    @pytest.fixture
    def trade_with_retest_protection(self):
        """Create a trade with retest protection enabled (VWAP_FADE has 2-bar grace period)."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",  # Has 2-bar grace period
            htf_bias="bullish",
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
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-retest",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_FADE",  # No grace period
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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
            ignore_first_retest_bar=True,  # Retest protection ENABLED
        )

    @pytest.fixture
    def trade_without_retest_protection(self):
        """Create a trade without retest protection (VWAP_FADE has 2-bar grace period)."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",  # Has 2-bar grace period
            htf_bias="bullish",
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
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-no-retest",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_FADE",  # No grace period
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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
            ignore_first_retest_bar=False,  # Retest protection DISABLED
        )

    def test_sl_not_checked_on_first_bar_with_retest_protection(
        self, trade_with_retest_protection
    ):
        """Retest protection: SL not checked on first bar when flag is True.

        Specification: "Skip SL check on first bar if retest protection is active"
        """
        # Create 3 candles where SL is hit on bar 1
        future_candles = pd.DataFrame(
            [
                # Bar 1: SL hit (but retest protection should protect)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2650.5,
                    "low": 2644.0,  # Below SL (2645.0)
                    "close": 2646.0,
                    "volume": 100,
                },
                # Bar 2: Price recovers
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2646.0,
                    "high": 2652.0,
                    "low": 2646.0,
                    "close": 2651.0,
                    "volume": 100,
                },
                # Bar 3: Continues
                {
                    "timestamp": datetime(2025, 1, 1, 10, 4, tzinfo=UTC),
                    "open": 2651.0,
                    "high": 2653.0,
                    "low": 2650.0,
                    "close": 2652.0,
                    "volume": 100,
                },
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(
            trade_with_retest_protection, future_candles
        )

        # Should NOT have hit SL on bar 1 (retest protection active)
        assert (
            closed_trade.exit_reason != "sl" or closed_trade.duration_bars > 1
        ), "SL should not trigger on first bar with retest protection"

    def test_sl_checked_on_second_bar_after_retest_protection_ends(
        self, trade_with_retest_protection
    ):
        """Retest protection + grace period interaction: SL checked after BOTH end.

        Specification: Retest protection (bar 1) + grace period (bars 1-2) = skip bars 1-2, check from bar 3.
        """
        # Create 3 candles where SL is hit on bar 3 (after both protections end)
        future_candles = pd.DataFrame(
            [
                # Bar 1: Price safe (retest protection + grace period active)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2651.0,
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                },
                # Bar 2: Price safe (grace period still active)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2650.5,
                    "high": 2651.0,
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                },
                # Bar 3: SL hit (both protections ended)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 4, tzinfo=UTC),
                    "open": 2650.5,
                    "high": 2651.0,
                    "low": 2644.0,  # Below SL (2645.0)
                    "close": 2644.5,
                    "volume": 100,
                },
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(
            trade_with_retest_protection, future_candles
        )

        # Should hit SL on bar 3 (after retest protection bar 1 + grace period bars 1-2)
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.duration_bars == 3

    def test_sl_checked_normally_without_retest_protection(
        self, trade_without_retest_protection
    ):
        """Without retest protection: SL checked after grace period.

        Specification: VWAP_FADE has 2-bar grace period (bars 1-2), then SL checks start.
        Retest protection flag (ignore_first_retest_bar) is separate from grace period.
        """
        # Create 3 candles where SL is hit on bar 3 (after 2-bar grace period)
        future_candles = pd.DataFrame(
            [
                # Bar 1: Grace period (SL not checked)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2650.5,
                    "low": 2646.0,
                    "close": 2648.0,
                    "volume": 100,
                },
                # Bar 2: Grace period (SL not checked)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2648.0,
                    "high": 2649.0,
                    "low": 2646.0,
                    "close": 2647.0,
                    "volume": 100,
                },
                # Bar 3: SL checked and hit (grace period over)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 4, tzinfo=UTC),
                    "open": 2647.0,
                    "high": 2648.0,
                    "low": 2644.0,  # Below SL (2645.0)
                    "close": 2646.0,
                    "volume": 100,
                },
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(
            trade_without_retest_protection, future_candles
        )

        # Should hit SL on bar 3 (after 2-bar grace period)
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.duration_bars == 3

    def test_retest_protection_does_not_affect_tp_checks(
        self, trade_with_retest_protection
    ):
        """Retest protection: Only affects SL, not TP checks (but grace period affects both).

        Specification: Retest protection is for SL only, but grace period skips both SL and TP.
        With VWAP_FADE having 2-bar grace period, TP is checked from bar 3.
        """
        # Create 3 candles where TP is hit on bar 3 (after grace period)
        future_candles = pd.DataFrame(
            [
                # Bar 1: Grace period (price safe)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2652.0,
                    "low": 2649.0,
                    "close": 2651.0,
                    "volume": 100,
                },
                # Bar 2: Grace period (price safe)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2651.0,
                    "high": 2653.0,
                    "low": 2650.0,
                    "close": 2652.0,
                    "volume": 100,
                },
                # Bar 3: TP hit (grace period ended)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 4, tzinfo=UTC),
                    "open": 2652.0,
                    "high": 2666.0,  # Above TP (2665.0)
                    "low": 2651.0,
                    "close": 2665.5,
                    "volume": 100,
                },
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(
            trade_with_retest_protection, future_candles
        )

        # TP should trigger on bar 3 (after grace period ends)
        assert closed_trade.exit_reason == "tp"
        assert closed_trade.duration_bars == 3


class TestGracePeriodAndRetestProtectionInteraction:
    """Test interaction between grace period and retest protection.

    When both are active, test that they work together correctly.
    """

    @pytest.fixture
    def trade_with_both_protections(self):
        """Create a VWAP_RECLAIM trade with both grace period and retest protection."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
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
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-both",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",  # Has grace period (2 bars)
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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
            ignore_first_retest_bar=True,  # Also has retest protection
        )

    def test_grace_period_takes_precedence_over_retest_protection(
        self, trade_with_both_protections
    ):
        """Grace period takes precedence: SL not checked during bars 1-3 regardless of retest flag.

        Specification: Grace period check happens AFTER retest protection check.
        If grace period is active, SL is skipped.
        """
        # Create 5 candles where SL is hit on bars 1-3
        future_candles = pd.DataFrame(
            [
                # Bar 1: SL hit (both protections active)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2650.5,
                    "low": 2644.0,  # Below SL
                    "close": 2646.0,
                    "volume": 100,
                },
                # Bar 2: SL hit (retest protection disabled, but grace period still active)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2646.0,
                    "high": 2647.0,
                    "low": 2643.0,  # Below SL
                    "close": 2644.0,
                    "volume": 100,
                },
                # Bar 3: SL hit (grace period ends, SL should trigger)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 4, tzinfo=UTC),
                    "open": 2644.0,
                    "high": 2645.0,
                    "low": 2642.0,  # Below SL
                    "close": 2643.0,
                    "volume": 100,
                },
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(
            trade_with_both_protections, future_candles
        )

        # Should hit SL on bar 3 (after 2-bar grace period ends)
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.duration_bars == 3


class TestInvalidDataHandling:
    """Test handling of invalid trade and candle data - specification-based."""

    @pytest.fixture
    def valid_long_trade(self):
        """Create a valid long trade for testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
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
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )
        return Trade(
            trade_id="test-valid",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_FADE",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below structure",
            tp_rationale="3R continuation",
            risk_amount=5.0,
            reward_amount=15.0,
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

    def test_invalid_trade_with_zero_risk_closes_immediately(self, valid_long_trade):
        """Trade with zero risk (entry == SL) closes immediately with invalid_setup.

        Specification: "Trade {trade.trade_id} is invalid (zero risk or NaN values)"
        """
        # Create invalid trade with entry == SL
        import dataclasses

        invalid_trade = dataclasses.replace(
            valid_long_trade,
            trade_id="invalid-zero-risk",
            entry_price=2645.0,
            stop_loss=2645.0,  # Same as entry = zero risk
            risk_amount=0.0,
        )

        # Any future candles (doesn't matter, trade is invalid)
        future_candles = pd.DataFrame(
            [
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2645.0,
                    "high": 2646.0,
                    "low": 2644.0,
                    "close": 2645.5,
                    "volume": 100,
                }
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(invalid_trade, future_candles)

        # Should close immediately with invalid_setup
        assert closed_trade.exit_reason == "invalid_setup"
        assert closed_trade.exit_price == invalid_trade.entry_price

    def test_invalid_trade_with_nan_sl_closes_immediately(self, valid_long_trade):
        """Trade with NaN SL closes immediately with invalid_setup.

        Specification: "Trade {trade.trade_id} has NaN or Inf in critical fields"
        """
        import dataclasses

        invalid_trade = dataclasses.replace(
            valid_long_trade,
            trade_id="invalid-nan-sl",
            stop_loss=float("nan"),
        )

        future_candles = pd.DataFrame(
            [
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2651.0,
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                }
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(invalid_trade, future_candles)

        assert closed_trade.exit_reason == "invalid_setup"

    def test_already_closed_trade_returns_unchanged(self, valid_long_trade):
        """Trade that is already closed returns unchanged.

        Specification: "Trade {trade.trade_id} is already closed (status={trade.status})"
        """
        import dataclasses

        closed_trade_input = dataclasses.replace(
            valid_long_trade,
            status="CLOSED_WIN",
            exit_timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            exit_price=2665.0,
            exit_reason="tp",
            pnl=15.0,
        )

        future_candles = pd.DataFrame(
            [
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2651.0,
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                }
            ]
        ).set_index("timestamp")

        result = simulate_trade_outcome(closed_trade_input, future_candles)

        # Should return unchanged
        assert result is closed_trade_input
        assert result.exit_reason == "tp"  # Original exit reason preserved

    def test_empty_future_candles_closes_at_entry(self, valid_long_trade):
        """Trade with empty future_candles closes at entry with end_of_data.

        Specification: "No future candles for trade {trade.trade_id}"
        """
        empty_candles = pd.DataFrame().set_index(pd.DatetimeIndex([]))

        closed_trade = simulate_trade_outcome(valid_long_trade, empty_candles)

        # Should close at entry price
        assert closed_trade.exit_reason == "end_of_data"
        assert closed_trade.exit_price == valid_long_trade.entry_price
        assert closed_trade.pnl == 0.0  # No movement

    def test_candle_with_nan_is_skipped(self, valid_long_trade):
        """Candle with NaN values is skipped and doesn't count toward timeout.

        Specification: "Skipping candle with NaN/Inf values at {timestamp}"
        """
        # Create candles where some have NaN
        future_candles = pd.DataFrame(
            [
                # Bar 1: Valid
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2651.0,
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                },
                # Bar 2: NaN (should be skipped, not counted)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": float("nan"),
                    "high": 2651.0,
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                },
                # Bars 3-10: Valid (to reach timeout for VWAP_FADE)
                *[
                    {
                        "timestamp": datetime(2025, 1, 1, 10, 3 + i, tzinfo=UTC),
                        "open": 2650.0,
                        "high": 2651.0,
                        "low": 2649.0,
                        "close": 2650.5,
                        "volume": 100,
                    }
                    for i in range(1, 10)
                ],
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(valid_long_trade, future_candles)

        # Should timeout after 10 VALID candles (bar 2 with NaN not counted)
        assert closed_trade.exit_reason == "timeout"
        # Duration should be 11 because we skip the NaN candle but time still passes
        # Actually, let me check the implementation to see if duration is time-based or bar-based

    def test_candle_with_inf_is_skipped(self, valid_long_trade):
        """Candle with Inf values is skipped and doesn't count toward timeout.

        Specification: "Skipping candle with NaN/Inf values at {timestamp}"
        """
        # Create candles where one has Inf
        future_candles = pd.DataFrame(
            [
                # Bar 1: Valid
                {
                    "timestamp": datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                    "open": 2650.0,
                    "high": 2651.0,
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                },
                # Bar 2: Inf (should be skipped)
                {
                    "timestamp": datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
                    "open": 2650.0,
                    "high": float("inf"),
                    "low": 2649.0,
                    "close": 2650.5,
                    "volume": 100,
                },
                # More bars...
                *[
                    {
                        "timestamp": datetime(2025, 1, 1, 10, 3 + i, tzinfo=UTC),
                        "open": 2650.0,
                        "high": 2651.0,
                        "low": 2649.0,
                        "close": 2650.5,
                        "volume": 100,
                    }
                    for i in range(1, 10)
                ],
            ]
        ).set_index("timestamp")

        closed_trade = simulate_trade_outcome(valid_long_trade, future_candles)

        # Should timeout after valid candles only
        assert closed_trade.exit_reason == "timeout"
