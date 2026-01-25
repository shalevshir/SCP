"""Candle Aggregator - converts ticks to 1-minute OHLCV candles.

This module implements tick-by-tick aggregation into 1-minute candles with
gap detection for the Data Adapter service.
"""

from dataclasses import dataclass
from datetime import datetime

from scp_shared.messaging.schemas import CandleMessage


@dataclass
class Tick:
    """Tick data structure."""

    timestamp: datetime
    price: float
    volume: float
    symbol: str


class CandleAggregator:
    """Aggregates ticks into 1-minute OHLCV candles.

    Tracks OHLCV values incrementally:
    - Open: First tick price in the minute
    - High: Maximum tick price in the minute
    - Low: Minimum tick price in the minute
    - Close: Last tick price in the minute
    - Volume: Sum of tick volumes in the minute

    Emits completed candle when minute boundary is crossed.
    Detects gaps when ticks skip > 1 minute.
    """

    def __init__(self, symbol: str, timeframe: str = "1m") -> None:
        """Initialize candle aggregator.

        Args:
            symbol: Asset symbol (e.g., "GC", "DXY")
            timeframe: Candle timeframe (currently only "1m" supported)
        """
        self.symbol = symbol
        self.timeframe = timeframe

        # Current candle state
        self.current_minute: datetime | None = None
        self.current_open: float | None = None
        self.current_high: float | None = None
        self.current_low: float | None = None
        self.current_close: float | None = None
        self.current_volume: float = 0.0

        # Gap detection
        self.gap_detected: bool = False
        self.gap_start: datetime | None = None
        self.gap_end: datetime | None = None

    def update(self, tick: Tick) -> CandleMessage | None:
        """Process new tick and return completed candle if minute boundary crossed.

        Args:
            tick: Incoming tick data

        Returns:
            CandleMessage if minute boundary was crossed, None otherwise
        """
        # Truncate to minute boundary
        tick_minute = tick.timestamp.replace(second=0, microsecond=0)

        # First tick ever
        if self.current_minute is None:
            self._start_new_candle(tick, tick_minute)
            return None

        # Same minute - update OHLCV
        if tick_minute == self.current_minute:
            self._update_current_candle(tick)
            return None

        # New minute - close current candle
        completed_candle = self._close_current_candle()

        # Check for gap (more than 1 minute difference)
        expected_next = self._add_minutes(self.current_minute, 1)
        if tick_minute > expected_next:
            self.gap_detected = True
            self.gap_start = expected_next
            self.gap_end = tick_minute
        else:
            self.gap_detected = False
            self.gap_start = None
            self.gap_end = None

        # Start new candle
        self._start_new_candle(tick, tick_minute)

        return completed_candle

    def reset_gap(self) -> None:
        """Reset gap detection state."""
        self.gap_detected = False
        self.gap_start = None
        self.gap_end = None

    def _start_new_candle(self, tick: Tick, minute: datetime) -> None:
        """Start tracking a new candle."""
        self.current_minute = minute
        self.current_open = tick.price
        self.current_high = tick.price
        self.current_low = tick.price
        self.current_close = tick.price
        self.current_volume = tick.volume

    def _update_current_candle(self, tick: Tick) -> None:
        """Update OHLCV values with new tick in same minute."""
        if self.current_high is None or tick.price > self.current_high:
            self.current_high = tick.price

        if self.current_low is None or tick.price < self.current_low:
            self.current_low = tick.price

        self.current_close = tick.price
        self.current_volume += tick.volume

    def _close_current_candle(self) -> CandleMessage:
        """Close current candle and return as CandleMessage."""
        if self.current_minute is None:
            raise ValueError("Cannot close candle - no current minute set")

        candle = CandleMessage(
            timestamp=self.current_minute,
            symbol=self.symbol,
            timeframe=self.timeframe,
            open=self.current_open or 0.0,
            high=self.current_high or 0.0,
            low=self.current_low or 0.0,
            close=self.current_close or 0.0,
            volume=self.current_volume,
        )

        return candle

    @staticmethod
    def _add_minutes(dt: datetime, minutes: int) -> datetime:
        """Add minutes to datetime (simple implementation for 1m only)."""
        from datetime import timedelta

        return dt + timedelta(minutes=minutes)
