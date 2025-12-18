"""Tests for grace period consistency across simulation paths (Bug Fix).

Bug: ACCEPTANCE_GRACE_BARS_RECLAIM (8 bars) is only used in check_trade_exit_single_bar,
but simulate_trade_to_completion still uses hardcoded 2 bars, causing inconsistent behavior.

Test coverage:
- simulate_trade_to_completion uses 8-bar grace period
- Both simulation paths produce consistent results
- Trades don't stop out during bars 1-8 in simulate_trade_to_completion
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from backtester.simulator import simulate_trade_outcome
from backtester.trade import Trade
from backtester.entry_model import EntryExecution
from common.types import Candle
from rule_engine.signal import Signal


@pytest.fixture
def sample_long_reclaim_trade():
    """Create a sample long VWAP_RECLAIM trade for testing."""
    signal = Signal(
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

    entry_execution = EntryExecution(
        signal_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
        entry_timestamp=datetime(2024, 11, 1, 10, 1, tzinfo=timezone.utc),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    return Trade(
        trade_id="TEST_001",
        symbol="GC",
        timeframe="5m",
        entry_execution=entry_execution,
        entry_timestamp=datetime(2024, 11, 1, 10, 1, tzinfo=timezone.utc),
        entry_price=2650.0,
        direction="long",
        setup_type="VWAP_RECLAIM",
        stop_loss=2640.0,
        take_profit=2680.0,
        sl_rationale="VWAP-zone SL",
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


def create_future_candles_hitting_sl(
    num_candles: int, entry_time: datetime
) -> pd.DataFrame:
    """Create future candles that hit SL."""
    candles = []
    for i in range(num_candles):
        timestamp = entry_time + pd.Timedelta(minutes=(i + 1) * 5)
        candles.append(
            {
                "timestamp": timestamp,
                "open": 2648.0,
                "high": 2649.0,
                "low": 2638.0,  # Below SL at 2640
                "close": 2642.0,
                "volume": 1000.0,
            }
        )

    df = pd.DataFrame(candles)
    df = df.set_index("timestamp")
    return df


class TestGracePeriodConsistency:
    """Test that grace period is consistent across simulation paths."""

    def test_simulate_trade_outcome_uses_8_bar_grace(self, sample_long_reclaim_trade):
        """simulate_trade_outcome should use 8-bar grace period, not 2 bars."""
        trade = sample_long_reclaim_trade

        # Create 10 future candles that all hit SL
        future_candles = create_future_candles_hitting_sl(10, trade.entry_timestamp)

        # Simulate trade
        result = simulate_trade_outcome(
            trade=trade,
            future_candles=future_candles,
            invalidation_checker=None,
            config=None,
            future_features=None,
        )

        # Trade should survive first 8 bars (grace period)
        # Should stop out on bar 9
        assert (
            result.duration_bars == 9
        ), f"Expected stop-out on bar 9, got bar {result.duration_bars}"
        assert result.exit_reason == "sl"

    def test_simulate_does_not_stop_out_during_grace_bars_1_to_8(
        self, sample_long_reclaim_trade
    ):
        """Verify trade doesn't stop out during bars 1-8 even when SL is hit."""
        trade = sample_long_reclaim_trade

        # Create only 8 candles (all hitting SL)
        future_candles = create_future_candles_hitting_sl(8, trade.entry_timestamp)

        result = simulate_trade_outcome(
            trade=trade,
            future_candles=future_candles,
            invalidation_checker=None,
            config=None,
            future_features=None,
        )

        # Trade should still be open (timeout, not stopped out)
        assert result.status != "STOPPED_OUT" or result.duration_bars > 8
        # If it closed, it should be timeout, not SL
        if result.status != "OPEN":
            # Might timeout at 20 bars for RECLAIM
            assert result.exit_reason != "sl" or result.duration_bars > 8

    def test_simulate_stops_out_on_bar_9(self, sample_long_reclaim_trade):
        """Verify trade stops out on bar 9 when SL is hit (after grace period)."""
        trade = sample_long_reclaim_trade

        # Create 15 candles (all hitting SL)
        future_candles = create_future_candles_hitting_sl(15, trade.entry_timestamp)

        result = simulate_trade_outcome(
            trade=trade,
            future_candles=future_candles,
            invalidation_checker=None,
            config=None,
            future_features=None,
        )

        # Trade should stop out on bar 9 (first bar after grace period)
        assert result.exit_reason == "sl"
        assert result.duration_bars == 9

    def test_grace_period_applies_to_tp_as_well(self, sample_long_reclaim_trade):
        """TP should also be skipped during grace period (bars 1-8)."""
        trade = sample_long_reclaim_trade

        # Create candles that hit TP early
        candles_data = []
        for i in range(10):
            timestamp = trade.entry_timestamp + pd.Timedelta(minutes=(i + 1) * 5)
            candles_data.append(
                {
                    "timestamp": timestamp,
                    "open": 2670.0,
                    "high": 2685.0,  # Above TP at 2680
                    "low": 2668.0,
                    "close": 2682.0,
                    "volume": 1000.0,
                }
            )

        future_candles = pd.DataFrame(candles_data).set_index("timestamp")

        result = simulate_trade_outcome(
            trade=trade,
            future_candles=future_candles,
            invalidation_checker=None,
            config=None,
            future_features=None,
        )

        # Trade should not hit TP during grace period (bars 1-8)
        # Should hit TP on bar 9 or later
        if result.exit_reason == "tp":
            assert (
                result.duration_bars >= 9
            ), f"TP should not trigger during grace period, but hit on bar {result.duration_bars}"
