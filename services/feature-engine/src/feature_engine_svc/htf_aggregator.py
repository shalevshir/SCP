"""HTF Candle Aggregator - aggregates 1m candles to 15m and 1h.

This module implements higher timeframe (HTF) candle aggregation by accumulating
1-minute candles and emitting 15-minute and 1-hour candles at boundaries.
"""

from datetime import datetime

from scp_shared.messaging.schemas import CandleMessage


class HTFCandleAggregator:
    """Aggregates 1m candles into 15m and 1h candles.
    
    Detects timeframe boundaries and emits completed HTF candles:
    - 15m boundaries: minutes 0, 15, 30, 45
    - 1h boundaries: minute 0
    
    Attributes:
        current_15m_*: State for current 15m candle being built
        current_1h_*: State for current 1h candle being built
        current_15m_start: Start timestamp of current 15m period
        current_1h_start: Start timestamp of current 1h period
        symbol: Current symbol being aggregated
    """
    
    def __init__(self):
        """Initialize HTF candle aggregator."""
        # 15m state
        self.current_15m_start: datetime | None = None
        self.current_15m_open: float | None = None
        self.current_15m_high: float | None = None
        self.current_15m_low: float | None = None
        self.current_15m_close: float | None = None
        self.current_15m_volume: float = 0.0
        
        # 1h state
        self.current_1h_start: datetime | None = None
        self.current_1h_open: float | None = None
        self.current_1h_high: float | None = None
        self.current_1h_low: float | None = None
        self.current_1h_close: float | None = None
        self.current_1h_volume: float = 0.0
        
        # Current symbol
        self.symbol: str | None = None
    
    def add_1m_candle(self, candle: CandleMessage) -> list[CandleMessage]:
        """Add 1m candle and return HTF candles if boundary crossed.
        
        Args:
            candle: 1-minute candle
            
        Returns:
            List of HTF candles (may contain 0, 1, or 2 candles).
            At hourly boundaries, returns [15m_candle, 1h_candle] to ensure
            both 15m and 1h features are computed.
        """
        self.symbol = candle.symbol
        
        # Update 15m aggregation
        self._update_15m(candle)
        
        # Update 1h aggregation
        self._update_1h(candle)
        
        results: list[CandleMessage] = []
        
        # Check for 1h boundary - emit BOTH 15m and 1h candles
        if self.is_1h_boundary(candle.timestamp):
            # First emit 15m candle (minute 59 is also a 15m boundary)
            candle_15m = self._emit_15m_candle()
            results.append(candle_15m)
            
            # Then emit 1h candle
            candle_1h = self._emit_1h_candle()
            results.append(candle_1h)
            
            # Reset both 15m and 1h
            self._reset_15m()
            self._reset_1h()
            return results
        
        # Check for 15m boundary (non-hourly)
        if self.is_15m_boundary(candle.timestamp):
            # Emit 15m candle
            candle_15m = self._emit_15m_candle()
            results.append(candle_15m)
            
            # Reset only 15m
            self._reset_15m()
            return results
        
        return results
    
    def _update_15m(self, candle: CandleMessage) -> None:
        """Update 15m aggregation state.
        
        Validates that incoming candle belongs to current period.
        If not (e.g., boundary candle was missed), resets and starts new period.
        """
        candle_period_start = self._get_15m_start(candle.timestamp)
        
        if self.current_15m_start is None:
            # Start new 15m period
            self.current_15m_start = candle_period_start
            self.current_15m_open = candle.open
            self.current_15m_high = candle.high
            self.current_15m_low = candle.low
            self.current_15m_close = candle.close
            self.current_15m_volume = candle.volume
        elif self.current_15m_start == candle_period_start:
            # Candle belongs to current period - update state
            if self.current_15m_high is None or candle.high > self.current_15m_high:
                self.current_15m_high = candle.high
            if self.current_15m_low is None or candle.low < self.current_15m_low:
                self.current_15m_low = candle.low
            self.current_15m_close = candle.close
            self.current_15m_volume += candle.volume
        else:
            # Candle belongs to different period (boundary was missed)
            # Reset and start new period
            self.current_15m_start = candle_period_start
            self.current_15m_open = candle.open
            self.current_15m_high = candle.high
            self.current_15m_low = candle.low
            self.current_15m_close = candle.close
            self.current_15m_volume = candle.volume
    
    def _update_1h(self, candle: CandleMessage) -> None:
        """Update 1h aggregation state.
        
        Validates that incoming candle belongs to current period.
        If not (e.g., boundary candle was missed), resets and starts new period.
        """
        candle_period_start = self._get_1h_start(candle.timestamp)
        
        if self.current_1h_start is None:
            # Start new 1h period
            self.current_1h_start = candle_period_start
            self.current_1h_open = candle.open
            self.current_1h_high = candle.high
            self.current_1h_low = candle.low
            self.current_1h_close = candle.close
            self.current_1h_volume = candle.volume
        elif self.current_1h_start == candle_period_start:
            # Candle belongs to current period - update state
            if self.current_1h_high is None or candle.high > self.current_1h_high:
                self.current_1h_high = candle.high
            if self.current_1h_low is None or candle.low < self.current_1h_low:
                self.current_1h_low = candle.low
            self.current_1h_close = candle.close
            self.current_1h_volume += candle.volume
        else:
            # Candle belongs to different period (boundary was missed)
            # Reset and start new period
            self.current_1h_start = candle_period_start
            self.current_1h_open = candle.open
            self.current_1h_high = candle.high
            self.current_1h_low = candle.low
            self.current_1h_close = candle.close
            self.current_1h_volume = candle.volume
    
    def _emit_15m_candle(self) -> CandleMessage:
        """Emit completed 15m candle."""
        if self.current_15m_start is None:
            raise ValueError("Cannot emit 15m candle - no data accumulated")
        
        return CandleMessage(
            timestamp=self.current_15m_start,
            symbol=self.symbol or "GC",
            timeframe="15m",
            open=self.current_15m_open or 0.0,
            high=self.current_15m_high or 0.0,
            low=self.current_15m_low or 0.0,
            close=self.current_15m_close or 0.0,
            volume=self.current_15m_volume,
        )
    
    def _emit_1h_candle(self) -> CandleMessage:
        """Emit completed 1h candle."""
        if self.current_1h_start is None:
            raise ValueError("Cannot emit 1h candle - no data accumulated")
        
        return CandleMessage(
            timestamp=self.current_1h_start,
            symbol=self.symbol or "GC",
            timeframe="1h",
            open=self.current_1h_open or 0.0,
            high=self.current_1h_high or 0.0,
            low=self.current_1h_low or 0.0,
            close=self.current_1h_close or 0.0,
            volume=self.current_1h_volume,
        )
    
    def _reset_15m(self) -> None:
        """Reset 15m aggregation state."""
        self.current_15m_start = None
        self.current_15m_open = None
        self.current_15m_high = None
        self.current_15m_low = None
        self.current_15m_close = None
        self.current_15m_volume = 0.0
    
    def _reset_1h(self) -> None:
        """Reset 1h aggregation state."""
        self.current_1h_start = None
        self.current_1h_open = None
        self.current_1h_high = None
        self.current_1h_low = None
        self.current_1h_close = None
        self.current_1h_volume = 0.0
    
    @staticmethod
    def is_15m_boundary(timestamp: datetime) -> bool:
        """Check if timestamp is a 15m boundary.
        
        Args:
            timestamp: Timestamp to check
            
        Returns:
            True if minute is 14, 29, 44, or 59 (end of 15m period)
        """
        minute = timestamp.minute
        return minute in [14, 29, 44, 59]
    
    @staticmethod
    def is_1h_boundary(timestamp: datetime) -> bool:
        """Check if timestamp is a 1h boundary.
        
        Args:
            timestamp: Timestamp to check
            
        Returns:
            True if minute is 59 (end of 1h period)
        """
        return timestamp.minute == 59
    
    @staticmethod
    def _get_15m_start(timestamp: datetime) -> datetime:
        """Get start timestamp of 15m period containing timestamp.
        
        Args:
            timestamp: Any timestamp within the period
            
        Returns:
            Start timestamp of the 15m period
        """
        minute = timestamp.minute
        if minute < 15:
            start_minute = 0
        elif minute < 30:
            start_minute = 15
        elif minute < 45:
            start_minute = 30
        else:
            start_minute = 45
        
        return timestamp.replace(minute=start_minute, second=0, microsecond=0)
    
    @staticmethod
    def _get_1h_start(timestamp: datetime) -> datetime:
        """Get start timestamp of 1h period containing timestamp.
        
        Args:
            timestamp: Any timestamp within the period
            
        Returns:
            Start timestamp of the 1h period
        """
        return timestamp.replace(minute=0, second=0, microsecond=0)

