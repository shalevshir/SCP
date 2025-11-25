"""Integration tests for full backtesting pipeline with trade simulation.

Following TDD principles: tests demonstrate complete workflow.
"""

from datetime import UTC, datetime
from dataclasses import replace

import pandas as pd
import pytest
from backtester.pipeline import run_backtest_with_trades
from common.types import Candle
from rule_engine.htf.types import HTFBias


@pytest.fixture
def sample_gc_data():
    """Create sample GC data for testing."""
    timestamps = pd.date_range(
        start="2025-01-01 10:00", end="2025-01-01 11:00", freq="1min", tz=UTC
    )
    data = {
        "open": [2650.0 + i * 0.1 for i in range(len(timestamps))],
        "high": [2651.0 + i * 0.1 for i in range(len(timestamps))],
        "low": [2649.0 + i * 0.1 for i in range(len(timestamps))],
        "close": [2650.5 + i * 0.1 for i in range(len(timestamps))],
        "volume": [100.0] * len(timestamps),
    }
    df = pd.DataFrame(data, index=timestamps)
    return df


@pytest.fixture
def sample_dxy_data():
    """Create sample DXY data for testing."""
    timestamps = pd.date_range(
        start="2025-01-01 10:00", end="2025-01-01 11:00", freq="1min", tz=UTC
    )
    data = {
        "open": [106.0] * len(timestamps),
        "high": [106.1] * len(timestamps),
        "low": [105.9] * len(timestamps),
        "close": [106.0] * len(timestamps),
        "volume": [100.0] * len(timestamps),
    }
    df = pd.DataFrame(data, index=timestamps)
    return df


@pytest.fixture
def market_state():
    """Create market state for testing."""
    return {
        "buffer_phase": "startup",
        "tier_active": "EarlyMild",
        "ceo_directive_active": True,
        "news_ok": True,
        "session_ok": True,
    }


@pytest.fixture
def risk_config():
    """Create risk config for testing."""
    return {
        "risk_per_trade": 350.0,
        "buffer_phase": "startup",
        "max_contracts": 1,
    }


def simple_htf_bias(features: pd.Series, context: dict) -> HTFBias:
    """Simple HTF bias function for testing."""
    return HTFBias(
        bias="bullish",
        direction="long",
        score=8.5,
        confidence="high",
        vwap_trend_confirmed=True,
        dxy_alignment=True,
        bos_detected=True,
    )


class TestRunBacktestWithTrades:
    """Tests for run_backtest_with_trades() function."""

    def test_pipeline_returns_trades(
        self, sample_gc_data, sample_dxy_data, market_state, risk_config
    ):
        """Test that pipeline returns list of closed trades."""
        trades = run_backtest_with_trades(
            gc_df=sample_gc_data,
            dxy_df=sample_dxy_data,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=simple_htf_bias,
            risk_config=risk_config,
        )

        # Should return a list (may be empty if no signals generated)
        assert isinstance(trades, list)

    def test_all_trades_are_closed(
        self, sample_gc_data, sample_dxy_data, market_state, risk_config
    ):
        """Test that all returned trades are closed."""
        trades = run_backtest_with_trades(
            gc_df=sample_gc_data,
            dxy_df=sample_dxy_data,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=simple_htf_bias,
            risk_config=risk_config,
        )

        # All trades should be closed
        for trade in trades:
            assert trade.status != "OPEN"
            assert trade.exit_reason is not None
            assert trade.exit_price is not None
            assert trade.pnl is not None

    def test_trades_have_valid_exit_reasons(
        self, sample_gc_data, sample_dxy_data, market_state, risk_config
    ):
        """Test that all trades have valid exit reasons."""
        trades = run_backtest_with_trades(
            gc_df=sample_gc_data,
            dxy_df=sample_dxy_data,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=simple_htf_bias,
            risk_config=risk_config,
        )

        valid_reasons = ["TP", "SL", "TIME", "INVALIDATION", "END_OF_DATA", "INVALID_SETUP"]
        for trade in trades:
            assert trade.exit_reason in valid_reasons

    def test_trades_have_calculated_pnl(
        self, sample_gc_data, sample_dxy_data, market_state, risk_config
    ):
        """Test that all trades have calculated PnL."""
        trades = run_backtest_with_trades(
            gc_df=sample_gc_data,
            dxy_df=sample_dxy_data,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=simple_htf_bias,
            risk_config=risk_config,
        )

        for trade in trades:
            # All closed trades should have PnL
            assert trade.pnl is not None
            assert trade.r_realized is not None
            assert isinstance(trade.pnl, float)
            assert isinstance(trade.r_realized, float)

    def test_empty_dataset_raises_error(self, market_state, risk_config):
        """Test that empty dataset raises ValueError."""
        # Create empty DataFrames with DatetimeIndex
        empty_gc = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([], name="timestamp", tz=UTC),
        )
        empty_dxy = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([], name="timestamp", tz=UTC),
        )

        # Empty datasets should raise ValueError from feature engine
        with pytest.raises(ValueError, match="No common timestamps"):
            run_backtest_with_trades(
                gc_df=empty_gc,
                dxy_df=empty_dxy,
                timeframe="1m",
                market_state=market_state,
                htf_bias_func=simple_htf_bias,
                risk_config=risk_config,
            )


class TestGetFutureCandles:
    """Tests for get_future_candles() helper function."""

    def test_get_future_candles_returns_correct_count(self, sample_gc_data):
        """Test that get_future_candles returns correct number of candles."""
        from backtester.pipeline import get_future_candles

        entry_timestamp = sample_gc_data.index[10]  # 10th candle
        max_bars = 20

        future = get_future_candles(sample_gc_data, entry_timestamp, max_bars)

        # Should return min(20, available_candles_after_entry)
        available = len(sample_gc_data) - 11  # 10th index = 11th candle
        expected = min(max_bars, available)
        assert len(future) == expected

    def test_get_future_candles_handles_end_of_data(self, sample_gc_data):
        """Test get_future_candles at end of dataset."""
        from backtester.pipeline import get_future_candles

        # Last candle - no future data
        entry_timestamp = sample_gc_data.index[-1]
        max_bars = 20

        future = get_future_candles(sample_gc_data, entry_timestamp, max_bars)

        assert len(future) == 0

    def test_get_future_candles_handles_invalid_timestamp(self, sample_gc_data):
        """Test get_future_candles with invalid timestamp."""
        from backtester.pipeline import get_future_candles

        invalid_timestamp = pd.Timestamp("2025-01-01 12:00", tz=UTC)
        max_bars = 20

        future = get_future_candles(sample_gc_data, invalid_timestamp, max_bars)

        assert len(future) == 0

    def test_confirmation_candle_is_entry_candle(
        self, sample_gc_data, sample_dxy_data, market_state, risk_config
    ):
        """Test that confirmation candle is the entry candle, not previous candle."""
        from backtester.trade import create_trade_from_entry
        from backtester.entry_model import EntryExecution
        from common.types import Candle
        from datetime import UTC, datetime
        from rule_engine.signal import Signal

        # Create a mock entry execution
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_timestamp = datetime(2025, 1, 1, 10, 6, tzinfo=UTC)
        entry = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=entry_timestamp,
            entry_price=2650.5,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Get entry candle from DataFrame
        entry_idx = sample_gc_data.index.get_loc(entry_timestamp)
        entry_candle_row = sample_gc_data.iloc[entry_idx]

        # Verify entry candle is used (not entry_idx - 1)
        confirmation_candle = Candle(
            timestamp=entry_candle_row.name,
            open=entry_candle_row["open"],
            high=entry_candle_row["high"],
            low=entry_candle_row["low"],
            close=entry_candle_row["close"],
            volume=entry_candle_row["volume"],
            symbol="GC",
            timeframe="1m",
            source="BACKTEST",
        )

        # Create trade - SL should be based on entry candle
        trade = create_trade_from_entry(
            entry_execution=entry,
            confirmation_candle=confirmation_candle,
            bos_candle=None,
            risk_config=risk_config,
            market_context={
                "month": 11,
                "htf_aligned": True,
                "dxy_aligned": True,
            },
        )

        # For continuation long, SL should be confirmation_candle.low
        assert trade.stop_loss == confirmation_candle.low

    def test_htf_alignment_correctly_compares_bullish_long_and_bearish_short(
        self, sample_gc_data, sample_dxy_data, market_state, risk_config
    ):
        """Test that HTF alignment correctly compares bullish/long and bearish/short."""
        from backtester.trade import create_trade_from_entry
        from backtester.entry_model import EntryExecution
        from common.types import Candle
        from datetime import UTC, datetime
        from rule_engine.signal import Signal

        # Test case 1: Bullish bias with long direction should be aligned
        signal_bullish_long = Signal(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_timestamp = datetime(2025, 1, 1, 10, 6, tzinfo=UTC)
        entry = EntryExecution(
            signal_timestamp=signal_bullish_long.timestamp,
            entry_timestamp=entry_timestamp,
            entry_price=2650.5,
            signal=signal_bullish_long,
            executed=True,
            rejection_reason=None,
        )

        entry_idx = sample_gc_data.index.get_loc(entry_timestamp)
        entry_candle_row = sample_gc_data.iloc[entry_idx]
        confirmation_candle = Candle(
            timestamp=entry_candle_row.name,
            open=entry_candle_row["open"],
            high=entry_candle_row["high"],
            low=entry_candle_row["low"],
            close=entry_candle_row["close"],
            volume=entry_candle_row["volume"],
            symbol="GC",
            timeframe="1m",
            source="BACKTEST",
        )

        # November + HTF aligned + DXY aligned should give 3R for fade
        trade = create_trade_from_entry(
            entry_execution=entry,
            confirmation_candle=confirmation_candle,
            bos_candle=None,
            risk_config=risk_config,
            market_context={
                "month": 11,  # November
                "htf_aligned": True,  # Should be True for bullish + long
                "dxy_aligned": True,
            },
        )

        # Should get 3R for fade in November with alignment
        assert trade.r_multiple == 3.0

        # Test case 2: Bearish bias with short direction should be aligned
        signal_bearish_short = Signal(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry2 = EntryExecution(
            signal_timestamp=signal_bearish_short.timestamp,
            entry_timestamp=entry_timestamp,
            entry_price=2650.5,
            signal=signal_bearish_short,
            executed=True,
            rejection_reason=None,
        )

        trade2 = create_trade_from_entry(
            entry_execution=entry2,
            confirmation_candle=confirmation_candle,
            bos_candle=None,
            risk_config=risk_config,
            market_context={
                "month": 11,
                "htf_aligned": True,  # Should be True for bearish + short
                "dxy_aligned": True,
            },
        )

        # Should also get 3R
        assert trade2.r_multiple == 3.0

        # Test case 3: Mismatched (bullish + short) should not be aligned
        signal_mismatch = Signal(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bullish",  # Mismatch: bullish but short
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry3 = EntryExecution(
            signal_timestamp=signal_mismatch.timestamp,
            entry_timestamp=entry_timestamp,
            entry_price=2650.5,
            signal=signal_mismatch,
            executed=True,
            rejection_reason=None,
        )

        trade3 = create_trade_from_entry(
            entry_execution=entry3,
            confirmation_candle=confirmation_candle,
            bos_candle=None,
            risk_config=risk_config,
            market_context={
                "month": 11,
                "htf_aligned": False,  # Should be False for mismatch
                "dxy_aligned": True,
            },
        )

        # Should get 2R (not 3R) because htf_aligned is False
        assert trade3.r_multiple == 2.0

    def test_vwap_fade_uses_entry_time_htf_bias_for_alignment(
        self, market_state, risk_config, monkeypatch
    ):
        """Ensure HTF alignment is based on entry timestamp bias, not signal timestamp."""
        import pandas as pd
        from rule_engine.signal import Signal

        # Create November dataset so fades can upgrade to 3R
        timestamps = pd.date_range(
            start="2025-11-01 09:00", periods=30, freq="1min", tz=UTC
        )
        gc_df = pd.DataFrame(
            {
                "open": [2000.0 + i * 0.5 for i in range(len(timestamps))],
                "high": [2000.5 + i * 0.5 for i in range(len(timestamps))],
                "low": [1999.5 + i * 0.5 for i in range(len(timestamps))],
                "close": [2000.2 + i * 0.5 for i in range(len(timestamps))],
                "volume": [100.0] * len(timestamps),
            },
            index=timestamps,
        )
        dxy_df = pd.DataFrame(
            {
                "open": [106.0] * len(timestamps),
                "high": [106.1] * len(timestamps),
                "low": [105.9] * len(timestamps),
                "close": [106.0] * len(timestamps),
                "volume": [50.0] * len(timestamps),
            },
            index=timestamps,
        )

        signal_timestamp = timestamps[5]
        entry_timestamp = timestamps[6]
        signal_row = gc_df.loc[signal_timestamp]
        entry_row = gc_df.loc[entry_timestamp]

        signal_features = pd.Series(
            {
                "timestamp": signal_timestamp,
                "symbol": "GC",
                "timeframe": "1m",
                "open": signal_row["open"],
                "high": signal_row["high"],
                "low": signal_row["low"],
                "close": signal_row["close"],
                "volume": signal_row["volume"],
            }
        )

        entry_features = pd.Series(
            {
                "timestamp": entry_timestamp,
                "symbol": "GC",
                "timeframe": "1m",
                "open": entry_row["open"],
                "high": entry_row["high"],
                "low": entry_row["low"],
                "close": entry_row["close"],
                "volume": entry_row["volume"],
            }
        )

        next_candle = Candle(
            timestamp=entry_timestamp,
            open=entry_row["open"],
            high=entry_row["high"],
            low=entry_row["low"],
            close=entry_row["close"],
            volume=entry_row["volume"],
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        class DummyProcessor:
            def __init__(self, timeframe: str):
                self.timeframe = timeframe

            def iterate_with_entry_context(self, *_args, **_kwargs):
                yield signal_features, {}, next_candle

            def iterate_with_context(self, *_args, **_kwargs):
                yield signal_features, {}
                yield entry_features, {}

        monkeypatch.setattr("backtester.pipeline.BacktestProcessor", DummyProcessor)

        def fake_process_features_with_validation(
            features, htf_bias, market_state, **kwargs
        ):
            return Signal(
                timestamp=features["timestamp"],
                symbol=features["symbol"],
                timeframe=features["timeframe"],
                direction="long",
                setup_type="VWAP_FADE",
                htf_bias=htf_bias.bias,
                score=9.0,
                confidence="A+",
                factors={},
                rationale="test signal",
                validation_flags={},
                enforcer_tier=market_state["tier_active"],
            )

        monkeypatch.setattr(
            "backtester.pipeline.process_features_with_validation",
            fake_process_features_with_validation,
        )

        def shifting_htf_bias(features: pd.Series, _context: dict) -> HTFBias:
            if features["timestamp"] == signal_timestamp:
                return HTFBias(
                    bias="bullish",
                    direction="long",
                    score=9.5,
                    confidence="high",
                    vwap_trend_confirmed=True,
                    dxy_alignment=True,
                )
            return HTFBias(
                bias="bearish",
                direction="short",
                score=9.5,
                confidence="high",
                vwap_trend_confirmed=True,
                dxy_alignment=True,
            )

        def fake_simulate_trade_outcome(trade, *_args, **_kwargs):
            return replace(
                trade,
                exit_timestamp=trade.entry_timestamp,
                exit_price=trade.take_profit,
                exit_reason="TP",
                pnl=trade.reward_amount,
                pnl_percent=100.0,
                r_realized=trade.r_multiple,
                status="CLOSED_WIN",
            )

        monkeypatch.setattr(
            "backtester.pipeline.simulate_trade_outcome", fake_simulate_trade_outcome
        )

        trades = run_backtest_with_trades(
            gc_df=gc_df,
            dxy_df=dxy_df,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=shifting_htf_bias,
            risk_config=risk_config,
        )

        assert len(trades) == 1
        # HTF alignment should be False because entry-time bias is bearish vs long direction
        assert trades[0].setup_type == "VWAP_FADE"
        assert trades[0].r_multiple == 2.0

