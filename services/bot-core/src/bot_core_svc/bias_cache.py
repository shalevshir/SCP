"""HTF Bias Cache with timestamp-aware lookup.

During high-speed replay, bias updates for different data-times arrive out of
order relative to features. This cache stores a history of bias updates indexed
by their DATA timestamp (not wall-clock time), and looks up the appropriate
bias for any given feature timestamp.
"""

import bisect
import threading
from datetime import datetime, timedelta, timezone

from scp_shared.messaging.schemas import HTFBiasMessage


class HTFBiasCache:
    """Thread-safe cache for HTF bias with timestamp-aware lookup.

    Stores a history of bias updates and returns the appropriate bias for
    any given data timestamp. This is critical for replay mode where bias
    updates may arrive out of order relative to features.

    Args:
        ttl_seconds: Time-to-live in DATA seconds (default: 3600 = 1 hour)
        max_history: Maximum number of bias entries to keep (default: 100)

    Example:
        >>> cache = HTFBiasCache(ttl_seconds=3600)
        >>> cache.update(bias_message)
        >>> bias = cache.get_for_timestamp(feature_timestamp)  # Get bias valid at feature time
        >>> bias_or_default = cache.get_or_default()  # Returns latest bias or neutral default
    """

    def __init__(self, ttl_seconds: int = 3600, max_history: int = 100) -> None:
        """Initialize bias cache.

        Args:
            ttl_seconds: TTL in data-time seconds (default: 3600 = 1 hour)
            max_history: Maximum bias entries to keep (default: 100)
        """
        self._lock = threading.Lock()
        # Store bias history as sorted list of (timestamp, bias) tuples
        self._history: list[tuple[datetime, HTFBiasMessage]] = []
        self._ttl_seconds = ttl_seconds
        self._max_history = max_history
        # Also keep latest for backwards compatibility
        self._latest: HTFBiasMessage | None = None

    def update(self, bias: HTFBiasMessage) -> None:
        """Update cache with new bias message.

        Args:
            bias: HTF bias message to cache
        """
        with self._lock:
            # Insert in sorted order by data timestamp
            ts = bias.timestamp
            # Use bisect to find insertion point
            timestamps = [t for t, _ in self._history]
            idx = bisect.bisect_right(timestamps, ts)
            self._history.insert(idx, (ts, bias))

            # Update latest if this is the most recent
            if self._latest is None or ts >= self._latest.timestamp:
                self._latest = bias

            # Trim old entries if exceeding max history
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

    def get_for_timestamp(self, ts: datetime) -> HTFBiasMessage | None:
        """Get the bias that was valid at a specific data timestamp.

        Returns the most recent bias update with timestamp <= ts.
        This ensures features are evaluated with the correct historical bias.

        Args:
            ts: Data timestamp to look up bias for

        Returns:
            Bias valid at that time, or None if no valid bias exists
        """
        with self._lock:
            if not self._history:
                return None

            # Binary search for the latest bias at or before ts
            timestamps = [t for t, _ in self._history]
            idx = bisect.bisect_right(timestamps, ts)

            if idx == 0:
                # No bias before this timestamp
                return None

            # Get the bias at idx-1 (most recent at or before ts)
            bias_ts, bias = self._history[idx - 1]

            # Check if within TTL (in data-time)
            age_seconds = (ts - bias_ts).total_seconds()
            if age_seconds > self._ttl_seconds:
                return None

            return bias

    def get(self) -> HTFBiasMessage | None:
        """Get latest cached bias (for backwards compatibility).

        Returns:
            Latest cached bias message or None if empty/expired
        """
        with self._lock:
            if self._latest is None:
                return None

            # Check wall-clock TTL expiration
            now = datetime.now(timezone.utc)
            age = (now - self._latest.timestamp).total_seconds()
            if age > self._ttl_seconds:
                return None

            return self._latest

    def get_or_default(self) -> HTFBiasMessage:
        """Get latest cached bias or neutral default if empty.

        Returns:
            Latest cached bias message or neutral default
        """
        bias = self.get()
        if bias is not None:
            return bias

        # Return neutral default
        return HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="neutral",
            score=5.0,
            confidence="C",
            structure_15m=None,
            structure_1h=None,
            dxy_aligned=False,
            chop_detected=True,
        )

    def get_for_timestamp_or_default(self, ts: datetime) -> HTFBiasMessage:
        """Get bias for timestamp or neutral default.

        Args:
            ts: Data timestamp to look up bias for

        Returns:
            Bias valid at that time, or neutral default
        """
        bias = self.get_for_timestamp(ts)
        if bias is not None:
            return bias

        # Return neutral default with the requested timestamp
        return HTFBiasMessage(
            timestamp=ts,
            bias="neutral",
            score=5.0,
            confidence="C",
            structure_15m=None,
            structure_1h=None,
            dxy_aligned=False,
            chop_detected=True,
        )

    def clear(self) -> None:
        """Clear cache."""
        with self._lock:
            self._history.clear()
            self._latest = None

    @property
    def is_empty(self) -> bool:
        """Check if cache is empty.

        Returns:
            True if cache is empty
        """
        with self._lock:
            return len(self._history) == 0

    @property
    def history_size(self) -> int:
        """Get number of bias entries in history.

        Returns:
            Number of bias entries
        """
        with self._lock:
            return len(self._history)

    @property
    def is_expired(self) -> bool:
        """Check if cache is expired based on wall-clock TTL.

        Returns:
            True if cache is empty or TTL has expired
        """
        with self._lock:
            if self._latest is None:
                return True

            now = datetime.now(timezone.utc)
            age = (now - self._latest.timestamp).total_seconds()
            return age > self._ttl_seconds

    @property
    def age_seconds(self) -> float | None:
        """Get age of latest bias in wall-clock seconds.

        Returns:
            Age in seconds or None if empty
        """
        with self._lock:
            if self._latest is None:
                return None

            now = datetime.now(timezone.utc)
            return (now - self._latest.timestamp).total_seconds()
