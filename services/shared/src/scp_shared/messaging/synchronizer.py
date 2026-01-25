"""Synchronizers - pairs messages by timestamp.

This module implements message buffering and synchronization to ensure that
related messages with matching timestamps are processed together.
"""

from datetime import datetime, timedelta
from typing import Dict

from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage, SignalMessage


class CandleSynchronizer:
    """Synchronizes GC and DXY candles by timestamp.

    Buffers incoming candles and emits pairs when both GC and DXY candles
    with matching timestamps are available. Handles late arrivals with
    configurable timeout.

    Attributes:
        timeout_seconds: Maximum age for buffered candles before removal
        gc_buffer: Buffer of GC candles keyed by timestamp
        dxy_buffer: Buffer of DXY candles keyed by timestamp
    """

    def __init__(self, timeout_seconds: int = 5):
        """Initialize candle synchronizer.

        Args:
            timeout_seconds: Maximum age for buffered candles (default: 5)
        """
        self.timeout_seconds = timeout_seconds
        self.gc_buffer: Dict[datetime, CandleMessage] = {}
        self.dxy_buffer: Dict[datetime, CandleMessage] = {}

    def add_candle(
        self,
        candle: CandleMessage,
    ) -> tuple[CandleMessage, CandleMessage] | None:
        """Add candle and return pair if match found.

        Args:
            candle: Incoming candle (GC or DXY)

        Returns:
            Tuple of (gc_candle, dxy_candle) if pair found, None otherwise

        Raises:
            ValueError: If candle symbol is not GC or DXY
        """
        # Route to appropriate buffer
        if candle.symbol == "GC":
            self.gc_buffer[candle.timestamp] = candle
            # Check for matching DXY candle
            if candle.timestamp in self.dxy_buffer:
                dxy_candle = self.dxy_buffer.pop(candle.timestamp)
                gc_candle = self.gc_buffer.pop(candle.timestamp)
                return (gc_candle, dxy_candle)
        elif candle.symbol == "DXY":
            self.dxy_buffer[candle.timestamp] = candle
            # Check for matching GC candle
            if candle.timestamp in self.gc_buffer:
                gc_candle = self.gc_buffer.pop(candle.timestamp)
                dxy_candle = self.dxy_buffer.pop(candle.timestamp)
                return (gc_candle, dxy_candle)
        else:
            raise ValueError(f"Unknown symbol: {candle.symbol}. Expected GC or DXY.")

        # Clean up stale candles
        self._cleanup_stale_candles(candle.timestamp)

        return None

    def _cleanup_stale_candles(self, current_timestamp: datetime) -> None:
        """Remove candles older than timeout.

        Args:
            current_timestamp: Reference timestamp for age calculation
        """
        # Only clean up if timeout is exceeded (in seconds, not minutes)
        # Convert timeout to minutes for candle-based cleanup
        cutoff_minutes = self.timeout_seconds // 60
        if cutoff_minutes < 1:
            cutoff_minutes = 1  # At least 1 minute

        cutoff = current_timestamp - timedelta(minutes=cutoff_minutes)

        # Remove stale GC candles
        stale_gc = [ts for ts in self.gc_buffer if ts < cutoff]
        for ts in stale_gc:
            del self.gc_buffer[ts]

        # Remove stale DXY candles
        stale_dxy = [ts for ts in self.dxy_buffer if ts < cutoff]
        for ts in stale_dxy:
            del self.dxy_buffer[ts]

    def get_buffer_stats(self) -> dict:
        """Get buffer statistics.

        Returns:
            Dictionary with buffer counts
        """
        return {
            "gc_count": len(self.gc_buffer),
            "dxy_count": len(self.dxy_buffer),
            "total_unpaired": len(self.gc_buffer) + len(self.dxy_buffer),
        }

    def clear(self) -> None:
        """Clear all buffers."""
        self.gc_buffer.clear()
        self.dxy_buffer.clear()


class CandleFeatureSynchronizer:
    """Synchronizes candles with features by timestamp.

    Buffers incoming candles and features and emits pairs when both
    are available for the same timestamp. This ensures the execution
    service processes candles with their corresponding features.

    Attributes:
        timeout_seconds: Maximum age for buffered messages before removal
        candle_buffer: Buffer of candles keyed by timestamp
        feature_buffer: Buffer of features keyed by timestamp
    """

    def __init__(self, timeout_seconds: int = 60):
        """Initialize candle-feature synchronizer.

        Args:
            timeout_seconds: Maximum age for buffered messages (default: 60)
        """
        self.timeout_seconds = timeout_seconds
        self.candle_buffer: Dict[datetime, CandleMessage] = {}
        self.feature_buffer: Dict[datetime, FeaturesMessage] = {}

    def add_candle(
        self,
        candle: CandleMessage,
    ) -> tuple[CandleMessage, FeaturesMessage] | None:
        """Add candle and return pair if matching features found.

        Args:
            candle: Incoming candle

        Returns:
            Tuple of (candle, features) if pair found, None otherwise
        """
        self.candle_buffer[candle.timestamp] = candle

        # Check for matching features
        if candle.timestamp in self.feature_buffer:
            features = self.feature_buffer.pop(candle.timestamp)
            candle_out = self.candle_buffer.pop(candle.timestamp)
            return (candle_out, features)

        # Clean up stale messages
        self._cleanup_stale(candle.timestamp)
        return None

    def add_features(
        self,
        features: FeaturesMessage,
    ) -> tuple[CandleMessage, FeaturesMessage] | None:
        """Add features and return pair if matching candle found.

        Args:
            features: Incoming features

        Returns:
            Tuple of (candle, features) if pair found, None otherwise
        """
        self.feature_buffer[features.timestamp] = features

        # Check for matching candle
        if features.timestamp in self.candle_buffer:
            candle = self.candle_buffer.pop(features.timestamp)
            features_out = self.feature_buffer.pop(features.timestamp)
            return (candle, features_out)
        # Clean up stale messages
        self._cleanup_stale(features.timestamp)
        return None

    def _cleanup_stale(self, current_timestamp: datetime) -> None:
        """Remove messages older than timeout.

        Args:
            current_timestamp: Reference timestamp for age calculation
        """
        cutoff = current_timestamp - timedelta(seconds=self.timeout_seconds)

        # Remove stale candles
        stale_candles = [ts for ts in self.candle_buffer if ts < cutoff]
        for ts in stale_candles:
            del self.candle_buffer[ts]

        # Remove stale features
        stale_features = [ts for ts in self.feature_buffer if ts < cutoff]
        for ts in stale_features:
            del self.feature_buffer[ts]

    def get_buffer_stats(self) -> dict:
        """Get buffer statistics.

        Returns:
            Dictionary with buffer counts
        """
        return {
            "candle_count": len(self.candle_buffer),
            "feature_count": len(self.feature_buffer),
            "total_unpaired": len(self.candle_buffer) + len(self.feature_buffer),
        }

    def clear(self) -> None:
        """Clear all buffers."""
        self.candle_buffer.clear()
        self.feature_buffer.clear()
