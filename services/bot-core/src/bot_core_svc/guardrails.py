"""Guardrails integration for Bot Core service."""

from datetime import datetime, timezone

from scp_shared.common.logger import get_logger
from scp_shared.validation import (
    BehaviorGuardrails,
    BehaviorState,
    BehaviorStateTracker,
    GuardrailResult,
    SessionConstraints,
)

from bot_core_svc.state_repository import DailyState, StateRepository

logger = get_logger(__name__)


class GuardrailsService:
    """Guardrails service with state persistence.
    
    Wraps BehaviorGuardrails and BehaviorStateTracker, integrating with
    StateRepository for persistent daily state tracking.
    
    Args:
        state_repo: State repository for persistence
    
    Example:
        >>> service = GuardrailsService(state_repo)
        >>> await service.load_state()
        >>> result = service.evaluate(session_constraints)
        >>> if result.allowed:
        ...     print("Guardrails passed")
    """
    
    def __init__(self, state_repo: StateRepository) -> None:
        """Initialize guardrails service.
        
        Args:
            state_repo: State repository for persistence
        """
        self._state_repo = state_repo
        self._guardrails = BehaviorGuardrails()
        self._tracker = BehaviorStateTracker()
        self._daily_state: DailyState | None = None
    
    async def load_state(self) -> None:
        """Load daily state from repository."""
        self._daily_state = await self._state_repo.load_today()
        
        # Initialize tracker with loaded state
        behavior_state = BehaviorState(
            consecutive_losses=self._daily_state.loss_streak,
            fatigue_flag=False,  # Not persisted, must be set manually
            session_extended=False,  # Not persisted, must be set manually
            last_reset=None,
        )
        self._tracker = BehaviorStateTracker(initial_state=behavior_state)
        
        logger.info(
            f"Loaded daily state: loss_streak={self._daily_state.loss_streak}, "
            f"trades_count={self._daily_state.trades_count}"
        )
    
    def evaluate(self, constraints: SessionConstraints) -> GuardrailResult:
        """Evaluate guardrails against current state.
        
        Args:
            constraints: Session constraints with limits
            
        Returns:
            GuardrailResult with allowed flag and reasons
        """
        return self._guardrails.evaluate(self._tracker.state, constraints)
    
    async def record_trade_outcome(
        self,
        won: bool | None,
        pnl: float = 0.0,
    ) -> None:
        """Record trade outcome and update state.
        
        Args:
            won: True if win, False if loss, None if breakeven
            pnl: P&L in dollars
        """
        # Update behavior state tracker
        self._tracker.record_trade_outcome(won)
        
        # Update daily state
        if self._daily_state is not None:
            self._daily_state.trades_count += 1
            self._daily_state.daily_loss += min(0, pnl)  # Only negative PnL
            
            if won is True:
                self._daily_state.wins += 1
            elif won is False:
                self._daily_state.losses += 1
            
            self._daily_state.loss_streak = self._tracker.state.consecutive_losses
            
            # Persist updated state
            await self._state_repo.save(self._daily_state)
            
            logger.info(
                f"Recorded trade outcome: won={won}, pnl={pnl:.2f}, "
                f"loss_streak={self._daily_state.loss_streak}"
            )
    
    def set_fatigue_flag(self, flagged: bool) -> None:
        """Set fatigue flag.
        
        Args:
            flagged: True to set fatigue flag, False to clear
        """
        self._tracker.set_fatigue_flag(flagged)
        logger.info(f"Fatigue flag set: {flagged}")
    
    def mark_session_extension(self, extended: bool) -> None:
        """Mark session as extended.
        
        Args:
            extended: True if session extended, False otherwise
        """
        self._tracker.mark_session_extension(extended)
        logger.info(f"Session extension marked: {extended}")
    
    async def reset_for_session(self) -> None:
        """Reset state for new session (new day)."""
        now = datetime.now(timezone.utc)
        self._tracker.reset_for_session(now)
        
        # Reset daily state in database
        self._daily_state = await self._state_repo.reset_today()
        
        logger.info(f"Reset guardrails state for new session at {now}")
    
    @property
    def state(self) -> BehaviorState:
        """Get current behavior state.
        
        Returns:
            Current behavior state
        """
        return self._tracker.state
    
    @property
    def daily_state(self) -> DailyState | None:
        """Get current daily state.
        
        Returns:
            Current daily state or None if not loaded
        """
        return self._daily_state

