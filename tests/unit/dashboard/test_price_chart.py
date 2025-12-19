"""Tests for price chart rendering with trade markers."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest
from backtester.replay_loop import BacktestResults
from backtester.trade import Trade
from dashboard.components.backtest.price_chart import (
    render_price_chart_with_markers,
    render_trade_details,
)


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


def test_render_price_chart_with_none_gc_df(empty_results):
    """Test that render_price_chart_with_markers handles None gc_df gracefully.

    This reproduces the bug where passing gc_df=None causes AttributeError
    when the function tries to call gc_df.empty without checking for None first.
    """
    # This should not raise AttributeError
    fig = render_price_chart_with_markers(
        results=empty_results,
        gc_df=None,
        selected_trade_id=None,
    )

    # Should return a valid figure with "No price data available" message
    assert fig is not None
    assert len(fig.layout.annotations) > 0
    assert "No price data available" in fig.layout.annotations[0].text


def test_render_price_chart_with_empty_gc_df(empty_results):
    """Test that render_price_chart_with_markers handles empty DataFrame."""
    empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    empty_df.index = pd.DatetimeIndex([])

    fig = render_price_chart_with_markers(
        results=empty_results,
        gc_df=empty_df,
        selected_trade_id=None,
    )

    # Should return a valid figure with "No price data available" message
    assert fig is not None
    assert len(fig.layout.annotations) > 0
    assert "No price data available" in fig.layout.annotations[0].text


def test_render_price_chart_with_none_pnl_in_hovertemplate():
    """Test that hovertemplate handles None pnl gracefully.

    This reproduces the bug where formatting selected_trade.pnl:.2f
    causes TypeError if pnl is None.
    """
    # Create sample price data
    dates = pd.date_range("2025-01-01 10:00:00", periods=10, freq="1min", tz=UTC)
    gc_df = pd.DataFrame(
        {
            "open": [2700.0] * 10,
            "high": [2705.0] * 10,
            "low": [2695.0] * 10,
            "close": [2702.0] * 10,
            "volume": [1000.0] * 10,
        },
        index=dates,
    )

    # Create a trade with exit_timestamp and exit_price but None pnl
    trade = MagicMock()
    trade.trade_id = "test-trade-123"
    trade.entry_timestamp = dates[0]
    trade.entry_price = 2700.0
    trade.direction = "long"
    trade.setup_type = "VWAP_RECLAIM"
    trade.stop_loss = 2690.0
    trade.take_profit = 2730.0
    trade.exit_timestamp = dates[5]
    trade.exit_price = 2710.0
    trade.pnl = None  # This is the bug trigger
    trade.r_realized = None  # Must also set r_realized for the None check
    trade.exit_reason = "TIME"

    signal = MagicMock()
    signal.score = 8.5
    trade.entry_execution = MagicMock()
    trade.entry_execution.signal = signal

    results = BacktestResults(
        trades=[trade],
        executions=[],
        total_pnl=0.0,
        win_rate=0.0,
        total_trades=1,
        winning_trades=0,
        losing_trades=0,
        average_r=0.0,
    )

    # This should not raise TypeError
    fig = render_price_chart_with_markers(
        results=results,
        gc_df=gc_df,
        selected_trade_id="test-trade-123",
    )

    # Should return a valid figure
    assert fig is not None
    # Verify the hovertemplate doesn't crash (check that figure was created)
    assert len(fig.data) > 0


def test_render_trade_details_with_none_exit_price():
    """Test that render_trade_details handles None exit_price gracefully.

    This reproduces the bug where checking only exit_timestamp but then
    formatting exit_price:.2f causes TypeError if exit_price is None.
    """
    # Create a trade with exit_timestamp set but exit_price None
    trade = MagicMock()
    trade.trade_id = "test-trade-456"
    trade.entry_timestamp = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
    trade.entry_price = 2700.0
    trade.direction = "long"
    trade.setup_type = "VWAP_RECLAIM"
    trade.stop_loss = 2690.0
    trade.take_profit = 2730.0
    trade.exit_timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    trade.exit_price = None  # This is the bug trigger
    trade.pnl = None
    trade.r_realized = None
    trade.exit_reason = "INVALIDATION"

    signal = MagicMock()
    signal.score = 8.5
    signal.confidence = "HIGH"
    signal.factors = {"vwap": 2.0, "structure": 1.5}
    trade.entry_execution = MagicMock()
    trade.entry_execution.signal = signal

    # This should not raise TypeError
    result = render_trade_details(trade)

    # Should return a valid HTML div
    assert result is not None
    # The result should be a dbc.Card, which is a list/component
    assert hasattr(result, "children") or isinstance(result, (list, dict))
