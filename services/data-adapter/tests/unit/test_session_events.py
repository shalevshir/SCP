"""Tests for SessionEventPublisher - session boundary event publishing."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from scp_shared.messaging.schemas import CandleMessage

from data_adapter.session_events import SessionEvent, SessionEventPublisher
from data_adapter.session_filter import GoldFuturesSessionFilter


class TestSessionEventPublisher:
    """Test suite for SessionEventPublisher."""

    @pytest.mark.asyncio
    async def test_session_date_uses_timezone_not_utc(self) -> None:
        """Session date should be in session timezone, not UTC.

        Example: 1:00 AM UTC on Jan 14 = 8:00 PM ET on Jan 13
        Session date should be Jan 13, not Jan 14.
        """
        mock_redis = AsyncMock()
        publisher = SessionEventPublisher(mock_redis)
        session_filter = GoldFuturesSessionFilter(enabled=True)

        # 1:00 AM UTC on January 14 = 8:00 PM ET on January 13 (standard time)
        # This is during trading hours (Sunday 6 PM ET to Friday 5 PM ET)
        candle_utc = CandleMessage(
            timestamp=datetime(
                2025, 1, 14, 1, 0, tzinfo=UTC
            ),  # 1 AM UTC = 8 PM ET Jan 13
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Initialize state (first call)
        await publisher.check_and_emit(candle_utc, session_filter)

        # Simulate transition from closed to open
        publisher._last_state = False  # Was closed
        await publisher.check_and_emit(candle_utc, session_filter)

        # Verify event was published
        assert mock_redis.xadd.called

        # Get the event data that was published
        # xadd is called as: xadd(stream_name, event_dict)
        call_args = mock_redis.xadd.call_args
        event_dict = call_args[0][1]  # Second positional argument

        # Verify session_date is Jan 13 (ET date), not Jan 14 (UTC date)
        assert event_dict["session_date"] == "2025-01-13"
        assert event_dict["event_type"] == "session.opened"
        assert event_dict["timezone"] == "America/New_York"

    @pytest.mark.asyncio
    async def test_session_date_handles_daylight_saving_time(self) -> None:
        """Session date correctly handles DST transitions."""
        mock_redis = AsyncMock()
        publisher = SessionEventPublisher(mock_redis)
        session_filter = GoldFuturesSessionFilter(enabled=True)

        # July (daylight time): 1:00 AM UTC = 9:00 PM ET previous day
        candle_dst = CandleMessage(
            timestamp=datetime(
                2025, 7, 15, 1, 0, tzinfo=UTC
            ),  # 1 AM UTC = 9 PM ET Jul 14
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Initialize state
        await publisher.check_and_emit(candle_dst, session_filter)

        # Simulate transition
        publisher._last_state = False
        await publisher.check_and_emit(candle_dst, session_filter)

        # Verify session_date is July 14 (ET date in DST)
        call_args = mock_redis.xadd.call_args
        event_dict = call_args[0][1]  # Second positional argument
        assert event_dict["session_date"] == "2025-07-14"

    @pytest.mark.asyncio
    async def test_session_closed_event_uses_timezone(self) -> None:
        """Session closed event also uses timezone for session_date."""
        mock_redis = AsyncMock()
        publisher = SessionEventPublisher(mock_redis)
        session_filter = GoldFuturesSessionFilter(enabled=True)

        # Friday 5:30 PM ET = 10:30 PM UTC (standard time, but Jan 17 is a Friday)
        # Actually, let's use a time that's clearly after market close
        # Friday 5:30 PM ET = 22:30 UTC (standard time) or 21:30 UTC (daylight time)
        # Using standard time: Jan 17, 2025 is a Friday, 5:30 PM ET = 22:30 UTC
        candle_close = CandleMessage(
            timestamp=datetime(
                2025, 1, 17, 22, 30, tzinfo=UTC
            ),  # 5:30 PM ET Jan 17 (standard time)
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Initialize state as open
        publisher._last_state = True
        await publisher.check_and_emit(candle_close, session_filter)

        # Verify event was published
        assert mock_redis.xadd.called

        # Verify session_date is Jan 17 (ET date)
        call_args = mock_redis.xadd.call_args
        event_dict = call_args[0][1]  # Second positional argument
        assert event_dict["session_date"] == "2025-01-17"
        assert event_dict["event_type"] == "session.closed"

    @pytest.mark.asyncio
    async def test_no_event_on_first_call(self) -> None:
        """First call initializes state but doesn't emit event."""
        mock_redis = AsyncMock()
        publisher = SessionEventPublisher(mock_redis)
        session_filter = GoldFuturesSessionFilter(enabled=True)

        candle = CandleMessage(
            timestamp=datetime(2025, 1, 14, 15, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # First call - should initialize but not emit
        await publisher.check_and_emit(candle, session_filter)

        # No event should be published
        assert not mock_redis.xadd.called

    @pytest.mark.asyncio
    async def test_no_event_on_no_state_change(self) -> None:
        """No event emitted when state doesn't change."""
        mock_redis = AsyncMock()
        publisher = SessionEventPublisher(mock_redis)
        session_filter = GoldFuturesSessionFilter(enabled=True)

        candle = CandleMessage(
            timestamp=datetime(2025, 1, 14, 15, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Initialize
        publisher._last_state = True

        # Call again with same state - no transition
        await publisher.check_and_emit(candle, session_filter)

        # No event should be published
        assert not mock_redis.xadd.called
