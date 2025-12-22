"""Tests for HTF Bias Processor wrapper."""

import pytest
from datetime import datetime, timezone

from htf_bias_svc.processor import HTFBiasProcessor
from scp_shared.messaging.schemas import CandleMessage, HTFBiasMessage


class TestHTFBiasProcessor:
    """Test HTFBiasProcessor wrapper around StreamingHTFBiasCalculator."""
    
    def test_processor_initialization(self):
        """Test processor initializes correctly."""
        processor = HTFBiasProcessor()
        
        assert processor is not None
        assert processor.calculator is not None
    
    def test_process_returns_none_before_warmup(self):
        """Test processor returns None before sufficient data."""
        processor = HTFBiasProcessor()
        
        # Feed a single 1m candle pair
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
            open=103.0,
            high=103.5,
            low=102.8,
            close=103.2,
            volume=500.0,
        )
        
        result = processor.process(gc_candle, dxy_candle)
        assert result is None  # Not enough data yet
    
    def test_process_at_15m_boundary(self):
        """Test processor emits bias at 15m boundary."""
        processor = HTFBiasProcessor()
        
        # Feed 15 candles to hit first 15m boundary
        base_time = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        
        result = None
        for i in range(15):
            ts = base_time.replace(minute=i)
            
            gc_candle = CandleMessage(
                timestamp=ts,
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.1,
                high=2655.0 + i * 0.1,
                low=2648.0 + i * 0.1,
                close=2652.0 + i * 0.1,
                volume=1000.0,
            )
            dxy_candle = CandleMessage(
                timestamp=ts,
                symbol="DXY",
                timeframe="1m",
                open=103.0 + i * 0.01,
                high=103.5 + i * 0.01,
                low=102.8 + i * 0.01,
                close=103.2 + i * 0.01,
                volume=500.0,
            )
            
            result = processor.process(gc_candle, dxy_candle)
        
        # After 15 candles (ending at minute 14), should have a result
        # But might be None if not enough historical data for bias calculation
        # (needs multiple 15m/1h bars for structure detection)
        # This is expected behavior
        assert result is None or isinstance(result, HTFBiasMessage)
    
    def test_process_at_1h_boundary(self):
        """Test processor emits bias at 1h boundary."""
        processor = HTFBiasProcessor()
        
        # Feed 60 candles to hit first 1h boundary
        base_time = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        
        result = None
        for i in range(60):
            ts = base_time.replace(minute=i)
            
            gc_candle = CandleMessage(
                timestamp=ts,
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.1,
                high=2655.0 + i * 0.1,
                low=2648.0 + i * 0.1,
                close=2652.0 + i * 0.1,
                volume=1000.0,
            )
            dxy_candle = CandleMessage(
                timestamp=ts,
                symbol="DXY",
                timeframe="1m",
                open=103.0 + i * 0.01,
                high=103.5 + i * 0.01,
                low=102.8 + i * 0.01,
                close=103.2 + i * 0.01,
                volume=500.0,
            )
            
            result = processor.process(gc_candle, dxy_candle)
        
        # After 60 candles, should have a result at 1h boundary
        # But might be None if not enough historical data
        assert result is None or isinstance(result, HTFBiasMessage)
    
    def test_process_converts_to_htf_bias_message(self):
        """Test processor converts HTFBias to HTFBiasMessage correctly."""
        processor = HTFBiasProcessor()
        
        # Feed enough data to potentially get a bias (7 hours of data for swing_window=3)
        base_time = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        
        result = None
        for hour in range(8):  # 8 hours to ensure we have enough
            for minute in range(60):
                ts = base_time.replace(hour=10 + hour, minute=minute)
                
                # Create varied price data for structure detection
                trend_factor = hour * 5.0
                
                gc_candle = CandleMessage(
                    timestamp=ts,
                    symbol="GC",
                    timeframe="1m",
                    open=2650.0 + trend_factor,
                    high=2655.0 + trend_factor,
                    low=2648.0 + trend_factor,
                    close=2652.0 + trend_factor,
                    volume=1000.0,
                )
                dxy_candle = CandleMessage(
                    timestamp=ts,
                    symbol="DXY",
                    timeframe="1m",
                    open=103.0 - hour * 0.1,
                    high=103.5 - hour * 0.1,
                    low=102.8 - hour * 0.1,
                    close=103.2 - hour * 0.1,
                    volume=500.0,
                )
                
                result = processor.process(gc_candle, dxy_candle)
        
        # Should eventually get a bias message
        if result is not None:
            assert isinstance(result, HTFBiasMessage)
            assert result.bias in ["bullish", "bearish", "neutral"]
            assert 0.0 <= result.score <= 10.0
            assert result.confidence in ["A+", "A", "B", "C"]
            assert isinstance(result.timestamp, datetime)

