"""Tests for price chart rendering with trade markers."""

import pandas as pd
import pytest
from backtester.replay_loop import BacktestResults
from backtester.trade import Trade
from dashboard.components.backtest.price_chart import render_price_chart_with_markers


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
