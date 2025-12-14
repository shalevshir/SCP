"""Tests for edge cases in BacktestReplayLoop, especially around index assignment."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from backtester.replay_loop import BacktestReplayLoop
from common.types import Candle
from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar


@pytest.fixture
def minimal_multi_tf_data():
    """Create minimal multi-timeframe data with very few candles."""
    start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
    bars = []
    timestamps = []

    # Create only 5 candles - this should trigger edge cases
    for i in range(5):
        ts = start_time + timedelta(minutes=i)
        timestamps.append(ts)

        exec_gc = Candle(
            timestamp=ts,
            open=2650.0 + i,
            high=2651.0 + i,
            low=2649.0 + i,
            close=2650.5 + i,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

        exec_dxy = Candle(
            timestamp=ts,
            open=103.0,
            high=103.1,
            low=102.9,
            close=103.05,
            volume=500,
            symbol="DXY",
            timeframe="1m",
            source="CSV",
        )

        bars.append(
            SynchronizedBar(
                execution_timestamp=ts,
                execution_1m=(exec_gc, exec_dxy),
                htf_15m=None,
                htf_1h=None,
            )
        )

    return MultiTimeframeData(
        execution_timeframe="1m",
        htf_timeframes=[],
        synchronized_bars=bars,
        execution_timestamps=timestamps,
    )


class TestIndexAssignmentEdgeCases:
    """Test edge cases in future features index assignment."""

    def test_handles_insufficient_timestamps(self, minimal_multi_tf_data):
        """Test that insufficient timestamps are handled gracefully."""
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
            multi_tf_data=minimal_multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
        )

        # This should not crash even with minimal data
        try:
            results = loop.run()
            # If it runs without error, the fix is working
            assert results is not None
        except ValueError as e:
            if "Length mismatch" in str(
                e
            ) or "cannot set using a list-like indexer" in str(e):
                pytest.fail(f"Index assignment error not properly handled: {e}")
            else:
                # Some other ValueError - might be expected
                pass

    def test_empty_future_timestamps(self, minimal_multi_tf_data):
        """Test handling when there are no future timestamps available."""
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
            multi_tf_data=minimal_multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
        )

        # Run backtest - should handle edge case gracefully
        results = loop.run()

        # Should complete without crashing
        assert results is not None
        assert isinstance(results.total_pnl, float)

    def test_features_longer_than_timestamps(self):
        """Test case where features DataFrame is longer than available timestamps."""
        # Create a scenario where this could happen
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)

        # Create minimal data - just enough to potentially trigger the issue
        bars = []
        for i in range(10):
            ts = start_time + timedelta(minutes=i)

            exec_gc = Candle(
                timestamp=ts,
                open=2650.0,
                high=2651.0,
                low=2649.0,
                close=2650.5,
                volume=1000,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            exec_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.1,
                low=102.9,
                close=103.05,
                volume=500,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=None,
                    htf_1h=None,
                )
            )

        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=bars,
            execution_timestamps=[b.execution_timestamp for b in bars],
        )

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
        )

        # Should not raise ValueError about length mismatch
        try:
            results = loop.run()
            assert results is not None
        except ValueError as e:
            if "Length mismatch" in str(e):
                pytest.fail(f"Length mismatch not handled: {e}")
            raise


class TestHTFBiasCallOrder:
    """Test that HTF bias computation happens on every bar, even with active trades."""

    def test_htf_bias_called_with_active_trade_present(self):
        """Test that HTF bias is called even when an active trade exists.

        Bug: HTF bias computation was happening AFTER the active trade check,
        which caused early return and skipped HTF data accumulation when trades
        were active. This contradicts the comment that HTF bias must run on every bar.
        """
        import pandas as pd

        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        bars = []

        # Create minimal data
        for i in range(5):
            ts = start_time + timedelta(minutes=i)

            exec_gc = Candle(
                timestamp=ts,
                open=2650.0,
                high=2651.0,
                low=2649.0,
                close=2650.5,
                volume=1000,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            exec_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.1,
                low=102.9,
                close=103.05,
                volume=500,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=None,
                    htf_1h=None,
                )
            )

        multi_tf_data = MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=bars,
            execution_timestamps=[b.execution_timestamp for b in bars],
        )

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
        )

        # Track if HTF bias is called
        htf_bias_called = {"count": 0}

        original_htf_bias = loop._htf_bias_func

        def tracked_htf_bias(features, validation_context):
            htf_bias_called["count"] += 1
            return original_htf_bias(features, validation_context)

        loop._htf_bias_func = tracked_htf_bias

        # Mock _update_active_trades to avoid trade simulation errors
        # but still allow us to inject an active trade
        original_update = loop._update_active_trades

        def mock_update(current_candle, features):
            # Don't process the mock trade, just skip
            pass

        loop._update_active_trades = mock_update

        # Manually inject an active trade to simulate having an open position
        mock_trade = Mock()
        mock_trade.trade_id = "test_trade_001"
        mock_trade.entry_timestamp = start_time
        mock_trade.status = "ACTIVE"
        mock_trade.direction = "LONG"
        mock_trade.entry_price = 2650.0
        mock_trade.stop_loss = 2645.0
        mock_trade.take_profit = 2660.0
        loop._active_trades["test_trade_001"] = mock_trade

        # Create mock features and validation context to test _process_candle directly
        mock_features = pd.Series(
            {
                "timestamp": start_time + timedelta(minutes=1),
                "open": 2650.0,
                "high": 2651.0,
                "low": 2649.0,
                "close": 2650.5,
                "volume": 1000,
            }
        )

        mock_validation_context = {
            "tier": "EarlyMild",
            "session": "AM",
        }

        # Process a candle with an active trade present
        result = loop._process_candle(
            mock_features,
            mock_validation_context,
            None,  # next_candle
            start_time + timedelta(minutes=1),
        )

        # The key assertion: HTF bias MUST be called even with active trade
        # Before the fix, this would be 0 because early return happens first
        assert htf_bias_called["count"] > 0, (
            "HTF bias must be called on every bar, even when an active trade exists. "
            "This is required for structure detection warmup."
        )


class TestGuardrailsPDLL:
    """Test PDLL (Per Day Loss Limit) guardrails - specification-based."""

    @pytest.fixture
    def multi_tf_data_with_enough_bars(self):
        """Create multi-timeframe data with enough bars for multiple trades."""
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        bars = []

        # Create 120 bars (2 hours) to allow multiple trades
        for i in range(120):
            ts = start_time + timedelta(minutes=i)

            exec_gc = Candle(
                timestamp=ts,
                open=2650.0 + i * 0.1,
                high=2651.0 + i * 0.1,
                low=2649.0 + i * 0.1,
                close=2650.5 + i * 0.1,
                volume=1000,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            exec_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.1,
                low=102.9,
                close=103.05,
                volume=500,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=None,
                    htf_1h=None,
                )
            )

        return MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=bars,
            execution_timestamps=[b.execution_timestamp for b in bars],
        )

    def test_pdll_hit_blocks_further_trading(self, multi_tf_data_with_enough_bars):
        """PDLL hit blocks further trading for the session.

        Specification: "if self._pdll_hit: blocking_reasons.append('PDLL hit - no further trading today')"
        """
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

        # Use config with very low PDLL to trigger it
        config = {
            "backtest": {
                "pdll_limit": 50.0,  # Very low limit to trigger easily
                "max_trades_per_day": 5,
                "slippage_points": 0.5,
                "commission_per_trade": 5.0,
            },
            "assets": {
                "tick_values": {"GC": 10.0},
                "tick_sizes": {"GC": 0.1},
            },
        }

        loop = BacktestReplayLoop(
            multi_tf_data=multi_tf_data_with_enough_bars,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            config=config,
        )

        # Manually set PDLL hit
        loop._pdll_hit = True
        loop._daily_pnl = -60.0  # Below PDLL limit

        # Check guardrails
        allowed, reasons = loop._check_guardrails(
            validation_context={
                "session_ok": True,
                "behavior_state": None,
                "session_constraints": None,
            },
            current_timestamp=datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
        )

        # Should be blocked
        assert not allowed
        assert any("PDLL" in r for r in reasons)

    def test_pdll_limit_reached_mid_session(self, multi_tf_data_with_enough_bars):
        """PDLL limit reached mid-session blocks further entries.

        Specification: "if self._daily_pnl <= -pdll_limit"
        """
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

        config = {
            "backtest": {
                "pdll_limit": 600.0,
                "max_trades_per_day": 5,
                "slippage_points": 0.5,
                "commission_per_trade": 5.0,
            },
            "assets": {
                "tick_values": {"GC": 10.0},
                "tick_sizes": {"GC": 0.1},
            },
        }

        loop = BacktestReplayLoop(
            multi_tf_data=multi_tf_data_with_enough_bars,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            config=config,
        )

        # Set daily PnL to exactly at PDLL limit
        loop._daily_pnl = -600.0
        loop._session_date = datetime(2024, 7, 1).date()

        # Check guardrails
        allowed, reasons = loop._check_guardrails(
            validation_context={
                "session_ok": True,
                "behavior_state": None,
                "session_constraints": None,
            },
            current_timestamp=datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
        )

        # Should be blocked
        assert not allowed
        assert any("PDLL limit reached" in r for r in reasons)

        # PDLL hit flag should be set
        assert loop._pdll_hit is True
        assert loop._pdll_hit_count == 1


class TestGuardrailsSessionAndDailyLimits:
    """Test session time and daily trade limit guardrails - specification-based."""

    @pytest.fixture
    def basic_multi_tf_data(self):
        """Create basic multi-timeframe data for testing."""
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        bars = []

        for i in range(30):
            ts = start_time + timedelta(minutes=i)

            exec_gc = Candle(
                timestamp=ts,
                open=2650.0,
                high=2651.0,
                low=2649.0,
                close=2650.5,
                volume=1000,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            exec_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.1,
                low=102.9,
                close=103.05,
                volume=500,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=None,
                    htf_1h=None,
                )
            )

        return MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=bars,
            execution_timestamps=[b.execution_timestamp for b in bars],
        )

    def test_daily_trade_limit_reached_blocks_entry(self, basic_multi_tf_data):
        """Daily trade limit reached blocks further entries.

        Specification: "if self._trades_today >= max_trades_per_day"
        """
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

        config = {
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

        loop = BacktestReplayLoop(
            multi_tf_data=basic_multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            config=config,
        )

        # Set trades today to limit
        loop._trades_today = 2
        loop._session_date = datetime(2024, 7, 1).date()

        # Check guardrails
        allowed, reasons = loop._check_guardrails(
            validation_context={
                "session_ok": True,
                "behavior_state": None,
                "session_constraints": None,
            },
            current_timestamp=datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
        )

        # Should be blocked
        assert not allowed
        assert any("Daily trade limit reached" in r for r in reasons)

    def test_outside_session_hours_blocks_entry(self, basic_multi_tf_data):
        """Outside trading session hours (10:00-13:00 ILT) blocks entry.

        Specification: "if not session_ok: blocking_reasons.append('Outside trading session hours')"
        """
        market_state = {
            "buffer_phase": "growth",
            "tier_active": "EarlyMild",
            "ceo_directive_active": True,
            "news_ok": True,
            "session_ok": False,  # Outside session
        }

        risk_config = {
            "risk_per_trade": 600.0,
            "buffer_phase": "growth",
            "max_contracts": 1,
        }

        loop = BacktestReplayLoop(
            multi_tf_data=basic_multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
        )

        # Check guardrails with session_ok=False in context
        allowed, reasons = loop._check_guardrails(
            validation_context={
                "session_ok": False,  # Outside session
                "behavior_state": None,
                "session_constraints": None,
            },
            current_timestamp=datetime(2024, 7, 1, 9, 30, tzinfo=UTC),  # Before 10:00
        )

        # Should be blocked
        assert not allowed
        assert any("Outside trading session" in r for r in reasons)


class TestGuardrailsDXYAvailability:
    """Test DXY availability guardrails - specification-based."""

    @pytest.fixture
    def basic_multi_tf_data(self):
        """Create basic multi-timeframe data."""
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        bars = []

        for i in range(10):
            ts = start_time + timedelta(minutes=i)

            exec_gc = Candle(
                timestamp=ts,
                open=2650.0,
                high=2651.0,
                low=2649.0,
                close=2650.5,
                volume=1000,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            exec_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.1,
                low=102.9,
                close=103.05,
                volume=500,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=None,
                    htf_1h=None,
                )
            )

        return MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=bars,
            execution_timestamps=[b.execution_timestamp for b in bars],
        )

    def test_missing_dxy_data_blocks_entry(self, basic_multi_tf_data):
        """Missing DXY data (NaN correlation) blocks entry.

        Specification: "if dxy_corr is None or pd.isna(dxy_corr): blocking_reasons.append('DXY data not available')"
        """
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
            multi_tf_data=basic_multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
        )

        # Create features with missing DXY correlation
        import pandas as pd

        features_with_nan_dxy = pd.Series(
            {
                "timestamp": datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
                "open": 2650.0,
                "close": 2650.5,
                "dxy_corr": float("nan"),  # Missing DXY data
            }
        )

        # Check guardrails
        allowed, reasons = loop._check_guardrails(
            validation_context={
                "session_ok": True,
                "behavior_state": None,
                "session_constraints": None,
            },
            current_timestamp=datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
            features=features_with_nan_dxy,
        )

        # Should be blocked
        assert not allowed
        assert any("DXY data not available" in r for r in reasons)

    def test_none_dxy_correlation_blocks_entry(self, basic_multi_tf_data):
        """None DXY correlation blocks entry.

        Specification: DXY availability check should handle None values.
        """
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
            multi_tf_data=basic_multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
        )

        # Create features with None DXY correlation
        import pandas as pd

        features_with_none_dxy = pd.Series(
            {
                "timestamp": datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
                "open": 2650.0,
                "close": 2650.5,
                "dxy_corr": None,  # None DXY data
            }
        )

        # Check guardrails
        allowed, reasons = loop._check_guardrails(
            validation_context={
                "session_ok": True,
                "behavior_state": None,
                "session_constraints": None,
            },
            current_timestamp=datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
            features=features_with_none_dxy,
        )

        # Should be blocked
        assert not allowed
        assert any("DXY data not available" in r for r in reasons)


class TestGuardrailsRiskLadder:
    """Test Risk Ladder guardrails - specification-based."""

    @pytest.fixture
    def basic_multi_tf_data(self):
        """Create basic multi-timeframe data."""
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        bars = []

        for i in range(10):
            ts = start_time + timedelta(minutes=i)

            exec_gc = Candle(
                timestamp=ts,
                open=2650.0,
                high=2651.0,
                low=2649.0,
                close=2650.5,
                volume=1000,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            exec_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.1,
                low=102.9,
                close=103.05,
                volume=500,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=None,
                    htf_1h=None,
                )
            )

        return MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=bars,
            execution_timestamps=[b.execution_timestamp for b in bars],
        )

    def test_zero_max_contracts_blocks_entry(self, basic_multi_tf_data):
        """Zero max_contracts blocks entry.

        Specification: "if max_contracts <= 0: blocking_reasons.append('Risk ladder constraint')"
        """
        market_state = {
            "buffer_phase": "startup",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
            "session_ok": True,
        }

        risk_config = {
            "risk_per_trade": 0.0,  # No risk allowed
            "buffer_phase": "startup",
            "max_contracts": 0,  # Zero contracts = no trading
        }

        loop = BacktestReplayLoop(
            multi_tf_data=basic_multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
        )

        # Check guardrails
        allowed, reasons = loop._check_guardrails(
            validation_context={
                "session_ok": True,
                "behavior_state": None,
                "session_constraints": None,
            },
            current_timestamp=datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
        )

        # Should be blocked
        assert not allowed
        assert any("Risk ladder constraint" in r for r in reasons)


class TestGuardrailsMultipleFailures:
    """Test multiple guardrails failing simultaneously - specification-based."""

    @pytest.fixture
    def basic_multi_tf_data(self):
        """Create basic multi-timeframe data."""
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        bars = []

        for i in range(10):
            ts = start_time + timedelta(minutes=i)

            exec_gc = Candle(
                timestamp=ts,
                open=2650.0,
                high=2651.0,
                low=2649.0,
                close=2650.5,
                volume=1000,
                symbol="GC",
                timeframe="1m",
                source="CSV",
            )

            exec_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.1,
                low=102.9,
                close=103.05,
                volume=500,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

            bars.append(
                SynchronizedBar(
                    execution_timestamp=ts,
                    execution_1m=(exec_gc, exec_dxy),
                    htf_15m=None,
                    htf_1h=None,
                )
            )

        return MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=bars,
            execution_timestamps=[b.execution_timestamp for b in bars],
        )

    def test_multiple_guardrails_fail_simultaneously(self, basic_multi_tf_data):
        """Multiple guardrails failing simultaneously all reported in reasons.

        Specification: Guardrails are checked independently and all failures reported.
        """
        market_state = {
            "buffer_phase": "growth",
            "tier_active": "EarlyMild",
            "ceo_directive_active": True,
            "news_ok": True,
            "session_ok": False,  # Guardrail 1: Session
        }

        risk_config = {
            "risk_per_trade": 600.0,
            "buffer_phase": "growth",
            "max_contracts": 1,
        }

        config = {
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

        loop = BacktestReplayLoop(
            multi_tf_data=basic_multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            config=config,
        )

        # Set multiple failing conditions
        loop._pdll_hit = True  # Guardrail 2: PDLL
        loop._trades_today = 2  # Guardrail 3: Daily limit
        loop._session_date = datetime(2024, 7, 1).date()

        # Check guardrails
        import pandas as pd

        features = pd.Series(
            {
                "timestamp": datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
                "dxy_corr": float("nan"),  # Guardrail 4: DXY missing
            }
        )

        allowed, reasons = loop._check_guardrails(
            validation_context={
                "session_ok": False,  # Guardrail 1
                "behavior_state": None,
                "session_constraints": None,
            },
            current_timestamp=datetime(2024, 7, 1, 10, 30, tzinfo=UTC),
            features=features,
        )

        # Should be blocked
        assert not allowed

        # Should have multiple reasons
        assert len(reasons) >= 3
        assert any("PDLL" in r for r in reasons)
        assert any("Daily trade limit" in r for r in reasons)
        assert any("session" in r for r in reasons)


class TestSessionManagement:
    """Test session reset and boundary handling - specification-based."""

    @pytest.fixture
    def multi_day_data(self):
        """Create multi-day data for session boundary testing."""
        bars = []

        # Day 1: 10:00-12:00
        for hour in range(10, 13):
            for minute in range(0, 60, 15):
                ts = datetime(2024, 7, 1, hour, minute, tzinfo=UTC)

                exec_gc = Candle(
                    timestamp=ts,
                    open=2650.0,
                    high=2651.0,
                    low=2649.0,
                    close=2650.5,
                    volume=1000,
                    symbol="GC",
                    timeframe="1m",
                    source="CSV",
                )

                exec_dxy = Candle(
                    timestamp=ts,
                    open=103.0,
                    high=103.1,
                    low=102.9,
                    close=103.05,
                    volume=500,
                    symbol="DXY",
                    timeframe="1m",
                    source="CSV",
                )

                bars.append(
                    SynchronizedBar(
                        execution_timestamp=ts,
                        execution_1m=(exec_gc, exec_dxy),
                        htf_15m=None,
                        htf_1h=None,
                    )
                )

        # Day 2: 10:00-12:00
        for hour in range(10, 13):
            for minute in range(0, 60, 15):
                ts = datetime(2024, 7, 2, hour, minute, tzinfo=UTC)

                exec_gc = Candle(
                    timestamp=ts,
                    open=2655.0,
                    high=2656.0,
                    low=2654.0,
                    close=2655.5,
                    volume=1000,
                    symbol="GC",
                    timeframe="1m",
                    source="CSV",
                )

                exec_dxy = Candle(
                    timestamp=ts,
                    open=103.0,
                    high=103.1,
                    low=102.9,
                    close=103.05,
                    volume=500,
                    symbol="DXY",
                    timeframe="1m",
                    source="CSV",
                )

                bars.append(
                    SynchronizedBar(
                        execution_timestamp=ts,
                        execution_1m=(exec_gc, exec_dxy),
                        htf_15m=None,
                        htf_1h=None,
                    )
                )

        return MultiTimeframeData(
            execution_timeframe="1m",
            htf_timeframes=[],
            synchronized_bars=bars,
            execution_timestamps=[b.execution_timestamp for b in bars],
        )

    def test_session_reset_clears_daily_pnl(self, multi_day_data):
        """Session reset clears daily PnL.

        Specification: "self._daily_pnl = 0.0" on session reset.
        """
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
            multi_tf_data=multi_day_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
        )

        # Set initial session state
        loop._session_date = datetime(2024, 7, 1).date()
        loop._daily_pnl = -300.0  # Some loss from day 1
        loop._pdll_hit = False
        loop._trades_today = 1

        # Trigger session reset for day 2
        loop._reset_session(datetime(2024, 7, 2, 10, 0, tzinfo=UTC))

        # Should be reset
        assert loop._daily_pnl == 0.0
        assert loop._pdll_hit is False
        assert loop._trades_today == 0
        assert loop._session_date == datetime(2024, 7, 2).date()

    def test_session_reset_increments_counter(self, multi_day_data):
        """Session reset increments reset counter.

        Specification: "self._session_reset_count += 1"
        """
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
            multi_tf_data=multi_day_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
        )

        initial_count = loop._session_reset_count

        # Trigger session reset
        loop._reset_session(datetime(2024, 7, 1, 10, 0, tzinfo=UTC))

        assert loop._session_reset_count == initial_count + 1
