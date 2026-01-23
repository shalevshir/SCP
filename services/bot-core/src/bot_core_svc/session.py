"""Session validation for Bot Core service."""

import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
        self._cached_timestamp: datetime | None = (
            None  # The timestamp that was validated
        )
        self._cached_at: datetime | None = None  # Real-time when cache was created
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
        # Check cache - must match timestamp and not be expired
        with self._lock:
            if (
                self._cached_result is not None
                and self._cached_timestamp is not None
                and self._is_cache_valid(timestamp)
            ):
                logger.debug(
                    f"Using cached session result for timestamp {timestamp.isoformat()}"
                )
                return self._cached_result

        # Validate
        result = self._validator.evaluate(timestamp)

        # Log session validation result for visibility (especially during replay)
        if result.session_ok:
            logger.debug(
                f"Session check PASS: {timestamp.isoformat()} | "
                f"window={result.constraints.window_start.strftime('%H:%M')}-"
                f"{result.constraints.window_end.strftime('%H:%M')} ILT"
            )
        else:
            logger.debug(
                f"Session check BLOCK: {timestamp.isoformat()} | "
                f"reason={result.reason} | "
                f"window={result.constraints.window_start.strftime('%H:%M')}-"
                f"{result.constraints.window_end.strftime('%H:%M')} ILT"
            )

        # Update cache
        with self._lock:
            self._cached_result = result
            self._cached_timestamp = timestamp
            self._cached_at = datetime.now(timezone.utc)

        return result

    def _is_cache_valid(self, timestamp: datetime) -> bool:
        """Check if cache is valid for the given timestamp.

        Cache is valid if:
        1. Cache exists (not None)
        2. Real-time TTL hasn't expired
        3. The new timestamp is in the same time window as the cached timestamp
           (same date and same hour, since session validation depends on date/time)

        Args:
            timestamp: Timestamp to validate against cache

        Returns:
            True if cache is valid for this timestamp, False otherwise
        """
        if self._cached_at is None or self._cached_timestamp is None:
            return False

        # Check real-time TTL expiration
        now = datetime.now(timezone.utc)
        age = (now - self._cached_at).total_seconds()
        if age > self._cache_ttl_seconds:
            return False

        # Check if timestamps are in the same time window
        # Session validation depends on date and time of day, so we need to ensure
        # both timestamps would evaluate to the same result
        tz = ZoneInfo(self._config.timezone)
        cached_local = self._cached_timestamp.astimezone(tz)
        new_local = timestamp.astimezone(tz)

        # Same date and same hour means they're in the same time window
        # (cache TTL is 60 seconds, so same hour is sufficient)
        if (
            cached_local.date() != new_local.date()
            or cached_local.hour != new_local.hour
        ):
            return False

        return True

    def clear_cache(self) -> None:
        """Clear cached session result."""
        with self._lock:
            self._cached_result = None
            self._cached_timestamp = None
            self._cached_at = None

        logger.debug("Session cache cleared")

    @property
    def config(self) -> SessionConfig:
        """Get session configuration.

        Returns:
            Session configuration
        """
        return self._config
