"""Tests for equity chart rendering with trade markers."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from backtester.entry_model import EntryExecution
from backtester.replay_loop import BacktestResults
from backtester.trade import Trade
from dashboard.components.backtest.equity_chart import render_equity_chart
from rule_engine.signal import Signal


@pytest.fixture
def empty_results():
    """Create empty BacktestResults for testing."""
    return BacktestResults(
        trades=[],
        executions=[],
        total_pnl=0.0,
        win_rate=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        average_r=0.0,
    )


@pytest.fixture
def sample_entry_execution():
    """Create a sample EntryExecution for testing."""
    signal = Signal(
        timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=9.0,
        confidence="A+",
        factors={"structure_alignment": 2.0, "vwap_relation": 2.0},
        rationale="HTF HH/HL intact, VWAP reclaim confirmed",
        validation_flags={"session_ok": True, "tier_ok": True},
        enforcer_tier="EarlyMild",
    )

    return EntryExecution(
        signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )


def test_render_equity_chart_with_trades_all_none_pnl(sample_entry_execution):
    """Test that render_equity_chart handles trades with all None PnL values.

    This reproduces the bug where if all trades have pnl=None, the equity_series
    will be empty, and accessing equity_series[0] at line 119 will raise IndexError.
    """
    # Create trades with None PnL (e.g., open trades or trades that haven't been closed)
    trades = [
        Trade(
            trade_id="test-trade-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below confirmation candle low",
            tp_rationale="3R continuation setup",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,  # None PnL
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
        ),
        Trade(
            trade_id="test-trade-002",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            entry_price=2651.0,
            direction="short",
            setup_type="VWAP_FADE",
            stop_loss=2655.0,
            take_profit=2636.0,
            sl_rationale="Above sweep candle high",
            tp_rationale="2R fade setup",
            risk_amount=4.0,
            reward_amount=8.0,
            r_multiple=2.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,  # None PnL
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
        ),
    ]

    results = BacktestResults(
        trades=trades,
        executions=[],
        total_pnl=0.0,
        win_rate=0.0,
        total_trades=2,
        winning_trades=0,
        losing_trades=0,
        average_r=0.0,
    )

    # This should not raise IndexError
    fig = render_equity_chart(results=results, display_mode="points")

    # Should return a valid figure with "No PnL data available" message
    assert fig is not None
    assert len(fig.layout.annotations) > 0
    assert "No PnL data available" in fig.layout.annotations[0].text
    assert "all trades have None PnL" in fig.layout.annotations[0].text


def test_render_equity_chart_with_valid_pnl(sample_entry_execution):
    """Test that render_equity_chart works correctly with valid PnL values."""
    # Create trades with valid PnL
    trades = [
        Trade(
            trade_id="test-trade-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below confirmation candle low",
            tp_rationale="3R continuation setup",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            exit_price=2665.0,
            exit_reason="TP",
            pnl=15.0,  # Valid PnL
            pnl_percent=300.0,
            r_realized=3.0,
            pnl_dollars=150.0,
            pnl_net=145.0,
            slippage_cost=2.5,
            commission_cost=2.5,
            status="CLOSED_WIN",
            duration_bars=4,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        ),
    ]

    results = BacktestResults(
        trades=trades,
        executions=[],
        total_pnl=15.0,
        win_rate=100.0,
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        average_r=3.0,
    )

    # Should render chart with data
    fig = render_equity_chart(results=results, display_mode="points")

    assert fig is not None
    # Should have traces (not just annotations)
    assert len(fig.data) > 0
    # Should not have "No PnL data available" message
    if fig.layout.annotations:
        assert "No PnL data available" not in str(fig.layout.annotations)


def test_render_equity_chart_with_mixed_pnl_sequential_trade_numbers(
    sample_entry_execution,
):
    """Test that trade_numbers are sequential (1, 2, 3) even when some trades have None PnL.

    This verifies the fix for the bug where enumerate index was used instead of
    a separate counter, causing gaps in trade_numbers when trades with pnl=None
    were skipped.
    """
    # Create trades: first has None PnL (should be skipped), others have valid PnL
    trades = [
        Trade(
            trade_id="test-trade-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below confirmation candle low",
            tp_rationale="3R continuation setup",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,  # First trade has None PnL - should be skipped
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
        ),
        Trade(
            trade_id="test-trade-002",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            entry_price=2651.0,
            direction="short",
            setup_type="VWAP_FADE",
            stop_loss=2655.0,
            take_profit=2636.0,
            sl_rationale="Above sweep candle high",
            tp_rationale="2R fade setup",
            risk_amount=4.0,
            reward_amount=8.0,
            r_multiple=2.0,
            contracts=1,
            exit_timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            exit_price=2636.0,
            exit_reason="TP",
            pnl=15.0,  # Valid PnL - should be included as trade #1
            pnl_percent=375.0,
            r_realized=3.75,
            pnl_dollars=150.0,
            pnl_net=145.0,
            slippage_cost=2.5,
            commission_cost=2.5,
            status="CLOSED_WIN",
            duration_bars=5,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        ),
        Trade(
            trade_id="test-trade-003",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 15, tzinfo=UTC),
            entry_price=2640.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2635.0,
            take_profit=2660.0,
            sl_rationale="Below confirmation candle low",
            tp_rationale="3R continuation setup",
            risk_amount=5.0,
            reward_amount=20.0,
            r_multiple=4.0,
            contracts=1,
            exit_timestamp=datetime(2025, 1, 1, 10, 20, tzinfo=UTC),
            exit_price=2660.0,
            exit_reason="TP",
            pnl=20.0,  # Valid PnL - should be included as trade #2
            pnl_percent=400.0,
            r_realized=4.0,
            pnl_dollars=200.0,
            pnl_net=195.0,
            slippage_cost=2.5,
            commission_cost=2.5,
            status="CLOSED_WIN",
            duration_bars=5,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        ),
        Trade(
            trade_id="test-trade-004",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 25, tzinfo=UTC),
            entry_price=2655.0,
            direction="short",
            setup_type="VWAP_FADE",
            stop_loss=2660.0,
            take_profit=2630.0,
            sl_rationale="Above sweep candle high",
            tp_rationale="2R fade setup",
            risk_amount=5.0,
            reward_amount=10.0,
            r_multiple=2.0,
            contracts=1,
            exit_timestamp=datetime(2025, 1, 1, 10, 30, tzinfo=UTC),
            exit_price=2630.0,
            exit_reason="TP",
            pnl=25.0,  # Valid PnL - should be included as trade #3
            pnl_percent=500.0,
            r_realized=5.0,
            pnl_dollars=250.0,
            pnl_net=245.0,
            slippage_cost=2.5,
            commission_cost=2.5,
            status="CLOSED_WIN",
            duration_bars=5,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        ),
    ]

    results = BacktestResults(
        trades=trades,
        executions=[],
        total_pnl=60.0,
        win_rate=100.0,
        total_trades=4,
        winning_trades=3,
        losing_trades=0,
        average_r=4.0,
    )

    # Should render chart with data
    fig = render_equity_chart(results=results, display_mode="points")

    assert fig is not None
    assert len(fig.data) > 0

    # Extract trade_numbers from the first trace (equity curve)
    equity_trace = fig.data[0]
    # Convert to list (x and y may be array, tuple, or list)
    trade_numbers = list(equity_trace.x)
    cumulative_pnl = list(equity_trace.y)

    # Verify trade_numbers are sequential starting from 1
    # Even though first trade was skipped, numbers should be [1, 2, 3], not [2, 3, 4]
    assert trade_numbers == [1, 2, 3], (
        f"Expected trade_numbers to be [1, 2, 3], got {trade_numbers}. "
        "This indicates the enumerate index bug is still present."
    )

    # Verify cumulative PnL values are correct
    assert cumulative_pnl == [
        15.0,
        35.0,
        60.0,
    ], f"Expected cumulative PnL to be [15.0, 35.0, 60.0], got {cumulative_pnl}"
