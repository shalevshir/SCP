"""Daily state tracker for PDLL and trade limit enforcement."""

from dataclasses import dataclass
from datetime import date, datetime

from scp_shared.alerts import AlertLevel, AlertType, send_alert
from scp_shared.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DailyState:
    """Daily trading state.
    
    Tracks daily P&L, trade count, and PDLL hit status.
    Resets at session boundaries (date change).
    
    Attributes:
        date: Trading date
        daily_pnl: Cumulative P&L in points for the day
        trades_count: Number of trades executed today
        pdll_hit: Whether PDLL (Per Day Loss Limit) was hit today
        consecutive_losses: Number of consecutive losses today
        wins: Number of winning trades today
        losses: Number of losing trades today
    """
    
    date: date
    daily_pnl: float = 0.0
    trades_count: int = 0
    pdll_hit: bool = False
    consecutive_losses: int = 0
    wins: int = 0
    losses: int = 0


class DailyStateTracker:
    """Tracks daily state and enforces PDLL and trade count limits.
    
    This tracker enforces SOP risk guardrails:
    - PDLL (Per Day Loss Limit): Stop trading when daily loss exceeds limit
    - Max trades per day: Prevent overtrading
    - Session resets: Reset state at day boundaries
    
    Example:
        >>> tracker = DailyStateTracker(pdll_limit=600.0, max_trades_per_day=2)
        >>> can_trade, reason = tracker.can_trade()
        >>> if can_trade:
        ...     tracker.record_trade_opened()
        >>> tracker.record_trade_closed(pnl=-50.0)
    """
    
    def __init__(
        self,
        pdll_limit: float = 600.0,
        max_trades_per_day: int = 2,
        max_consecutive_losses: int = 2,
    ) -> None:
        """Initialize daily state tracker.
        
        Args:
            pdll_limit: Per day loss limit in points (default: 600.0)
            max_trades_per_day: Maximum trades allowed per day (default: 2)
            max_consecutive_losses: Maximum consecutive losses before halt (default: 2)
        """
        if max_consecutive_losses < 1:
            raise ValueError("max_consecutive_losses must be at least 1")
        self._pdll_limit = pdll_limit
        self._max_trades_per_day = max_trades_per_day
        self._max_consecutive_losses = max_consecutive_losses
        self._state = DailyState(date=date.today())
        
        logger.info(
            f"DailyStateTracker initialized: pdll_limit={pdll_limit}, "
            f"max_trades_per_day={max_trades_per_day}, "
            f"max_consecutive_losses={max_consecutive_losses}"
        )
    
    def can_trade(self) -> tuple[bool, str | None]:
        """Check if trading is allowed based on daily limits.
        
        Returns:
            Tuple of (allowed, reason) where allowed is True if trading is permitted,
            and reason explains why if blocked. Reason uses standardized halt codes:
            - "PDLL" for per-day loss limit
            - "LOSS_STREAK" for consecutive loss limit
            - "MAX_TRADES" for daily trade count limit
            - None if trading is allowed
        
        Checks (in priority order):
            1. PDLL already hit today
            2. Daily P&L at or below negative PDLL limit
            3. Loss streak at or above maximum
            4. Daily trade count at or above maximum
        """
        # Check if PDLL was already hit
        if self._state.pdll_hit:
            return False, "PDLL"
        
        # Check if daily P&L exceeds loss limit
        if self._state.daily_pnl <= -self._pdll_limit:
            self._state.pdll_hit = True
            logger.warning(
                f"PDLL limit reached: daily_pnl={self._state.daily_pnl:.2f} <= -{self._pdll_limit}"
            )
            send_alert(
                AlertLevel.CRITICAL,
                AlertType.PDLL_HIT,
                f"Daily loss limit reached: {self._state.daily_pnl:.2f} points",
                context={
                    "daily_pnl": self._state.daily_pnl,
                    "pdll_limit": self._pdll_limit,
                    "trades_count": self._state.trades_count,
                    "date": self._state.date.isoformat(),
                    "timestamp": datetime.now().isoformat(),
                },
            )
            return False, "PDLL"
        
        # Check if loss streak exceeded
        if self._state.consecutive_losses >= self._max_consecutive_losses:
            return False, "LOSS_STREAK"
        
        # Check if daily trade count exceeded
        if self._state.trades_count >= self._max_trades_per_day:
            return False, "MAX_TRADES"
        
        return True, None
    
    def record_trade_opened(self) -> None:
        """Record that a trade was opened.
        
        Increments the daily trade counter.
        """
        self._state.trades_count += 1
        logger.debug(
            f"Trade opened: daily count now {self._state.trades_count}/{self._max_trades_per_day}"
        )
    
    def record_trade_closed(self, pnl: float) -> None:
        """Record that a trade was closed and update daily P&L.
        
        Args:
            pnl: Trade P&L in points (positive for profit, negative for loss)
        """
        self._state.daily_pnl += pnl
        
        # Update win/loss tracking
        if pnl > 0:
            # Win: increment wins, reset loss streak
            self._state.wins += 1
            self._state.consecutive_losses = 0
            logger.debug(
                f"Trade closed (WIN): pnl={pnl:.2f} points, "
                f"daily_pnl now {self._state.daily_pnl:.2f}, "
                f"consecutive_losses reset to 0"
            )
        elif pnl < 0:
            # Loss: increment losses and loss streak
            self._state.losses += 1
            self._state.consecutive_losses += 1
            logger.debug(
                f"Trade closed (LOSS): pnl={pnl:.2f} points, "
                f"daily_pnl now {self._state.daily_pnl:.2f}, "
                f"consecutive_losses now {self._state.consecutive_losses}"
            )
        else:
            # Breakeven: no change to win/loss/streak
            logger.debug(
                f"Trade closed (BREAKEVEN): pnl=0.00 points, "
                f"daily_pnl now {self._state.daily_pnl:.2f}"
            )
        
        # Log warning if approaching PDLL
        if self._state.daily_pnl < 0:
            remaining = self._pdll_limit + self._state.daily_pnl
            if remaining < 100:  # Within 100 points of PDLL
                logger.warning(
                    f"Approaching PDLL: {remaining:.2f} points remaining "
                    f"(daily_pnl={self._state.daily_pnl:.2f}, limit={self._pdll_limit})"
                )
    
    def check_session_reset(self, current_date: date) -> None:
        """Check if session has changed and reset state if needed.
        
        Args:
            current_date: Current trading date
            
        Note:
            This should be called at the start of each candle processing
            to detect date boundaries.
        """
        if current_date != self._state.date:
            logger.info(
                f"Session reset: {self._state.date} -> {current_date} "
                f"(prev: pnl={self._state.daily_pnl:.2f}, trades={self._state.trades_count}, "
                f"pdll_hit={self._state.pdll_hit})"
            )
            self._state = DailyState(date=current_date)
            logger.info(f"New session started: date={current_date}")
    
    @property
    def state(self) -> DailyState:
        """Get current daily state.
        
        Returns:
            Current DailyState
        """
        return self._state
    
    @property
    def pdll_limit(self) -> float:
        """Get PDLL limit.
        
        Returns:
            PDLL limit in points
        """
        return self._pdll_limit
    
    @property
    def max_trades_per_day(self) -> int:
        """Get max trades per day.
        
        Returns:
            Maximum trades allowed per day
        """
        return self._max_trades_per_day
    
    def restore_from_trades(
        self,
        trades: list,
        current_date: date,
    ) -> None:
        """Restore daily state from historical trades.
        
        Called during service startup to restore daily P&L and trade count
        from trades executed today (before the restart).
        
        Args:
            trades: List of TradeRecord objects from today
            current_date: Current trading date
            
        Example:
            >>> tracker = DailyStateTracker(pdll_limit=600.0, max_trades_per_day=2)
            >>> todays_trades = await repo.get_trades_for_date(datetime.now())
            >>> tracker.restore_from_trades(todays_trades, date.today())
        """
        # Reset state to current date
        self._state = DailyState(date=current_date)
        
        # Count all trades (open and closed) opened today
        self._state.trades_count = len(trades)
        
        # Sum P&L and track wins/losses from closed trades only
        total_pnl = 0.0
        wins = 0
        losses = 0
        consecutive_losses = 0
        
        # Sort trades by close time to compute consecutive losses correctly
        closed_trades = [t for t in trades if t.pnl is not None]
        closed_trades.sort(key=lambda t: t.exit_timestamp or t.entry_timestamp)
        
        for trade in closed_trades:
            pnl = float(trade.pnl)
            total_pnl += pnl
            
            if pnl > 0:
                wins += 1
                consecutive_losses = 0  # Reset on win
            elif pnl < 0:
                losses += 1
                consecutive_losses += 1
        
        self._state.daily_pnl = total_pnl
        self._state.wins = wins
        self._state.losses = losses
        self._state.consecutive_losses = consecutive_losses
        
        # Check if PDLL was already hit
        if total_pnl <= -self._pdll_limit:
            self._state.pdll_hit = True
            logger.warning(
                f"PDLL already hit after restoration: "
                f"daily_pnl={total_pnl:.2f} <= -{self._pdll_limit}"
            )
            send_alert(
                AlertLevel.CRITICAL,
                AlertType.PDLL_HIT,
                f"PDLL already hit (restored state): {total_pnl:.2f} points",
                context={
                    "daily_pnl": total_pnl,
                    "pdll_limit": self._pdll_limit,
                    "trades_count": self._state.trades_count,
                    "date": current_date.isoformat(),
                    "restored_on_startup": True,
                    "timestamp": datetime.now().isoformat(),
                },
            )
        
        logger.info(
            f"Daily state restored: date={current_date}, "
            f"trades_count={self._state.trades_count}, "
            f"daily_pnl={self._state.daily_pnl:.2f}, "
            f"wins={self._state.wins}, losses={self._state.losses}, "
            f"consecutive_losses={self._state.consecutive_losses}, "
            f"pdll_hit={self._state.pdll_hit}"
        )
    
    def reset_state(self) -> None:
        """Reset daily state to initial values.
        
        Used for testing to clear state between test runs.
        """
        self._state = DailyState(date=date.today())
        logger.info("Daily state reset to initial values")

