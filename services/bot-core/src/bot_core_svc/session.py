"""Session validation for Bot Core service."""

import threading
from datetime import datetime, timedelta, timezone

from scp_shared.common.logger import get_logger
from scp_shared.validation import (
    SessionConfig,
    SessionConstraints,
    SessionResult,
    SessionValidator,
    load_session_config,
)

logger = get_logger(__name__)


class SessionValidationService:
    """Session validation with caching.
    
    Loads session configuration and validates timestamps against trading windows.
    Results are cached with 1-minute TTL to avoid repeated validation.
    
    Args:
        config_path: Optional path to validation config file
        cache_ttl_seconds: Cache TTL in seconds (default: 60)
    
    Example:
        >>> service = SessionValidationService()
        >>> result = service.evaluate(datetime.now(timezone.utc))
        >>> if result.session_ok:
        ...     print(f"Session allowed: {result.constraints.name}")
    """
    
    def __init__(
        self,
        config_path: str | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        """Initialize session validation service.
        
        Args:
            config_path: Optional path to validation config file
            cache_ttl_seconds: Cache TTL in seconds (default: 60)
        """
        # Load session configuration
        self._config = load_session_config(config_path)
        self._validator = SessionValidator(self._config)
        
        # Cache setup
        self._lock = threading.Lock()
        self._cached_result: SessionResult | None = None
        self._cached_at: datetime | None = None
        self._cache_ttl_seconds = cache_ttl_seconds
        
        logger.info(
            f"Session validation service initialized with timezone: {self._config.timezone}"
        )
    
    def evaluate(self, timestamp: datetime) -> SessionResult:
        """Evaluate timestamp against session rules.
        
        Args:
            timestamp: Timestamp to evaluate (should be UTC)
            
        Returns:
            SessionResult with session_ok flag and constraints
        """
        # Check cache
        with self._lock:
            if self._cached_result is not None and not self._is_cache_expired():
                logger.debug("Using cached session result")
                return self._cached_result
        
        # Validate
        result = self._validator.evaluate(timestamp)
        
        # Update cache
        with self._lock:
            self._cached_result = result
            self._cached_at = datetime.now(timezone.utc)
        
        return result
    
    def _is_cache_expired(self) -> bool:
        """Check if cache has expired.
        
        Returns:
            True if expired, False otherwise
        """
        if self._cached_at is None:
            return True
        
        now = datetime.now(timezone.utc)
        age = (now - self._cached_at).total_seconds()
        return age > self._cache_ttl_seconds
    
    def clear_cache(self) -> None:
        """Clear cached session result."""
        with self._lock:
            self._cached_result = None
            self._cached_at = None
        
        logger.debug("Session cache cleared")
    
    @property
    def config(self) -> SessionConfig:
        """Get session configuration.
        
        Returns:
            Session configuration
        """
        return self._config

