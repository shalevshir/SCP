"""Trading session definitions and utilities.

Defines the trading sessions for Gold futures with their valid hours.
Sessions are defined in UTC and can be converted to any timezone.
"""

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

from scp_shared.common.logger import get_logger

logger = get_logger(__name__)


class TradingSession(Enum):
    """Trading session identifiers."""

    ASIA = "asia"
    LONDON = "london"
    NY = "ny"
    OFF_HOURS = "off_hours"
    MARKET_CLOSED = "market_closed"


@dataclass(frozen=True)
class SessionWindow:
    """Definition of a trading session window."""

    session: TradingSession
    start_utc: time  # Start time in UTC
    end_utc: time  # End time in UTC (exclusive)
    description: str
    tradeable: bool  # Whether signals should be executed during this session


# Session definitions in UTC
# Gold futures trade Sunday 6 PM ET - Friday 5 PM ET with daily 5-6 PM ET halt
# DXY trades Sunday 8 PM ET - Friday 5 PM ET with daily 5-8 PM ET halt
SESSION_WINDOWS: list[SessionWindow] = [
    # Asia session: 01:00-07:00 UTC (DXY reopens at 01:00 UTC after maintenance)
    SessionWindow(
        session=TradingSession.ASIA,
        start_utc=time(1, 0),  # After DXY reopens (8 PM ET = 01:00 UTC in winter)
        end_utc=time(7, 0),
        description="Asia/Tokyo session",
        tradeable=True,  # DXY available, correlation data present
    ),
    # London session: 07:00-12:00 UTC (London open 08:00 GMT, overlap with Asia ends)
    SessionWindow(
        session=TradingSession.LONDON,
        start_utc=time(7, 0),
        end_utc=time(12, 0),
        description="London session",
        tradeable=True,  # High liquidity, good for Gold
    ),
    # NY session: 12:00-21:00 UTC (US market hours, ends before maintenance)
    SessionWindow(
        session=TradingSession.NY,
        start_utc=time(12, 0),
        end_utc=time(21, 0),
        description="New York session",
        tradeable=True,  # Highest liquidity for Gold
    ),
    # Off-hours: 21:00-01:00 UTC (daily maintenance window for DXY: 5-8 PM ET)
    SessionWindow(
        session=TradingSession.OFF_HOURS,
        start_utc=time(21, 0),
        end_utc=time(1, 0),  # Wraps past midnight
        description="Off-hours (DXY maintenance)",
        tradeable=False,  # DXY closed, no correlation data
    ),
]

# Session encoding for Prometheus metrics
SESSION_ENCODING: dict[TradingSession, float] = {
    TradingSession.ASIA: 1.0,
    TradingSession.LONDON: 2.0,
    TradingSession.NY: 3.0,
    TradingSession.OFF_HOURS: 4.0,
    TradingSession.MARKET_CLOSED: 0.0,
}


def get_current_session(timestamp: datetime) -> TradingSession:
    """Determine the current trading session for a given timestamp.

    Args:
        timestamp: Timezone-aware datetime (preferably UTC)

    Returns:
        TradingSession enum value

    Raises:
        ValueError: If timestamp is not timezone-aware
    """
    if timestamp.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")

    # Convert to UTC for comparison
    utc_dt = timestamp.astimezone(ZoneInfo("UTC"))
    current_time = utc_dt.time()
    weekday = utc_dt.weekday()  # 0=Monday, 6=Sunday

    # Check for weekend closure
    # Friday 22:00 UTC (5 PM ET) to Sunday 23:00 UTC (6 PM ET)
    if weekday == 4 and current_time >= time(22, 0):  # Friday after 10 PM UTC
        return TradingSession.MARKET_CLOSED
    if weekday == 5:  # Saturday - fully closed
        return TradingSession.MARKET_CLOSED
    if weekday == 6 and current_time < time(23, 0):  # Sunday before 11 PM UTC
        return TradingSession.MARKET_CLOSED

    # Check each session window
    for window in SESSION_WINDOWS:
        if _time_in_window(current_time, window.start_utc, window.end_utc):
            return window.session

    # Fallback (shouldn't happen with properly defined windows)
    logger.warning(f"No session found for {utc_dt.isoformat()}, defaulting to OFF_HOURS")
    return TradingSession.OFF_HOURS


def is_session_tradeable(session: TradingSession) -> bool:
    """Check if the given session allows trade execution.

    Args:
        session: Trading session to check

    Returns:
        True if signals should be executed during this session
    """
    if session == TradingSession.MARKET_CLOSED:
        return False

    for window in SESSION_WINDOWS:
        if window.session == session:
            return window.tradeable

    return False


def get_session_info(session: TradingSession) -> SessionWindow | None:
    """Get the session window info for a given session.

    Args:
        session: Trading session

    Returns:
        SessionWindow if found, None otherwise
    """
    for window in SESSION_WINDOWS:
        if window.session == session:
            return window
    return None


def _time_in_window(current: time, start: time, end: time) -> bool:
    """Check if current time is within a time window.

    Handles windows that wrap past midnight (e.g., 21:00-01:00).

    Args:
        current: Current time to check
        start: Window start time
        end: Window end time

    Returns:
        True if current is within [start, end)
    """
    if start <= end:
        # Normal window (e.g., 07:00-12:00)
        return start <= current < end
    else:
        # Wrap-around window (e.g., 21:00-01:00)
        return current >= start or current < end


def format_session_for_display(
    session: TradingSession, timezone: str = "Asia/Jerusalem"
) -> str:
    """Format session info for display in dashboard.

    Args:
        session: Trading session
        timezone: Timezone for display (default: Israel)

    Returns:
        Human-readable session description
    """
    info = get_session_info(session)
    if info is None:
        if session == TradingSession.MARKET_CLOSED:
            return "MARKET CLOSED (Weekend)"
        return f"{session.value.upper()}"

    # Convert UTC times to display timezone
    tz = ZoneInfo(timezone)
    utc = ZoneInfo("UTC")

    # Create dummy datetimes to convert times
    dummy_date = datetime(2024, 1, 15)  # Monday
    start_utc = datetime.combine(dummy_date, info.start_utc, tzinfo=utc)
    end_utc = datetime.combine(dummy_date, info.end_utc, tzinfo=utc)

    start_local = start_utc.astimezone(tz).strftime("%H:%M")
    end_local = end_utc.astimezone(tz).strftime("%H:%M")

    tradeable_str = "✓ Tradeable" if info.tradeable else "✗ No Trading"

    return f"{session.value.upper()} ({start_local}-{end_local} ILT) - {tradeable_str}"
