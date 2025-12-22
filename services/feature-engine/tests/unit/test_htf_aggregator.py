"""Tests for HTFCandleAggregator."""

import pytest
from datetime import datetime, timezone

from feature_engine_svc.htf_aggregator import HTFCandleAggregator
from scp_shared.messaging.schemas import CandleMessage


class TestHTFCandleAggregator:
    """Test HTF candle aggregation (1m to 15m/1h)."""
    
    def test_15m_boundary_detection(self):
        """15m boundaries detected at minutes 14, 29, 44, 59 (end of periods)."""
        agg = HTFCandleAggregator()
        
        # Not a boundary
        assert not agg.is_15m_boundary(datetime(2025, 1, 15, 10, 5, tzinfo=timezone.utc))
        assert not agg.is_15m_boundary(datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc))
        
        # Boundaries (end of 15m periods)
        assert agg.is_15m_boundary(datetime(2025, 1, 15, 10, 14, tzinfo=timezone.utc))
        assert agg.is_15m_boundary(datetime(2025, 1, 15, 10, 29, tzinfo=timezone.utc))
        assert agg.is_15m_boundary(datetime(2025, 1, 15, 10, 44, tzinfo=timezone.utc))
        assert agg.is_15m_boundary(datetime(2025, 1, 15, 10, 59, tzinfo=timezone.utc))
    
    def test_1h_boundary_detection(self):
        """1h boundaries detected at minute 59 (end of period)."""
        agg = HTFCandleAggregator()
        
        # Not a boundary
        assert not agg.is_1h_boundary(datetime(2025, 1, 15, 10, 5, tzinfo=timezone.utc))
        assert not agg.is_1h_boundary(datetime(2025, 1, 15, 10, 15, tzinfo=timezone.utc))
        assert not agg.is_1h_boundary(datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc))
        
        # Boundaries (end of 1h periods)
        assert agg.is_1h_boundary(datetime(2025, 1, 15, 10, 59, tzinfo=timezone.utc))
        assert agg.is_1h_boundary(datetime(2025, 1, 15, 11, 59, tzinfo=timezone.utc))
    
    def test_15m_aggregation_basic(self):
        """15 x 1m candles aggregate into 1 x 15m candle."""
        agg = HTFCandleAggregator()
        
        # Feed 15 x 1m candles
        for i in range(15):
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
            
            # No 15m candle until boundary
            if i < 14:
                assert len(results) == 0
            else:
                # At 10:14, should emit 15m candle for 10:00-10:14
                assert len(results) == 1
                candle_15m = results[0]
                assert candle_15m.timeframe == "15m"
                assert candle_15m.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
                assert candle_15m.open == 2650.0  # First candle open
                assert candle_15m.close == 2666.0  # Last candle close (2652 + 14)
                assert candle_15m.high == 2669.0  # Max high (2655 + 14)
                assert candle_15m.low == 2648.0  # Min low (first candle)
                assert candle_15m.volume == 15000.0  # Sum of volumes
    
    def test_1h_aggregation_basic(self):
        """60 x 1m candles aggregate into 1 x 1h candle + 4 x 15m candles."""
        agg = HTFCandleAggregator()
        
        # Feed 60 x 1m candles
        for i in range(60):
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
            
            # 15m candles emitted at 14, 29, 44
            # At 59: BOTH 15m and 1h emitted (2 candles)
            if i == 59:
                assert len(results) == 2
                # Results should be [15m, 1h] - 15m first
                candle_15m = results[0]
                candle_1h = results[1]
                
                assert candle_15m.timeframe == "15m"
                assert candle_15m.timestamp == datetime(2025, 1, 15, 10, 45, tzinfo=timezone.utc)
                
                assert candle_1h.timeframe == "1h"
                assert candle_1h.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
                assert candle_1h.open == 2650.0
                assert abs(candle_1h.close - 2657.9) < 0.01
                assert candle_1h.volume == 60000.0
    
    def test_multiple_15m_periods(self):
        """Multiple 15m periods handled correctly."""
        agg = HTFCandleAggregator()
        
        candles_15m = []
        
        # Feed 30 x 1m candles (2 x 15m periods)
        for i in range(30):
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
            for result in results:
                if result.timeframe == "15m":
                    candles_15m.append(result)
        
        # Should have 2 x 15m candles
        assert len(candles_15m) == 2
        assert candles_15m[0].timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert candles_15m[1].timestamp == datetime(2025, 1, 15, 10, 15, tzinfo=timezone.utc)
    
    def test_15m_and_1h_emitted_together(self):
        """At hour boundary, BOTH 15m and 1h candles emitted.
        
        This is critical: at minute 59, both the 15m candle (45-59) and
        the 1h candle must be returned. Otherwise the 15m features for
        that period are never computed/published.
        """
        agg = HTFCandleAggregator()
        
        # Feed 60 x 1m candles
        candles_15m = []
        candles_1h = []
        
        for i in range(60):
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
            for result in results:
                if result.timeframe == "15m":
                    candles_15m.append(result)
                elif result.timeframe == "1h":
                    candles_1h.append(result)
        
        # MUST have 4 x 15m candles (at 14, 29, 44, 59)
        # Each 15m period needs its own features computed
        assert len(candles_15m) == 4
        assert candles_15m[0].timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert candles_15m[1].timestamp == datetime(2025, 1, 15, 10, 15, tzinfo=timezone.utc)
        assert candles_15m[2].timestamp == datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert candles_15m[3].timestamp == datetime(2025, 1, 15, 10, 45, tzinfo=timezone.utc)
        
        # Should have 1 x 1h candle (at 59)
        assert len(candles_1h) == 1
        assert candles_1h[0].timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    
    def test_ohlcv_aggregation_correctness(self):
        """OHLCV values aggregated correctly."""
        agg = HTFCandleAggregator()
        
        # Feed candles with specific OHLCV values
        candles_1m = [
            CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                symbol="GC", timeframe="1m",
                open=2650.0, high=2655.0, low=2648.0, close=2652.0, volume=1000.0,
            ),
            CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
                symbol="GC", timeframe="1m",
                open=2652.0, high=2660.0, low=2650.0, close=2658.0, volume=1500.0,
            ),
            CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc),
                symbol="GC", timeframe="1m",
                open=2658.0, high=2662.0, low=2656.0, close=2660.0, volume=1200.0,
            ),
        ]
        
        for candle in candles_1m:
            agg.add_1m_candle(candle)
        
        # Check 15m buffer state
        assert agg.current_15m_open == 2650.0  # First open
        assert agg.current_15m_high == 2662.0  # Max high
        assert agg.current_15m_low == 2648.0  # Min low
        assert agg.current_15m_close == 2660.0  # Last close
        assert agg.current_15m_volume == 3700.0  # Sum
    
    def test_reset_after_boundary(self):
        """Aggregation state resets after boundary."""
        agg = HTFCandleAggregator()
        
        # Feed 15 candles
        for i in range(15):
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
        
        # State should be reset
        assert agg.current_15m_open is None
        assert agg.current_15m_volume == 0.0
        
        # Add first candle of next period
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 15, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2660.0,
            high=2665.0,
            low=2658.0,
            close=2662.0,
            volume=1100.0,
        )
        agg.add_1m_candle(candle)
        
        # New period started
        assert agg.current_15m_open == 2660.0
        assert agg.current_15m_volume == 1100.0
    
    def test_dxy_symbol_handled(self):
        """DXY candles handled same as GC."""
        agg = HTFCandleAggregator()
        
        # Feed 15 x 1m DXY candles
        for i in range(15):
            candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5,
                high=104.6,
                low=104.4,
                close=104.55,
                volume=0.0,
            )
            results = agg.add_1m_candle(candle)
            
            if i == 14:
                assert len(results) == 1
                assert results[0].symbol == "DXY"
                assert results[0].timeframe == "15m"
    
    def test_missed_boundary_candle_15m(self):
        """If boundary candle is missed, next period starts correctly.
        
        Scenario:
        - Candles 10:00-10:13 are processed (period 10:00-10:14)
        - Candle 10:14 (boundary) is MISSED
        - Candle 10:15 arrives - should start NEW period 10:15-10:29
        - NOT merge into previous period 10:00-10:14
        """
        agg = HTFCandleAggregator()
        
        # Feed candles 10:00-10:13 (14 candles, period 10:00-10:14)
        for i in range(14):
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
            assert len(results) == 0  # No boundary yet
        
        # Verify state is for period 10:00-10:14
        assert agg.current_15m_start == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert agg.current_15m_open == 2650.0
        assert agg.current_15m_close == 2665.0  # 2652 + 13
        
        # MISS boundary candle 10:14, jump to 10:15
        # This should start a NEW period, not merge into previous
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 15, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2700.0,  # Different price to detect merge
            high=2705.0,
            low=2698.0,
            close=2702.0,
            volume=2000.0,
        )
        results = agg.add_1m_candle(candle)
        
        # Should have started new period 10:15-10:29
        assert agg.current_15m_start == datetime(2025, 1, 15, 10, 15, tzinfo=timezone.utc)
        assert agg.current_15m_open == 2700.0  # New period's open
        assert agg.current_15m_close == 2702.0  # New period's close
        assert agg.current_15m_volume == 2000.0  # Only new candle's volume
        
        # Previous period's close should NOT be 2702.0 (would indicate merge)
        # The previous period should have been reset or not contain 10:15 data
    
    def test_missed_boundary_candle_1h(self):
        """If 1h boundary candle is missed, next period starts correctly."""
        agg = HTFCandleAggregator()
        
        # Feed candles 10:00-10:58 (59 candles, period 10:00-10:59)
        for i in range(59):
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
        
        # Verify state is for period 10:00-10:59
        assert agg.current_1h_start == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        
        # MISS boundary candle 10:59, jump to 11:00
        # This should start a NEW period, not merge into previous
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2750.0,  # Different price to detect merge
            high=2755.0,
            low=2748.0,
            close=2752.0,
            volume=3000.0,
        )
        results = agg.add_1m_candle(candle)
        
        # Should have started new period 11:00-11:59
        assert agg.current_1h_start == datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc)
        assert agg.current_1h_open == 2750.0  # New period's open
        assert agg.current_1h_close == 2752.0  # New period's close
        assert agg.current_1h_volume == 3000.0  # Only new candle's volume

