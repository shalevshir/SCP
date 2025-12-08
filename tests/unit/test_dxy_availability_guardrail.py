"""Unit tests for DXY availability guardrail (Guardrail 6).

This test verifies that the DXY availability guardrail properly blocks trades
when DXY data is missing or invalid (NaN/None values in dxy_corr).
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from backtester.replay_loop import BacktestReplayLoop
from common.types import Candle
from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar


@pytest.fixture
def market_state():
    """Create standard market state for testing."""
    return {
        "buffer_phase": "growth",
        "tier_active": "EarlyMild",
        "ceo_directive_active": True,
        "news_ok": True,
        "session_ok": True,
    }


@pytest.fixture
def risk_config():
    """Create standard risk config for testing."""
    return {
        "risk_per_trade": 600.0,
        "buffer_phase": "growth",
        "max_contracts": 1,
    }


@pytest.fixture
def config_override():
    """Create config override with backtest settings."""
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


def create_multi_tf_data_with_missing_dxy(
    start_time: datetime, num_candles: int, dxy_missing_at: list[int]
) -> MultiTimeframeData:
    """Create multi-timeframe data with DXY missing at specified indices.

    Args:
        start_time: Start timestamp
        num_candles: Number of candles to generate
        dxy_missing_at: List of indices where DXY should be None/invalid

    Returns:
        MultiTimeframeData with synchronized bars
    """
    bars = []
    timestamps = []

    for i in range(num_candles):
        ts = start_time + timedelta(minutes=i)
        timestamps.append(ts)

        # Create GC candle (always valid)
        gc_price = 2650.0 + (i * 0.1)
        exec_gc = Candle(
            timestamp=ts,
            open=gc_price,
            high=gc_price + 1.0,
            low=gc_price - 1.0,
            close=gc_price + 0.5,
            volume=1000 + i,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )

        # Create DXY candle (may be invalid at specified indices)
        if i in dxy_missing_at:
            # Create candle with NaN values to simulate missing data
            exec_dxy = Candle(
                timestamp=ts,
                open=np.nan,
                high=np.nan,
                low=np.nan,
                close=np.nan,
                volume=0,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )
        else:
            dxy_price = 103.0 + (i * 0.01)
            exec_dxy = Candle(
                timestamp=ts,
                open=dxy_price,
                high=dxy_price + 0.1,
                low=dxy_price - 0.1,
                close=dxy_price + 0.05,
                volume=500 + i,
                symbol="DXY",
                timeframe="1m",
                source="CSV",
            )

        # Add HTF data at 15m boundaries
        htf_15m = None
        if i % 15 == 14 or i == 0:
            htf_15m_gc = Candle(
                timestamp=start_time + timedelta(minutes=(i // 15) * 15),
                open=2649.0 + (i // 15) * 1.5,
                high=2652.0 + (i // 15) * 1.5,
                low=2648.0 + (i // 15) * 1.5,
                close=2651.0 + (i // 15) * 1.5,
                volume=15000 + (i // 15) * 1000,
                symbol="GC",
                timeframe="15m",
                source="CSV",
            )

            if i in dxy_missing_at:
                htf_15m_dxy = Candle(
                    timestamp=start_time + timedelta(minutes=(i // 15) * 15),
                    open=np.nan,
                    high=np.nan,
                    low=np.nan,
                    close=np.nan,
                    volume=0,
                    symbol="DXY",
                    timeframe="15m",
                    source="CSV",
                )
            else:
                htf_15m_dxy = Candle(
                    timestamp=start_time + timedelta(minutes=(i // 15) * 15),
                    open=102.9 - (i // 15) * 0.15,
                    high=103.3 - (i // 15) * 0.15,
                    low=102.8 - (i // 15) * 0.15,
                    close=103.1 - (i // 15) * 0.15,
                    volume=7500 + (i // 15) * 500,
                    symbol="DXY",
                    timeframe="15m",
                    source="CSV",
                )
            htf_15m = (htf_15m_gc, htf_15m_dxy)

        # Add HTF data at 1h boundaries
        htf_1h = None
        if i % 60 == 59 or i == 0:
            htf_1h_gc = Candle(
                timestamp=start_time + timedelta(hours=i // 60),
                open=2648.0 + (i // 60) * 6.0,
                high=2654.0 + (i // 60) * 6.0,
                low=2647.0 + (i // 60) * 6.0,
                close=2653.0 + (i // 60) * 6.0,
                volume=60000 + (i // 60) * 5000,
                symbol="GC",
                timeframe="1h",
                source="CSV",
            )

            if i in dxy_missing_at:
                htf_1h_dxy = Candle(
                    timestamp=start_time + timedelta(hours=i // 60),
                    open=np.nan,
                    high=np.nan,
                    low=np.nan,
                    close=np.nan,
                    volume=0,
                    symbol="DXY",
                    timeframe="1h",
                    source="CSV",
                )
            else:
                htf_1h_dxy = Candle(
                    timestamp=start_time + timedelta(hours=i // 60),
                    open=102.5 - (i // 60) * 0.6,
                    high=103.8 - (i // 60) * 0.6,
                    low=102.4 - (i // 60) * 0.6,
                    close=103.5 - (i // 60) * 0.6,
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

    return MultiTimeframeData(
        execution_timeframe="1m",
        htf_timeframes=["15m", "1h"],
        synchronized_bars=bars,
        execution_timestamps=timestamps,
    )


class TestDXYAvailabilityGuardrail:
    """Test DXY availability guardrail enforcement."""

    def test_guardrail_blocks_when_dxy_corr_is_none(
        self, market_state, risk_config, config_override
    ):
        """Test that guardrail blocks trades when dxy_corr is None."""
        # Create a mock features series with dxy_corr = None
        features = pd.Series(
            {
                "timestamp": datetime(2024, 7, 1, 10, 0, tzinfo=UTC),
                "open": 2650.0,
                "high": 2651.0,
                "low": 2649.0,
                "close": 2650.5,
                "volume": 1000,
                "dxy_corr": None,
            }
        )

        validation_context = {
            "session_ok": True,
            "behavior_state": None,
            "session_constraints": None,
        }

        # Create replay loop
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        multi_tf_data = create_multi_tf_data_with_missing_dxy(
            start_time, num_candles=60, dxy_missing_at=[]
        )

        loop = BacktestReplayLoop(
            multi_tf_data=multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            config=config_override,
        )

        # Check guardrails with None dxy_corr
        allowed, reasons = loop._check_guardrails(
            validation_context, features["timestamp"], features
        )

        # Should block due to missing DXY data
        assert not allowed
        assert any("DXY data not available" in reason for reason in reasons)

    def test_guardrail_blocks_when_dxy_corr_is_nan(
        self, market_state, risk_config, config_override
    ):
        """Test that guardrail blocks trades when dxy_corr is NaN."""
        features = pd.Series(
            {
                "timestamp": datetime(2024, 7, 1, 10, 0, tzinfo=UTC),
                "open": 2650.0,
                "high": 2651.0,
                "low": 2649.0,
                "close": 2650.5,
                "volume": 1000,
                "dxy_corr": np.nan,
            }
        )

        validation_context = {
            "session_ok": True,
            "behavior_state": None,
            "session_constraints": None,
        }

        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        multi_tf_data = create_multi_tf_data_with_missing_dxy(
            start_time, num_candles=60, dxy_missing_at=[]
        )

        loop = BacktestReplayLoop(
            multi_tf_data=multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            config=config_override,
        )

        # Check guardrails with NaN dxy_corr
        allowed, reasons = loop._check_guardrails(
            validation_context, features["timestamp"], features
        )

        # Should block due to missing DXY data
        assert not allowed
        assert any("DXY data not available" in reason for reason in reasons)

    def test_guardrail_allows_when_dxy_corr_is_valid(
        self, market_state, risk_config, config_override
    ):
        """Test that guardrail allows trades when dxy_corr is valid."""
        features = pd.Series(
            {
                "timestamp": datetime(2024, 7, 1, 10, 0, tzinfo=UTC),
                "open": 2650.0,
                "high": 2651.0,
                "low": 2649.0,
                "close": 2650.5,
                "volume": 1000,
                "dxy_corr": -0.75,  # Valid correlation value
            }
        )

        validation_context = {
            "session_ok": True,
            "behavior_state": None,
            "session_constraints": None,
        }

        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
        multi_tf_data = create_multi_tf_data_with_missing_dxy(
            start_time, num_candles=60, dxy_missing_at=[]
        )

        loop = BacktestReplayLoop(
            multi_tf_data=multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            config=config_override,
        )

        # Check guardrails with valid dxy_corr
        allowed, reasons = loop._check_guardrails(
            validation_context, features["timestamp"], features
        )

        # Should NOT block due to DXY (may block for other reasons)
        # But specifically, should not have DXY availability message
        assert "DXY data not available" not in reasons

    def test_backtest_with_missing_dxy_produces_no_trades(
        self, market_state, risk_config, config_override
    ):
        """Test end-to-end: backtest with missing DXY produces no trades."""
        start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)

        # Create data where DXY is missing for all candles
        multi_tf_data = create_multi_tf_data_with_missing_dxy(
            start_time, num_candles=180, dxy_missing_at=list(range(180))
        )

        loop = BacktestReplayLoop(
            multi_tf_data=multi_tf_data,
            timeframe="1m",
            market_state=market_state,
            risk_config=risk_config,
            config=config_override,
        )

        results = loop.run()

        # With DXY missing, no trades should be executed
        assert results.total_trades == 0
        assert len(results.trades) == 0

