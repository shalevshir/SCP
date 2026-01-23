"""Active trade checker for Bot Core service.

This module provides a simple check to see if there are active trades,
matching the backtester behavior where signal generation is blocked
when an active trade exists.
"""

from scp_shared.common.logger import get_logger
from scp_shared.database import DatabasePool

logger = get_logger(__name__)


class ActiveTradeChecker:
    """Check for active trades in the database.

    This ensures Bot Core doesn't publish signals when there's already
    an active trade, matching the backtester behavior.

    Example:
        >>> checker = ActiveTradeChecker(db_pool, max_active=1)
        >>> if await checker.can_take_new_trade():
        ...     await publisher.publish(signal)
    """

    def __init__(
        self,
        db_pool: DatabasePool,
        max_active_trades: int = 1,
    ) -> None:
        """Initialize active trade checker.

        Args:
            db_pool: Database connection pool
            max_active_trades: Maximum concurrent trades allowed (default: 1)
        """
        self._db_pool = db_pool
        self._max_active_trades = max_active_trades

    async def get_active_trade_count(self) -> int:
        """Get count of active (open) trades.

        Returns:
            Number of trades with state='OPEN'
        """
        query = "SELECT COUNT(*) as count FROM trades WHERE state = 'OPEN'"
        row = await self._db_pool.fetchrow(query)
        return row["count"] if row else 0

    async def can_take_new_trade(self) -> tuple[bool, int]:
        """Check if a new trade can be opened.

        Returns:
            Tuple of (can_trade, active_count)
        """
        active_count = await self.get_active_trade_count()
        can_trade = active_count < self._max_active_trades

        if not can_trade:
            logger.debug(
                f"Active trade limit reached: {active_count}/{self._max_active_trades}"
            )

        return can_trade, active_count
