"""Streaming HTF Bias Calculator for incremental processing.

This module provides StreamingHTFBiasCalculator that maintains separate
streaming processors for 1H and 15M timeframes and calls the existing
compute_htf_bias() function to generate HTFBias objects.

Architecture: Detects bar boundaries and delegates to existing HTF calculator.
"""

from datetime import datetime

import pandas as pd
from scp_shared.common.logger import get_logger
from scp_shared.common.types import Candle
from scp_shared.indicators.streaming import StreamingFeatureProcessor

from scp_shared.rule_engine.htf.calculator import compute_htf_bias
from scp_shared.rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


class StreamingHTFBiasCalculator:
    """Streaming HTF bias calculator with multi-timeframe support.

    Maintains separate streaming processors for 1H and 15M timeframes,
    detects bar boundaries, and calls existing compute_htf_bias() function.

    Attributes:
        processor_1h: Streaming feature processor for 1H timeframe
        processor_15m: Streaming feature processor for 15M timeframe
        current_1h_bar: Current 1H bar being built from 1M bars
        current_15m_bar: Current 15M bar being built from 1M bars
        current_htf_bias: Most recent HTF bias calculation
        features_1h: Most recent 1H features
        features_15m: Most recent 15M features
    """

    def __init__(self):
        """Initialize streaming HTF bias calculator."""
        # Create streaming processors for each timeframe
        # Use smaller swing_window (3 instead of 5) to need fewer bars for structure detection
        # swing_window=3 needs 7 bars, swing_window=5 needs 11 bars
        # 1H with swing_window=3 needs 7 hours instead of 11 hours
        # 15M with swing_window=3 needs 7*15min = 1.75 hours instead of 2.75 hours
        self.processor_1h = StreamingFeatureProcessor(timeframe="1h", swing_window=3)
        self.processor_15m = StreamingFeatureProcessor(timeframe="15m", swing_window=3)

        # Track current HTF bars being built
        self.current_1h_timestamp: datetime | None = None
        self.current_15m_timestamp: datetime | None = None

        # Store current state
        self.current_htf_bias: HTFBias | None = None
        self.features_1h: pd.Series = pd.Series(dtype=object)
        self.features_15m: pd.Series = pd.Series(dtype=object)

        # Historical buffers for HTF calculation (needed for structure/FVG detection)
        self.df_1h_buffer: list[dict] = []
        self.df_15m_buffer: list[dict] = []
        self.dxy_1h_buffer: list[dict] = []
        
        # HTF candle aggregation state (properly aggregates 1M -> HTF OHLCV)
        # 15M GC aggregation
        self._gc_15m_start: datetime | None = None
        self._gc_15m_open: float | None = None
        self._gc_15m_high: float | None = None
        self._gc_15m_low: float | None = None
        self._gc_15m_close: float | None = None
        self._gc_15m_volume: float = 0.0
        
        # 1H GC aggregation
        self._gc_1h_start: datetime | None = None
        self._gc_1h_open: float | None = None
        self._gc_1h_high: float | None = None
        self._gc_1h_low: float | None = None
        self._gc_1h_close: float | None = None
        self._gc_1h_volume: float = 0.0
        
        # 1H DXY aggregation
        self._dxy_1h_start: datetime | None = None
        self._dxy_1h_open: float | None = None
        self._dxy_1h_high: float | None = None
        self._dxy_1h_low: float | None = None
        self._dxy_1h_close: float | None = None

        logger.info("Streaming HTF bias calculator initialized")

    def update(self, gc_bar: Candle, dxy_bar: Candle) -> HTFBias | None:
        """Update with new 1M bar and compute HTF bias if boundaries reached.

        Args:
            gc_bar: New 1M Gold candle
            dxy_bar: New 1M DXY candle

        Returns:
            HTFBias object if boundary reached, else None
        """
        # Update HTF candle aggregation (must happen before boundary check)
        self._update_15m_aggregation(gc_bar)
        self._update_1h_aggregation(gc_bar, dxy_bar)
        
        # Detect 15M boundary
        is_15m_close = self._is_15m_boundary(gc_bar.timestamp)

        # Detect 1H boundary
        is_1h_close = self._is_1h_boundary(gc_bar.timestamp)

        # At 15M boundary, emit aggregated candle and update processor
        if is_15m_close:
            # Create aggregated 15M candle from accumulated values
            if self._gc_15m_start is not None:
                gc_15m_candle = Candle(
                    timestamp=self._gc_15m_start,
                    symbol="GC",
                    timeframe="15m",
                    source="aggregated",
                    open=self._gc_15m_open or gc_bar.open,
                    high=self._gc_15m_high or gc_bar.high,
                    low=self._gc_15m_low or gc_bar.low,
                    close=self._gc_15m_close or gc_bar.close,
                    volume=self._gc_15m_volume,
                )
                # Pass aggregated 15M candle to processor (not 1M candle)
                self.features_15m = self.processor_15m.update(gc_15m_candle, dxy_bar)
            else:
                # Fallback if no aggregation happened (shouldn't occur)
                self.features_15m = self.processor_15m.update(gc_bar, dxy_bar)
            # Store properly aggregated 15M bar in historical buffer
            self._emit_15m_to_buffer()
            logger.debug(f"15M bar closed at {gc_bar.timestamp}")

        # At 1H boundary, emit aggregated candle and update processor
        if is_1h_close:
            # Create aggregated 1H candle from accumulated values
            if self._gc_1h_start is not None:
                gc_1h_candle = Candle(
                    timestamp=self._gc_1h_start,
                    symbol="GC",
                    timeframe="1h",
                    source="aggregated",
                    open=self._gc_1h_open or gc_bar.open,
                    high=self._gc_1h_high or gc_bar.high,
                    low=self._gc_1h_low or gc_bar.low,
                    close=self._gc_1h_close or gc_bar.close,
                    volume=self._gc_1h_volume,
                )
                # Pass aggregated 1H candle to processor (not 1M candle)
                self.features_1h = self.processor_1h.update(gc_1h_candle, dxy_bar)
            else:
                # Fallback if no aggregation happened (shouldn't occur)
                self.features_1h = self.processor_1h.update(gc_bar, dxy_bar)
            # Store properly aggregated 1H bar in historical buffer
            self._emit_1h_to_buffer()
            logger.info(
                f"1H bar closed at {gc_bar.timestamp} | "
                f"1H bars in buffer: {len(self.df_1h_buffer)} | "
                f"1H structure: {self.features_1h.get('structure_label', 'N/A')}"
            )

        # Compute HTF bias when we have both 1H and 15M features
        # Trigger on either 1H or 15M close (but need both to exist)
        if (
            (is_1h_close or is_15m_close)
            and not self.features_1h.empty
            and not self.features_15m.empty
        ):
            try:
                # Convert buffers to DataFrames for structure detection
                df_1h = None
                df_15m = None
                dxy_1h = None

                if len(self.df_1h_buffer) > 0:
                    df_1h = pd.DataFrame(self.df_1h_buffer)

                if len(self.df_15m_buffer) > 0:
                    df_15m = pd.DataFrame(self.df_15m_buffer)

                if len(self.dxy_1h_buffer) > 0:
                    dxy_1h = pd.DataFrame(self.dxy_1h_buffer)

                # Call existing HTF bias calculator
                # #region agent log
                import json as _json
                # Get last 3 1H bars from buffer to see actual candles
                _last_1h_bars = []
                if len(self.df_1h_buffer) > 0:
                    for _bar in self.df_1h_buffer[-3:]:
                        _last_1h_bars.append({
                            "ts": str(_bar.get("timestamp", "N/A")),
                            "o": _bar.get("open"),
                            "h": _bar.get("high"),
                            "l": _bar.get("low"),
                            "c": _bar.get("close"),
                        })
                _htf_debug = {
                    "timestamp": str(gc_bar.timestamp),
                    "features_1h": {
                        "structure_label": str(self.features_1h.get("structure_label", "N/A")),
                        "close": float(self.features_1h.get("close", 0)) if self.features_1h.get("close") is not None and not pd.isna(self.features_1h.get("close", 0)) else None,
                        "ema_9": float(self.features_1h.get("ema_9", 0)) if self.features_1h.get("ema_9") is not None and not pd.isna(self.features_1h.get("ema_9", 0)) else None,
                        "ema_20": float(self.features_1h.get("ema_20", 0)) if self.features_1h.get("ema_20") is not None and not pd.isna(self.features_1h.get("ema_20", 0)) else None,
                        "ema_50": str(self.features_1h.get("ema_50")),  # Show raw value to debug why missing
                    },
                    "features_15m": {
                        "structure_label": str(self.features_15m.get("structure_label", "N/A")),
                        "close": float(self.features_15m.get("close", 0)) if self.features_15m.get("close") is not None and not pd.isna(self.features_15m.get("close", 0)) else None,
                        "ema_9": float(self.features_15m.get("ema_9", 0)) if self.features_15m.get("ema_9") is not None and not pd.isna(self.features_15m.get("ema_9", 0)) else None,
                        "ema_20": float(self.features_15m.get("ema_20", 0)) if self.features_15m.get("ema_20") is not None and not pd.isna(self.features_15m.get("ema_20", 0)) else None,
                        "ema_50": float(self.features_15m.get("ema_50", 0)) if self.features_15m.get("ema_50") is not None and not pd.isna(self.features_15m.get("ema_50", 0)) else None,
                    },
                    "buffer_sizes": {
                        "df_1h": len(self.df_1h_buffer),
                        "df_15m": len(self.df_15m_buffer),
                    },
                    "last_1h_bars": _last_1h_bars,
                }
                with open("/Users/shalev/Code/SCP/.cursor/debug.log", "a") as _f:
                    _f.write(_json.dumps({"location": "htf:streaming.py:compute", "message": "htf_features_input", "data": _htf_debug, "timestamp": int(datetime.now().timestamp() * 1000), "sessionId": "debug-session", "hypothesisId": "E"}) + "\n")
                # #endregion
                self.current_htf_bias = compute_htf_bias(
                    features_1h=self.features_1h,
                    features_15m=self.features_15m,
                    dxy_1h=dxy_1h,
                    df_15m=df_15m,
                    df_1h=df_1h,
                    sweep_events_15m=None,  # TODO: Add liquidity sweep detection
                    timestamp=pd.Timestamp(gc_bar.timestamp),
                )

                logger.debug(
                    f"HTF bias updated: {self.current_htf_bias.bias} "
                    f"(score: {self.current_htf_bias.score:.1f}, "
                    f"confidence: {self.current_htf_bias.confidence})"
                )

                return self.current_htf_bias

            except Exception as e:
                logger.error(f"HTF bias calculation failed: {e}", exc_info=True)

        return None

    def _is_15m_boundary(self, timestamp: datetime) -> bool:
        """Check if timestamp is at a 15M bar boundary.

        Args:
            timestamp: Current timestamp

        Returns:
            True if this is the last 1M bar of a 15M period
        """
        # 15M boundaries occur when minute is 14, 29, 44, or 59
        return timestamp.minute % 15 == 14

    def _is_1h_boundary(self, timestamp: datetime) -> bool:
        """Check if timestamp is at a 1H bar boundary.

        Args:
            timestamp: Current timestamp

        Returns:
            True if this is the last 1M bar of a 1H period
        """
        # 1H boundaries occur when minute is 59
        return timestamp.minute == 59

    def _update_15m_aggregation(self, gc_bar: Candle) -> None:
        """Update 15M GC candle aggregation with new 1M bar."""
        period_start = self._get_15m_start(gc_bar.timestamp)
        
        if self._gc_15m_start is None or self._gc_15m_start != period_start:
            # New period - reset aggregation
            self._gc_15m_start = period_start
            self._gc_15m_open = gc_bar.open
            self._gc_15m_high = gc_bar.high
            self._gc_15m_low = gc_bar.low
            self._gc_15m_close = gc_bar.close
            self._gc_15m_volume = gc_bar.volume
        else:
            # Same period - update aggregation
            if gc_bar.high > (self._gc_15m_high or 0):
                self._gc_15m_high = gc_bar.high
            if gc_bar.low < (self._gc_15m_low or float('inf')):
                self._gc_15m_low = gc_bar.low
            self._gc_15m_close = gc_bar.close
            self._gc_15m_volume += gc_bar.volume
    
    def _update_1h_aggregation(self, gc_bar: Candle, dxy_bar: Candle) -> None:
        """Update 1H GC and DXY candle aggregation with new 1M bars."""
        period_start = self._get_1h_start(gc_bar.timestamp)
        
        # GC aggregation
        if self._gc_1h_start is None or self._gc_1h_start != period_start:
            # New period - reset aggregation
            self._gc_1h_start = period_start
            self._gc_1h_open = gc_bar.open
            self._gc_1h_high = gc_bar.high
            self._gc_1h_low = gc_bar.low
            self._gc_1h_close = gc_bar.close
            self._gc_1h_volume = gc_bar.volume
        else:
            # Same period - update aggregation
            if gc_bar.high > (self._gc_1h_high or 0):
                self._gc_1h_high = gc_bar.high
            if gc_bar.low < (self._gc_1h_low or float('inf')):
                self._gc_1h_low = gc_bar.low
            self._gc_1h_close = gc_bar.close
            self._gc_1h_volume += gc_bar.volume
        
        # DXY aggregation
        if self._dxy_1h_start is None or self._dxy_1h_start != period_start:
            # New period - reset aggregation
            self._dxy_1h_start = period_start
            self._dxy_1h_open = dxy_bar.open
            self._dxy_1h_high = dxy_bar.high
            self._dxy_1h_low = dxy_bar.low
            self._dxy_1h_close = dxy_bar.close
        else:
            # Same period - update aggregation
            if dxy_bar.high > (self._dxy_1h_high or 0):
                self._dxy_1h_high = dxy_bar.high
            if dxy_bar.low < (self._dxy_1h_low or float('inf')):
                self._dxy_1h_low = dxy_bar.low
            self._dxy_1h_close = dxy_bar.close
    
    def _emit_15m_to_buffer(self) -> None:
        """Emit completed 15M aggregated candle to buffer and reset."""
        if self._gc_15m_start is None:
            return
        
        self.df_15m_buffer.append({
            "timestamp": self._gc_15m_start,
            "open": self._gc_15m_open,
            "high": self._gc_15m_high,
            "low": self._gc_15m_low,
            "close": self._gc_15m_close,
            "volume": self._gc_15m_volume,
        })
        
        # Limit buffer size (keep last 200 bars = ~2 days)
        max_buffer_size = 200
        if len(self.df_15m_buffer) > max_buffer_size:
            self.df_15m_buffer = self.df_15m_buffer[-max_buffer_size:]
        
        # Reset aggregation for next period
        self._gc_15m_start = None
        self._gc_15m_open = None
        self._gc_15m_high = None
        self._gc_15m_low = None
        self._gc_15m_close = None
        self._gc_15m_volume = 0.0
    
    def _emit_1h_to_buffer(self) -> None:
        """Emit completed 1H aggregated candles to buffers and reset."""
        if self._gc_1h_start is None:
            return
        
        # Add GC bar
        self.df_1h_buffer.append({
            "timestamp": self._gc_1h_start,
            "open": self._gc_1h_open,
            "high": self._gc_1h_high,
            "low": self._gc_1h_low,
            "close": self._gc_1h_close,
            "volume": self._gc_1h_volume,
        })
        
        # Add DXY bar
        self.dxy_1h_buffer.append({
            "timestamp": self._dxy_1h_start,
            "open": self._dxy_1h_open,
            "high": self._dxy_1h_high,
            "low": self._dxy_1h_low,
            "close": self._dxy_1h_close,
        })
        
        # Limit buffer size to prevent memory growth (keep last 200 bars = ~8 days)
        max_buffer_size = 200
        if len(self.df_1h_buffer) > max_buffer_size:
            self.df_1h_buffer = self.df_1h_buffer[-max_buffer_size:]
        if len(self.dxy_1h_buffer) > max_buffer_size:
            self.dxy_1h_buffer = self.dxy_1h_buffer[-max_buffer_size:]
        
        # Reset aggregation for next period
        self._gc_1h_start = None
        self._gc_1h_open = None
        self._gc_1h_high = None
        self._gc_1h_low = None
        self._gc_1h_close = None
        self._gc_1h_volume = 0.0
        self._dxy_1h_start = None
        self._dxy_1h_open = None
        self._dxy_1h_high = None
        self._dxy_1h_low = None
        self._dxy_1h_close = None
    
    def _get_15m_start(self, timestamp: datetime) -> datetime:
        """Get start timestamp of 15M period containing timestamp."""
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
    
    def _get_1h_start(self, timestamp: datetime) -> datetime:
        """Get start timestamp of 1H period containing timestamp."""
        return timestamp.replace(minute=0, second=0, microsecond=0)

    def get_current_features_15m(self) -> pd.Series:
        """Get current 15M features.

        Returns:
            Series with current 15M features (empty if not yet available)
        """
        return self.features_15m

    def get_current_features_1h(self) -> pd.Series:
        """Get current 1H features.

        Returns:
            Series with current 1H features (empty if not yet available)
        """
        return self.features_1h

    def get_current_bias(self) -> HTFBias | None:
        """Get current HTF bias.

        Returns:
            Most recent HTFBias object, or None if not yet calculated
        """
        return self.current_htf_bias

    def is_warmed_up(self) -> bool:
        """Check if calculator has enough data for reliable HTF bias.

        Returns:
            True if we have processed at least 1 complete 1H bar and 4 15M bars
        """
        # Need at least 1 complete 1H bar and 4 15M bars (1 hour) for meaningful context
        # The processor's is_warmed_up() check is too strict (requires 50 bars each)
        return len(self.df_1h_buffer) >= 1 and len(self.df_15m_buffer) >= 4
