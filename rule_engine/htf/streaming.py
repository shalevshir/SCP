"""Streaming HTF Bias Calculator for incremental processing.

This module provides StreamingHTFBiasCalculator that maintains separate
streaming processors for 1H and 15M timeframes and calls the existing
compute_htf_bias() function to generate HTFBias objects.

Architecture: Detects bar boundaries and delegates to existing HTF calculator.
"""

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from common.logger import get_logger
from common.types import Candle

from feature_engine.streaming import StreamingFeatureProcessor
from rule_engine.htf.calculator import compute_htf_bias
from rule_engine.htf.types import HTFBias

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
        # Use smaller swing_window for 1H (3 instead of 5) to need fewer bars
        # 1H with swing_window=3 needs 7 bars (7 hours) instead of 11 bars (11 hours)
        self.processor_1h = StreamingFeatureProcessor(timeframe="1h", swing_window=3)
        self.processor_15m = StreamingFeatureProcessor(timeframe="15m", swing_window=5)

        # Track current HTF bars being built
        self.current_1h_timestamp: Optional[datetime] = None
        self.current_15m_timestamp: Optional[datetime] = None

        # Store current state
        self.current_htf_bias: Optional[HTFBias] = None
        self.features_1h: pd.Series = pd.Series(dtype=object)
        self.features_15m: pd.Series = pd.Series(dtype=object)

        # Historical buffers for HTF calculation (needed for structure/FVG detection)
        self.df_1h_buffer: list[dict] = []
        self.df_15m_buffer: list[dict] = []
        self.dxy_1h_buffer: list[dict] = []

        logger.info("Streaming HTF bias calculator initialized")

    def update(self, gc_bar: Candle, dxy_bar: Candle) -> Optional[HTFBias]:
        """Update with new 1M bar and compute HTF bias if boundaries reached.
        
        Args:
            gc_bar: New 1M Gold candle
            dxy_bar: New 1M DXY candle
            
        Returns:
            HTFBias object if boundary reached, else None
        """
        # Detect 15M boundary
        is_15m_close = self._is_15m_boundary(gc_bar.timestamp)
        
        # Detect 1H boundary
        is_1h_close = self._is_1h_boundary(gc_bar.timestamp)

        # Always update 15M processor
        if is_15m_close:
            self.features_15m = self.processor_15m.update(gc_bar, dxy_bar)
            # Store 15M bar for historical buffer
            self._add_to_15m_buffer(gc_bar)
            logger.debug(f"15M bar closed at {gc_bar.timestamp}")

        # Update 1H processor at 1H boundary
        if is_1h_close:
            self.features_1h = self.processor_1h.update(gc_bar, dxy_bar)
            # Store 1H bar for historical buffer
            self._add_to_1h_buffer(gc_bar, dxy_bar)
            logger.info(
                f"1H bar closed at {gc_bar.timestamp} | "
                f"1H bars in buffer: {len(self.df_1h_buffer)} | "
                f"1H structure: {self.features_1h.get('structure_label', 'N/A')}"
            )

        # Compute HTF bias when we have both 1H and 15M features
        # Trigger on either 1H or 15M close (but need both to exist)
        if (is_1h_close or is_15m_close) and not self.features_1h.empty and not self.features_15m.empty:
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

    def _add_to_1h_buffer(self, gc_bar: Candle, dxy_bar: Candle) -> None:
        """Add completed 1H bar to historical buffer.
        
        Args:
            gc_bar: Completed 1H GC bar
            dxy_bar: Corresponding DXY bar
        """
        # Add GC bar
        self.df_1h_buffer.append({
            "timestamp": gc_bar.timestamp,
            "open": gc_bar.open,
            "high": gc_bar.high,
            "low": gc_bar.low,
            "close": gc_bar.close,
            "volume": gc_bar.volume,
        })

        # Add DXY bar
        self.dxy_1h_buffer.append({
            "timestamp": dxy_bar.timestamp,
            "open": dxy_bar.open,
            "high": dxy_bar.high,
            "low": dxy_bar.low,
            "close": dxy_bar.close,
        })

        # Limit buffer size to prevent memory growth (keep last 200 bars = ~8 days)
        max_buffer_size = 200
        if len(self.df_1h_buffer) > max_buffer_size:
            self.df_1h_buffer = self.df_1h_buffer[-max_buffer_size:]
        if len(self.dxy_1h_buffer) > max_buffer_size:
            self.dxy_1h_buffer = self.dxy_1h_buffer[-max_buffer_size:]

    def _add_to_15m_buffer(self, gc_bar: Candle) -> None:
        """Add completed 15M bar to historical buffer.
        
        Args:
            gc_bar: Completed 15M GC bar
        """
        self.df_15m_buffer.append({
            "timestamp": gc_bar.timestamp,
            "open": gc_bar.open,
            "high": gc_bar.high,
            "low": gc_bar.low,
            "close": gc_bar.close,
            "volume": gc_bar.volume,
        })

        # Limit buffer size (keep last 200 bars = ~2 days)
        max_buffer_size = 200
        if len(self.df_15m_buffer) > max_buffer_size:
            self.df_15m_buffer = self.df_15m_buffer[-max_buffer_size:]

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

    def get_current_bias(self) -> Optional[HTFBias]:
        """Get current HTF bias.
        
        Returns:
            Most recent HTFBias object, or None if not yet calculated
        """
        return self.current_htf_bias

    def is_warmed_up(self) -> bool:
        """Check if calculator has enough data for reliable HTF bias.
        
        Returns:
            True if both processors are warmed up
        """
        return self.processor_1h.is_warmed_up() and self.processor_15m.is_warmed_up()

