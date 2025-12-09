"""Integration tests for backtesting pipeline with entry execution."""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from backtester.entry_model import EntryExecution
from backtester.pipeline import run_backtest_with_entries
from common.types import Candle
from feature_engine.backtesting import BacktestProcessor
from rule_engine.htf.types import HTFBias


class TestBacktestProcessorEntryContext:
    """Tests for BacktestProcessor.iterate_with_entry_context method."""

    @pytest.fixture
    def sample_data(self):
        """Generate sample GC and DXY DataFrames for testing."""
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        timestamps = [base_time + timedelta(minutes=i) for i in range(100)]

        gc_df = pd.DataFrame(
            {
                "open": [2000.0 + i * 0.5 for i in range(100)],
                "high": [2002.0 + i * 0.5 for i in range(100)],
                "low": [1998.0 + i * 0.5 for i in range(100)],
                "close": [2001.0 + i * 0.5 for i in range(100)],
                "volume": [1000.0 + i * 10 for i in range(100)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        dxy_df = pd.DataFrame(
            {
                "open": [100.0 - i * 0.02 for i in range(100)],
                "high": [100.5 - i * 0.02 for i in range(100)],
                "low": [99.5 - i * 0.02 for i in range(100)],
                "close": [100.0 - i * 0.02 for i in range(100)],
                "volume": [1000.0 for _ in range(100)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        return gc_df, dxy_df

    def test_iterate_with_entry_context_yields_three_values(self, sample_data):
        """Test that iterate_with_entry_context yields tuples."""
        gc_df, dxy_df = sample_data
        processor = BacktestProcessor(timeframe="1m")

        results = list(processor.iterate_with_entry_context(gc_df, dxy_df))

        assert len(results) > 0
        # Each result should be a tuple of 3 elements
        features, validation_context, next_candle = results[0]
        assert isinstance(features, pd.Series)
        assert isinstance(validation_context, dict)
        assert isinstance(next_candle, Candle) or next_candle is None

    def test_next_candle_has_correct_timestamp(self, sample_data):
        """Test that next_candle timestamp is exactly 1 bar after features timestamp."""
        gc_df, dxy_df = sample_data
        processor = BacktestProcessor(timeframe="1m")

        results = list(processor.iterate_with_entry_context(gc_df, dxy_df))

        # Check first result (should have next candle)
        features, _, next_candle = results[0]
        assert next_candle is not None
        assert next_candle.timestamp == features["timestamp"] + timedelta(minutes=1)

    def test_next_candle_is_none_at_dataset_end(self, sample_data):
        """Test that next_candle is None for the last bar in dataset."""
        gc_df, dxy_df = sample_data
        processor = BacktestProcessor(timeframe="1m")

        results = list(processor.iterate_with_entry_context(gc_df, dxy_df))

        # Last result should have next_candle=None
        features, _, next_candle = results[-1]
        assert next_candle is None

    def test_next_candle_contains_only_ohlcv_data(self, sample_data):
        """Test that next_candle only contains raw OHLCV data (no derived features)."""
        gc_df, dxy_df = sample_data
        processor = BacktestProcessor(timeframe="1m")

        results = list(processor.iterate_with_entry_context(gc_df, dxy_df))

        features, _, next_candle = results[0]
        assert next_candle is not None

        # Verify Candle has expected fields only
        assert hasattr(next_candle, "timestamp")
        assert hasattr(next_candle, "open")
        assert hasattr(next_candle, "high")
        assert hasattr(next_candle, "low")
        assert hasattr(next_candle, "close")
        assert hasattr(next_candle, "volume")
        assert hasattr(next_candle, "symbol")
        assert hasattr(next_candle, "timeframe")

        # Verify Candle does NOT have derived features
        assert not hasattr(next_candle, "vwap")
        assert not hasattr(next_candle, "rsi")
        assert not hasattr(next_candle, "ema_9")

    def test_no_lookahead_bias_in_next_candle(self, sample_data):
        """Test that providing next_candle doesn't introduce look-ahead bias."""
        gc_df, dxy_df = sample_data
        processor = BacktestProcessor(timeframe="1m")

        # Modify last candle to have different but valid value
        gc_df_modified = gc_df.copy()
        # Change last candle close (but keep it valid: within high/low range)
        last_idx = -1
        gc_df_modified.iloc[last_idx, gc_df_modified.columns.get_loc("close")] = (
            gc_df_modified.iloc[last_idx]["low"] + 0.5
        )

        # Get results without modification
        results_original = list(processor.iterate_with_entry_context(gc_df, dxy_df))

        # Get results with modification
        results_modified = list(
            processor.iterate_with_entry_context(gc_df_modified, dxy_df)
        )

        # All features except last should be identical
        # (not affected by future change)
        for i in range(len(results_original) - 2):
            features_orig, _, _ = results_original[i]
            features_mod, _, _ = results_modified[i]

            # Features should not be affected by future data
            assert features_orig["close"] == features_mod["close"]
            assert features_orig["vwap"] == features_mod["vwap"]


class TestPipelineIntegration:
    """Tests for full pipeline integration with entry execution."""

    @pytest.fixture
    def minimal_data(self):
        """Generate minimal dataset for pipeline testing."""
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        timestamps = [base_time + timedelta(minutes=i) for i in range(60)]

        gc_df = pd.DataFrame(
            {
                "open": [2000.0 + i for i in range(60)],
                "high": [2005.0 + i for i in range(60)],
                "low": [1995.0 + i for i in range(60)],
                "close": [2001.0 + i for i in range(60)],
                "volume": [1000.0 for _ in range(60)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        dxy_df = pd.DataFrame(
            {
                "open": [100.0 for _ in range(60)],
                "high": [100.5 for _ in range(60)],
                "low": [99.5 for _ in range(60)],
                "close": [100.0 for _ in range(60)],
                "volume": [1000.0 for _ in range(60)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        return gc_df, dxy_df

    def test_pipeline_returns_entry_executions(self, minimal_data):
        """Test that pipeline returns list of EntryExecution objects."""
        gc_df, dxy_df = minimal_data

        def dummy_htf_func(features, context):
            return HTFBias(
                bias="bullish",
                direction="long",
                score=8.5,
                confidence="high",
                vwap_trend_confirmed=True,
                seasonality_adjustment=0.0,
            )

        market_state = {
            "buffer_phase": "growth",
            "tier_active": "EarlyMild",
            "ceo_directive_active": True,
            "news_ok": True,
            "session_ok": True,
        }

        executions, _ = run_backtest_with_entries(
            gc_df=gc_df,
            dxy_df=dxy_df,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=dummy_htf_func,
        )

        assert isinstance(executions, list)
        assert len(executions) > 0
        assert all(isinstance(e, EntryExecution) for e in executions)

    def test_pipeline_only_executes_a_plus_signals(self, minimal_data):
        """Test that only A+ confidence signals result in executed entries."""
        gc_df, dxy_df = minimal_data

        # HTF function that produces low-score signals (should be Reject)
        def reject_htf_func(features, context):
            return HTFBias(
                bias="neutral",
                direction="neutral",
                score=3.0,
                confidence="low",
                vwap_trend_confirmed=False,
                seasonality_adjustment=0.0,
                conflict_detected=True,
                conflict_reason="htf_bearish",
            )

        market_state = {
            "buffer_phase": "startup",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
            "session_ok": True,
        }

        executions, _ = run_backtest_with_entries(
            gc_df=gc_df,
            dxy_df=dxy_df,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=reject_htf_func,
        )

        # All executions should have executed=False (no A+ signals)
        executed_count = sum(1 for e in executions if e.executed)
        assert executed_count == 0

    def test_pipeline_entry_timestamp_after_signal(self, minimal_data):
        """Test that entry timestamp is always after signal timestamp."""
        gc_df, dxy_df = minimal_data

        def bullish_htf_func(features, context):
            return HTFBias(
                bias="bullish",
                direction="long",
                score=9.0,
                confidence="high",
                vwap_trend_confirmed=True,
                seasonality_adjustment=0.5,
            )

        market_state = {
            "buffer_phase": "growth",
            "tier_active": "EarlyMild",
            "ceo_directive_active": True,
            "news_ok": True,
            "session_ok": True,
        }

        executions, _ = run_backtest_with_entries(
            gc_df=gc_df,
            dxy_df=dxy_df,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=bullish_htf_func,
        )

        # For executed entries, entry_timestamp > signal_timestamp
        for execution in executions:
            if execution.executed:
                assert execution.entry_timestamp > execution.signal_timestamp

    def test_pipeline_handles_end_of_dataset_gracefully(self, minimal_data):
        """Test that pipeline handles signals at end of dataset (no next candle)."""
        gc_df, dxy_df = minimal_data

        def bullish_htf_func(features, context):
            return HTFBias(
                bias="bullish",
                direction="long",
                score=9.0,
                confidence="high",
                vwap_trend_confirmed=True,
                seasonality_adjustment=0.0,
            )

        market_state = {
            "buffer_phase": "growth",
            "tier_active": "EarlyMild",
            "ceo_directive_active": True,
            "news_ok": True,
            "session_ok": True,
        }

        executions, _ = run_backtest_with_entries(
            gc_df=gc_df,
            dxy_df=dxy_df,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=bullish_htf_func,
        )

        # Last execution should have executed=False
        # (either due to no next candle OR validation rejection)
        assert executions[-1].executed is False

        # At least verify we got executions for all bars
        assert len(executions) > 0

    def test_pipeline_entry_prices_are_deterministic(self, minimal_data):
        """Test that pipeline produces same entry prices for same inputs."""
        gc_df, dxy_df = minimal_data

        def bullish_htf_func(features, context):
            return HTFBias(
                bias="bullish",
                direction="long",
                score=9.0,
                confidence="high",
                vwap_trend_confirmed=True,
                seasonality_adjustment=0.0,
            )

        market_state = {
            "buffer_phase": "growth",
            "tier_active": "EarlyMild",
            "ceo_directive_active": True,
            "news_ok": True,
            "session_ok": True,
        }

        # Run pipeline twice
        executions1, _ = run_backtest_with_entries(
            gc_df=gc_df,
            dxy_df=dxy_df,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=bullish_htf_func,
        )

        executions2, _ = run_backtest_with_entries(
            gc_df=gc_df,
            dxy_df=dxy_df,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=bullish_htf_func,
        )

        # All entry prices should be identical
        assert len(executions1) == len(executions2)
        for e1, e2 in zip(executions1, executions2, strict=False):
            assert e1.entry_price == e2.entry_price
            assert e1.executed == e2.executed

    def test_pipeline_handles_missing_session_constraints(
        self, minimal_data, monkeypatch
    ):
        """Pipeline should still run when validation context lacks session constraints."""
        gc_df, dxy_df = minimal_data

        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        features_series = pd.Series(
            {
                "timestamp": timestamp,
                "symbol": "GC",
                "timeframe": "1m",
                "open": 2000.0,
                "high": 2001.0,
                "low": 1999.5,
                "close": 2000.5,
                "volume": 1000.0,
                "vwap": 2000.0,
                "rsi": 50.0,
                "ema_9": 2000.2,
                "ema_20": 1999.8,
                "ema_50": 1999.0,
                "dxy_corr": -0.9,
                "structure_label": "HH",
                "structure_type": "HH",
                "vwap_deviation": 0.1,
            }
        )

        next_candle = Candle(
            timestamp=timestamp + timedelta(minutes=1),
            open=2001.0,
            high=2002.0,
            low=1999.0,
            close=2001.5,
            volume=1100.0,
            symbol="GC",
            timeframe="1m",
            source="SIM",
        )

        class DummyProcessor:
            def __init__(self, timeframe):
                self.timeframe = timeframe

            def iterate_with_entry_context(self, *_args, **_kwargs):
                yield features_series, {}, next_candle

        monkeypatch.setattr("backtester.pipeline.BacktestProcessor", DummyProcessor)

        def dummy_htf_func(features, context):
            assert context == {}
            return HTFBias(
                bias="bullish",
                direction="long",
                score=9.0,
                confidence="high",
                vwap_trend_confirmed=True,
                dxy_alignment=True,
            )

        market_state = {
            "buffer_phase": "growth",
            "tier_active": "EarlyMild",
            "ceo_directive_active": True,
            "news_ok": True,
            "session_ok": True,
        }

        executions, _ = run_backtest_with_entries(
            gc_df=gc_df,
            dxy_df=dxy_df,
            timeframe="1m",
            market_state=market_state,
            htf_bias_func=dummy_htf_func,
        )

        assert len(executions) == 1
        assert isinstance(executions[0], EntryExecution)
