"""Integration tests comparing incremental vs vectorized feature calculation.

These tests ensure that the incremental FeatureState produces the same output
as the vectorized process_features() within acceptable tolerance.
"""

from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import pytest

from common.types import Candle
from feature_engine.state import FeatureState
from feature_engine.integration import process_features
from feature_engine.backtesting import BacktestProcessor
from data_layer.loader import HistoricalDataLoader


class TestFeatureParity:
    """Tests comparing incremental vs vectorized feature calculation."""

    @pytest.fixture
    def sample_candles(self):
        """Generate sample GC and DXY candles for testing."""
        gc_candles = []
        dxy_candles = []
        
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        
        for i in range(100):
            timestamp = base_time + timedelta(minutes=i)
            
            # GC candles - trending up
            gc_candles.append(Candle(
                timestamp=timestamp,
                open=2000.0 + i * 0.5,
                high=2002.0 + i * 0.5,
                low=1998.0 + i * 0.5,
                close=2001.0 + i * 0.5,
                volume=1000.0 + i * 10,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            ))
            
            # DXY candles - trending down (inverse correlation)
            dxy_candles.append(Candle(
                timestamp=timestamp,
                open=100.0 - i * 0.02,
                high=100.5 - i * 0.02,
                low=99.5 - i * 0.02,
                close=100.0 - i * 0.02,
                volume=500.0 + i * 5,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            ))
        
        return gc_candles, dxy_candles

    def test_vwap_parity(self, sample_candles):
        """Test VWAP matches between incremental and vectorized."""
        gc_candles, dxy_candles = sample_candles
        
        # Incremental calculation
        state = FeatureState(timeframe="1m", session_reset=False)
        inc_vwaps = []
        
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None:
                inc_vwaps.append(features["vwap"])
        
        # Vectorized calculation
        gc_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in gc_candles
        ])
        dxy_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "close": c.close,
            }
            for c in dxy_candles
        ])
        
        # Set index without inplace to avoid pandas compatibility issues
        gc_indexed = gc_df.copy()
        gc_indexed.index = gc_indexed["ts_event"]
        gc_indexed = gc_indexed.drop(columns=["ts_event"])
        
        dxy_indexed = dxy_df.copy()
        dxy_indexed.index = dxy_indexed["ts_event"]
        dxy_indexed = dxy_indexed.drop(columns=["ts_event"])
        
        vec_features = process_features(gc_indexed, dxy_indexed, "1m")
        
        # Compare VWAP values
        vec_vwaps = vec_features["vwap"].values
        
        # Should have same length
        assert len(inc_vwaps) == len(vec_vwaps)
        
        # VWAP should match exactly (cumulative calculation)
        for inc, vec in zip(inc_vwaps, vec_vwaps):
            assert abs(inc - vec) < 0.01, f"VWAP mismatch: {inc} vs {vec}"

    def test_rsi_parity(self, sample_candles):
        """Test RSI matches between incremental and vectorized within tolerance."""
        gc_candles, dxy_candles = sample_candles
        
        # Incremental calculation
        state = FeatureState(timeframe="1m")
        inc_rsis = []
        
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None and features["rsi"] is not None:
                inc_rsis.append(features["rsi"])
        
        # Vectorized calculation
        gc_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in gc_candles
        ])
        dxy_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "close": c.close,
            }
            for c in dxy_candles
        ])
        
        # Set index without inplace to avoid pandas compatibility issues
        gc_indexed = gc_df.copy()
        gc_indexed.index = gc_indexed["ts_event"]
        gc_indexed = gc_indexed.drop(columns=["ts_event"])
        
        dxy_indexed = dxy_df.copy()
        dxy_indexed.index = dxy_indexed["ts_event"]
        dxy_indexed = dxy_indexed.drop(columns=["ts_event"])
        
        vec_features = process_features(gc_indexed, dxy_indexed, "1m")
        
        # Compare RSI values (skip NaN)
        vec_rsis = vec_features["rsi"].dropna().values
        
        # Should have similar length (within warmup period difference)
        assert abs(len(inc_rsis) - len(vec_rsis)) <= 1
        
        # RSI should match within tolerance (±0.1 per spec)
        min_len = min(len(inc_rsis), len(vec_rsis))
        for i in range(min_len):
            inc = inc_rsis[i]
            vec = vec_rsis[i]
            assert abs(inc - vec) < 0.1, f"RSI mismatch at {i}: {inc} vs {vec}"

    def test_ema_parity(self, sample_candles):
        """Test EMA matches between incremental and vectorized within tolerance."""
        gc_candles, dxy_candles = sample_candles
        
        # Incremental calculation
        state = FeatureState(timeframe="1m")
        inc_ema9 = []
        inc_ema20 = []
        inc_ema50 = []
        
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None:
                inc_ema9.append(features["ema_9"])
                inc_ema20.append(features["ema_20"])
                inc_ema50.append(features["ema_50"])
        
        # Vectorized calculation
        gc_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in gc_candles
        ])
        dxy_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "close": c.close,
            }
            for c in dxy_candles
        ])
        
        # Set index without inplace to avoid pandas compatibility issues
        gc_indexed = gc_df.copy()
        gc_indexed.index = gc_indexed["ts_event"]
        gc_indexed = gc_indexed.drop(columns=["ts_event"])
        
        dxy_indexed = dxy_df.copy()
        dxy_indexed.index = dxy_indexed["ts_event"]
        dxy_indexed = dxy_indexed.drop(columns=["ts_event"])
        
        vec_features = process_features(gc_indexed, dxy_indexed, "1m")
        
        # Compare EMA values
        vec_ema9 = vec_features["ema_9"].values
        vec_ema20 = vec_features["ema_20"].values
        vec_ema50 = vec_features["ema_50"].values
        
        # Should have same length
        assert len(inc_ema9) == len(vec_ema9)
        
        # EMA should match within tolerance (< 0.0001 per spec)
        for i in range(len(inc_ema9)):
            assert abs(inc_ema9[i] - vec_ema9[i]) < 0.0001, \
                f"EMA9 mismatch at {i}: {inc_ema9[i]} vs {vec_ema9[i]}"
            assert abs(inc_ema20[i] - vec_ema20[i]) < 0.0001, \
                f"EMA20 mismatch at {i}: {inc_ema20[i]} vs {vec_ema20[i]}"
            assert abs(inc_ema50[i] - vec_ema50[i]) < 0.0001, \
                f"EMA50 mismatch at {i}: {inc_ema50[i]} vs {vec_ema50[i]}"

    def test_dxy_correlation_parity(self, sample_candles):
        """Test DXY correlation matches between incremental and vectorized."""
        gc_candles, dxy_candles = sample_candles
        
        # Incremental calculation
        state = FeatureState(timeframe="1m")
        inc_corrs = []
        
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None and features["dxy_corr"] is not None:
                inc_corrs.append(features["dxy_corr"])
        
        # Vectorized calculation
        gc_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in gc_candles
        ])
        dxy_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "close": c.close,
            }
            for c in dxy_candles
        ])
        
        # Set index without inplace to avoid pandas compatibility issues
        gc_indexed = gc_df.copy()
        gc_indexed.index = gc_indexed["ts_event"]
        gc_indexed = gc_indexed.drop(columns=["ts_event"])
        
        dxy_indexed = dxy_df.copy()
        dxy_indexed.index = dxy_indexed["ts_event"]
        dxy_indexed = dxy_indexed.drop(columns=["ts_event"])
        
        vec_features = process_features(gc_indexed, dxy_indexed, "1m")
        
        # Compare correlation values (skip NaN)
        vec_corrs = vec_features["dxy_corr"].dropna().values
        
        # Should have similar length
        assert abs(len(inc_corrs) - len(vec_corrs)) <= 1
        
        # Correlation should match within tolerance
        min_len = min(len(inc_corrs), len(vec_corrs))
        for i in range(min_len):
            inc = inc_corrs[i]
            vec = vec_corrs[i]
            assert abs(inc - vec) < 0.01, \
                f"DXY correlation mismatch at {i}: {inc} vs {vec}"

    def test_vwap_deviation_parity(self, sample_candles):
        """Test VWAP deviation matches between incremental and vectorized."""
        gc_candles, dxy_candles = sample_candles
        
        # Incremental calculation
        state = FeatureState(timeframe="1m", session_reset=False)
        inc_devs = []
        
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None and features["vwap_deviation"] is not None:
                inc_devs.append(features["vwap_deviation"])
        
        # Vectorized calculation
        gc_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in gc_candles
        ])
        dxy_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "close": c.close,
            }
            for c in dxy_candles
        ])
        
        # Set index without inplace to avoid pandas compatibility issues
        gc_indexed = gc_df.copy()
        gc_indexed.index = gc_indexed["ts_event"]
        gc_indexed = gc_indexed.drop(columns=["ts_event"])
        
        dxy_indexed = dxy_df.copy()
        dxy_indexed.index = dxy_indexed["ts_event"]
        dxy_indexed = dxy_indexed.drop(columns=["ts_event"])
        
        vec_features = process_features(gc_indexed, dxy_indexed, "1m")
        
        # Compare deviation values (skip NaN)
        vec_devs = vec_features["vwap_deviation"].dropna().values
        
        # Should have same length
        assert len(inc_devs) == len(vec_devs)
        
        # Deviation should match within tolerance
        for i in range(len(inc_devs)):
            inc = inc_devs[i]
            vec = vec_devs[i]
            assert abs(inc - vec) < 0.01, \
                f"VWAP deviation mismatch at {i}: {inc} vs {vec}"

    def test_full_feature_parity(self, sample_candles):
        """Test all features match between incremental and vectorized."""
        gc_candles, dxy_candles = sample_candles
        
        # Incremental calculation
        state = FeatureState(timeframe="1m", session_reset=False)
        inc_features_list = []
        
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None:
                inc_features_list.append(features)
        
        # Vectorized calculation
        gc_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in gc_candles
        ])
        dxy_df = pd.DataFrame([
            {
                "ts_event": c.timestamp,
                "close": c.close,
            }
            for c in dxy_candles
        ])
        
        # Set index without inplace to avoid pandas compatibility issues
        gc_indexed = gc_df.copy()
        gc_indexed.index = gc_indexed["ts_event"]
        gc_indexed = gc_indexed.drop(columns=["ts_event"])
        
        dxy_indexed = dxy_df.copy()
        dxy_indexed.index = dxy_indexed["ts_event"]
        dxy_indexed = dxy_indexed.drop(columns=["ts_event"])
        
        vec_features = process_features(gc_indexed, dxy_indexed, "1m")
        
        # Convert incremental to DataFrame
        inc_df = pd.DataFrame(inc_features_list)
        
        # Compare key numeric columns
        numeric_cols = ["vwap", "rsi", "ema_9", "ema_20", "ema_50", 
                       "dxy_corr", "vwap_deviation"]
        
        for col in numeric_cols:
            if col in inc_df.columns and col in vec_features.columns:
                inc_vals = inc_df[col].dropna().values
                vec_vals = vec_features[col].dropna().values
                
                # Should have similar length
                min_len = min(len(inc_vals), len(vec_vals))
                
                if min_len > 0:
                    # Calculate max difference
                    diffs = [abs(inc_vals[i] - vec_vals[i]) for i in range(min_len)]
                    max_diff = max(diffs)
                    
                    # Tolerance depends on indicator
                    if col in ["ema_9", "ema_20", "ema_50"]:
                        tolerance = 0.0001
                    elif col == "rsi":
                        tolerance = 0.1
                    else:
                        tolerance = 0.01
                    
                    assert max_diff < tolerance, \
                        f"{col} max diff {max_diff} exceeds tolerance {tolerance}"

    def test_backtest_processor_vs_incremental_vwap(self, sample_candles):
        """Test BacktestProcessor VWAP matches incremental FeatureState."""
        gc_candles, dxy_candles = sample_candles
        
        # Convert candles to DataFrames
        gc_df = pd.DataFrame({
            "open": [c.open for c in gc_candles],
            "high": [c.high for c in gc_candles],
            "low": [c.low for c in gc_candles],
            "close": [c.close for c in gc_candles],
            "volume": [c.volume for c in gc_candles],
        }, index=pd.DatetimeIndex([c.timestamp for c in gc_candles], name="timestamp"))
        
        dxy_df = pd.DataFrame({
            "open": [c.open for c in dxy_candles],
            "high": [c.high for c in dxy_candles],
            "low": [c.low for c in dxy_candles],
            "close": [c.close for c in dxy_candles],
            "volume": [c.volume for c in dxy_candles],
        }, index=pd.DatetimeIndex([c.timestamp for c in dxy_candles], name="timestamp"))
        
        # Backtest processor
        processor = BacktestProcessor(timeframe="1m")
        # Unpack tuples: extract just features
        backtest_features = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        
        # Incremental state
        state = FeatureState(timeframe="1m")
        inc_features = []
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None and state.is_ready():
                inc_features.append(features)
        
        # Should have same number of features
        assert len(backtest_features) == len(inc_features)
        
        # Compare VWAP values (exact match expected)
        for i, (bt_feat, inc_feat) in enumerate(zip(backtest_features, inc_features)):
            assert abs(bt_feat["vwap"] - inc_feat["vwap"]) < 0.01, \
                f"VWAP mismatch at index {i}: backtest={bt_feat['vwap']}, incremental={inc_feat['vwap']}"

    def test_backtest_processor_vs_incremental_rsi(self, sample_candles):
        """Test BacktestProcessor RSI matches incremental FeatureState."""
        gc_candles, dxy_candles = sample_candles
        
        # Convert candles to DataFrames
        gc_df = pd.DataFrame({
            "open": [c.open for c in gc_candles],
            "high": [c.high for c in gc_candles],
            "low": [c.low for c in gc_candles],
            "close": [c.close for c in gc_candles],
            "volume": [c.volume for c in gc_candles],
        }, index=pd.DatetimeIndex([c.timestamp for c in gc_candles], name="timestamp"))
        
        dxy_df = pd.DataFrame({
            "open": [c.open for c in dxy_candles],
            "high": [c.high for c in dxy_candles],
            "low": [c.low for c in dxy_candles],
            "close": [c.close for c in dxy_candles],
            "volume": [c.volume for c in dxy_candles],
        }, index=pd.DatetimeIndex([c.timestamp for c in dxy_candles], name="timestamp"))
        
        # Backtest processor
        processor = BacktestProcessor(timeframe="1m")
        # Unpack tuples: extract just features
        backtest_features = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        
        # Incremental state
        state = FeatureState(timeframe="1m")
        inc_features = []
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None and state.is_ready():
                inc_features.append(features)
        
        # Compare RSI values (within tolerance)
        for i, (bt_feat, inc_feat) in enumerate(zip(backtest_features, inc_features)):
            if bt_feat["rsi"] is not None and inc_feat["rsi"] is not None:
                assert abs(bt_feat["rsi"] - inc_feat["rsi"]) < 0.5, \
                    f"RSI mismatch at index {i}: backtest={bt_feat['rsi']}, incremental={inc_feat['rsi']}"

    def test_backtest_processor_vs_incremental_ema(self, sample_candles):
        """Test BacktestProcessor EMAs match incremental FeatureState."""
        gc_candles, dxy_candles = sample_candles
        
        # Convert candles to DataFrames
        gc_df = pd.DataFrame({
            "open": [c.open for c in gc_candles],
            "high": [c.high for c in gc_candles],
            "low": [c.low for c in gc_candles],
            "close": [c.close for c in gc_candles],
            "volume": [c.volume for c in gc_candles],
        }, index=pd.DatetimeIndex([c.timestamp for c in gc_candles], name="timestamp"))
        
        dxy_df = pd.DataFrame({
            "open": [c.open for c in dxy_candles],
            "high": [c.high for c in dxy_candles],
            "low": [c.low for c in dxy_candles],
            "close": [c.close for c in dxy_candles],
            "volume": [c.volume for c in dxy_candles],
        }, index=pd.DatetimeIndex([c.timestamp for c in dxy_candles], name="timestamp"))
        
        # Backtest processor
        processor = BacktestProcessor(timeframe="1m")
        # Unpack tuples: extract just features
        backtest_features = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        
        # Incremental state
        state = FeatureState(timeframe="1m")
        inc_features = []
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None and state.is_ready():
                inc_features.append(features)
        
        # Compare EMA values (within tight tolerance)
        for i, (bt_feat, inc_feat) in enumerate(zip(backtest_features, inc_features)):
            for period in [9, 20, 50]:
                ema_key = f"ema_{period}"
                assert abs(bt_feat[ema_key] - inc_feat[ema_key]) < 0.01, \
                    f"{ema_key} mismatch at index {i}: backtest={bt_feat[ema_key]}, incremental={inc_feat[ema_key]}"

    def test_backtest_processor_vs_incremental_dxy_corr(self, sample_candles):
        """Test BacktestProcessor DXY correlation matches incremental FeatureState."""
        gc_candles, dxy_candles = sample_candles
        
        # Convert candles to DataFrames
        gc_df = pd.DataFrame({
            "open": [c.open for c in gc_candles],
            "high": [c.high for c in gc_candles],
            "low": [c.low for c in gc_candles],
            "close": [c.close for c in gc_candles],
            "volume": [c.volume for c in gc_candles],
        }, index=pd.DatetimeIndex([c.timestamp for c in gc_candles], name="timestamp"))
        
        dxy_df = pd.DataFrame({
            "open": [c.open for c in dxy_candles],
            "high": [c.high for c in dxy_candles],
            "low": [c.low for c in dxy_candles],
            "close": [c.close for c in dxy_candles],
            "volume": [c.volume for c in dxy_candles],
        }, index=pd.DatetimeIndex([c.timestamp for c in dxy_candles], name="timestamp"))
        
        # Backtest processor
        processor = BacktestProcessor(timeframe="1m")
        # Unpack tuples: extract just features
        backtest_features = [f for f, _ in processor.iterate_with_context(gc_df, dxy_df)]
        
        # Incremental state
        state = FeatureState(timeframe="1m")
        inc_features = []
        for gc, dxy in zip(gc_candles, dxy_candles):
            features = state.update(gc_candle=gc, dxy_candle=dxy)
            if features is not None and state.is_ready():
                inc_features.append(features)
        
        # Compare DXY correlation values (within tolerance)
        for i, (bt_feat, inc_feat) in enumerate(zip(backtest_features, inc_features)):
            if bt_feat["dxy_corr"] is not None and inc_feat["dxy_corr"] is not None:
                assert abs(bt_feat["dxy_corr"] - inc_feat["dxy_corr"]) < 0.05, \
                    f"DXY corr mismatch at index {i}: backtest={bt_feat['dxy_corr']}, incremental={inc_feat['dxy_corr']}"


class TestEdgeCases:
    """Tests for edge cases in incremental feature calculation."""

    def test_missing_gc_candles(self):
        """Test handling of missing GC candles."""
        state = FeatureState(timeframe="1m")
        
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        
        # Add DXY candle only
        dxy_candle = Candle(
            base_time, 100.0, 101.0, 99.0, 100.5, 500.0, "DXY", "1m", "TEST"
        )
        features = state.update(dxy_candle=dxy_candle)
        
        # Should return None (no GC data yet)
        assert features is None
        
        # Add GC candle
        gc_candle = Candle(
            base_time, 2000.0, 2002.0, 1998.0, 2001.0, 1000.0, "GC", "1m", "TEST"
        )
        features = state.update(gc_candle=gc_candle)
        
        # Should return features now
        assert features is not None

    def test_missing_dxy_candles(self):
        """Test handling of missing DXY candles."""
        state = FeatureState(timeframe="1m")
        
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        
        # Add GC candles without DXY
        for i in range(10):
            gc_candle = Candle(
                base_time + timedelta(minutes=i),
                2000.0 + i, 2002.0 + i, 1998.0 + i, 2001.0 + i,
                1000.0, "GC", "1m", "TEST"
            )
            features = state.update(gc_candle=gc_candle)
            
            # Should return features but dxy_corr should be None
            assert features is not None
            assert features["dxy_corr"] is None

    def test_timestamp_gaps(self):
        """Test handling of timestamp gaps."""
        state = FeatureState(timeframe="1m")
        
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        
        # Add candle at time 0
        gc1 = Candle(
            base_time, 2000.0, 2002.0, 1998.0, 2001.0, 1000.0, "GC", "1m", "TEST"
        )
        features1 = state.update(gc_candle=gc1)
        
        # Skip to time 5 (gap of 4 minutes)
        gc2 = Candle(
            base_time + timedelta(minutes=5),
            2005.0, 2007.0, 2003.0, 2006.0, 1000.0, "GC", "1m", "TEST"
        )
        features2 = state.update(gc_candle=gc2)
        
        # Should still calculate features
        assert features1 is not None
        assert features2 is not None

    def test_session_boundary(self):
        """Test VWAP resets at session boundary."""
        state = FeatureState(timeframe="1m", session_reset=True)
        
        # First session
        day1_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        gc1 = Candle(
            day1_time, 2000.0, 2002.0, 1998.0, 2001.0, 1000.0, "GC", "1m", "TEST"
        )
        features1 = state.update(gc_candle=gc1)
        vwap1 = features1["vwap"]
        
        # Add more candles same day
        for i in range(1, 5):
            gc = Candle(
                day1_time + timedelta(minutes=i),
                2000.0 + i, 2002.0 + i, 1998.0 + i, 2001.0 + i,
                1000.0, "GC", "1m", "TEST"
            )
            state.update(gc_candle=gc)
        
        # New session (next day)
        day2_time = datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
        gc2 = Candle(
            day2_time, 2000.0, 2002.0, 1998.0, 2001.0, 1000.0, "GC", "1m", "TEST"
        )
        features2 = state.update(gc_candle=gc2)
        vwap2 = features2["vwap"]
        
        # VWAP should reset (be close to typical price)
        typical_price = (2002.0 + 1998.0 + 2001.0) / 3
        assert abs(vwap2 - typical_price) < 0.01

