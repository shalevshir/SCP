"""Tests for CandleSynchronizer."""

import pytest
from datetime import datetime, timezone

from feature_engine_svc.synchronizer import CandleSynchronizer
from scp_shared.messaging.schemas import CandleMessage


class TestCandleSynchronizer:
    """Test candle synchronization (GC + DXY pairing)."""
    
    def test_synchronized_candles_emitted_immediately(self):
        """When GC and DXY arrive for same timestamp, pair emitted immediately."""
        sync = CandleSynchronizer(timeout_seconds=5)
        
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
        
        # Add GC first
        result1 = sync.add_candle(gc_candle)
        assert result1 is None  # No pair yet
        
        # Add DXY - should complete the pair
        result2 = sync.add_candle(dxy_candle)
        assert result2 is not None
        gc_out, dxy_out = result2
        assert gc_out.timestamp == gc_candle.timestamp
        assert dxy_out.timestamp == dxy_candle.timestamp
    
    def test_dxy_arrives_first(self):
        """DXY can arrive before GC and still pair correctly."""
        sync = CandleSynchronizer(timeout_seconds=5)
        
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
        
        # Add DXY first
        result1 = sync.add_candle(dxy_candle)
        assert result1 is None
        
        # Add GC - should complete the pair
        result2 = sync.add_candle(gc_candle)
        assert result2 is not None
    
    def test_multiple_timestamps_buffered(self):
        """Multiple timestamps can be buffered simultaneously."""
        sync = CandleSynchronizer(timeout_seconds=5)
        
        gc1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        gc2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2652.0,
            high=2657.0,
            low=2650.0,
            close=2654.0,
            volume=1100.0,
        )
        dxy1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        dxy2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.55,
            high=104.65,
            low=104.45,
            close=104.60,
            volume=0.0,
        )
        
        # Add GC candles
        assert sync.add_candle(gc1) is None
        assert sync.add_candle(gc2) is None
        
        # Add DXY candles - should complete pairs
        pair1 = sync.add_candle(dxy1)
        assert pair1 is not None
        assert pair1[0].timestamp == gc1.timestamp
        
        pair2 = sync.add_candle(dxy2)
        assert pair2 is not None
        assert pair2[0].timestamp == gc2.timestamp
    
    def test_timeout_removes_stale_candles(self):
        """Candles older than timeout are removed."""
        sync = CandleSynchronizer(timeout_seconds=2)
        
        old_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        
        # Add old candle
        sync.add_candle(old_candle)
        
        # Simulate time passing by adding a much later candle
        new_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 5, tzinfo=timezone.utc),  # 5 minutes later
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        sync.add_candle(new_candle)
        
        # Old candle should be removed from buffer
        assert len(sync.gc_buffer) == 0
        assert len(sync.dxy_buffer) == 1
    
    def test_get_buffer_stats(self):
        """Buffer statistics are reported correctly."""
        sync = CandleSynchronizer(timeout_seconds=5)
        
        gc1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        gc2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2652.0,
            high=2657.0,
            low=2650.0,
            close=2654.0,
            volume=1100.0,
        )
        
        sync.add_candle(gc1)
        sync.add_candle(gc2)
        
        stats = sync.get_buffer_stats()
        assert stats["gc_count"] == 2
        assert stats["dxy_count"] == 0
        assert stats["total_unpaired"] == 2
    
    def test_clear_buffers(self):
        """Buffers can be cleared."""
        sync = CandleSynchronizer(timeout_seconds=5)
        
        gc = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        sync.add_candle(gc)
        sync.add_candle(dxy)
        
        sync.clear()
        
        stats = sync.get_buffer_stats()
        assert stats["gc_count"] == 0
        assert stats["dxy_count"] == 0
    
    def test_same_timestamp_different_symbols_paired(self):
        """Candles with same timestamp but different symbols are paired."""
        sync = CandleSynchronizer(timeout_seconds=5)
        
        gc = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        sync.add_candle(gc)
        pair = sync.add_candle(dxy)
        
        assert pair is not None
        gc_out, dxy_out = pair
        assert gc_out.symbol == "GC"
        assert dxy_out.symbol == "DXY"
        assert gc_out.timestamp == dxy_out.timestamp
    
    def test_unknown_symbol_raises_error(self):
        """Adding candle with unknown symbol raises ValueError."""
        sync = CandleSynchronizer(timeout_seconds=5)
        
        unknown = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="UNKNOWN",
            timeframe="1m",
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000.0,
        )
        
        with pytest.raises(ValueError, match="Unknown symbol"):
            sync.add_candle(unknown)

