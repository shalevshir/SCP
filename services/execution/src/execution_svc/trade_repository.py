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
        >>> repo = TradeRepository(db_pool)
        >>> trade_id = await repo.insert_trade(trade_record)
        >>> await repo.update_trade(trade_id, {"exit_price": 2660.0})
        >>> open_trades = await repo.get_open_trades()
    """
    
    def __init__(self, db_pool: DatabasePool) -> None:
        """Initialize trade repository.
        
        Args:
            db_pool: Database connection pool
        """
        self._db_pool = db_pool
    
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
            
        Returns:
            Trade ID (UUID string)
        """
        query = """
            INSERT INTO trades (
                signal_id, direction, setup_type, entry_price,
                sl_price, tp_price, quantity, opened_at, state
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'OPEN')
            RETURNING id
        """
        
        # Convert signal_id string to UUID
        signal_uuid = UUID(signal_id)
        
        row = await self._db_pool.fetch_one(
            query,
            signal_uuid,
            direction,
            setup_type,
            entry_price,
            sl_price,
            tp_price,
            quantity,
            opened_at,
        )
        
        trade_id = str(row["id"])
        
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
        # Get trade to calculate P&L
        trade = await self.get_trade(trade_id)
        if trade is None:
            logger.error(f"Cannot close trade {trade_id}: not found")
            return
        
        # Calculate P&L
        if trade.direction == "long":
            pnl_points = exit_price - trade.entry_price
        else:  # short
            pnl_points = trade.entry_price - exit_price
        
        # Calculate R-multiple
        r_multiple = pnl_points / trade.risk_amount if trade.risk_amount > 0 else 0.0
        
        # Determine state
        state = "CLOSED"
        if "SL" in exit_reason:
            state = "CLOSED"  # Stopped out is still closed
        
        # Update trade
        query = """
            UPDATE trades
            SET closed_at = $1,
                exit_price = $2,
                exit_reason = $3,
                pnl_points = $4,
                r_multiple = $5,
                state = $6
            WHERE id = $7
        """
        
        await self._db_pool.execute(
            query,
            closed_at,
            exit_price,
            exit_reason,
            pnl_points,
            r_multiple,
            state,
            UUID(trade_id),
        )
        
        logger.info(
            f"Closed trade {trade_id}: exit={exit_price:.2f}, "
            f"pnl={pnl_points:.2f} points ({r_multiple:.2f}R), reason={exit_reason}"
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
                   exit_price, exit_reason, pnl_points
            FROM trades
            WHERE id = $1
        """
        
        row = await self._db_pool.fetch_one(query, UUID(trade_id))
        
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
            symbol="GC",  # Hardcoded for Phase 6
            direction=row["direction"],
            setup_type=row["setup_type"],
            entry_price=row["entry_price"],
            sl_price=row["sl_price"],
            tp_price=row["tp_price"],
            risk_amount=risk_amount,
            reward_amount=reward_amount,
            entry_timestamp=row["opened_at"],
            exit_timestamp=row["closed_at"],
            exit_price=row["exit_price"],
            exit_reason=row["exit_reason"],
            pnl=row["pnl_points"],
        )
    
    async def get_open_trades(self) -> list[TradeRecord]:
        """Get all open trades.
        
        Returns:
            List of open trade records
        """
        query = """
            SELECT id, signal_id, direction, setup_type, entry_price,
                   sl_price, tp_price, quantity, opened_at
            FROM trades
            WHERE state = 'OPEN'
            ORDER BY opened_at ASC
        """
        
        rows = await self._db_pool.fetch_all(query)
        
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
                symbol="GC",  # Hardcoded for Phase 6
                direction=row["direction"],
                setup_type=row["setup_type"],
                entry_price=row["entry_price"],
                sl_price=row["sl_price"],
                tp_price=row["tp_price"],
                risk_amount=risk_amount,
                reward_amount=reward_amount,
                entry_timestamp=row["opened_at"],
            )
            trades.append(trade)
        
        return trades
    
    async def reconcile_positions(self) -> list[TradeRecord]:
        """Reconcile open trades on startup (for recovery).
        
        Returns:
            List of open trades that need position reconciliation
        """
        open_trades = await self.get_open_trades()
        
        logger.info(f"Reconciled {len(open_trades)} open trades on startup")
        
        return open_trades


