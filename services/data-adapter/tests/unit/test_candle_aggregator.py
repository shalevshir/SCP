"""Tests for CandleAggregator - tick to 1m candle aggregation."""

from dataclasses import dataclass
from datetime import UTC, datetime

from scp_shared.messaging.schemas import CandleMessage

from data_adapter.candle_aggregator import CandleAggregator


@dataclass
class Tick:
    """Simple tick data structure for testing."""
    
    timestamp: datetime
    price: float
    volume: float
    symbol: str = "GC"


class TestCandleAggregator:
    """Test suite for CandleAggregator."""
    
    def test_first_tick_initializes_candle(self) -> None:
        """First tick in minute starts new candle."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        tick = Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 5, tzinfo=UTC),
            price=2650.0,
            volume=10.0,
        )
        
        result = agg.update(tick)
        
        # Candle not closed yet
        assert result is None
        # But aggregator has started tracking
        assert agg.current_open == 2650.0
        assert agg.current_high == 2650.0
        assert agg.current_low == 2650.0
        assert agg.current_close == 2650.0
        assert agg.current_volume == 10.0
    
    def test_multiple_ticks_within_minute_update_ohlc(self) -> None:
        """Multiple ticks within same minute update OHLC values."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        # First tick at 10:00:05 - establishes open
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 5, tzinfo=UTC),
            price=2650.0,
            volume=10.0,
        ))
        
        # Second tick at 10:00:30 - new high
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC),
            price=2655.0,
            volume=20.0,
        ))
        
        # Third tick at 10:00:45 - new low
        result = agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 45, tzinfo=UTC),
            price=2648.0,
            volume=15.0,
        ))
        
        # Still no completed candle
        assert result is None
        
        # But values updated correctly
        assert agg.current_open == 2650.0
        assert agg.current_high == 2655.0
        assert agg.current_low == 2648.0
        assert agg.current_close == 2648.0
        assert agg.current_volume == 45.0
    
    def test_minute_boundary_closes_candle(self) -> None:
        """Tick at new minute closes previous candle."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        # Ticks in minute 10:00
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 5, tzinfo=UTC),
            price=2650.0,
            volume=10.0,
        ))
        
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC),
            price=2655.0,
            volume=20.0,
        ))
        
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 45, tzinfo=UTC),
            price=2648.0,
            volume=15.0,
        ))
        
        # First tick of new minute (10:01:00) closes 10:00 candle
        result = agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC),
            price=2652.0,
            volume=25.0,
        ))
        
        # Should return completed candle
        assert result is not None
        assert isinstance(result, CandleMessage)
        assert result.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        assert result.symbol == "GC"
        assert result.timeframe == "1m"
        assert result.open == 2650.0
        assert result.high == 2655.0
        assert result.low == 2648.0
        assert result.close == 2648.0  # Last tick before boundary
        assert result.volume == 45.0
    
    def test_new_candle_starts_after_boundary(self) -> None:
        """After closing a candle, aggregator starts tracking new one."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        # Complete first candle
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC),
            price=2650.0,
            volume=10.0,
        ))
        
        result = agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC),
            price=2652.0,
            volume=25.0,
        ))
        
        # Candle closed
        assert result is not None
        
        # New candle started
        assert agg.current_open == 2652.0
        assert agg.current_high == 2652.0
        assert agg.current_low == 2652.0
        assert agg.current_close == 2652.0
        assert agg.current_volume == 25.0
        assert agg.current_minute == datetime(2025, 1, 15, 10, 1, tzinfo=UTC)
    
    def test_gap_detection_multi_minute_jump(self) -> None:
        """Detect gap when tick timestamp jumps > 1 minute."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        # Tick at 10:00
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC),
            price=2650.0,
            volume=10.0,
        ))
        
        # Jump to 10:05 (5-minute gap)
        result = agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 5, 30, tzinfo=UTC),
            price=2655.0,
            volume=20.0,
        ))
        
        # Should close 10:00 candle and detect gap
        assert result is not None
        assert result.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        
        # Gap should be detected
        assert agg.gap_detected
        assert agg.gap_start == datetime(2025, 1, 15, 10, 1, tzinfo=UTC)
        assert agg.gap_end == datetime(2025, 1, 15, 10, 5, tzinfo=UTC)
    
    def test_no_gap_on_consecutive_minutes(self) -> None:
        """No gap detected for consecutive minute boundaries."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        # Tick at 10:00
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC),
            price=2650.0,
            volume=10.0,
        ))
        
        # Tick at 10:01 (consecutive)
        result = agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC),
            price=2652.0,
            volume=20.0,
        ))
        
        # Candle closed but no gap
        assert result is not None
        assert not agg.gap_detected
    
    def test_reset_gap_detection_after_read(self) -> None:
        """Gap detection state can be reset."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        # Create a gap
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC),
            price=2650.0,
            volume=10.0,
        ))
        
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 5, 30, tzinfo=UTC),
            price=2655.0,
            volume=20.0,
        ))
        
        assert agg.gap_detected
        
        # Reset gap state
        agg.reset_gap()
        
        assert not agg.gap_detected
        assert agg.gap_start is None
        assert agg.gap_end is None
    
    def test_empty_minute_no_ticks(self) -> None:
        """Aggregator handles minutes with no ticks gracefully."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        # No ticks yet
        assert agg.current_minute is None
        assert agg.current_open is None
    
    def test_single_tick_creates_valid_candle(self) -> None:
        """Single tick creates candle where OHLC all equal."""
        agg = CandleAggregator(symbol="GC", timeframe="1m")
        
        # Single tick at 10:00
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC),
            price=2650.0,
            volume=10.0,
        ))
        
        # Boundary tick closes it
        result = agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC),
            price=2652.0,
            volume=5.0,
        ))
        
        assert result is not None
        assert result.open == 2650.0
        assert result.high == 2650.0
        assert result.low == 2650.0
        assert result.close == 2650.0
        assert result.volume == 10.0
    
    def test_dxy_symbol_aggregation(self) -> None:
        """CandleAggregator works with DXY symbol."""
        agg = CandleAggregator(symbol="DXY", timeframe="1m")
        
        agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 0, 30, tzinfo=UTC),
            price=104.5,
            volume=0.0,  # DXY often has zero volume
            symbol="DXY",
        ))
        
        result = agg.update(Tick(
            timestamp=datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC),
            price=104.6,
            volume=0.0,
            symbol="DXY",
        ))
        
        assert result is not None
        assert result.symbol == "DXY"
        assert result.volume == 0.0

