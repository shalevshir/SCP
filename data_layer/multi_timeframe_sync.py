"""Multi-timeframe synchronization layer for market data.

This module provides MultiTimeframeSyncLayer that loads and synchronizes
data across multiple timeframes (execution timeframe + HTF timeframes)
to ensure all feeds are aligned to the execution timeframe timestamps.

Architecture:
- Loads data for execution timeframe (1m) and HTF timeframes (15m, 1h)
- Aligns all HTF data to execution timeframe timestamps
- Provides synchronized access to all timeframe data at each execution bar
- Handles missing data gracefully (returns None for unavailable HTF bars)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
from common.exceptions import DataSourceError
from common.logger import get_logger
from common.types import Candle

from data_layer.loader import HistoricalDataLoader

logger = get_logger(__name__)


@dataclass
class SynchronizedBar:
    """Synchronized data for all timeframes at execution timestamp.
    
    Represents all available timeframe data aligned to a single
    execution timestamp. HTF bars are the most recent bar that
    closed at or before the execution timestamp.
    
    Attributes:
        execution_timestamp: Execution timeframe timestamp
        execution_1m: Tuple of (GC, DXY) candles for 1m timeframe
        htf_15m: Optional tuple of (GC, DXY) candles for 15m timeframe
        htf_1h: Optional tuple of (GC, DXY) candles for 1h timeframe
    """
    
    execution_timestamp: datetime
    execution_1m: tuple[Candle, Candle]  # (GC, DXY)
    htf_15m: Optional[tuple[Candle, Candle]]  # (GC, DXY) or None
    htf_1h: Optional[tuple[Candle, Candle]]  # (GC, DXY) or None


@dataclass
class MultiTimeframeData:
    """Container for all synchronized timeframe data.
    
    Attributes:
        execution_timeframe: Execution timeframe (e.g., "1m")
        htf_timeframes: List of HTF timeframes (e.g., ["15m", "1h"])
        synchronized_bars: List of SynchronizedBar objects
        execution_timestamps: List of execution timestamps (for indexing)
    """
    
    execution_timeframe: str
    htf_timeframes: list[str]
    synchronized_bars: list[SynchronizedBar]
    execution_timestamps: list[datetime]
    
    def __len__(self) -> int:
        """Return number of synchronized bars."""
        return len(self.synchronized_bars)
    
    def get_bar(self, timestamp: datetime) -> Optional[SynchronizedBar]:
        """Get synchronized bar for specific timestamp.
        
        Args:
            timestamp: Execution timestamp to look up
            
        Returns:
            SynchronizedBar if found, None otherwise
        """
        try:
            idx = self.execution_timestamps.index(timestamp)
            return self.synchronized_bars[idx]
        except ValueError:
            return None


class MultiTimeframeSyncLayer:
    """Synchronizes multiple timeframe data to execution timeframe.
    
    Loads GC and DXY data for execution timeframe (1m) and HTF timeframes
    (15m, 1h), then aligns all HTF data to execution timeframe timestamps.
    
    Example:
        >>> from datetime import datetime, timezone
        >>> sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
        >>> start = datetime(2025, 9, 30, 10, 0, tzinfo=timezone.utc)
        >>> end = datetime(2025, 9, 30, 13, 0, tzinfo=timezone.utc)
        >>> data = sync_layer.load(start, end)
        >>> bar = data.get_bar(start)
        >>> print(f"1m: {bar.execution_1m}, 15m: {bar.htf_15m}, 1h: {bar.htf_1h}")
    """
    
    def __init__(
        self,
        data_dir: str,
        execution_timeframe: str = "1m",
        htf_timeframes: list[str] | None = None,
    ) -> None:
        """Initialize sync layer.
        
        Args:
            data_dir: Path to directory containing CSV files
            execution_timeframe: Execution timeframe (default: "1m")
            htf_timeframes: List of HTF timeframes (default: ["15m", "1h"])
            
        Raises:
            ValueError: If execution_timeframe is invalid or HTF timeframes
                       are not larger than execution timeframe
        """
        if not execution_timeframe or not execution_timeframe.strip():
            raise ValueError("Execution timeframe cannot be empty")
        
        if htf_timeframes is None:
            htf_timeframes = ["15m", "1h"]
        
        # Validate HTF timeframes are larger than execution timeframe
        # This is a simple check - in production, would parse and compare
        # For now, assume execution is 1m and HTF are 15m, 1h
        if execution_timeframe == "1m":
            for htf in htf_timeframes:
                if htf not in ["15m", "1h", "4h", "1d"]:
                    raise ValueError(
                        f"HTF timeframe {htf} must be larger than execution timeframe {execution_timeframe}"
                    )
        
        self.data_dir = data_dir
        self.execution_timeframe = execution_timeframe
        self.htf_timeframes = htf_timeframes
        self.loader = HistoricalDataLoader(data_dir)
        
        logger.info(
            f"MultiTimeframeSyncLayer initialized | "
            f"execution={execution_timeframe} | "
            f"htf={htf_timeframes}"
        )
    
    def load(
        self,
        start: datetime,
        end: datetime,
        symbols: list[str] | None = None,
    ) -> MultiTimeframeData:
        """Load and synchronize all timeframe data.
        
        Args:
            start: Start datetime (timezone-aware UTC)
            end: End datetime (timezone-aware UTC)
            symbols: List of symbols to load (default: ["GC", "DXY"])
            
        Returns:
            MultiTimeframeData with all synchronized bars
            
        Raises:
            DataSourceError: If data loading fails
            ValueError: If no overlapping timestamps found
        """
        if symbols is None:
            symbols = ["GC", "DXY"]
        
        logger.info(
            f"Loading multi-timeframe data from {start.isoformat()} "
            f"to {end.isoformat()} for symbols {symbols}"
        )
        
        # Load all timeframe data
        all_data = self._load_all_timeframes(start, end, symbols)
        
        # Synchronize all feeds to execution timeframe
        synchronized_bars = self._synchronize_all_feeds(all_data)
        
        if not synchronized_bars:
            raise ValueError(
                f"No synchronized bars created. Check data availability "
                f"for timeframes {[self.execution_timeframe] + self.htf_timeframes}"
            )
        
        execution_timestamps = [bar.execution_timestamp for bar in synchronized_bars]
        
        logger.info(
            f"Loaded {len(synchronized_bars)} synchronized bars "
            f"from {execution_timestamps[0]} to {execution_timestamps[-1]}"
        )
        
        return MultiTimeframeData(
            execution_timeframe=self.execution_timeframe,
            htf_timeframes=self.htf_timeframes,
            synchronized_bars=synchronized_bars,
            execution_timestamps=execution_timestamps,
        )
    
    def _load_all_timeframes(
        self,
        start: datetime,
        end: datetime,
        symbols: list[str],
    ) -> dict[str, dict[str, pd.DataFrame]]:
        """Load data for all symbols and timeframes.
        
        Args:
            start: Start datetime
            end: End datetime
            symbols: List of symbols to load
            
        Returns:
            Nested dict: {symbol: {timeframe: DataFrame}}
            
        Raises:
            DataSourceError: If data loading fails
        """
        all_data: dict[str, dict[str, pd.DataFrame]] = {}
        all_timeframes = [self.execution_timeframe] + self.htf_timeframes
        
        for symbol in symbols:
            all_data[symbol] = {}
            for timeframe in all_timeframes:
                try:
                    data = self.loader.load([symbol], timeframe, start, end)
                    df = data.get(symbol)
                    if df is None or df.empty:
                        logger.warning(
                            f"No data loaded for {symbol} {timeframe} "
                            f"from {start.isoformat()} to {end.isoformat()}"
                        )
                        # Create empty DataFrame with correct schema
                        all_data[symbol][timeframe] = pd.DataFrame(
                            columns=["open", "high", "low", "close", "volume", "symbol"]
                        ).set_index(
                            pd.DatetimeIndex([], name="timestamp", tz="UTC")
                        )
                    else:
                        all_data[symbol][timeframe] = df
                        logger.debug(
                            f"Loaded {len(df)} rows for {symbol} {timeframe}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to load {symbol} {timeframe}: {e}. "
                        f"Continuing with empty DataFrame for this timeframe."
                    )
                    # Create empty DataFrame with correct schema instead of failing
                    all_data[symbol][timeframe] = pd.DataFrame(
                        columns=["open", "high", "low", "close", "volume", "symbol"]
                    ).set_index(
                        pd.DatetimeIndex([], name="timestamp", tz="UTC")
                    )
        
        return all_data
    
    def _synchronize_all_feeds(
        self,
        all_data: dict[str, dict[str, pd.DataFrame]],
    ) -> list[SynchronizedBar]:
        """Synchronize all timeframe data to execution timeframe.
        
        Args:
            all_data: Nested dict {symbol: {timeframe: DataFrame}}
            
        Returns:
            List of SynchronizedBar objects
        """
        # Get execution timeframe data
        exec_gc = all_data["GC"][self.execution_timeframe]
        exec_dxy = all_data["DXY"][self.execution_timeframe]
        
        # Align execution timeframe GC and DXY (inner join)
        if exec_gc.empty or exec_dxy.empty:
            logger.warning("Empty execution timeframe data")
            return []
        
        common_timestamps = exec_gc.index.intersection(exec_dxy.index)
        if len(common_timestamps) == 0:
            logger.warning("No overlapping timestamps between GC and DXY execution data")
            return []
        
        # Align HTF timeframes to execution
        htf_aligned: dict[str, dict[str, pd.Series]] = {}
        for htf_tf in self.htf_timeframes:
            htf_aligned[htf_tf] = {}
            htf_aligned[htf_tf]["GC"] = self._align_htf_to_execution(
                exec_gc, all_data["GC"][htf_tf], htf_tf
            )
            htf_aligned[htf_tf]["DXY"] = self._align_htf_to_execution(
                exec_dxy, all_data["DXY"][htf_tf], htf_tf
            )
        
        # Build synchronized bars
        synchronized_bars: list[SynchronizedBar] = []
        for ts in common_timestamps:
            # Get execution bars
            exec_gc_row = exec_gc.loc[ts]
            exec_dxy_row = exec_dxy.loc[ts]
            exec_gc_bar = self._df_row_to_candle(exec_gc_row, "GC", self.execution_timeframe)
            exec_dxy_bar = self._df_row_to_candle(exec_dxy_row, "DXY", self.execution_timeframe)
            
            # Get HTF bars
            htf_15m = None
            htf_1h = None
            
            if "15m" in self.htf_timeframes:
                htf_15m_gc_series = htf_aligned["15m"]["GC"].get(ts)
                htf_15m_dxy_series = htf_aligned["15m"]["DXY"].get(ts)
                if (htf_15m_gc_series is not None and 
                    htf_15m_dxy_series is not None and
                    isinstance(htf_15m_gc_series, pd.Series) and
                    isinstance(htf_15m_dxy_series, pd.Series)):
                    htf_15m_gc_bar = self._series_to_candle(htf_15m_gc_series, "GC", "15m")
                    htf_15m_dxy_bar = self._series_to_candle(htf_15m_dxy_series, "DXY", "15m")
                    if htf_15m_gc_bar and htf_15m_dxy_bar:
                        htf_15m = (htf_15m_gc_bar, htf_15m_dxy_bar)
            
            if "1h" in self.htf_timeframes:
                htf_1h_gc_series = htf_aligned["1h"]["GC"].get(ts)
                htf_1h_dxy_series = htf_aligned["1h"]["DXY"].get(ts)
                if (htf_1h_gc_series is not None and 
                    htf_1h_dxy_series is not None and
                    isinstance(htf_1h_gc_series, pd.Series) and
                    isinstance(htf_1h_dxy_series, pd.Series)):
                    htf_1h_gc_bar = self._series_to_candle(htf_1h_gc_series, "GC", "1h")
                    htf_1h_dxy_bar = self._series_to_candle(htf_1h_dxy_series, "DXY", "1h")
                    if htf_1h_gc_bar and htf_1h_dxy_bar:
                        htf_1h = (htf_1h_gc_bar, htf_1h_dxy_bar)
            
            bar = SynchronizedBar(
                execution_timestamp=ts,
                execution_1m=(exec_gc_bar, exec_dxy_bar),
                htf_15m=htf_15m,
                htf_1h=htf_1h,
            )
            synchronized_bars.append(bar)
        
        return synchronized_bars
    
    def _align_htf_to_execution(
        self,
        execution_df: pd.DataFrame,
        htf_df: pd.DataFrame,
        timeframe: str,
    ) -> pd.Series:
        """Align HTF data to execution timeframe timestamps.
        
        For each execution timestamp, returns the most recent HTF bar
        that closed at or before that timestamp.
        
        Args:
            execution_df: Execution timeframe DataFrame
            htf_df: HTF timeframe DataFrame
            timeframe: HTF timeframe string (for logging)
            
        Returns:
            Series indexed by execution timestamps with HTF bar data
            (or None if no HTF bar available)
        """
        if htf_df.empty:
            logger.debug(f"No HTF data for {timeframe}, returning None for all timestamps")
            return pd.Series(index=execution_df.index, dtype=object)
        
        aligned = pd.Series(index=execution_df.index, dtype=object)
        htf_timestamps = htf_df.index
        
        for exec_ts in execution_df.index:
            # Find most recent HTF bar <= exec_ts
            valid_htf = htf_timestamps[htf_timestamps <= exec_ts]
            if len(valid_htf) > 0:
                latest_htf_ts = valid_htf.max()
                aligned[exec_ts] = htf_df.loc[latest_htf_ts]
            else:
                aligned[exec_ts] = None
        
        return aligned
    
    def _df_row_to_candle(
        self,
        row: pd.Series,
        symbol: str,
        timeframe: str,
    ) -> Candle:
        """Convert DataFrame row to Candle object.
        
        Args:
            row: DataFrame row (Series)
            symbol: Symbol name
            timeframe: Timeframe string
            
        Returns:
            Candle object
        """
        return Candle(
            timestamp=row.name,  # Index is timestamp
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            symbol=symbol,
            timeframe=timeframe,
            source="CSV",
        )
    
    def _series_to_candle(
        self,
        series: pd.Series | None,
        symbol: str,
        timeframe: str,
    ) -> Candle | None:
        """Convert aligned Series to Candle object.
        
        Args:
            series: Series with OHLCV data (or None)
            symbol: Symbol name
            timeframe: Timeframe string
            
        Returns:
            Candle object or None
        """
        if series is None:
            return None
        
        # Check if series is actually a Series (not a scalar/float)
        if not isinstance(series, pd.Series):
            return None
        
        # Check for NaN values in required columns
        required_cols = ["open", "high", "low", "close", "volume"]
        if not all(col in series.index for col in required_cols):
            return None
        
        if any(pd.isna(series.get(col)) for col in required_cols):
            return None
        
        # series.name is the timestamp from the DataFrame index
        if series.name is None:
            return None
        
        return Candle(
            timestamp=series.name,
            open=float(series["open"]),
            high=float(series["high"]),
            low=float(series["low"]),
            close=float(series["close"]),
            volume=float(series["volume"]),
            symbol=symbol,
            timeframe=timeframe,
            source="CSV",
        )

