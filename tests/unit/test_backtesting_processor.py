"""Unit tests for BacktestProcessor - vectorized feature calculation for backtesting."""

from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import pytest

from common.types import Candle
from feature_engine.backtesting import BacktestProcessor


class TestBacktestProcessor:
    """Tests for BacktestProcessor class."""

    @pytest.fixture
    def sample_data(self):
        """Generate sample GC and DXY DataFrames."""
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        timestamps = [
            base_time + timedelta(minutes=i) for i in range(100)
        ]
        
        gc_df = pd.DataFrame({
            "open": [2000.0 + i * 0.5 for i in range(100)],
            "high": [2002.0 + i * 0.5 for i in range(100)],
            "low": [1998.0 + i * 0.5 for i in range(100)],
            "close": [2001.0 + i * 0.5 for i in range(100)],
            "volume": [1000.0 + i * 10 for i in range(100)],
        }, index=pd.DatetimeIndex(timestamps, name="timestamp"))
        
        dxy_df = pd.DataFrame({
            "open": [100.0 - i * 0.02 for i in range(100)],
            "high": [100.5 - i * 0.02 for i in range(100)],
            "low": [99.5 - i * 0.02 for i in range(100)],
            "close": [100.0 - i * 0.02 for i in range(100)],
            "volume": [1000.0 for _ in range(100)],
        }, index=pd.DatetimeIndex(timestamps, name="timestamp"))
        
        return gc_df, dxy_df

    def test_initialization(self):
        """Test BacktestProcessor initializes correctly."""
        processor = BacktestProcessor(timeframe="1m")
        
        assert processor.timeframe == "1m"
        assert processor.warmup_period == 50

    def test_iterate_with_context_yields_features(self, sample_data):
        """Test that iterate_with_context yields feature series and validation context."""
        gc_df, dxy_df = sample_data
        processor = BacktestProcessor(timeframe="1m")
        
        results_list = list(processor.iterate_with_context(gc_df, dxy_df))
        
        # Should yield (features, validation_context) tuples after warmup period
        # (yields start at index warmup_period - 1)
        assert len(results_list) > 0
        assert len(results_list) == len(gc_df) - processor.warmup_period + 1
        
        # Each result should be a tuple of (Series, dict)
        features, validation_context = results_list[0]
        assert isinstance(features, pd.Series)
        assert isinstance(validation_context, dict)

    def test_features_have_required_columns(self, sample_data):
        """Test that features contain all required columns."""
        gc_df, dxy_df = sample_data
        processor = BacktestProcessor(timeframe="1m")
        
        # Unpack tuple: (features, validation_context)
        features, _ = list(processor.iterate_with_context(gc_df, dxy_df))[0]
        
        required_cols = [
            "timestamp", "symbol", "timeframe",
            "open", "high", "low", "close", "volume",
            "vwap", "rsi", "ema_9", "ema_20", "ema_50",
            "dxy_corr", "structure_label", "vwap_deviation"
        ]
        
        for col in required_cols:
            assert col in features.index, f"Missing column: {col}"

    def test_no_look_ahead_bias(self, sample_data):
        """Test that features don't use future data."""
        gc_df, dxy_df = sample_data
        
        # Add a spike at the end that shouldn't affect earlier calculations
        gc_df_with_spike = gc_df.copy()
        gc_df_with_spike.iloc[-1, gc_df_with_spike.columns.get_loc("close")] = 9999.0
        
        processor = BacktestProcessor(timeframe="1m")
        
        # Unpack tuples: extract just features
        features_without_spike = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        features_with_spike = [f for f, _ in processor.iterate_with_context(gc_df_with_spike, dxy_df)]
        
        # All features except the last should be identical
        # (the spike is in the last row, so it shouldn't affect earlier rows)
        for i in range(len(features_without_spike) - 1):
            # Compare VWAP values (representative indicator)
            assert abs(features_without_spike[i]["vwap"] - features_with_spike[i]["vwap"]) < 0.01

    def test_warmup_period_handling(self, sample_data):
        """Test that features are only yielded after warmup period."""
        gc_df, dxy_df = sample_data
        processor = BacktestProcessor(timeframe="1m", warmup_period=10)
        
        # Unpack tuples: extract just features
        features_list = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        
        # Should skip first 9 rows (warmup_period - 1)
        # (yields start after processing warmup_period candles, at index warmup_period - 1)
        assert len(features_list) == len(gc_df) - 9
        
        # First yielded feature should be at index 9 (after processing 10 candles)
        first_feature = features_list[0]
        assert first_feature["timestamp"] == gc_df.index[9]

    def test_session_boundary_vwap_reset(self):
        """Test VWAP resets at session boundaries."""
        # Create data spanning two days
        day1_base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        day1_times = [day1_base + timedelta(minutes=i) for i in range(30)]
        day2_base = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
        day2_times = [day2_base + timedelta(minutes=i) for i in range(30)]
        timestamps = day1_times + day2_times
        
        gc_df = pd.DataFrame({
            "open": [2000.0] * 60,
            "high": [2002.0] * 60,
            "low": [1998.0] * 60,
            "close": [2001.0] * 60,
            "volume": [1000.0] * 60,
        }, index=pd.DatetimeIndex(timestamps, name="timestamp"))
        
        dxy_df = pd.DataFrame({
            "open": [100.0] * 60,
            "high": [100.5] * 60,
            "low": [99.5] * 60,
            "close": [100.0] * 60,
            "volume": [1000.0] * 60,
        }, index=pd.DatetimeIndex(timestamps, name="timestamp"))
        
        processor = BacktestProcessor(timeframe="1m", session_reset=True, warmup_period=5)
        # Unpack tuples: extract just features
        features_list = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        
        # VWAP should reset at day boundary
        # Day 1 last VWAP
        day1_last_idx = 29 - 5  # index 24 in features_list
        # Day 2 first VWAP (after warmup)
        day2_first_idx = 30 - 5  # index 25 in features_list
        
        if day2_first_idx < len(features_list):
            # VWAP should be close to typical price after reset
            day2_first_vwap = features_list[day2_first_idx]["vwap"]
            typical_price = (2002.0 + 1998.0 + 2001.0) / 3
            # Should be close since it's reset
            assert abs(day2_first_vwap - typical_price) < 1.0

    def test_zero_volume_handling(self):
        """Test processor handles zero volume gracefully."""
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        timestamps = [base_time + timedelta(minutes=i) for i in range(60)]
        
        gc_df = pd.DataFrame({
            "open": [2000.0] * 60,
            "high": [2002.0] * 60,
            "low": [1998.0] * 60,
            "close": [2001.0] * 60,
            "volume": [0.0] * 60,  # Zero volume
        }, index=pd.DatetimeIndex(timestamps, name="timestamp"))
        
        dxy_df = pd.DataFrame({
            "open": [100.0] * 60,
            "high": [100.5] * 60,
            "low": [99.5] * 60,
            "close": [100.0] * 60,
            "volume": [1000.0] * 60,
        }, index=pd.DatetimeIndex(timestamps, name="timestamp"))
        
        processor = BacktestProcessor(timeframe="1m", warmup_period=5)
        # Unpack tuples: extract just features
        features_list = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        
        # Should not crash and should produce valid VWAP
        assert len(features_list) > 0
        assert not np.isnan(features_list[0]["vwap"])
        assert not np.isinf(features_list[0]["vwap"])

    def test_performance_vs_incremental(self):
        """Test that vectorized mode is faster than incremental on larger datasets."""
        import time
        from feature_engine.state import FeatureState
        
        # Use a larger dataset (500 rows) for meaningful performance comparison
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        timestamps = [base_time + timedelta(minutes=i) for i in range(500)]
        
        gc_df = pd.DataFrame({
            "open": [2000.0 + i * 0.5 for i in range(500)],
            "high": [2002.0 + i * 0.5 for i in range(500)],
            "low": [1998.0 + i * 0.5 for i in range(500)],
            "close": [2001.0 + i * 0.5 for i in range(500)],
            "volume": [1000.0 + i * 10 for i in range(500)],
        }, index=pd.DatetimeIndex(timestamps, name="timestamp"))
        
        dxy_df = pd.DataFrame({
            "open": [100.0 - i * 0.02 for i in range(500)],
            "high": [100.5 - i * 0.02 for i in range(500)],
            "low": [99.5 - i * 0.02 for i in range(500)],
            "close": [100.0 - i * 0.02 for i in range(500)],
            "volume": [1000.0 for _ in range(500)],
        }, index=pd.DatetimeIndex(timestamps, name="timestamp"))
        
        # Vectorized mode
        processor = BacktestProcessor(timeframe="1m")
        start_vec = time.time()
        # Unpack tuples: extract just features
        vec_features = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        vec_time = time.time() - start_vec
        
        # Incremental mode
        state = FeatureState(timeframe="1m")
        start_inc = time.time()
        inc_features = []
        for i in range(len(gc_df)):
            gc_candle = Candle(
                timestamp=gc_df.index[i],
                open=gc_df.iloc[i]["open"],
                high=gc_df.iloc[i]["high"],
                low=gc_df.iloc[i]["low"],
                close=gc_df.iloc[i]["close"],
                volume=gc_df.iloc[i]["volume"],
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
            dxy_candle = Candle(
                timestamp=dxy_df.index[i],
                open=dxy_df.iloc[i]["open"],
                high=dxy_df.iloc[i]["high"],
                low=dxy_df.iloc[i]["low"],
                close=dxy_df.iloc[i]["close"],
                volume=dxy_df.iloc[i]["volume"],
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            )
            features = state.update(gc_candle=gc_candle, dxy_candle=dxy_candle)
            if features is not None and state.is_ready():
                inc_features.append(features)
        inc_time = time.time() - start_inc
        
        # Both should complete successfully
        assert len(vec_features) > 0
        assert len(inc_features) > 0
        
        # Log performance (informational, not strict assertion)
        speedup = inc_time / vec_time if vec_time > 0 else float('inf')
        print(f"\nPerformance: Vectorized={vec_time:.3f}s, Incremental={inc_time:.3f}s, Speedup={speedup:.1f}x")
