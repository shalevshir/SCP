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
        assert closed_trade.duration_bars == 3  # Hits SL on 3rd bar (4 total candles)

    def test_sl_priority_over_tp(self, long_continuation_trade):
        """Test SL takes priority when both hit in same candle."""
        # Single candle that hits both SL and TP
        candles = [
            make_candle(
                timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                open=2650.0,
                high=2666.0,  # Above TP (2665.0)
                low=2644.0,  # Below SL (2645.0)
                close=2655.0,
                volume=100,
            )
        ]

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        # SL should take priority per SOP
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.exit_price == 2645.0
        assert closed_trade.status == "STOPPED_OUT"

    def test_gap_beyond_sl_long(self, long_continuation_trade):
        """Test gap opening beyond SL - should exit at SL, not worse."""
        # Candle opens way below SL (gap down)
        candles = [
            make_candle(
                timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                open=2640.0,  # Opens below SL (2645.0)
                high=2642.0,
                low=2638.0,
                close=2641.0,
                volume=100,
            )
        ]

        df = pd.DataFrame([c.__dict__ for c in candles])
        df = df.set_index("timestamp")

        closed_trade = simulate_trade_outcome(long_continuation_trade, df)

        # Should exit at SL, not at worse gap price
        assert closed_trade.exit_reason == "sl"
        assert closed_trade.exit_price == 2645.0

    def test_gap_beyond_tp_long(self, long_continuation_trade):
        """Test gap opening beyond TP - should exit at TP."""
        # Candle opens way above TP (gap up)
        candles = [
            make_candle(
                timestamp=datetime(2025, 1, 1, 10, 2, tzinfo=UTC),
                open=2670.0,  # Opens above TP (2665.0)
                high=2672.0,
                low=2668.0,
                close=2671.0,
                volume=100,
            )
        ]

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

    def test_skipped_nan_candles_dont_count_toward_timeout(self, long_continuation_trade):
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

