"""Daily state repository for Bot Core service."""

from dataclasses import dataclass
from datetime import date, datetime, timezone

from scp_shared.common.logger import get_logger
from scp_shared.database import DatabasePool

logger = get_logger(__name__)


@dataclass
class DailyState:
    """Daily trading state.
    
    Attributes:
        date: Trading date
        loss_streak: Consecutive losses
        daily_loss: Total P&L loss for the day
        trades_count: Number of trades executed
        wins: Number of winning trades
        losses: Number of losing trades
        pdll_hits: Number of times PDLL was hit
    """
    
    date: date
    loss_streak: int = 0
    daily_loss: float = 0.0
    trades_count: int = 0
    wins: int = 0
    losses: int = 0
    pdll_hits: int = 0


class StateRepository:
    """Repository for persisting daily state.
    
    Handles loading and saving daily trading state to/from the database.
    
    Args:
        db_pool: Database connection pool
    
    Example:
        >>> repo = StateRepository(db_pool)
        >>> state = await repo.load_today()
        >>> state.trades_count += 1
        >>> await repo.save(state)
    """
    
    def __init__(self, db_pool: DatabasePool) -> None:
        """Initialize state repository.
        
        Args:
            db_pool: Database connection pool
        """
        self._db_pool = db_pool
    
    async def load_today(self) -> DailyState:
        """Load today's state from database.
        
        If no record exists for today, returns a fresh state.
        
        Returns:
            Daily state for today
        """
        today = date.today()
        return await self.load(today)
    
    async def load(self, trading_date: date) -> DailyState:
        """Load state for a specific date.
        
        Args:
            trading_date: Date to load state for
            
        Returns:
            Daily state for the date
        """
        query = """
            SELECT date, loss_streak, daily_loss, trades_count, wins, losses, pdll_hits
            FROM daily_state
            WHERE date = $1
        """
        
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(query, trading_date)
            
            if row is None:
                logger.info(f"No state found for {trading_date}, returning fresh state")
                return DailyState(date=trading_date)
            
            state = DailyState(
                date=row["date"],
                loss_streak=row["loss_streak"],
                daily_loss=float(row["daily_loss"]),
                trades_count=row["trades_count"],
                wins=row["wins"],
                losses=row["losses"],
                pdll_hits=row["pdll_hits"],
            )
            
            logger.info(
                f"Loaded state for {trading_date}: "
                f"loss_streak={state.loss_streak}, "
                f"trades_count={state.trades_count}, "
                f"daily_loss={state.daily_loss:.2f}"
            )
            
            return state
    
    async def save(self, state: DailyState) -> None:
        """Save state to database.
        
        Uses INSERT ... ON CONFLICT to upsert the state.
        
        Args:
            state: Daily state to save
        """
        query = """
            INSERT INTO daily_state (
                date, loss_streak, daily_loss, trades_count, wins, losses, pdll_hits
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (date) DO UPDATE SET
                loss_streak = EXCLUDED.loss_streak,
                daily_loss = EXCLUDED.daily_loss,
                trades_count = EXCLUDED.trades_count,
                wins = EXCLUDED.wins,
                losses = EXCLUDED.losses,
                pdll_hits = EXCLUDED.pdll_hits
        """
        
        async with self._db_pool.acquire() as conn:
            await conn.execute(
                query,
                state.date,
                state.loss_streak,
                state.daily_loss,
                state.trades_count,
                state.wins,
                state.losses,
                state.pdll_hits,
            )
        
        logger.debug(
            f"Saved state for {state.date}: "
            f"loss_streak={state.loss_streak}, "
            f"trades_count={state.trades_count}"
        )
    
    async def reset_today(self) -> DailyState:
        """Reset today's state to fresh values.
        
        Returns:
            Fresh daily state for today
        """
        today = date.today()
        fresh_state = DailyState(date=today)
        await self.save(fresh_state)
        
        logger.info(f"Reset state for {today}")
        
        return fresh_state

