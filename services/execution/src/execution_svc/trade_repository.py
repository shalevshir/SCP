"""Trade repository for database persistence."""

from datetime import datetime
from typing import Any
from uuid import UUID

from scp_shared.common.logger import get_logger
from scp_shared.database import DatabasePool
from scp_shared.execution.types import TradeRecord

logger = get_logger(__name__)


class TradeRepository:
    """Database repository for trade persistence.

    Handles CRUD operations for trades table and provides recovery methods.

    Example:
        >>> repo = TradeRepository(db_pool, point_value=100.0)
        >>> trade_id = await repo.insert_trade(trade_record)
        >>> await repo.update_trade(trade_id, {"exit_price": 2660.0})
        >>> open_trades = await repo.get_open_trades()
    """

    def __init__(self, db_pool: DatabasePool, point_value: float = 100.0) -> None:
        """Initialize trade repository.

        Args:
            db_pool: Database connection pool
            point_value: Dollar value per point for P&L calculation (default: $100 for GC)
        """
        self._db_pool = db_pool
        self._point_value = point_value

    async def insert_trade(
        self,
        signal_id: str,
        direction: str,
        setup_type: str,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        quantity: int,
        opened_at: datetime,
        entry_bar_idx: int | None = None,
    ) -> str:
        """Insert new trade record.

        Args:
            signal_id: Source signal ID
            direction: Trade direction ("long" or "short")
            setup_type: Setup type (e.g., "VWAP_RECLAIM")
            entry_price: Entry price
            sl_price: Stop loss price
            tp_price: Take profit price
            quantity: Number of contracts
            opened_at: Trade open timestamp
            entry_bar_idx: Bar index when trade was entered

        Returns:
            Trade ID (UUID string)
        """
        query = """
            INSERT INTO trades (
                signal_id, direction, setup_type, entry_price,
                sl_price, original_sl_price, tp_price, quantity, opened_at, entry_bar_idx, state
            )
            VALUES ($1, $2, $3, $4, $5, $5, $6, $7, $8, $9, 'OPEN')
            RETURNING id
        """

        # Convert signal_id string to UUID
        signal_uuid = UUID(signal_id)

        # NOTE: Both sl_price and original_sl_price are set to the same value initially.
        # The original_sl_price will never change (used for R-multiple calculation).
        # The sl_price may be updated to breakeven later (used for trade management).
        row = await self._db_pool.fetchrow(
            query,
            signal_uuid,
            direction,
            setup_type,
            entry_price,
            sl_price,  # Used for both sl_price and original_sl_price
            tp_price,
            quantity,
            opened_at,
            entry_bar_idx,
        )

        trade_id = str(row["id"]) if row else None
        if trade_id is None:
            raise ValueError(f"Failed to insert trade: {row} signal_id: {signal_uuid}")

        logger.info(
            f"Inserted trade {trade_id}: {direction} {setup_type} @ {entry_price:.2f}"
        )

        return trade_id

    async def update_trade(
        self,
        trade_id: str,
        updates: dict[str, Any],
    ) -> None:
        """Update trade record.

        Args:
            trade_id: Trade ID
            updates: Dictionary of fields to update
        """
        # Build dynamic UPDATE query
        set_clauses = []
        values = []
        param_idx = 1

        for key, value in updates.items():
            set_clauses.append(f"{key} = ${param_idx}")
            values.append(value)
            param_idx += 1

        # Add trade_id as last parameter
        values.append(UUID(trade_id))

        query = f"""
            UPDATE trades
            SET {', '.join(set_clauses)}
            WHERE id = ${param_idx}
        """

        await self._db_pool.execute(query, *values)

        logger.debug(f"Updated trade {trade_id}: {list(updates.keys())}")

    async def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        closed_at: datetime,
    ) -> None:
        """Close trade with exit details.

        Args:
            trade_id: Trade ID
            exit_price: Exit price
            exit_reason: Exit reason (e.g., "TP_HIT", "SL_HIT")
            closed_at: Trade close timestamp
        """
        # Get trade data including quantity for P&L calculation
        # CRITICAL: Use original_sl_price for R-multiple (never changes)
        # sl_price may have been updated to breakeven, which corrupts R calculation
        query = """
            SELECT direction, entry_price, sl_price, original_sl_price, quantity
            FROM trades
            WHERE id = $1
        """
        row = await self._db_pool.fetchrow(query, UUID(trade_id))
        if row is None:
            error_msg = f"Trade {trade_id} not found"
            logger.error(f"Cannot close trade: {error_msg}")
            raise ValueError(error_msg)

        # Calculate P&L (convert Decimal to float for arithmetic)
        entry_price_float = float(row["entry_price"])
        direction = row["direction"]
        quantity = row["quantity"]

        if direction == "long":
            pnl_points = exit_price - entry_price_float
        else:  # short
            pnl_points = entry_price_float - exit_price

        # Calculate P&L in dollars: points * point_value * quantity
        # For GC futures: point_value = $100 per point
        pnl_dollars = pnl_points * self._point_value * quantity

        # CRITICAL: Calculate R-multiple using original_sl_price (not current sl_price)
        # After breakeven is set, sl_price changes but original_sl_price remains constant
        original_sl_float = float(row["original_sl_price"])
        if direction == "long":
            risk_amount = entry_price_float - original_sl_float
        else:  # short
            risk_amount = original_sl_float - entry_price_float
        r_multiple = pnl_points / risk_amount if risk_amount > 0 else 0.0

        # Determine state
        state = "CLOSED"
        if "SL" in exit_reason:
            state = "CLOSED"  # Stopped out is still closed

        # Truncate exit_reason to fit VARCHAR(30) column
        exit_reason_truncated = (
            exit_reason[:30] if len(exit_reason) > 30 else exit_reason
        )

        # Update trade
        query = """
            UPDATE trades
            SET closed_at = $1,
                exit_price = $2,
                exit_reason = $3,
                pnl_points = $4,
                pnl_dollars = $5,
                r_multiple = $6,
                state = $7
            WHERE id = $8
        """

        await self._db_pool.execute(
            query,
            closed_at,
            exit_price,
            exit_reason_truncated,
            pnl_points,
            pnl_dollars,
            r_multiple,
            state,
            UUID(trade_id),
        )

        logger.info(
            f"Closed trade {trade_id}: exit={exit_price:.2f}, "
            f"pnl={pnl_points:.2f} points (${pnl_dollars:.2f}, {r_multiple:.2f}R), "
            f"reason={exit_reason}"
        )

    async def get_trade(self, trade_id: str) -> TradeRecord | None:
        """Get trade by ID.

        Args:
            trade_id: Trade ID

        Returns:
            TradeRecord if found, None otherwise
        """
        query = """
            SELECT id, signal_id, direction, setup_type, entry_price,
                   sl_price, tp_price, quantity, opened_at, closed_at,
                   exit_price, exit_reason, pnl_points, entry_bar_idx, reached_1r
            FROM trades
            WHERE id = $1
        """

        row = await self._db_pool.fetchrow(query, UUID(trade_id))

        if row is None:
            return None

        # Calculate risk_amount and reward_amount
        if row["direction"] == "long":
            risk_amount = row["entry_price"] - row["sl_price"]
            reward_amount = row["tp_price"] - row["entry_price"]
        else:  # short
            risk_amount = row["sl_price"] - row["entry_price"]
            reward_amount = row["entry_price"] - row["tp_price"]

        return TradeRecord(
            trade_id=str(row["id"]),
            signal_id=str(row["signal_id"]),
            symbol="GC",  # Hardcoded for Phase 6
            direction=row["direction"],
            setup_type=row["setup_type"],
            entry_price=row["entry_price"],
            sl_price=row["sl_price"],
            tp_price=row["tp_price"],
            quantity=row["quantity"],
            risk_amount=risk_amount,
            reward_amount=reward_amount,
            entry_timestamp=row["opened_at"],
            exit_timestamp=row["closed_at"],
            exit_price=row["exit_price"],
            exit_reason=row["exit_reason"],
            pnl=row["pnl_points"],
            entry_bar_idx=row["entry_bar_idx"],
            reached_1r=row["reached_1r"] or False,
        )

    async def get_open_trades(self) -> list[TradeRecord]:
        """Get all open trades.

        Returns:
            List of open trade records
        """
        query = """
            SELECT id, signal_id, direction, setup_type, entry_price,
                   sl_price, tp_price, quantity, opened_at, entry_bar_idx, reached_1r
            FROM trades
            WHERE state = 'OPEN'
            ORDER BY opened_at ASC
        """

        rows = await self._db_pool.fetch(query)

        trades = []
        for row in rows:
            # Calculate risk_amount and reward_amount
            if row["direction"] == "long":
                risk_amount = row["entry_price"] - row["sl_price"]
                reward_amount = row["tp_price"] - row["entry_price"]
            else:  # short
                risk_amount = row["sl_price"] - row["entry_price"]
                reward_amount = row["entry_price"] - row["tp_price"]

            trade = TradeRecord(
                trade_id=str(row["id"]),
                signal_id=str(row["signal_id"]),
                symbol="GC",  # Hardcoded for Phase 6
                direction=row["direction"],
                setup_type=row["setup_type"],
                entry_price=row["entry_price"],
                sl_price=row["sl_price"],
                tp_price=row["tp_price"],
                quantity=row["quantity"],
                risk_amount=risk_amount,
                reward_amount=reward_amount,
                entry_timestamp=row["opened_at"],
                entry_bar_idx=row["entry_bar_idx"],
                reached_1r=row["reached_1r"] or False,
            )
            trades.append(trade)

        return trades

    async def update_reached_1r(self, trade_id: str, reached_1r: bool = True) -> None:
        """Update reached_1r status for a trade.

        Args:
            trade_id: Trade ID
            reached_1r: Whether trade has reached +1R
        """
        query = """
            UPDATE trades
            SET reached_1r = $1
            WHERE id = $2
        """

        await self._db_pool.execute(query, reached_1r, UUID(trade_id))

        logger.debug(f"Updated trade {trade_id} reached_1r={reached_1r}")

    async def update_breakeven(self, trade_id: str, be_price: float) -> None:
        """Update current SL price to breakeven.

        NOTE: This updates sl_price (current stop), NOT original_sl_price.
        The original_sl_price is preserved for R-multiple calculation.

        Args:
            trade_id: Trade ID
            be_price: Breakeven stop loss price (entry ± 0.1R buffer)
        """
        query = """
            UPDATE trades
            SET sl_price = $1
            WHERE id = $2
        """

        await self._db_pool.execute(query, be_price, UUID(trade_id))

        logger.info(f"Updated trade {trade_id} SL to BE: {be_price:.2f}")

    async def update_quantity(self, trade_id: str, new_quantity: int) -> None:
        """Update trade quantity after partial close.

        This is called after successfully reducing a position via the broker.
        The quantity must be updated to ensure correct P&L calculations when
        the remaining position is closed.

        Args:
            trade_id: Trade ID
            new_quantity: New quantity after reduction (must be > 0)

        Raises:
            ValueError: If new_quantity is <= 0
        """
        if new_quantity <= 0:
            raise ValueError(
                f"Invalid quantity {new_quantity}: must be greater than 0"
            )

        query = """
            UPDATE trades
            SET quantity = $1
            WHERE id = $2
        """

        await self._db_pool.execute(query, new_quantity, UUID(trade_id))

        logger.info(
            f"Updated trade {trade_id} quantity to {new_quantity} contracts"
        )

    async def reconcile_positions(self) -> list[TradeRecord]:
        """Reconcile open trades on startup (for recovery).

        Returns:
            List of open trades that need position reconciliation
        """
        open_trades = await self.get_open_trades()

        logger.info(f"Reconciled {len(open_trades)} open trades on startup")

        return open_trades

    async def get_trades_for_date(self, trade_date: datetime) -> list[TradeRecord]:
        """Get all trades (open and closed) for a specific trading date.

        Used for restoring daily state (P&L and trade count) after service restart.

        Args:
            trade_date: Trading date to query trades for

        Returns:
            List of all trades opened on the specified date
        """
        query = """
            SELECT id, signal_id, direction, setup_type, entry_price,
                   sl_price, tp_price, quantity, opened_at, closed_at,
                   exit_price, exit_reason, pnl_points, entry_bar_idx, reached_1r
            FROM trades
            WHERE DATE(opened_at) = DATE($1)
            ORDER BY opened_at ASC
        """

        rows = await self._db_pool.fetch(query, trade_date)

        trades = []
        for row in rows:
            # Calculate risk_amount and reward_amount
            if row["direction"] == "long":
                risk_amount = row["entry_price"] - row["sl_price"]
                reward_amount = row["tp_price"] - row["entry_price"]
            else:  # short
                risk_amount = row["sl_price"] - row["entry_price"]
                reward_amount = row["entry_price"] - row["tp_price"]

            trade = TradeRecord(
                trade_id=str(row["id"]),
                signal_id=str(row["signal_id"]),
                symbol="GC",  # Hardcoded for Phase 6
                direction=row["direction"],
                setup_type=row["setup_type"],
                entry_price=row["entry_price"],
                sl_price=row["sl_price"],
                tp_price=row["tp_price"],
                quantity=row["quantity"],
                risk_amount=risk_amount,
                reward_amount=reward_amount,
                entry_timestamp=row["opened_at"],
                exit_timestamp=row["closed_at"],
                exit_price=row["exit_price"],
                exit_reason=row["exit_reason"],
                pnl=row["pnl_points"],
                entry_bar_idx=row["entry_bar_idx"],
                reached_1r=row["reached_1r"] or False,
            )
            trades.append(trade)

        logger.debug(f"Retrieved {len(trades)} trades for date {trade_date.date()}")

        return trades
