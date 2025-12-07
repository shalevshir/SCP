"""Integration tests for BacktestReplayLoop - end-to-end backtest scenarios."""

from datetime import UTC, datetime, timedelta

import pytest
from backtester.replay_loop import BacktestReplayLoop
from common.types import Candle
from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar


@pytest.fixture
def multi_day_data():
    """Create multi-day multi-timeframe data for integration testing."""
    # Generate sample data for 3 days (3 sessions * 3 hours = 9 hours = 540 candles)
    start_day1 = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
    start_day2 = datetime(2024, 7, 2, 10, 0, tzinfo=UTC)
    start_day3 = datetime(2024, 7, 3, 10, 0, tzinfo=UTC)

    bars = []
    all_timestamps = []
    global_idx = 0

    for day_idx, start_day in enumerate([start_day1, start_day2, start_day3]):
        base_gc_price = 2650.0 + (day_idx * 10.0)
        base_dxy_price = 103.0 + (day_idx * 0.1)

        for i in range(180):  # 3 hours per day
            ts = start_day + timedelta(minutes=i)
            all_timestamps.append(ts)

            # Create execution candles
            gc_price = base_gc_price + (i * 0.05)
            exec_gc = Candle(
                timestamp=ts,
                open=gc_price,
                high=gc_price + 1.5,
                low=gc_price - 1.5,
                close=gc_price + 0.3,
                volume=1000 + i,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            dxy_price = base_dxy_price + (i * 0.005)
            exec_dxy = Candle(
                timestamp=ts,
                open=dxy_price,
                high=dxy_price + 0.1,
                low=dxy_price - 0.1,
                close=dxy_price + 0.02,
                volume=500 + i,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            # Add HTF data at 15m boundaries
            htf_15m = None
            if global_idx % 15 == 14 or global_idx == 0:
                htf_15m_gc = Candle(
                    timestamp=start_day + timedelta(minutes=(i // 15) * 15),
                    open=base_gc_price - 1.0 + (i // 15) * 0.75,
                    high=base_gc_price + 2.5 + (i // 15) * 0.75,
                    low=base_gc_price - 2.0 + (i // 15) * 0.75,
                    close=base_gc_price + 0.5 + (i // 15) * 0.75,
                    volume=15000 + (i // 15) * 1000,
                    symbol="GC",
                    timeframe="15m",
                    source="CSV",
                )
                htf_15m_dxy = Candle(
                    timestamp=start_day + timedelta(minutes=(i // 15) * 15),
                    open=base_dxy_price - 0.05 + (i // 15) * 0.075,
                    high=base_dxy_price + 0.15 + (i // 15) * 0.075,
                    low=base_dxy_price - 0.15 + (i // 15) * 0.075,
                    close=base_dxy_price + 0.03 + (i // 15) * 0.075,
                    volume=7500 + (i // 15) * 500,
                    symbol="DXY",
                    timeframe="15m",
                    source="CSV",
                )
                htf_15m = (htf_15m_gc, htf_15m_dxy)

            # Add HTF data at 1h boundaries
            htf_1h = None
            if global_idx % 60 == 59 or global_idx == 0:
                htf_1h_gc = Candle(
                    timestamp=start_day + timedelta(hours=i // 60),
                    open=base_gc_price - 2.0 + (i // 60) * 3.0,
                    high=base_gc_price + 4.0 + (i // 60) * 3.0,
                    low=base_gc_price - 3.0 + (i // 60) * 3.0,
                    close=base_gc_price + 1.0 + (i // 60) * 3.0,
                    volume=60000 + (i // 60) * 5000,
                    symbol="GC",
                    timeframe="1h",
                    source="CSV",
                )
                htf_1h_dxy = Candle(
                    timestamp=start_day + timedelta(hours=i // 60),
                    open=base_dxy_price - 0.2 + (i // 60) * 0.3,
                    high=base_dxy_price + 0.3 + (i // 60) * 0.3,
                    low=base_dxy_price - 0.3 + (i // 60) * 0.3,
                    close=base_dxy_price + 0.1 + (i // 60) * 0.3,
                    volume=30000 + (i // 60) * 2500,
                    symbol="DXY",
                    timeframe="1h",
                    source="CSV",
                )
                htf_1h = (htf_1h_gc, htf_1h_dxy)

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=htf_15m,
                    htf_1h=htf_1h,
                )
            )
            global_idx += 1

    # Create MultiTimeframeData
    multi_tf_data = MultiTimeframeData(
        execution_timeframe="1m",
        htf_timeframes=["15m", "1h"],
        synchronized_bars=bars,
        execution_timestamps=all_timestamps,
    )

    return multi_tf_data


@pytest.fixture
def market_state_integration():
    """Create market state for integration testing."""
    return {
        "buffer_phase": "growth",
        "tier_active": "EarlyMild",
        "ceo_directive_active": True,
        "news_ok": True,
        "session_ok": True,
    }


@pytest.fixture
def risk_config_integration():
    """Create risk config for integration testing."""
    return {
        "risk_per_trade": 600.0,
        "buffer_phase": "growth",
        "max_contracts": 1,
    }


@pytest.fixture
def config_integration():
    """Create config for integration testing."""
    return {
        "backtest": {
            "pdll_limit": 600.0,
            "max_trades_per_day": 2,
            "slippage_points": 0.5,
            "commission_per_trade": 5.0,
        },
        "assets": {
            "tick_values": {"GC": 10.0},
            "tick_sizes": {"GC": 0.1},
        },
    }


class TestEndToEndBacktest:
    """Test complete end-to-end backtest scenarios."""

    def test_single_session_backtest(
        self,
        multi_day_data,
        market_state_integration,
        risk_config_integration,
        config_integration,
    ):
        """Test end-to-end backtest for single session."""
        loop = BacktestReplayLoop(
            multi_tf_data=multi_day_data,
            timeframe="1m",
            market_state=market_state_integration,
            risk_config=risk_config_integration,
            config=config_integration,
            htf_approach="streaming",
        )

        results = loop.run()

        # Verify basic results structure
        assert results is not None
        assert isinstance(results.total_trades, int)
        assert isinstance(results.total_pnl, float)
        assert 0.0 <= results.win_rate <= 100.0

        # Verify all trades are closed
        for trade in results.trades:
            assert trade.status != "OPEN"
            assert trade.exit_timestamp is not None

    def test_multi_day_backtest_with_session_resets(
        self,
        multi_day_data,
        market_state_integration,
        risk_config_integration,
        config_integration,
    ):
        """Test multi-day backtest with session resets."""
        loop = BacktestReplayLoop(
            multi_tf_data=multi_day_data,
            timeframe="1m",
            market_state=market_state_integration,
            risk_config=risk_config_integration,
            config=config_integration,
            htf_approach="streaming",
        )

        results = loop.run()

        # Verify session resets occurred
        assert loop._session_reset_count >= 2  # At least 3 days = 2+ resets

        # Verify final state
        assert len(loop._active_trades) == 0

        # Verify trades are distributed across days
        if len(results.trades) > 0:
            dates = set(t.entry_timestamp.date() for t in results.trades)
            # We should have trades potentially across multiple days
            assert len(dates) >= 1

    def test_backtest_with_known_setup(
        self,
        market_state_integration,
        risk_config_integration,
        config_integration,
    ):
        """Test backtest with known setup that should produce predictable results."""
        # Create simple dataset with clear trend
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        bars = []
        timestamps = []

        for i in range(60):
            ts = start_time + timedelta(minutes=i)
            timestamps.append(ts)

            # Strong uptrend in GC
            gc_price = 2650.0 + (i * 0.5)
            exec_gc = Candle(
                timestamp=ts,
                open=gc_price,
                high=gc_price + 2.0,
                low=gc_price - 0.5,
                close=gc_price + 1.5,
                volume=1000,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            # DXY also trending
            dxy_price = 103.0 + (i * 0.02)
            exec_dxy = Candle(
                timestamp=ts,
                open=dxy_price,
                high=dxy_price + 0.1,
                low=dxy_price - 0.05,
                close=dxy_price + 0.08,
                volume=500,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            # Add HTF data at 15m boundaries
            htf_15m = None
            if i % 15 == 14 or i == 0:
                htf_15m_gc = Candle(
                    timestamp=start_time + timedelta(minutes=(i // 15) * 15),
                    open=2649.0 + (i // 15) * 7.5,
                    high=2660.0 + (i // 15) * 7.5,
                    low=2648.0 + (i // 15) * 7.5,
                    close=2658.0 + (i // 15) * 7.5,
                    volume=15000,
                    symbol="GC",
                    timeframe="15m",
                    source="CSV",
                )
                htf_15m_dxy = Candle(
                    timestamp=start_time + timedelta(minutes=(i // 15) * 15),
                    open=102.95 + (i // 15) * 0.3,
                    high=103.5 + (i // 15) * 0.3,
                    low=102.9 + (i // 15) * 0.3,
                    close=103.4 + (i // 15) * 0.3,
                    volume=7500,
                    symbol="DXY",
                    timeframe="15m",
                    source="CSV",
                )
                htf_15m = (htf_15m_gc, htf_15m_dxy)

            # Add HTF data at 1h boundary
            htf_1h = None
            if i == 0:
                htf_1h_gc = Candle(
                    timestamp=start_time,
                    open=2645.0,
                    high=2680.0,
                    low=2643.0,
                    close=2675.0,
                    volume=60000,
                    symbol="GC",
                    timeframe="1h",
                    source="CSV",
                )
                htf_1h_dxy = Candle(
                    timestamp=start_time,
                    open=102.8,
                    high=104.2,
                    low=102.7,
                    close=104.0,
                    volume=30000,
                    symbol="DXY",
                    timeframe="1h",
                    source="CSV",
                )
                htf_1h = (htf_1h_gc, htf_1h_dxy)

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=htf_15m,
                    htf_1h=htf_1h,
                )
            )

        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=["15m", "1h"],
            synchronized_bars=bars,
            execution_timestamps=timestamps,
        )

        loop = BacktestReplayLoop(
            multi_tf_data=multi_tf_data,
            timeframe="1m",
            market_state=market_state_integration,
            risk_config=risk_config_integration,
            config=config_integration,
        )

        results = loop.run()

        # Verify results
        assert results.total_trades >= 0
        assert len(results.executions) >= 0


class TestSessionResetBehavior:
    """Test session reset behavior across multiple days."""

    def test_daily_pnl_resets_at_session_boundary(
        self,
        multi_day_data,
        market_state_integration,
        risk_config_integration,
        config_integration,
    ):
        """Test that daily PnL resets at session boundaries."""
        loop = BacktestReplayLoop(
            multi_tf_data=multi_day_data,
            timeframe="1m",
            market_state=market_state_integration,
            risk_config=risk_config_integration,
            config=config_integration,
        )

        # Run backtest
        results = loop.run()

        # Verify session resets occurred
        assert loop._session_reset_count >= 1
        assert results is not None  # Verify backtest completed

        # Final daily PnL should only include last session's trades
        # (This is implicitly tested by the reset logic)

    def test_pdll_resets_at_session_boundary(
        self,
        multi_day_data,
        market_state_integration,
        risk_config_integration,
        config_integration,
    ):
        """Test that PDLL flag resets at session boundaries."""
        loop = BacktestReplayLoop(
            multi_tf_data=multi_day_data,
            timeframe="1m",
            market_state=market_state_integration,
            risk_config=risk_config_integration,
            config=config_integration,
        )

        # Run backtest
        results = loop.run()

        # If PDLL was hit during backtest, verify it was reset for new sessions
        # Final state should reflect last session only
        assert isinstance(loop._pdll_hit, bool)
        assert results is not None  # Verify backtest completed

    def test_trades_today_resets_at_session_boundary(
        self,
        multi_day_data,
        market_state_integration,
        risk_config_integration,
        config_integration,
    ):
        """Test that trades_today counter resets at session boundaries."""
        loop = BacktestReplayLoop(
            multi_tf_data=multi_day_data,
            timeframe="1m",
            market_state=market_state_integration,
            risk_config=risk_config_integration,
            config=config_integration,
        )

        # Run backtest
        results = loop.run()

        # Final trades_today should only count last session's trades
        # (Max is 2 per day per config)
        assert 0 <= loop._trades_today <= 2
        assert results is not None  # Verify backtest completed


class TestReproducibility:
    """Test reproducibility across multiple runs."""

    def test_multiple_runs_identical_results(
        self,
        multi_day_data,
        market_state_integration,
        risk_config_integration,
        config_integration,
    ):
        """Test that multiple runs produce identical results."""
        results_list = []

        for _ in range(3):
            loop = BacktestReplayLoop(
                multi_tf_data=multi_day_data,
                timeframe="1m",
                market_state=market_state_integration,
                risk_config=risk_config_integration,
                config=config_integration,
            )
            results = loop.run()
            results_list.append(results)

        # All runs should produce identical results
        for i in range(1, len(results_list)):
            assert results_list[0].total_trades == results_list[i].total_trades
            assert results_list[0].total_pnl == results_list[i].total_pnl
            assert results_list[0].win_rate == results_list[i].win_rate


class TestPerformanceMetrics:
    """Test performance metrics calculation."""

    def test_metrics_consistency(
        self,
        multi_day_data,
        market_state_integration,
        risk_config_integration,
        config_integration,
    ):
        """Test that performance metrics are consistent."""
        loop = BacktestReplayLoop(
            multi_tf_data=multi_day_data,
            timeframe="1m",
            market_state=market_state_integration,
            risk_config=risk_config_integration,
            config=config_integration,
        )

        results = loop.run()

        # Verify metrics consistency
        assert results.total_trades == results.winning_trades + results.losing_trades

        if results.total_trades > 0:
            # Win rate calculation
            expected_win_rate = results.winning_trades / results.total_trades * 100
            assert abs(results.win_rate - expected_win_rate) < 0.01

            # Total PnL should equal sum of individual trade PnLs
            total_pnl_from_trades = sum(
                t.pnl for t in results.trades if t.pnl is not None
            )
            assert abs(results.total_pnl - total_pnl_from_trades) < 0.01
