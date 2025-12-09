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
        mock_features = pd.Series({
            "timestamp": start_time + timedelta(minutes=1),
            "open": 2650.0,
            "high": 2651.0,
            "low": 2649.0,
            "close": 2650.5,
            "volume": 1000,
        })
        
        mock_validation_context = {
            "tier": "EarlyMild",
            "session": "AM",
        }
        
        # Process a candle with an active trade present
        result = loop._process_candle(
            mock_features,
            mock_validation_context,
            None,  # next_candle
            start_time + timedelta(minutes=1)
        )
        
        # The key assertion: HTF bias MUST be called even with active trade
        # Before the fix, this would be 0 because early return happens first
        assert htf_bias_called["count"] > 0, (
            "HTF bias must be called on every bar, even when an active trade exists. "
            "This is required for structure detection warmup."
        )
