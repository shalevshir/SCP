"""Type definitions for SCP trading bot.

This module contains core data models used throughout the application,
including the unified Candle schema for market data.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    """Unified market candle/bar data model.

    Represents OHLCV (Open, High, Low, Close, Volume) data for a specific
    time period with metadata. Immutable to ensure data integrity throughout
    the data pipeline.

    Attributes:
        timestamp: Candle opening time (timezone-aware UTC datetime)
        open: Opening price (must be positive)
        high: Highest price in period (must be >= open, close, low)
        low: Lowest price in period (must be <= open, close, high)
        close: Closing price (must be positive)
        volume: Trading volume (must be non-negative, can be 0)
        symbol: Asset symbol (e.g., "GC", "DXY")
        timeframe: Candle period (e.g., "1m", "5m", "15m")
        source: Data source identifier (e.g., "CSV", "SIMULATION")

    Raises:
        NormalizationError: If validation fails

    Example:
        >>> from datetime import datetime, timezone
        >>> candle = Candle(
        ...     timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        ...     open=100.0,
        ...     high=105.0,
        ...     low=95.0,
        ...     close=102.0,
        ...     volume=1000.0,
        ...     symbol="GC",
        ...     timeframe="1m",
        ...     source="CSV"
        ... )
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    timeframe: str
    source: str

    def __post_init__(self) -> None:
        """Validate candle data after initialization.

        Raises:
            NormalizationError: If any validation rule is violated
        """
        from scp_shared.common.exceptions import NormalizationError

        # Validate timestamp is timezone-aware
        if self.timestamp.tzinfo is None:
            raise NormalizationError(
                "Timestamp must be timezone-aware",
                timestamp=str(self.timestamp),
                symbol=self.symbol,
            )

        # Validate OHLC values are positive
        if self.open <= 0:
            raise NormalizationError(
                "Open price must be positive",
                open=self.open,
                symbol=self.symbol,
            )

        if self.high <= 0:
            raise NormalizationError(
                "High price must be positive",
                high=self.high,
                symbol=self.symbol,
            )

        if self.low <= 0:
            raise NormalizationError(
                "Low price must be positive",
                low=self.low,
                symbol=self.symbol,
            )

        if self.close <= 0:
            raise NormalizationError(
                "Close price must be positive",
                close=self.close,
                symbol=self.symbol,
            )

        # Validate OHLC relationships
        if self.high < self.low:
            raise NormalizationError(
                "High price cannot be less than low price",
                high=self.high,
                low=self.low,
                symbol=self.symbol,
            )

        if self.high < self.open:
            raise NormalizationError(
                "High price cannot be less than open price",
                high=self.high,
                open=self.open,
                symbol=self.symbol,
            )

        if self.high < self.close:
            raise NormalizationError(
                "High price cannot be less than close price",
                high=self.high,
                close=self.close,
                symbol=self.symbol,
            )

        if self.low > self.open:
            raise NormalizationError(
                "Low price cannot be greater than open price",
                low=self.low,
                open=self.open,
                symbol=self.symbol,
            )

        if self.low > self.close:
            raise NormalizationError(
                "Low price cannot be greater than close price",
                low=self.low,
                close=self.close,
                symbol=self.symbol,
            )

        # Validate volume is non-negative
        if self.volume < 0:
            raise NormalizationError(
                "Volume cannot be negative",
                volume=self.volume,
                symbol=self.symbol,
            )

        # Validate string fields are not empty
        if not self.symbol or not self.symbol.strip():
            raise NormalizationError(
                "Symbol cannot be empty",
                symbol=self.symbol,
            )

        if not self.timeframe or not self.timeframe.strip():
            raise NormalizationError(
                "Timeframe cannot be empty",
                timeframe=self.timeframe,
                symbol=self.symbol,
            )

        if not self.source or not self.source.strip():
            raise NormalizationError(
                "Source cannot be empty",
                source=self.source,
                symbol=self.symbol,
            )
