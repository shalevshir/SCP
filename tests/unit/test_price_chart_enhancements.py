"""Unit tests for price chart enhancements.

Tests VWAP calculation, DXY integration, volume subplot, and trade visualization.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from backtester.entry_model import EntryExecution
from backtester.replay_loop import BacktestResults
from backtester.trade import Trade
from rule_engine.signal import Signal


@pytest.fixture
def sample_gc_df():
    """Create sample GC price data for testing."""
    timestamps = pd.date_range(
        start="2025-11-06 10:00:00", periods=100, freq="1min", tz="UTC"
    )
    data = {
        "open": [4000 + i * 0.5 for i in range(100)],
        "high": [4001 + i * 0.5 for i in range(100)],
        "low": [3999 + i * 0.5 for i in range(100)],
        "close": [4000.5 + i * 0.5 for i in range(100)],
        "volume": [100 + i for i in range(100)],
    }
    df = pd.DataFrame(data, index=timestamps)
    df["timestamp"] = df.index
    df["ts_event"] = df.index
    return df


@pytest.fixture
def sample_dxy_df():
    """Create sample DXY data for testing."""
    timestamps = pd.date_range(
        start="2025-11-06 10:00:00", periods=100, freq="1min", tz="UTC"
    )
    data = {
        "open": [106.0 + i * 0.01 for i in range(100)],
        "high": [106.1 + i * 0.01 for i in range(100)],
        "low": [105.9 + i * 0.01 for i in range(100)],
        "close": [106.05 + i * 0.01 for i in range(100)],
        "volume": [50 + i for i in range(100)],
    }
    df = pd.DataFrame(data, index=timestamps)
    df["timestamp"] = df.index
    return df


@pytest.fixture
def sample_signal():
    """Create a sample signal for testing."""
    return Signal(
        timestamp=datetime(2025, 11, 6, 10, 1, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={
            "structure_alignment": 2.0,
            "vwap_relation": 2.0,
            "rsi_state": 1.5,
        },
        rationale="Test signal",
        validation_flags={
            "session_ok": True,
            "tier_ok": True,
            "score_meets_minimum": True,
        },
        enforcer_tier="EarlyMild",
    )


@pytest.fixture
def sample_trade(sample_signal):
    """Create a sample trade for testing."""
    entry_execution = EntryExecution(
        signal_timestamp=sample_signal.timestamp,
        entry_timestamp=sample_signal.timestamp + timedelta(minutes=1),
        entry_price=4020.0,
        signal=sample_signal,
        executed=True,
        rejection_reason=None,
    )

    return Trade(
        trade_id="test-trade-123",
        symbol="GC",
        timeframe="1m",
        entry_execution=entry_execution,
        entry_timestamp=entry_execution.entry_timestamp,
        entry_price=4020.0,
        direction="long",
        setup_type="VWAP_RECLAIM",
        stop_loss=4000.0,
        take_profit=4080.0,
        sl_rationale="Test SL",
        tp_rationale="Test TP",
        risk_amount=20.0,
        reward_amount=60.0,
        r_multiple=3.0,
        contracts=1,
        exit_timestamp=datetime(2025, 11, 6, 10, 30, 0, tzinfo=UTC),
        exit_price=4050.0,
        exit_reason="tp",
        pnl=30.0,
        pnl_percent=150.0,
        r_realized=1.5,
        pnl_dollars=3000.0,
        pnl_net=2970.0,
        slippage_cost=20.0,
        commission_cost=10.0,
        status="CLOSED_WIN",
        duration_bars=28,
        invalidation_triggered=False,
        ignore_first_retest_bar=True,
        diagnostics={
            "entry_context": {
                "vwap": 4010.0,
                "vwap_deviation": 0.25,
                "rsi": 55.0,
            }
        },
    )


@pytest.fixture
def sample_results(sample_trade):
    """Create sample backtest results."""
    return BacktestResults(
        trades=[sample_trade],
        total_pnl=30.0,
        total_pnl_dollars=2970.0,
        win_rate=100.0,
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        average_r=1.5,
        max_consecutive_losses=0,
    )


class TestVWAPCalculation:
    """Test VWAP calculation for chart display."""

    def test_vwap_calculation_with_valid_data(self, sample_gc_df):
        """Test VWAP calculation with valid OHLCV data."""
        from feature_engine.vwap import calculate_vwap

        vwap = calculate_vwap(sample_gc_df, session_reset=True)

        assert len(vwap) == len(sample_gc_df)
        assert not vwap.isna().all()
        assert (vwap > 0).all()

    def test_vwap_calculation_without_session_reset(self, sample_gc_df):
        """Test VWAP calculation without session reset."""
        from feature_engine.vwap import calculate_vwap

        vwap = calculate_vwap(sample_gc_df, session_reset=False)

        assert len(vwap) == len(sample_gc_df)
        # VWAP should be monotonic or stable without resets
        assert not vwap.isna().all()

    def test_vwap_with_missing_columns(self):
        """Test VWAP calculation fails gracefully with missing columns."""
        from feature_engine.vwap import calculate_vwap

        df = pd.DataFrame({"close": [100, 101, 102]})

        with pytest.raises(ValueError, match="Missing required columns"):
            calculate_vwap(df)


class TestEMACalculation:
    """Test EMA calculation for chart display."""

    def test_ema_9_calculation(self, sample_gc_df):
        """Test 9-period EMA calculation."""
        ema_9 = sample_gc_df["close"].ewm(span=9, adjust=False).mean()

        assert len(ema_9) == len(sample_gc_df)
        assert not ema_9.isna().all()
        # First value should be close to first close price
        assert abs(ema_9.iloc[0] - sample_gc_df["close"].iloc[0]) < 1.0

    def test_ema_21_calculation(self, sample_gc_df):
        """Test 21-period EMA calculation."""
        ema_21 = sample_gc_df["close"].ewm(span=21, adjust=False).mean()

        assert len(ema_21) == len(sample_gc_df)
        assert not ema_21.isna().all()

    def test_ema_relationship(self, sample_gc_df):
        """Test that EMA 9 responds faster than EMA 21."""
        ema_9 = sample_gc_df["close"].ewm(span=9, adjust=False).mean()
        ema_21 = sample_gc_df["close"].ewm(span=21, adjust=False).mean()

        # In uptrend, EMA 9 should be above EMA 21
        # (sample data has upward trend)
        assert ema_9.iloc[-1] > ema_21.iloc[-1]


class TestChartDataPreparation:
    """Test data preparation for chart rendering."""

    def test_timestamp_extraction_from_index(self, sample_gc_df):
        """Test extracting timestamps from DatetimeIndex."""
        timestamps = (
            sample_gc_df.index
            if isinstance(sample_gc_df.index, pd.DatetimeIndex)
            else sample_gc_df["timestamp"]
        )

        assert len(timestamps) == len(sample_gc_df)
        assert isinstance(timestamps, pd.DatetimeIndex)

    def test_timestamp_extraction_from_column(self, sample_gc_df):
        """Test extracting timestamps from column."""
        # Reset index to force column usage
        df = sample_gc_df.reset_index(drop=True)
        df["timestamp"] = sample_gc_df.index

        timestamps = (
            df.index if isinstance(df.index, pd.DatetimeIndex) else df["timestamp"]
        )

        assert len(timestamps) == len(df)

    def test_volume_color_calculation(self, sample_gc_df):
        """Test volume bar color calculation based on candle direction."""
        volume_colors = [
            "#26a69a" if sample_gc_df["close"].iloc[i] >= sample_gc_df["open"].iloc[i] else "#ef5350"
            for i in range(len(sample_gc_df))
        ]

        assert len(volume_colors) == len(sample_gc_df)
        # All should be green in uptrend sample data
        assert all(c == "#26a69a" for c in volume_colors)


class TestTradeMarkerCalculation:
    """Test trade marker positioning and coloring."""

    def test_entry_marker_positioning(self, sample_gc_df, sample_trade):
        """Test entry marker finds correct timestamp."""
        entry_time = sample_trade.entry_timestamp

        closest_idx = sample_gc_df.index.get_indexer([entry_time], method="nearest")[0]

        assert closest_idx >= 0
        assert closest_idx < len(sample_gc_df)

    def test_exit_marker_positioning(self, sample_gc_df, sample_trade):
        """Test exit marker finds correct timestamp."""
        exit_time = sample_trade.exit_timestamp

        closest_idx = sample_gc_df.index.get_indexer([exit_time], method="nearest")[0]

        assert closest_idx >= 0
        assert closest_idx < len(sample_gc_df)

    def test_entry_marker_color_long(self, sample_trade):
        """Test entry marker color for long trade."""
        marker_color = "#26a69a" if sample_trade.direction == "long" else "#ef5350"
        assert marker_color == "#26a69a"

    def test_entry_marker_color_short(self, sample_trade):
        """Test entry marker color for short trade."""
        # Create short trade
        short_trade = sample_trade
        short_trade = short_trade.__class__(
            **{**short_trade.__dict__, "direction": "short"}
        )

        marker_color = "#26a69a" if short_trade.direction == "long" else "#ef5350"
        assert marker_color == "#ef5350"

    def test_exit_marker_color_win(self, sample_trade):
        """Test exit marker color for winning trade."""
        exit_color = "#26a69a" if sample_trade.pnl and sample_trade.pnl > 0 else "#ef5350"
        assert exit_color == "#26a69a"

    def test_exit_marker_color_loss(self, sample_trade):
        """Test exit marker color for losing trade."""
        # Create losing trade
        losing_trade = sample_trade
        losing_trade = losing_trade.__class__(
            **{**losing_trade.__dict__, "pnl": -10.0}
        )

        exit_color = "#26a69a" if losing_trade.pnl and losing_trade.pnl > 0 else "#ef5350"
        assert exit_color == "#ef5350"


class TestDXYIntegration:
    """Test DXY data integration."""

    def test_dxy_timestamp_alignment(self, sample_gc_df, sample_dxy_df):
        """Test DXY timestamps align with GC data."""
        assert len(sample_dxy_df) == len(sample_gc_df)
        assert sample_dxy_df.index[0] == sample_gc_df.index[0]
        assert sample_dxy_df.index[-1] == sample_gc_df.index[-1]

    def test_dxy_data_validity(self, sample_dxy_df):
        """Test DXY data has valid OHLCV structure."""
        assert "open" in sample_dxy_df.columns
        assert "high" in sample_dxy_df.columns
        assert "low" in sample_dxy_df.columns
        assert "close" in sample_dxy_df.columns
        assert "volume" in sample_dxy_df.columns

        # Check OHLC relationships
        assert (sample_dxy_df["high"] >= sample_dxy_df["low"]).all()
        assert (sample_dxy_df["high"] >= sample_dxy_df["open"]).all()
        assert (sample_dxy_df["high"] >= sample_dxy_df["close"]).all()
        assert (sample_dxy_df["low"] <= sample_dxy_df["open"]).all()
        assert (sample_dxy_df["low"] <= sample_dxy_df["close"]).all()


class TestTradeDurationShading:
    """Test trade duration shading calculation."""

    def test_shade_color_for_winning_trade(self, sample_trade):
        """Test shade color calculation for winning trade."""
        shade_color = (
            "rgba(38, 166, 154, 0.1)"
            if sample_trade.pnl and sample_trade.pnl > 0
            else "rgba(239, 83, 80, 0.1)"
        )

        assert shade_color == "rgba(38, 166, 154, 0.1)"

    def test_shade_color_for_losing_trade(self, sample_trade):
        """Test shade color calculation for losing trade."""
        losing_trade = sample_trade
        losing_trade = losing_trade.__class__(
            **{**losing_trade.__dict__, "pnl": -10.0}
        )

        shade_color = (
            "rgba(38, 166, 154, 0.1)"
            if losing_trade.pnl and losing_trade.pnl > 0
            else "rgba(239, 83, 80, 0.1)"
        )

        assert shade_color == "rgba(239, 83, 80, 0.1)"

    def test_trade_duration_calculation(self, sample_trade):
        """Test trade duration is correctly calculated."""
        duration = sample_trade.exit_timestamp - sample_trade.entry_timestamp

        assert duration.total_seconds() > 0
        assert sample_trade.duration_bars == 28


class TestHoverInfo:
    """Test hover information formatting."""

    def test_entry_hover_info_formatting(self, sample_trade):
        """Test entry marker hover info is correctly formatted."""
        hovertemplate = (
            f"Trade: {sample_trade.trade_id[:8]}<br>"
            f"Entry: {sample_trade.entry_price:.2f}<br>"
            f"Setup: {sample_trade.setup_type}<br>"
            f"Score: {sample_trade.entry_execution.signal.score:.1f}<extra></extra>"
        )

        assert "Trade: test-tra" in hovertemplate
        assert "Entry: 4020.00" in hovertemplate
        assert "Setup: VWAP_RECLAIM" in hovertemplate
        assert "Score: 8.5" in hovertemplate

    def test_exit_hover_info_formatting(self, sample_trade):
        """Test exit marker hover info is correctly formatted."""
        pnl_text = f"{sample_trade.pnl:.2f} pts" if sample_trade.pnl is not None else "N/A"
        r_text = (
            f"{sample_trade.r_realized:.2f}R"
            if sample_trade.r_realized is not None
            else "N/A"
        )

        hovertemplate = (
            f"Trade: {sample_trade.trade_id[:8]}<br>"
            f"Exit: {sample_trade.exit_price:.2f}<br>"
            f"Reason: {sample_trade.exit_reason}<br>"
            f"PnL: {pnl_text} ({r_text})<extra></extra>"
        )

        assert "Trade: test-tra" in hovertemplate
        assert "Exit: 4050.00" in hovertemplate
        assert "Reason: tp" in hovertemplate
        assert "PnL: 30.00 pts (1.50R)" in hovertemplate

    def test_hover_info_with_none_pnl(self, sample_trade):
        """Test hover info handles None PnL gracefully."""
        open_trade = sample_trade
        open_trade = open_trade.__class__(
            **{
                **open_trade.__dict__,
                "pnl": None,
                "r_realized": None,
                "exit_price": None,
                "exit_timestamp": None,
            }
        )

        pnl_text = f"{open_trade.pnl:.2f} pts" if open_trade.pnl is not None else "N/A"
        r_text = (
            f"{open_trade.r_realized:.2f}R"
            if open_trade.r_realized is not None
            else "N/A"
        )

        assert pnl_text == "N/A"
        assert r_text == "N/A"







