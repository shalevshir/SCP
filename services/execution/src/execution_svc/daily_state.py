"""Daily state tracker for PDLL and trade limit enforcement."""

from dataclasses import dataclass
from datetime import date

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
    """
    
    date: date
    daily_pnl: float = 0.0
    trades_count: int = 0
    pdll_hit: bool = False


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
    ) -> None:
        """Initialize daily state tracker.
        
        Args:
            pdll_limit: Per day loss limit in points (default: 600.0)
            max_trades_per_day: Maximum trades allowed per day (default: 2)
        """
        self._pdll_limit = pdll_limit
        self._max_trades_per_day = max_trades_per_day
        self._state = DailyState(date=date.today())
        
        logger.info(
            f"DailyStateTracker initialized: pdll_limit={pdll_limit}, "
            f"max_trades_per_day={max_trades_per_day}"
        )
    
    def can_trade(self) -> tuple[bool, str | None]:
        """Check if trading is allowed based on daily limits.
        
        Returns:
            Tuple of (allowed, reason) where allowed is True if trading is permitted,
            and reason explains why if blocked.
        
        Checks (in priority order):
            1. PDLL already hit today
            2. Daily P&L at or below negative PDLL limit
            3. Daily trade count at or above maximum
        """
        # Check if PDLL was already hit
        if self._state.pdll_hit:
            return False, "PDLL hit - no further trading today"
        
        # Check if daily P&L exceeds loss limit
        if self._state.daily_pnl <= -self._pdll_limit:
            self._state.pdll_hit = True
            logger.warning(
                f"PDLL limit reached: daily_pnl={self._state.daily_pnl:.2f} <= -{self._pdll_limit}"
            )
            return False, f"PDLL limit reached: {self._state.daily_pnl:.2f}"
        
        # Check if daily trade count exceeded
        if self._state.trades_count >= self._max_trades_per_day:
            return False, f"Daily trade limit: {self._state.trades_count}/{self._max_trades_per_day}"
        
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
        logger.debug(
            f"Trade closed: pnl={pnl:.2f} points, daily_pnl now {self._state.daily_pnl:.2f}"
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

