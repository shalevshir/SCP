"""DataStream - Historical data iterator for simulation.

This module provides DataStream that loads historical data and yields
synchronized GC/DXY candle pairs with support for seeking and warmup.

Architecture:
- Replaces HistoricalStreamSimulator
- Supports efficient seeking to any timestamp
- Provides warmup candles for indicator initialization
- Thread-safe iteration
"""

from datetime import datetime, timedelta
from typing import Iterator, Optional

from common.logger import get_logger
from common.types import Candle
from data_layer.loader import HistoricalDataLoader
from data_layer.multi_timeframe_sync import (
    MultiTimeframeData,
    MultiTimeframeSyncLayer,
    SynchronizedBar,
)

logger = get_logger(__name__)


class DataStream:
    """Historical data stream with seeking and warmup support.

    Manages loading historical data and provides iterator interface
    for simulation. Supports seeking to specific timestamps and
    provides separate warmup candles for indicator initialization.

    Attributes:
        data_dir: Path to data directory
        gc_candles: List of Gold candles
        dxy_candles: List of DXY candles
        current_index: Current position in stream
        stream_start_index: Index where live simulation starts
        warmup_bars: Number of bars before stream_start_index
        stream_bars: Number of bars from stream_start_index to end
    """

    def __init__(self, data_dir: str, enable_multi_timeframe: bool = False):
        """Initialize data stream.

        Args:
            data_dir: Path to directory containing OHLCV CSV files
            enable_multi_timeframe: If True, use multi-timeframe sync layer
                                   (default: False for backward compatibility)
        """
        self.data_dir = data_dir
        self.gc_candles: list[Candle] = []
        self.dxy_candles: list[Candle] = []
        self.current_index = 0
        self.stream_start_index = 0
        self.warmup_bars = 0
        self.stream_bars = 0

        self._loader = HistoricalDataLoader(data_dir)
        self.enable_multi_timeframe = enable_multi_timeframe
        self._sync_layer: Optional[MultiTimeframeSyncLayer] = None
        self._multi_tf_data: Optional[MultiTimeframeData] = None

        if enable_multi_timeframe:
            self._sync_layer = MultiTimeframeSyncLayer(data_dir)

        logger.info(
            f"DataStream initialized with data_dir: {data_dir} | "
            f"multi_timeframe={enable_multi_timeframe}"
        )

    def load(
        self,
        start: datetime,
        end: datetime,
        timeframe: str = "1m",
    ) -> int:
        """Load historical data for date range.

        Args:
            start: Start datetime (UTC)
            end: End datetime (UTC)
            timeframe: Timeframe to load (default: "1m")

        Returns:
            Number of candles loaded

        Raises:
            DataSourceError: If data loading fails
        """
        logger.info(
            f"Loading data from {start.isoformat()} to {end.isoformat()} "
            f"({timeframe})"
        )

        # Load data
        data = self._loader.load(
            symbols=["GC", "DXY"],
            timeframe=timeframe,
            start=start,
            end=end,
        )

        gc_df = data.get("GC")
        dxy_df = data.get("DXY")

        if gc_df is None or gc_df.empty:
            logger.warning("No GC data loaded")
            return 0

        if dxy_df is None or dxy_df.empty:
            logger.warning("No DXY data loaded")
            return 0

        # Convert DataFrames to Candle lists
        self.gc_candles = []
        self.dxy_candles = []

        # Align data by timestamp (inner join)
        common_times = gc_df.index.intersection(dxy_df.index)

        for ts in common_times:
            gc_row = gc_df.loc[ts]
            dxy_row = dxy_df.loc[ts]

            # Create GC candle
            gc_candle = Candle(
                timestamp=ts.to_pydatetime(),
                open=float(gc_row["open"]),
                high=float(gc_row["high"]),
                low=float(gc_row["low"]),
                close=float(gc_row["close"]),
                volume=float(gc_row.get("volume", 0.0)),
                symbol="GC",
                timeframe=timeframe,
                source="CSV",
            )
            self.gc_candles.append(gc_candle)

            # Create DXY candle
            dxy_candle = Candle(
                timestamp=ts.to_pydatetime(),
                open=float(dxy_row["open"]),
                high=float(dxy_row["high"]),
                low=float(dxy_row["low"]),
                close=float(dxy_row["close"]),
                volume=float(dxy_row.get("volume", 0.0)),
                symbol="DXY",
                timeframe=timeframe,
                source="CSV",
            )
            self.dxy_candles.append(dxy_candle)

        # Initialize indices
        self.current_index = 0
        self.stream_start_index = 0
        self.warmup_bars = 0
        self.stream_bars = len(self.gc_candles)

        logger.info(f"Loaded {len(self.gc_candles):,} aligned candle pairs")
        
        # If multi-timeframe enabled, also load synchronized data
        if self.enable_multi_timeframe and self._sync_layer:
            try:
                self._multi_tf_data = self._sync_layer.load(start, end)
                logger.info(
                    f"Multi-timeframe sync: {len(self._multi_tf_data)} synchronized bars"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load multi-timeframe data: {e}. "
                    f"Continuing with single timeframe mode."
                )
                self._multi_tf_data = None
        
        return len(self.gc_candles)

    def seek_to_timestamp(self, target: datetime) -> int:
        """Seek to specific timestamp, setting warmup boundary.

        All candles before target become warmup candles.
        Iteration starts from target timestamp.

        Args:
            target: Target timestamp to seek to (UTC)

        Returns:
            Index of target timestamp (or nearest after)

        Raises:
            ValueError: If no candles loaded or target out of range
        """
        if not self.gc_candles:
            raise ValueError("No candles loaded")

        # Find index of target timestamp
        target_index = 0
        for i, candle in enumerate(self.gc_candles):
            if candle.timestamp >= target:
                target_index = i
                break
        else:
            # Target is after all candles
            target_index = len(self.gc_candles)

        # Set boundaries
        self.stream_start_index = target_index
        self.current_index = target_index
        self.warmup_bars = target_index
        self.stream_bars = len(self.gc_candles) - target_index

        logger.info(
            f"Seeked to {target.isoformat()} | "
            f"warmup_bars={self.warmup_bars} | "
            f"stream_bars={self.stream_bars}"
        )

        return target_index

    def get_warmup_candles(self) -> Iterator[tuple[Candle, Candle]]:
        """Iterate through warmup candles (before stream_start_index).

        Yields:
            Tuple of (gc_candle, dxy_candle) for each warmup bar
        """
        for i in range(self.stream_start_index):
            yield self.gc_candles[i], self.dxy_candles[i]

    def get_candle_at(self, index: int) -> tuple[Candle, Candle]:
        """Get candle pair at specific index.

        Args:
            index: Index to retrieve

        Returns:
            Tuple of (gc_candle, dxy_candle)

        Raises:
            IndexError: If index out of range
        """
        if index < 0 or index >= len(self.gc_candles):
            raise IndexError(f"Index {index} out of range [0, {len(self.gc_candles)})")
        return self.gc_candles[index], self.dxy_candles[index]

    def advance(self) -> Optional[tuple[Candle, Candle]]:
        """Advance to next candle and return it.

        Returns:
            Tuple of (gc_candle, dxy_candle), or None if exhausted
        """
        if not self.has_more():
            return None

        gc_candle = self.gc_candles[self.current_index]
        dxy_candle = self.dxy_candles[self.current_index]
        self.current_index += 1

        return gc_candle, dxy_candle

    def has_more(self) -> bool:
        """Check if more candles are available.

        Returns:
            True if current_index < total candles
        """
        return self.current_index < len(self.gc_candles)

    def get_progress(self) -> float:
        """Get current progress through stream portion.

        Returns:
            Progress as fraction [0.0, 1.0] where 0 = stream_start_index
        """
        if self.stream_bars == 0:
            return 0.0

        bars_processed = self.current_index - self.stream_start_index
        return bars_processed / self.stream_bars

    def reset(self) -> None:
        """Reset to stream start (after warmup)."""
        self.current_index = self.stream_start_index
        logger.debug(f"Stream reset to index {self.current_index}")

    def reset_to_beginning(self) -> None:
        """Reset to absolute beginning (including warmup)."""
        self.current_index = 0
        self.stream_start_index = 0
        self.warmup_bars = 0
        self.stream_bars = len(self.gc_candles)
        logger.debug("Stream reset to beginning")

    def __iter__(self) -> Iterator[tuple[Candle, Candle]]:
        """Iterate through stream portion (after warmup).

        Yields:
            Tuple of (gc_candle, dxy_candle) for each bar
        """
        # Start from stream_start_index
        self.current_index = self.stream_start_index

        while self.has_more():
            candle_pair = self.advance()
            if candle_pair:
                yield candle_pair

    def __len__(self) -> int:
        """Return total number of candles."""
        return len(self.gc_candles)
    
    def get_synchronized_bar(self, timestamp: datetime) -> Optional[SynchronizedBar]:
        """Get synchronized multi-timeframe bar for specific timestamp.
        
        Requires multi-timeframe mode to be enabled. Returns None if:
        - Multi-timeframe mode is disabled
        - No synchronized data available
        - Timestamp not found
        
        Args:
            timestamp: Execution timestamp to look up
            
        Returns:
            SynchronizedBar with all timeframe data, or None
        """
        if not self.enable_multi_timeframe or self._multi_tf_data is None:
            return None
        
        return self._multi_tf_data.get_bar(timestamp)
    
    def get_current_synchronized_bar(self) -> Optional[SynchronizedBar]:
        """Get synchronized bar for current index.
        
        Returns:
            SynchronizedBar for current position, or None if not available
        """
        if not self.gc_candles or self.current_index >= len(self.gc_candles):
            return None
        
        current_timestamp = self.gc_candles[self.current_index].timestamp
        return self.get_synchronized_bar(current_timestamp)
    
    @property
    def multi_timeframe_data(self) -> Optional[MultiTimeframeData]:
        """Get multi-timeframe data if available.
        
        Returns:
            MultiTimeframeData object, or None if not loaded
        """
        return self._multi_tf_data

