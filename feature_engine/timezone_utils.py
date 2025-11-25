"""Timezone utilities for VWAP session management.

This module provides timezone-aware session ID calculation for VWAP resets.
VWAP sessions reset at 08:20 AM Eastern Time (Regular Trading Hours open),
which is the institutional standard for Gold futures.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    import pandas as pd

# Constants
VWAP_RESET_TIME = time(8, 20, 0)  # 08:20:00
ET_TIMEZONE = ZoneInfo("America/New_York")  # Handles EST/EDT automatically


def get_vwap_session_id(timestamp: datetime) -> date:
    """Compute VWAP session ID for a given timestamp.

    VWAP sessions run from 08:20 ET to 08:19:59 ET the next day.
    This aligns with Regular Trading Hours (RTH) open for Gold futures,
    which is the institutional standard for intraday VWAP calculation.

    DST transitions are handled automatically by the America/New_York timezone.

    Args:
        timestamp: Timestamp to compute session ID for.
                  If timezone-naive, assumes UTC.

    Returns:
        date: Session identifier (date when session started at 08:20 ET).
              All bars from 08:20 ET on date D to 08:19:59 ET on date D+1
              will have session ID = D.

    Example:
        >>> from datetime import datetime
        >>> from zoneinfo import ZoneInfo
        >>> # Bar at 08:19 ET on Jan 15 belongs to Jan 14 session
        >>> ts1 = datetime(2025, 1, 15, 8, 19, tzinfo=ZoneInfo("America/New_York"))
        >>> get_vwap_session_id(ts1)
        datetime.date(2025, 1, 14)
        >>> # Bar at 08:20 ET on Jan 15 starts Jan 15 session
        >>> ts2 = datetime(2025, 1, 15, 8, 20, tzinfo=ZoneInfo("America/New_York"))
        >>> get_vwap_session_id(ts2)
        datetime.date(2025, 1, 15)

    Notes:
        - If timestamp is timezone-naive, it's assumed to be UTC
        - DST transitions are handled automatically (EST ↔ EDT)
        - First bar of dataset mid-session is handled correctly
    """
    # Convert timezone-naive timestamps to UTC
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))

    # Convert to Eastern Time
    et_timestamp = timestamp.astimezone(ET_TIMEZONE)

    # Get date and time in ET
    et_date = et_timestamp.date()
    et_time = et_timestamp.time()

    # If before 08:20 ET, belongs to previous day's session
    if et_time < VWAP_RESET_TIME:
        session_id = et_date - timedelta(days=1)
    else:
        session_id = et_date

    return session_id


def get_session_id_series(timestamps: list[datetime] | pd.Series) -> list[date]:
    """Compute VWAP session IDs for a series of timestamps.

    This is a convenience function for vectorized operations.

    Args:
        timestamps: List or pandas Series of datetime objects

    Returns:
        List of session IDs (dates)

    Example:
        >>> import pandas as pd
        >>> timestamps = pd.date_range('2025-01-15 06:00', periods=5, freq='2h', tz='UTC')
        >>> session_ids = get_session_id_series(timestamps)
    """
    return [get_vwap_session_id(ts) for ts in timestamps]

