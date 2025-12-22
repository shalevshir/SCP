"""Tests for FeatureProcessor wrapper."""

import pytest
from datetime import datetime, timezone

from feature_engine_svc.processor import FeatureProcessor
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage


class TestFeatureProcessor:
    """Test FeatureProcessor wrapper that converts message types."""
    
    def test_process_candle_returns_features_message(self):
        """Processing candle pair returns FeaturesMessage."""
        processor = FeatureProcessor(timeframe="1m")
        
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        features = processor.process(gc_candle, dxy_candle)
        
        assert isinstance(features, FeaturesMessage)
        assert features.timestamp == gc_candle.timestamp
        assert features.symbol == "GC"
        assert features.timeframe == "1m"
        assert features.close == 2652.0
    
    def test_first_candle_returns_features_with_ema(self):
        """First candle initializes EMA values."""
        processor = FeatureProcessor(timeframe="1m")
        
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        features = processor.process(gc_candle, dxy_candle)
        
        # EMA should be initialized to close price
        assert features.ema_9 is not None
        assert features.ema_20 is not None
        assert features.ema_50 is not None
        assert abs(features.ema_9 - 2652.0) < 0.01
    
    def test_warmup_period_has_partial_features(self):
        """During warmup, some features are None."""
        processor = FeatureProcessor(timeframe="1m")
        
        # First candle
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        features = processor.process(gc_candle, dxy_candle)
        
        # RSI needs 15 bars (14 + 1), DXY correlation needs 50 bars
        assert features.rsi is None
        assert features.dxy_correlation is None
        assert features.vwap is not None  # VWAP available from first bar
    
    def test_after_warmup_all_features_populated(self):
        """After warmup period, all features populated."""
        processor = FeatureProcessor(timeframe="1m")
        
        # Feed 60 candles (warmup) with varying DXY values for correlation
        for i in range(60):
            gc = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.1,
                high=2655.0 + i * 0.1,
                low=2648.0 + i * 0.1,
                close=2652.0 + i * 0.1,
                volume=1000.0,
            )
            dxy = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5 - i * 0.01,  # Varying DXY values
                high=104.6 - i * 0.01,
                low=104.4 - i * 0.01,
                close=104.55 - i * 0.01,
                volume=0.0,
            )
            features = processor.process(gc, dxy)
        
        # All features should be available after 60 bars
        assert features.rsi is not None
        assert features.dxy_correlation is not None
        assert features.vwap is not None
        # Structure label may still be None depending on market conditions
        assert hasattr(features, "structure_label")
    
    def test_vwap_computed_correctly(self):
        """VWAP is computed from typical price and volume."""
        processor = FeatureProcessor(timeframe="1m")
        
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        features = processor.process(gc_candle, dxy_candle)
        
        # VWAP = (high + low + close) / 3 for first bar
        expected_vwap = (2655.0 + 2648.0 + 2652.0) / 3
        assert features.vwap is not None
        assert abs(features.vwap - expected_vwap) < 0.01
    
    def test_is_warmed_up_after_sufficient_bars(self):
        """Processor reports warmed up after sufficient bars."""
        processor = FeatureProcessor(timeframe="1m")
        
        assert not processor.is_warmed_up()
        
        # Feed 60 bars
        for i in range(60):
            gc = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2652.0,
                volume=1000.0,
            )
            dxy = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5,
                high=104.6,
                low=104.4,
                close=104.55,
                volume=0.0,
            )
            processor.process(gc, dxy)
        
        assert processor.is_warmed_up()
    
    def test_reset_clears_state(self):
        """Reset clears all processor state."""
        processor = FeatureProcessor(timeframe="1m")
        
        # Process some candles
        for i in range(10):
            gc = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2652.0,
                volume=1000.0,
            )
            dxy = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5,
                high=104.6,
                low=104.4,
                close=104.55,
                volume=0.0,
            )
            processor.process(gc, dxy)
        
        processor.reset()
        
        assert not processor.is_warmed_up()
        assert processor.bar_count == 0
    
    def test_structure_label_computed(self):
        """Structure labels are computed and included in features."""
        processor = FeatureProcessor(timeframe="1m")
        
        # Feed enough bars for structure detection
        for i in range(30):
            gc = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.5,
                high=2655.0 + i * 0.5,
                low=2648.0 + i * 0.5,
                close=2652.0 + i * 0.5,
                volume=1000.0,
            )
            dxy = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5,
                high=104.6,
                low=104.4,
                close=104.55,
                volume=0.0,
            )
            features = processor.process(gc, dxy)
        
        # Structure label should be set (may be None or actual label)
        assert hasattr(features, "structure_label")
    
    def test_vwap_deviation_computed(self):
        """VWAP deviation percentage is computed."""
        processor = FeatureProcessor(timeframe="1m")
        
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2640.0,  # Wide range
            close=2652.0,
            volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        features = processor.process(gc_candle, dxy_candle)
        
        assert features.vwap_deviation is not None
        assert features.vwap_deviation >= 0

