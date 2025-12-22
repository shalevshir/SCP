"""Gap Detector - detects and backfills missing candles.

This module detects gaps in candle data (missing minutes) and triggers
historical backfill from Databento or database.
"""

from datetime import datetime, timedelta
from typing import Protocol

from scp_shared.messaging.schemas import CandleMessage


class HistoricalFetcher(Protocol):
    """Protocol for historical data fetcher."""
    
    async def fetch_candles(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1m",
    ) -> list[CandleMessage]:
        """Fetch historical candles for given time range."""
        ...


class GapDetector:
    """Detects gaps in candle stream and triggers backfill.
    
    Tracks last timestamp per symbol and detects when incoming candles
    skip > 1 minute. Provides backfill functionality to request missing
    candles from historical data source.
    """
    
    def __init__(self, historical_fetcher: HistoricalFetcher | None = None) -> None:
        """Initialize gap detector.
        
        Args:
            historical_fetcher: Optional fetcher for historical backfill
        """
        self.historical_fetcher = historical_fetcher
        
        # Track last timestamp per symbol
        self.last_timestamp_by_symbol: dict[str, datetime] = {}
        
        # Current gap state
        self.gap_start: datetime | None = None
        self.gap_end: datetime | None = None
        
        # For backward compatibility
        self.last_timestamp: datetime | None = None
    
    def check_gap(self, candle: CandleMessage) -> bool:
        """Check if candle indicates a gap since last candle.
        
        Args:
            candle: Incoming candle to check
            
        Returns:
            True if gap detected, False otherwise
        """
        symbol = candle.symbol
        
        # First candle for this symbol - no gap
        if symbol not in self.last_timestamp_by_symbol:
            self.last_timestamp_by_symbol[symbol] = candle.timestamp
            self.last_timestamp = candle.timestamp
            return False
        
        last_ts = self.last_timestamp_by_symbol[symbol]
        expected_next = last_ts + timedelta(minutes=1)
        
        # Check if gap exists (candle timestamp > expected next)
        if candle.timestamp > expected_next:
            self.gap_start = expected_next
            self.gap_end = candle.timestamp
            self.last_timestamp_by_symbol[symbol] = candle.timestamp
            self.last_timestamp = candle.timestamp
            return True
        
        # No gap - update timestamp
        self.last_timestamp_by_symbol[symbol] = candle.timestamp
        self.last_timestamp = candle.timestamp
        self.gap_start = None
        self.gap_end = None
        return False
    
    def get_missing_timestamps(self) -> list[datetime]:
        """Get list of missing minute timestamps in current gap.
        
        Returns:
            List of datetime objects for missing minutes
        """
        if self.gap_start is None or self.gap_end is None:
            return []
        
        missing = []
        current = self.gap_start
        
        while current < self.gap_end:
            missing.append(current)
            current += timedelta(minutes=1)
        
        return missing
    
    async def backfill(self, symbol: str) -> list[CandleMessage]:
        """Backfill missing candles from historical data.
        
        Args:
            symbol: Symbol to backfill
            
        Returns:
            List of backfilled candles
        """
        if self.gap_start is None or self.gap_end is None:
            return []
        
        if self.historical_fetcher is None:
            return []
        
        # Fetch historical candles for gap period
        candles = await self.historical_fetcher.fetch_candles(
            symbol=symbol,
            start=self.gap_start,
            end=self.gap_end,
            timeframe="1m",
        )
        
        return candles
    
    def reset(self) -> None:
        """Reset gap detection state."""
        self.gap_start = None
        self.gap_end = None

