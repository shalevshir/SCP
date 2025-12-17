"""Test that invalid candles don't increment bar counters.

Regression test for bug where NaN/Inf candles increment _trade_bar_counts
before validation check, causing grace periods and timeouts to fire early.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from backtester.replay_loop import BacktestReplayLoop
from backtester.simulator import is_valid_candle
from backtester.trade import Trade
from common.types import Candle


class TestInvalidCandleBarCount:
    """Test that invalid candles are skipped without incrementing bar counters."""

    def test_is_valid_candle_detects_nan(self):
        """Test that is_valid_candle detects NaN values."""
        valid_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=2650.0,
            high=2652.0,
            low=2648.0,
            close=2651.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        assert is_valid_candle(valid_candle) is True

        invalid_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=math.nan,
            high=2652.0,
            low=2648.0,
            close=2651.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        assert is_valid_candle(invalid_candle) is False

    def test_is_valid_candle_detects_inf(self):
        """Test that is_valid_candle detects Inf values."""
        invalid_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=2650.0,
            high=math.inf,
            low=2648.0,
            close=2651.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        assert is_valid_candle(invalid_candle) is False

    def test_invalid_candle_does_not_increment_bar_counter(self):
        """Test that invalid candles don't increment _trade_bar_counts.

        Regression test for bug where bar counter is incremented before
        check_trade_exit_single_bar validates the candle, causing grace
        periods and timeouts to fire earlier than intended.

        Scenario:
        - Trade enters at bar 0
        - Bar 1 is invalid (NaN) - should be skipped
        - Bar 2 is valid - should still be bar 1 for grace period
        - For RECLAIM, grace period is 2 bars, so SL should still be skipped
        """
        from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar

        from backtester.entry_model import EntryExecution
        from rule_engine.signal import Signal

        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        # Create signal and entry execution for RECLAIM trade
        signal = Signal(
            timestamp=base_time,
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"structure": 3.0, "vwap": 2.5, "dxy": 1.5},
            rationale="Test signal",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=base_time,
            entry_timestamp=base_time,
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Create a RECLAIM trade (grace period = 2 bars)
        trade = Trade(
            trade_id="TEST_001",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=base_time,
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2640.0,
            take_profit=2680.0,
            sl_rationale="Below structure",
            tp_rationale="3R target",
            risk_amount=10.0,
            reward_amount=30.0,
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

        # Create minimal multi-timeframe data with invalid candle
        gc_invalid = Candle(
            timestamp=base_time + timedelta(minutes=5),
            open=math.nan,  # Invalid!
            high=2652.0,
            low=2648.0,
            close=2651.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        dxy_candle = Candle(
            timestamp=base_time + timedelta(minutes=5),
            open=103.0,
            high=103.1,
            low=102.9,
            close=103.05,
            volume=500.0,
            symbol="DXY",
            timeframe="1m",
            source="CSV",
        )

        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=[
                SynchronizedBar(
                    execution_timestamp=base_time + timedelta(minutes=5),
                    execution_1m=(gc_invalid, dxy_candle),
                    htf_15m=None,
                    htf_1h=None,
                )
            ],
            execution_timestamps=[base_time + timedelta(minutes=5)],
        )

        # Create loop
        market_state = {
            "buffer_phase": "growth",
            "tier_active": "EarlyMild",
            "ceo_directive_active": True,
            "news_ok": True,
            "session_ok": True,
        }
        risk_config = {
            "risk_per_trade": 600.0,
            "buffer_phase": "growth",
            "max_contracts": 1,
        }

        loop = BacktestReplayLoop(
            multi_tf_data=multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            htf_approach="streaming",
            log_signals=False,
        )

        # Manually add trade to active trades
        loop._active_trades[trade.trade_id] = trade

        # Before processing invalid candle, bar count should be 0
        assert loop._trade_bar_counts.get(trade.trade_id, 0) == 0

        # Process invalid candle using _update_active_trades
        loop._update_active_trades(gc_invalid, features=None)

        # CRITICAL: Bar count should still be 0 (invalid candle skipped)
        # This is the bug we're testing for - currently it WILL be 1 (wrong)
        assert (
            loop._trade_bar_counts.get(trade.trade_id, 0) == 0
        ), "Invalid candle should not increment bar counter"


