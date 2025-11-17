"""Behavior guardrails enforcing SOP loss streaks, fatigue, and extensions."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from common.logger import get_logger
from validation.session_validator import SessionConstraints

logger = get_logger(__name__)


@dataclass(frozen=True)
class BehaviorState:
    """Immutable snapshot of behavioral state for guardrail evaluation."""

    consecutive_losses: int = 0
    fatigue_flag: bool = False
    session_extended: bool = False
    last_reset: datetime | None = None


@dataclass(frozen=True)
class GuardrailResult:
    """Result of guardrail evaluation."""

    allowed: bool
    reasons: list[str] = field(default_factory=list)


class BehaviorStateTracker:
    """
    Tracks mutable behavioral state across trades and sessions.

    This tracker maintains loss streaks, fatigue flags, and session extension
    markers, providing state snapshots for guardrail evaluation.
    """

    def __init__(self, initial_state: BehaviorState | None = None) -> None:
        """Initialize tracker with optional starting state."""
        self._state = initial_state or BehaviorState()

    @property
    def state(self) -> BehaviorState:
        """Get current immutable state snapshot."""
        return self._state

    def record_trade_outcome(self, won: bool) -> None:
        """
        Record trade outcome and update loss streak.

        Args:
            won: True if trade was profitable, False otherwise.
        """
        if won:
            self._state = replace(self._state, consecutive_losses=0)
        else:
            self._state = replace(
                self._state, consecutive_losses=self._state.consecutive_losses + 1
            )
            logger.info(
                "Loss recorded: consecutive_losses=%d", self._state.consecutive_losses
            )

    def set_fatigue_flag(self, flagged: bool) -> None:
        """Set or clear the fatigue flag."""
        self._state = replace(self._state, fatigue_flag=flagged)
        if flagged:
            logger.warning("Fatigue flag set - trading should halt")

    def mark_session_extension(self, extended: bool) -> None:
        """Mark session as extended beyond allowed window."""
        self._state = replace(self._state, session_extended=extended)
        if extended:
            logger.warning("Session extension marked - trading should halt")

    def reset_for_session(self, now: datetime) -> None:
        """
        Reset state at session start per SOP.

        Args:
            now: Timestamp of reset for audit trail.
        """
        self._state = BehaviorState(last_reset=now)
        logger.info("Behavior state reset for new session at %s", now.isoformat())


class BehaviorGuardrails:
    """
    Evaluates behavioral state against SOP guardrails.

    Enforces:
    - Loss streak limits (session-specific via SessionConstraints)
    - Fatigue flag halts
    - Session extension halts
    """

    def evaluate(
        self, state: BehaviorState, constraints: SessionConstraints
    ) -> GuardrailResult:
        """
        Evaluate state against guardrail rules.

        Args:
            state: Current behavioral state snapshot.
            constraints: Active session constraints defining limits.

        Returns:
            GuardrailResult with allowed flag and list of blocking reasons.
        """
        reasons: list[str] = []

        # Rule 1: Loss streak limit (session-specific)
        if state.consecutive_losses >= constraints.max_losses:
            reasons.append(
                f"Loss streak limit reached: {state.consecutive_losses} "
                f"consecutive losses (max_losses={constraints.max_losses})"
            )
            logger.warning(
                "Rejected by BehaviorGuardrails: loss streak %d >= %d",
                state.consecutive_losses,
                constraints.max_losses,
            )

        # Rule 2: Fatigue flag (immediate halt)
        if state.fatigue_flag:
            reasons.append("Fatigue flag is set - operator requires break")
            logger.warning("Rejected by BehaviorGuardrails: fatigue flag active")

        # Rule 3: Session extension (halt when beyond window)
        if state.session_extended:
            reasons.append("Session extended beyond allowed trading window")
            logger.warning("Rejected by BehaviorGuardrails: session extended")

        allowed = not bool(reasons)
        if allowed:
            logger.debug("Behavior guardrails passed: all conditions met")

        return GuardrailResult(allowed=allowed, reasons=reasons)
