"""Data source client stubs for market data retrieval.

This module contains stub implementations of data clients that will be
replaced with real API integrations in future phases.
"""

from datetime import datetime

from common.exceptions import DataSourceError
from common.types import Candle


class CMEGCClient:
    """CME Gold Futures (GC) data client stub.

    This is a placeholder implementation that defines the interface for
    retrieving CME Gold Futures market data. In Phase 1, it returns an
    empty list to enable testing without external dependencies.

    Future implementations will connect to:
    - CME Group API
    - Third-party data providers (Bloomberg, Reuters, etc.)
    - Historical data archives

    Example:
        >>> from datetime import datetime, timezone
        >>> client = CMEGCClient()
        >>> start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        >>> end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        >>> candles = client.fetch(start, end, "1m")
        >>> # Currently returns empty list
    """

    def __init__(self) -> None:
        """Initialize the CME GC client stub."""
        pass

    def fetch(
        self,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[Candle]:
        """Fetch CME Gold Futures (GC) candle data.

        Args:
            start: Start datetime (must be timezone-aware UTC)
            end: End datetime (must be timezone-aware UTC, must be after start)
            timeframe: Candle timeframe (e.g., "1m", "5m", "15m")

        Returns:
            List of Candle objects representing OHLCV data.
            Currently returns empty list in stub implementation.

        Raises:
            DataSourceError: If validation fails (invalid dates, empty timeframe, etc.)

        Note:
            **This is a stub implementation for Phase 1.**

            Current behavior: Returns empty list to enable testing without
            external dependencies.

            Future behavior: Will fetch real-time and historical data from
            CME Group APIs or data providers.

        Example:
            >>> client = CMEGCClient()
            >>> from datetime import datetime, timezone
            >>> start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
            >>> end = datetime(2025, 1, 1, 23, 59, tzinfo=timezone.utc)
            >>> candles = client.fetch(start, end, "5m")
            >>> assert isinstance(candles, list)
        """
        # Validate start datetime is timezone-aware
        if start.tzinfo is None:
            raise DataSourceError(
                "Start datetime must be timezone-aware",
                start=str(start),
                symbol="GC",
            )

        # Validate end datetime is timezone-aware
        if end.tzinfo is None:
            raise DataSourceError(
                "End datetime must be timezone-aware",
                end=str(end),
                symbol="GC",
            )

        # Validate start is before end
        if start >= end:
            raise DataSourceError(
                "Start time must be before end time",
                start=str(start),
                end=str(end),
                symbol="GC",
            )

        # Validate timeframe is not empty
        if not timeframe or not timeframe.strip():
            raise DataSourceError(
                "Timeframe cannot be empty",
                timeframe=timeframe,
                symbol="GC",
            )

        # Stub implementation: return empty list
        # Future: This will connect to CME API and return real data
        return []


class DXYIndexClient:
    """U.S. Dollar Index (DXY) data client stub.

    This is a placeholder implementation that defines the interface for
    retrieving DXY Index market data. In Phase 1, it returns an empty
    list to enable testing without external dependencies.

    Future implementations will connect to:
    - ICE (Intercontinental Exchange) data feeds
    - Third-party data providers (Bloomberg, Reuters, etc.)
    - Historical data archives

    Example:
        >>> from datetime import datetime, timezone
        >>> client = DXYIndexClient()
        >>> start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        >>> end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        >>> candles = client.fetch(start, end, "1m")
        >>> # Currently returns empty list
    """

    def __init__(self) -> None:
        """Initialize the DXY Index client stub."""
        pass

    def fetch(
        self,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[Candle]:
        """Fetch U.S. Dollar Index (DXY) candle data.

        Args:
            start: Start datetime (must be timezone-aware UTC)
            end: End datetime (must be timezone-aware UTC, must be after start)
            timeframe: Candle timeframe (e.g., "1m", "5m", "15m")

        Returns:
            List of Candle objects representing OHLCV data.
            Currently returns empty list in stub implementation.

        Raises:
            DataSourceError: If validation fails (invalid dates, empty timeframe, etc.)

        Note:
            **This is a stub implementation for Phase 1.**

            Current behavior: Returns empty list to enable testing without
            external dependencies.

            Future behavior: Will fetch real-time and historical data from
            ICE data feeds or third-party data providers.

        Example:
            >>> client = DXYIndexClient()
            >>> from datetime import datetime, timezone
            >>> start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
            >>> end = datetime(2025, 1, 1, 23, 59, tzinfo=timezone.utc)
            >>> candles = client.fetch(start, end, "5m")
            >>> assert isinstance(candles, list)
        """
        # Validate start datetime is timezone-aware
        if start.tzinfo is None:
            raise DataSourceError(
                "Start datetime must be timezone-aware",
                start=str(start),
                symbol="DXY",
            )

        # Validate end datetime is timezone-aware
        if end.tzinfo is None:
            raise DataSourceError(
                "End datetime must be timezone-aware",
                end=str(end),
                symbol="DXY",
            )

        # Validate start is before end
        if start >= end:
            raise DataSourceError(
                "Start time must be before end time",
                start=str(start),
                end=str(end),
                symbol="DXY",
            )

        # Validate timeframe is not empty
        if not timeframe or not timeframe.strip():
            raise DataSourceError(
                "Timeframe cannot be empty",
                timeframe=timeframe,
                symbol="DXY",
            )

        # Stub implementation: return empty list
        # Future: This will connect to ICE data feeds and return real data
        return []
