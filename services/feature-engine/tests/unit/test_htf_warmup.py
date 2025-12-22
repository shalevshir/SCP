"""Tests for HTF aggregator warmup functionality."""

import pytest
from datetime import datetime, timezone

from feature_engine_svc.htf_aggregator import HTFCandleAggregator
from scp_shared.messaging.schemas import CandleMessage


class TestHTFAggregatorWarmup:
    """Test HTF aggregator warmup to prevent incomplete candles."""
    
    def test_warmup_prevents_incomplete_15m_candle(self):
        """Warmup ensures first 15m candle includes all period data."""
        agg = HTFCandleAggregator()
        
        # Simulate warmup: Feed candles from start of 15m period (10:00-10:04)
        # Service starts at 10:05
        warmup_candles = []
        for i in range(5):  # 10:00 through 10:04
            warmup_candles.append(CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i,
                high=2655.0 + i,
                low=2648.0 + i,
                close=2652.0 + i,
                volume=1000.0,
            ))
        
        # Feed warmup candles (no emission expected)
        for candle in warmup_candles:
            results = agg.add_1m_candle(candle)
            assert len(results) == 0  # Mid-period, no emission
        
        # Verify aggregator state has warmup data
        assert agg.current_15m_open == 2650.0  # First candle's open
        assert agg.current_15m_high == 2659.0  # Max high (2655 + 4)
        assert agg.current_15m_low == 2648.0  # Min low
        assert agg.current_15m_close == 2656.0  # Last close (2652 + 4)
        assert agg.current_15m_volume == 5000.0  # 5 candles
        
        # Now feed remaining candles (10:05-10:14)
        for i in range(5, 15):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i,
                high=2655.0 + i,
                low=2648.0 + i,
                close=2652.0 + i,
                volume=1000.0,
            )
            results = agg.add_1m_candle(candle)
            
            # At minute 14, should emit complete 15m candle
            if i == 14:
                assert len(results) == 1
                result = results[0]
                assert result.timeframe == "15m"
                assert result.open == 2650.0  # CORRECT: First candle from warmup
                assert result.close == 2666.0  # Last candle (2652 + 14)
                assert result.high == 2669.0  # Max high
                assert result.low == 2648.0  # Min low
                assert result.volume == 15000.0  # All 15 candles
    
    def test_without_warmup_incomplete_15m_candle(self):
        """Without warmup, first 15m candle is incomplete (missing early data)."""
        agg = HTFCandleAggregator()
        
        # Service starts at 10:05 WITHOUT warmup
        # Aggregator starts fresh, missing 10:00-10:04 data
        
        # Feed candles starting from 10:05
        for i in range(5, 15):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i,
                high=2655.0 + i,
                low=2648.0 + i,
                close=2652.0 + i,
                volume=1000.0,
            )
            results = agg.add_1m_candle(candle)
            
            if i == 14:
                assert len(results) == 1
                result = results[0]
                assert result.timeframe == "15m"
                # INCORRECT: Open is from 10:05 instead of 10:00
                assert result.open == 2655.0  # Wrong! Should be 2650.0
                assert result.close == 2666.0  # Correct
                # High/low might also be wrong if extremes occurred in 10:00-10:04
                assert result.volume == 10000.0  # Wrong! Missing 5 candles
    
    def test_warmup_handles_1h_boundary(self):
        """Warmup ensures 1h candle includes all period data."""
        agg = HTFCandleAggregator()
        
        # Simulate service starting at 10:30 (mid-hour)
        # Warmup with candles from 10:00-10:29
        for i in range(30):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.1,
                high=2655.0 + i * 0.1,
                low=2648.0 + i * 0.1,
                close=2652.0 + i * 0.1,
                volume=1000.0,
            )
            agg.add_1m_candle(candle)
        
        # Verify 1h state has warmup data
        assert agg.current_1h_open == 2650.0
        assert agg.current_1h_volume == 30000.0
        
        # Feed remaining candles (10:30-10:59)
        for i in range(30, 60):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.1,
                high=2655.0 + i * 0.1,
                low=2648.0 + i * 0.1,
                close=2652.0 + i * 0.1,
                volume=1000.0,
            )
            results = agg.add_1m_candle(candle)
            
            if i == 59:
                # At hourly boundary, both 15m and 1h emitted
                assert len(results) == 2
                candle_15m = results[0]
                candle_1h = results[1]
                assert candle_15m.timeframe == "15m"
                assert candle_1h.timeframe == "1h"
                assert candle_1h.open == 2650.0  # Correct from warmup
                assert candle_1h.volume == 60000.0  # All 60 candles
    
    def test_warmup_with_partial_15m_period(self):
        """Warmup handles partial 15m period correctly."""
        agg = HTFCandleAggregator()
        
        # Service starts at 10:22 (in 10:15-10:29 period)
        # Warmup with 10:15-10:21 (7 candles)
        for i in range(15, 22):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2652.0,
                volume=1000.0,
            )
            agg.add_1m_candle(candle)
        
        # Verify 15m state
        assert agg.current_15m_start == datetime(2025, 1, 15, 10, 15, tzinfo=timezone.utc)
        assert agg.current_15m_volume == 7000.0
        
        # Feed remaining candles (10:22-10:29)
        for i in range(22, 30):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2652.0,
                volume=1000.0,
            )
            results = agg.add_1m_candle(candle)
            
            if i == 29:
                assert len(results) == 1
                result = results[0]
                assert result.volume == 15000.0  # Complete 15m period

