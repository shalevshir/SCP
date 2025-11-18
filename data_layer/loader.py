"""Historical data loader for backtesting.

This module provides the HistoricalDataLoader class for loading GC and DXY
historical data from CSV files into pandas DataFrames.
"""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from common.logger import get_logger
from common.types import Candle

from data_layer.clients import LocalCSVClient

logger = get_logger(__name__)


class HistoricalDataLoader:
    """Loader for historical market data from CSV files.

    This class provides a high-level interface for loading GC (Gold Futures)
    and DXY (Dollar Index) data from CSV files into pandas DataFrames suitable
    for backtesting and analysis.

    The loader:
    - Handles symbol-to-filename mapping (e.g., "DXY" -> "DX_ohlcv-1m.csv")
    - Returns DataFrames with timestamp index
    - Validates data integrity (sorted, unique timestamps)
    - Logs loading statistics

    Example:
        >>> from datetime import datetime, timezone
        >>> from pathlib import Path
        >>> loader = HistoricalDataLoader(Path("data/gc_dx_ohlcv"))
        >>> start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=timezone.utc)
        >>> end = datetime(2025, 9, 30, 4, 30, 0, tzinfo=timezone.utc)
        >>> data = loader.load(["GC", "DXY"], "1m", start, end)
        >>> gc_df = data["GC"]
        >>> dxy_df = data["DXY"]
    """

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        """Initialize the loader with data directory path.

        Args:
            data_dir: Path to directory containing CSV files
        """
        self.data_dir = Path(data_dir)

    def load(
        self,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, pd.DataFrame]:
        """Load historical data for multiple symbols.

        Args:
            symbols: List of symbols to load (e.g., ["GC", "DXY"])
            timeframe: Timeframe for data (e.g., "1m", "15m", "1h")
            start: Start datetime (timezone-aware UTC)
            end: End datetime (timezone-aware UTC)

        Returns:
            Dictionary keyed by symbol, with DataFrames as values.
            Each DataFrame has:
            - Index: timestamp (DatetimeIndex, UTC, sorted, unique)
            - Columns: open, high, low, close, volume, symbol

        Raises:
            DataSourceError: If file not found or data cannot be loaded

        Example:
            >>> loader = HistoricalDataLoader("data/gc_dx_ohlcv")
            >>> data = loader.load(["GC"], "1m", start, end)
            >>> df = data["GC"]
            >>> print(df.head())
        """
        result: dict[str, pd.DataFrame] = {}

        for symbol in symbols:
            # Map symbol to filename
            file_symbol = self._map_symbol_to_filename(symbol)
            file_path = self.data_dir / f"{file_symbol}_ohlcv-{timeframe}.csv"

            # Load data using LocalCSVClient
            client = LocalCSVClient(file_path)
            candles = client.fetch(start, end, timeframe)

            # Convert to DataFrame
            df = self._candles_to_dataframe(candles)

            # Log loading stats
            logger.info(
                f"Loaded {len(df)} rows for {symbol} ({timeframe}) "
                f"from {start.isoformat()} to {end.isoformat()}"
            )

            result[symbol] = df

        return result

    def _map_symbol_to_filename(self, symbol: str) -> str:
        """Map symbol to CSV filename prefix.

        Args:
            symbol: Symbol name (e.g., "GC", "DXY")

        Returns:
            Filename prefix (e.g., "GC", "DX")

        Note:
            DXY maps to "DX" because the CSV files use "DX" prefix.
        """
        if symbol == "DXY":
            return "DX"
        return symbol

    def _candles_to_dataframe(self, candles: list[Candle]) -> pd.DataFrame:
        """Convert list of Candle objects to pandas DataFrame.

        Args:
            candles: List of Candle objects

        Returns:
            DataFrame with timestamp index and OHLCV columns.
            Returns empty DataFrame with correct schema if candles is empty.
        """
        if not candles:
            # Return empty DataFrame with correct schema
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "volume", "symbol"]
            ).set_index(
                pd.DatetimeIndex([], name="timestamp", tz="UTC")
            )

        # Extract data from candles
        data = {
            "timestamp": [c.timestamp for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
            "symbol": [c.symbol for c in candles],
        }

        # Create DataFrame
        df = pd.DataFrame(data)

        # Set timestamp as index
        df = df.set_index("timestamp")
        df.index.name = "timestamp"

        # Sort by timestamp
        df = df.sort_index()

        # Validate index is unique
        if not df.index.is_unique:
            logger.warning(
                "Duplicate timestamps found in data, keeping first occurrence"
            )
            df = df[~df.index.duplicated(keep="first")]

        return df

