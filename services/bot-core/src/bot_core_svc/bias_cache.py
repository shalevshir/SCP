"""HTF Bias Cache with TTL."""

import threading
from datetime import datetime, timedelta, timezone

from scp_shared.messaging.schemas import HTFBiasMessage


class HTFBiasCache:
    """Thread-safe cache for HTF bias with TTL.
    
    Caches the latest HTF bias update and provides fallback to neutral
    if cache has expired.
    
    Args:
        ttl_seconds: Time-to-live in seconds (default: 300 = 5 minutes)
    
    Example:
        >>> cache = HTFBiasCache(ttl_seconds=300)
        >>> cache.update(bias_message)
        >>> bias = cache.get()  # Returns bias or None if expired
        >>> bias_or_default = cache.get_or_default()  # Returns bias or neutral default
    """
    
    def __init__(self, ttl_seconds: int = 300) -> None:
        """Initialize bias cache with TTL.
        
        Args:
            ttl_seconds: Cache TTL in seconds (default: 300 = 5 minutes)
        """
        self._lock = threading.Lock()
        self._bias: HTFBiasMessage | None = None
        self._updated_at: datetime | None = None
        self._ttl_seconds = ttl_seconds
    
    def update(self, bias: HTFBiasMessage) -> None:
        """Update cache with new bias message.
        
        Args:
            bias: HTF bias message to cache
        """
        with self._lock:
            self._bias = bias
            self._updated_at = datetime.now(timezone.utc)
    
    def get(self) -> HTFBiasMessage | None:
        """Get cached bias if not expired.
        
        Returns:
            Cached bias message or None if expired/empty
        """
        with self._lock:
            if self._bias is None:
                return None
            
            if self._is_expired():
                return None
            
            return self._bias
    
    def get_or_default(self) -> HTFBiasMessage:
        """Get cached bias or neutral default if expired/empty.
        
        Returns:
            Cached bias message or neutral default
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
    
    def _is_expired(self) -> bool:
        """Check if cache has expired.
        
        Returns:
            True if expired, False otherwise
        """
        if self._updated_at is None:
            return True
        
        now = datetime.now(timezone.utc)
        age = (now - self._updated_at).total_seconds()
        return age > self._ttl_seconds
    
    def clear(self) -> None:
        """Clear cache."""
        with self._lock:
            self._bias = None
            self._updated_at = None
    
    @property
    def is_empty(self) -> bool:
        """Check if cache is empty.
        
        Returns:
            True if cache is empty
        """
        with self._lock:
            return self._bias is None
    
    @property
    def is_expired(self) -> bool:
        """Check if cache is expired.
        
        Returns:
            True if cache is expired or empty
        """
        with self._lock:
            return self._is_expired()
    
    @property
    def age_seconds(self) -> float | None:
        """Get cache age in seconds.
        
        Returns:
            Age in seconds or None if empty
        """
        with self._lock:
            if self._updated_at is None:
                return None
            
            now = datetime.now(timezone.utc)
            return (now - self._updated_at).total_seconds()

