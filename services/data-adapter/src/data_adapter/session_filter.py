"""Session Filter - wrapper for session hour validation.

This module provides a simple wrapper around the validation layer's
SessionValidator for use in the Data Adapter service.
"""

from datetime import time
from zoneinfo import ZoneInfo

from scp_shared.messaging.schemas import CandleMessage


class SessionFilter:
    """Simple session hour filter for Data Adapter.

    Provides basic time-of-day filtering without full SOP validation.
    For production use, can be integrated with validation.SessionValidator.
    """

    def __init__(
        self,
        window_start: time = time(0, 0),
        window_end: time = time(23, 59),
        timezone: str = "UTC",
        enabled: bool = True,
        check_weekends: bool = False,
    ) -> None:
        """Initialize session filter.

        Args:
            window_start: Start of trading window (inclusive)
            window_end: End of trading window (exclusive)
            timezone: Timezone for window (default: UTC)
            enabled: Whether filtering is enabled (default: True)
            check_weekends: Whether to reject weekends (default: False)
        """
        self.window_start = window_start
        self.window_end = window_end
        self.timezone = ZoneInfo(timezone)
        self.enabled = enabled
        self.check_weekends = check_weekends

    def is_trading_hours(self, candle: CandleMessage) -> bool:
        """Check if candle timestamp is within trading hours.

        Args:
            candle: Candle to check

        Returns:
            True if within trading hours, False otherwise
        """
        # If filtering disabled, allow all
        if not self.enabled:
            return True

        # Convert to configured timezone
        local_dt = candle.timestamp.astimezone(self.timezone)

        # Check weekend
        if self.check_weekends:
            # Saturday = 5, Sunday = 6
            if local_dt.weekday() >= 5:
                return False

        # Check time window
        current_time = local_dt.time()

        # Handle normal window (start < end)
        if self.window_start <= self.window_end:
            return self.window_start <= current_time < self.window_end

        # Handle wrap-around window (e.g., 22:00 - 02:00)
        return current_time >= self.window_start or current_time < self.window_end


class GoldFuturesSessionFilter(SessionFilter):
    """Session filter configured for Gold futures (GC) market hours.

    Gold futures trade:
    - Sunday 6:00 PM ET to Friday 5:00 PM ET
    - Daily maintenance break: 5:00 PM - 6:00 PM ET (Monday-Thursday)

    This filter accounts for weekend closures and daily maintenance windows.
    """

    def __init__(self, enabled: bool = True) -> None:
        """Initialize Gold futures session filter.

        Args:
            enabled: Whether filtering is enabled (default: True)
        """
        # Initialize parent with ET timezone
        # Note: window_start/end are not directly used since we have custom logic
        super().__init__(
            window_start=time(18, 0),  # 6 PM ET
            window_end=time(17, 0),  # 5 PM ET (wraps around)
            timezone="America/New_York",
            enabled=enabled,
            check_weekends=True,
        )

    def is_trading_hours(self, candle: CandleMessage) -> bool:
        """Check if candle timestamp is within Gold futures trading hours.

        Args:
            candle: Candle to check

        Returns:
            True if within trading hours, False otherwise
        """
        # If filtering disabled, allow all
        if not self.enabled:
            return True

        # Convert to ET timezone
        local_dt = candle.timestamp.astimezone(self.timezone)
        weekday = local_dt.weekday()  # 0=Monday, 6=Sunday
        current_time = local_dt.time()

        # Weekend close: Friday 5 PM to Sunday 6 PM
        if weekday == 4 and current_time >= time(17, 0):  # Friday after 5 PM
            return False
        if weekday == 5:  # Saturday - fully closed
            return False
        if weekday == 6 and current_time < time(18, 0):  # Sunday before 6 PM
            return False

        # Daily maintenance break: 5 PM - 6 PM (Monday-Thursday)
        # Weekday 0-3 = Monday-Thursday
        if weekday < 4 and time(17, 0) <= current_time < time(18, 0):
            return False

        # All other times are valid trading hours
        return True
