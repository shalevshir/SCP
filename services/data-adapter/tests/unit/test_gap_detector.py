"""Tests for GapDetector - gap detection and historical backfill."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from scp_shared.messaging.schemas import CandleMessage

from data_adapter.gap_detector import GapDetector


class TestGapDetector:
    """Test suite for GapDetector."""
    
    def test_no_gap_on_first_candle(self) -> None:
        """First candle doesn't trigger gap detection."""
        detector = GapDetector()
        
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        has_gap = detector.check_gap(candle)
        
        assert not has_gap
        assert detector.last_timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
    
    def test_no_gap_on_consecutive_candles(self) -> None:
        """Consecutive 1m candles don't trigger gap."""
        detector = GapDetector()
        
        candle1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2651.0,
            high=2653.0,
            low=2650.0,
            close=2652.0,
            volume=1000.0,
        )
        
        detector.check_gap(candle1)
        has_gap = detector.check_gap(candle2)
        
        assert not has_gap
    
    def test_gap_detected_on_skip(self) -> None:
        """Gap detected when candle skips > 1 minute."""
        detector = GapDetector()
        
        candle1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        # Skip to 10:05 (5-minute gap)
        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 5, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2655.0,
            high=2657.0,
            low=2654.0,
            close=2656.0,
            volume=1000.0,
        )
        
        detector.check_gap(candle1)
        has_gap = detector.check_gap(candle2)
        
        assert has_gap
        assert detector.gap_start == datetime(2025, 1, 15, 10, 1, tzinfo=UTC)
        assert detector.gap_end == datetime(2025, 1, 15, 10, 5, tzinfo=UTC)
    
    def test_get_missing_timestamps(self) -> None:
        """get_missing_timestamps returns list of missing minute boundaries."""
        detector = GapDetector()
        
        candle1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 5, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2655.0,
            high=2657.0,
            low=2654.0,
            close=2656.0,
            volume=1000.0,
        )
        
        detector.check_gap(candle1)
        detector.check_gap(candle2)
        
        missing = detector.get_missing_timestamps()
        
        assert len(missing) == 4
        assert missing[0] == datetime(2025, 1, 15, 10, 1, tzinfo=UTC)
        assert missing[1] == datetime(2025, 1, 15, 10, 2, tzinfo=UTC)
        assert missing[2] == datetime(2025, 1, 15, 10, 3, tzinfo=UTC)
        assert missing[3] == datetime(2025, 1, 15, 10, 4, tzinfo=UTC)
    
    @pytest.mark.asyncio
    async def test_backfill_requests_missing_candles(self) -> None:
        """backfill() requests missing candles from historical API."""
        # Mock historical data fetcher
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_candles = AsyncMock(return_value=[
            CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                open=2651.0,
                high=2652.0,
                low=2650.0,
                close=2651.5,
                volume=500.0,
            ),
            CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),
                symbol="GC",
                timeframe="1m",
                open=2651.5,
                high=2653.0,
                low=2651.0,
                close=2652.0,
                volume=500.0,
            ),
        ])
        
        detector = GapDetector(historical_fetcher=mock_fetcher)
        
        candle1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 3, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2652.0,
            high=2654.0,
            low=2651.5,
            close=2653.0,
            volume=1000.0,
        )
        
        detector.check_gap(candle1)
        detector.check_gap(candle2)
        
        # Backfill missing candles
        backfilled = await detector.backfill(symbol="GC")
        
        assert len(backfilled) == 2
        assert backfilled[0].timestamp == datetime(2025, 1, 15, 10, 1, tzinfo=UTC)
        assert backfilled[1].timestamp == datetime(2025, 1, 15, 10, 2, tzinfo=UTC)
        
        # Verify fetcher was called with correct timestamps
        mock_fetcher.fetch_candles.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_backfill_without_gap_returns_empty(self) -> None:
        """backfill() returns empty list when no gap exists."""
        detector = GapDetector()
        
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        detector.check_gap(candle)
        
        backfilled = await detector.backfill(symbol="GC")
        
        assert len(backfilled) == 0
    
    def test_reset_gap_state(self) -> None:
        """reset() clears gap detection state."""
        detector = GapDetector()
        
        candle1 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        candle2 = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 5, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2655.0,
            high=2657.0,
            low=2654.0,
            close=2656.0,
            volume=1000.0,
        )
        
        detector.check_gap(candle1)
        detector.check_gap(candle2)
        
        assert detector.gap_start is not None
        
        detector.reset()
        
        assert detector.gap_start is None
        assert detector.gap_end is None
    
    def test_multiple_symbols_tracked_separately(self) -> None:
        """Different symbols tracked with separate timestamps."""
        detector = GapDetector()
        
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        detector.check_gap(gc_candle)
        detector.check_gap(dxy_candle)
        
        # No gap for GC (first candle)
        # No gap for DXY (first candle for DXY)
        assert detector.last_timestamp_by_symbol.get("GC") == datetime(
            2025, 1, 15, 10, 0, tzinfo=UTC
        )
        assert detector.last_timestamp_by_symbol.get("DXY") == datetime(
            2025, 1, 15, 10, 2, tzinfo=UTC
        )

