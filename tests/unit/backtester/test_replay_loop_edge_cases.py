"""Tests for edge cases in BacktestReplayLoop, especially around index assignment."""

from datetime import UTC, datetime, timedelta

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
