"""Repository pattern implementations for common queries."""

from datetime import datetime
from typing import Any

import asyncpg

from scp_shared.database.connection import DatabasePool


class CandleRepository:
    """Repository for candle data queries."""

    def __init__(self, db_pool: DatabasePool) -> None:
        """Initialize repository.

        Args:
            db_pool: Database connection pool
        """
        self.db = db_pool

    async def insert_candle(
        self,
        timestamp: datetime,
        symbol: str,
        timeframe: str,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> None:
        """Insert a candle into the database.

        Args:
            timestamp: Candle timestamp
            symbol: Asset symbol
            timeframe: Timeframe string
            open_price: Opening price
            high: High price
            low: Low price
            close: Closing price
            volume: Volume
        """
        query = """
            INSERT INTO candles (
                timestamp, symbol, timeframe, open, high, low, close, volume
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (timestamp, symbol, timeframe) DO NOTHING
        """
        await self.db.execute(
            query, timestamp, symbol, timeframe, open_price, high, low, close, volume
        )

    async def get_recent_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[asyncpg.Record]:
        """Get recent candles for warmup.

        Args:
            symbol: Asset symbol
            timeframe: Timeframe string
            limit: Number of candles to retrieve

        Returns:
            List of candle records
        """
        query = """
            SELECT timestamp, symbol, timeframe, open, high, low, close, volume
            FROM candles
            WHERE symbol = $1 AND timeframe = $2
            ORDER BY timestamp DESC
            LIMIT $3
        """
        return await self.db.fetch(query, symbol, timeframe, limit)

    async def get_candle_by_timestamp(
        self,
        timestamp: datetime,
        symbol: str,
        timeframe: str,
    ) -> asyncpg.Record | None:
        """Get a candle by exact timestamp.

        Args:
            timestamp: Candle timestamp
            symbol: Asset symbol
            timeframe: Timeframe string

        Returns:
            Candle record if found, None otherwise
        """
        query = """
            SELECT timestamp, symbol, timeframe, open, high, low, close, volume
            FROM candles
            WHERE timestamp = $1 AND symbol = $2 AND timeframe = $3
        """
        return await self.db.fetchrow(query, timestamp, symbol, timeframe)


class TradeRepository:
    """Repository for trade data queries."""

    def __init__(self, db_pool: DatabasePool) -> None:
        """Initialize repository.

        Args:
            db_pool: Database connection pool
        """
        self.db = db_pool

    async def insert_trade(self, trade_data: dict[str, Any]) -> str:
        """Insert a new trade.

        Args:
            trade_data: Trade data dictionary

        Returns:
            Trade ID
        """
        query = """
            INSERT INTO trades (
                signal_id, direction, setup_type, entry_price, sl_price, tp_price,
                quantity, opened_at, confirmations, state
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
        """
        trade_id = await self.db.fetchval(
            query,
            trade_data["signal_id"],
            trade_data["direction"],
            trade_data["setup_type"],
            trade_data["entry_price"],
            trade_data["sl_price"],
            trade_data["tp_price"],
            trade_data["quantity"],
            trade_data["opened_at"],
            trade_data.get("confirmations"),
            "OPEN",
        )
        return str(trade_id)

    async def get_open_trades(self) -> list[asyncpg.Record]:
        """Get all open trades.

        Returns:
            List of open trade records
        """
        query = """
            SELECT * FROM trades
            WHERE state = 'OPEN'
            ORDER BY opened_at DESC
        """
        return await self.db.fetch(query)

    async def close_trade(
        self,
        trade_id: str,
        closed_at: datetime,
        exit_price: float,
        exit_reason: str,
        pnl_points: float,
        pnl_dollars: float,
    ) -> None:
        """Close a trade.

        Args:
            trade_id: Trade ID
            closed_at: Close timestamp
            exit_price: Exit price
            exit_reason: Reason for exit
            pnl_points: P&L in points
            pnl_dollars: P&L in dollars
        """
        query = """
            UPDATE trades
            SET closed_at = $2, exit_price = $3, exit_reason = $4,
                pnl_points = $5, pnl_dollars = $6, state = 'CLOSED'
            WHERE id = $1
        """
        await self.db.execute(
            query, trade_id, closed_at, exit_price, exit_reason, pnl_points, pnl_dollars
        )
