"""Session Event Publisher - emits session open/close events to Redis.

This module publishes session boundary events (open/close) to notify downstream
services of market session changes for proper state management.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime

import redis.asyncio as redis
from scp_shared.common import get_logger
from scp_shared.messaging.schemas import CandleMessage

from data_adapter.session_filter import SessionFilter

logger = get_logger(__name__)


@dataclass
class SessionEvent:
    """Session event data structure."""

    event_type: str  # "session.opened" | "session.closed"
    timestamp: datetime
    session_date: date
    timezone: str


class SessionEventPublisher:
    """Publishes session open/close events to Redis stream.

    Detects session state transitions (open <-> closed) and publishes
    events to notify downstream services. Used for daily state resets
    and session-aware trading logic.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        stream: str = "session.events",
    ) -> None:
        """Initialize session event publisher.

        Args:
            redis_client: Redis client for publishing
            stream: Redis stream name (default: session.events)
        """
        self.redis_client = redis_client
        self.stream = stream
        self._last_state: bool | None = None  # True = open, False = closed

    async def check_and_emit(
        self,
        candle: CandleMessage,
        session_filter: SessionFilter,
    ) -> None:
        """Check for session state transitions and emit events.

        Detects when the market transitions between open and closed states,
        emitting appropriate events.

        Args:
            candle: Current candle to check
            session_filter: Session filter to determine if hours are valid
        """
        # Check current state
        is_open = session_filter.is_trading_hours(candle)

        # Initialize on first call
        if self._last_state is None:
            self._last_state = is_open
            if is_open:
                logger.info(f"Session initialized as OPEN at {candle.timestamp}")
            else:
                logger.info(f"Session initialized as CLOSED at {candle.timestamp}")
            return

        # Detect state transitions
        if is_open and not self._last_state:
            # Transition: closed -> open
            # Convert timestamp to session timezone to get correct session date
            local_dt = candle.timestamp.astimezone(session_filter.timezone)
            event = SessionEvent(
                event_type="session.opened",
                timestamp=candle.timestamp,
                session_date=local_dt.date(),
                timezone=str(session_filter.timezone),
            )
            await self._publish(event)
            logger.info(f"Session OPENED at {candle.timestamp}")

        elif not is_open and self._last_state:
            # Transition: open -> closed
            # Convert timestamp to session timezone to get correct session date
            local_dt = candle.timestamp.astimezone(session_filter.timezone)
            event = SessionEvent(
                event_type="session.closed",
                timestamp=candle.timestamp,
                session_date=local_dt.date(),
                timezone=str(session_filter.timezone),
            )
            await self._publish(event)
            logger.info(f"Session CLOSED at {candle.timestamp}")

        # Update state
        self._last_state = is_open

    async def _publish(self, event: SessionEvent) -> None:
        """Publish session event to Redis stream.

        Args:
            event: SessionEvent to publish
        """
        try:
            # Convert event to dict and publish
            event_dict = asdict(event)

            # Convert datetime objects to ISO strings for Redis
            event_dict["timestamp"] = event.timestamp.isoformat()
            event_dict["session_date"] = event.session_date.isoformat()

            # Publish to stream
            message_id = await self.redis_client.xadd(
                self.stream,
                event_dict,
            )

            logger.debug(f"Published {event.event_type} event: {message_id}")

        except Exception as e:
            logger.error(f"Error publishing session event: {e}", exc_info=True)
