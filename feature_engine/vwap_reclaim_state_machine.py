"""VWAP Reclaim State Machine - Lifecycle Management.

This module implements a formal state machine for VWAP_RECLAIM setup lifecycle,
ensuring proper sequencing from detection through confirmation to execution.

The state machine enforces:
- No premature execution (must be CONFIRMED)
- Expiration of stale reclaims (> MAX_CONFIRM_WINDOW bars)
- Clear invalidation when structural thesis breaks
- Complete audit trail via transition history

States:
    NONE: No active reclaim
    DETECTED: Reclaim identified (brief transition state)
    PENDING_ACCEPTANCE: Waiting for confirmation
    CONFIRMED: Entry-ready (confirmation received)
    EXECUTED: Trade opened
    EXPIRED: Reclaim timed out without confirmation
    INVALIDATED: Structurally broken (HTF break, VWAP loss, etc.)

Valid transitions:
    NONE -> DETECTED -> PENDING_ACCEPTANCE
    PENDING_ACCEPTANCE -> CONFIRMED (on confirmation)
    PENDING_ACCEPTANCE -> EXPIRED (on timeout)
    CONFIRMED -> EXECUTED (on execution)
    ANY -> INVALIDATED (on structural break)

Following Shir Capital SOP: VWAP reclaim requires multi-phase validation
before entry to prevent early stops and preserve A+ selectivity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from common.logger import get_logger

logger = get_logger(__name__)


class VWAPReclaimState(Enum):
    """VWAP Reclaim lifecycle states."""

    NONE = "none"  # No active reclaim
    DETECTED = "detected"  # Reclaim identified (brief transition)
    PENDING_ACCEPTANCE = "pending"  # Waiting for confirmation
    CONFIRMED = "confirmed"  # Entry-ready
    EXECUTED = "executed"  # Trade opened
    EXPIRED = "expired"  # Reclaim timed out
    INVALIDATED = "invalidated"  # Structurally broken


@dataclass
class StateTransition:
    """Record of a state transition for audit trail."""

    from_state: VWAPReclaimState
    to_state: VWAPReclaimState
    bar_idx: int
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


class VWAPReclaimStateMachine:
    """State machine for VWAP_RECLAIM setup lifecycle.

    Manages the complete lifecycle from detection through execution,
    enforcing proper sequencing and expiration rules.

    Args:
        max_confirm_window: Maximum bars to wait for confirmation (default: 10)

    Example:
        >>> sm = VWAPReclaimStateMachine()
        >>> sm.on_reclaim_detected(bar_idx=100, direction="above")
        >>> sm.current_state
        VWAPReclaimState.PENDING_ACCEPTANCE
        >>> sm.on_confirmation(bar_idx=103, confirmation_type="vwap_hold")
        >>> sm.can_execute()
        True
    """

    def __init__(self, max_confirm_window: int = 10):
        """Initialize state machine."""
        self.max_confirm_window = max_confirm_window

        # Current state
        self.current_state = VWAPReclaimState.NONE

        # Detection tracking
        self.detection_bar_idx: int | None = None
        self.reclaim_direction: str | None = None  # "above" or "below"

        # Confirmation tracking
        self.confirmations: set[str] = set()

        # Transition history for audit trail
        self.transition_history: list[StateTransition] = []

    def on_reclaim_detected(self, bar_idx: int, direction: str) -> None:
        """Handle VWAP reclaim detection.

        Transitions: NONE -> DETECTED -> PENDING_ACCEPTANCE

        Args:
            bar_idx: Bar index where reclaim detected
            direction: "above" for long, "below" for short
        """
        if self.current_state != VWAPReclaimState.NONE:
            logger.warning(
                f"Reclaim detected while in state {self.current_state.value} at bar {bar_idx}. "
                "Resetting previous reclaim."
            )
            self.reset()

        # NONE -> DETECTED
        self._transition(
            to_state=VWAPReclaimState.DETECTED,
            bar_idx=bar_idx,
            reason=f"VWAP reclaim {direction} detected",
        )

        # Store detection context
        self.detection_bar_idx = bar_idx
        self.reclaim_direction = direction

        # DETECTED -> PENDING_ACCEPTANCE (immediate transition)
        self._transition(
            to_state=VWAPReclaimState.PENDING_ACCEPTANCE,
            bar_idx=bar_idx,
            reason="Entering confirmation window",
        )

        logger.info(
            f"VWAP reclaim detected at bar {bar_idx} (direction={direction}). "
            f"State: {self.current_state.value}"
        )

    def on_confirmation(self, bar_idx: int, confirmation_type: str) -> None:
        """Handle confirmation signal.

        Transitions: PENDING_ACCEPTANCE -> CONFIRMED

        Args:
            bar_idx: Bar index where confirmation detected
            confirmation_type: Type of confirmation (e.g., "vwap_hold", "volume_expansion")

        Raises:
            ValueError: If not in PENDING_ACCEPTANCE state
        """
        if self.current_state == VWAPReclaimState.EXPIRED:
            raise ValueError(
                f"Cannot confirm reclaim in EXPIRED state at bar {bar_idx}. "
                "Reclaim timed out."
            )

        if self.current_state == VWAPReclaimState.INVALIDATED:
            raise ValueError(
                f"Cannot confirm reclaim in INVALIDATED state at bar {bar_idx}. "
                "Reclaim structurally broken."
            )

        if self.current_state != VWAPReclaimState.PENDING_ACCEPTANCE:
            # Allow confirmation in CONFIRMED state (multiple confirmations)
            if self.current_state != VWAPReclaimState.CONFIRMED:
                raise ValueError(
                    f"Cannot confirm reclaim in state {self.current_state.value} at bar {bar_idx}. "
                    "Must be PENDING_ACCEPTANCE."
                )

        # Add confirmation to set
        self.confirmations.add(confirmation_type)

        # Transition to CONFIRMED (if not already)
        if self.current_state == VWAPReclaimState.PENDING_ACCEPTANCE:
            self._transition(
                to_state=VWAPReclaimState.CONFIRMED,
                bar_idx=bar_idx,
                reason=f"Confirmation received: {confirmation_type}",
            )
            logger.info(
                f"VWAP reclaim confirmed at bar {bar_idx} "
                f"(confirmation={confirmation_type}, bars_waited={bar_idx - self.detection_bar_idx})"
            )
        else:
            # Already confirmed, just log additional confirmation
            logger.debug(
                f"Additional confirmation at bar {bar_idx}: {confirmation_type}"
            )

    def on_execution(self, bar_idx: int) -> None:
        """Handle trade execution.

        Transitions: CONFIRMED -> EXECUTED

        Args:
            bar_idx: Bar index where execution occurred

        Raises:
            ValueError: If not in CONFIRMED state
        """
        if self.current_state != VWAPReclaimState.CONFIRMED:
            raise ValueError(
                f"Cannot execute reclaim in state {self.current_state.value} at bar {bar_idx}. "
                "Must be CONFIRMED."
            )

        self._transition(
            to_state=VWAPReclaimState.EXECUTED,
            bar_idx=bar_idx,
            reason="Trade executed",
        )

        logger.info(
            f"VWAP reclaim executed at bar {bar_idx} "
            f"(confirmations={list(self.confirmations)})"
        )

    def on_expiration(self, bar_idx: int) -> None:
        """Handle reclaim expiration.

        Transitions: PENDING_ACCEPTANCE -> EXPIRED

        Args:
            bar_idx: Bar index where expiration occurred
        """
        if self.current_state not in [
            VWAPReclaimState.PENDING_ACCEPTANCE,
            VWAPReclaimState.CONFIRMED,
        ]:
            logger.warning(
                f"Expiration called in state {self.current_state.value} at bar {bar_idx}. "
                "Ignoring."
            )
            return

        bars_waited = bar_idx - self.detection_bar_idx if self.detection_bar_idx else 0

        self._transition(
            to_state=VWAPReclaimState.EXPIRED,
            bar_idx=bar_idx,
            reason=f"Reclaim expired after {bars_waited} bars (max: {self.max_confirm_window})",
        )

        logger.info(
            f"VWAP reclaim expired at bar {bar_idx} "
            f"(bars_waited={bars_waited}, max={self.max_confirm_window})"
        )

    def on_invalidation(self, bar_idx: int, reason: str) -> None:
        """Handle reclaim invalidation.

        Transitions: ANY -> INVALIDATED

        Args:
            bar_idx: Bar index where invalidation occurred
            reason: Reason for invalidation (e.g., "htf_break", "vwap_loss")
        """
        if self.current_state == VWAPReclaimState.INVALIDATED:
            logger.debug(
                f"Invalidation called while already INVALIDATED at bar {bar_idx}. "
                "Ignoring."
            )
            return

        self._transition(
            to_state=VWAPReclaimState.INVALIDATED,
            bar_idx=bar_idx,
            reason=f"Invalidation: {reason}",
        )

        logger.info(f"VWAP reclaim invalidated at bar {bar_idx} (reason={reason})")

    def on_stop_out(self, bar_idx: int) -> None:
        """Handle stop-loss exit.

        Sprint 3 Task 7: Distinguish stop-loss from invalidation.
        Stop-out transitions to INVALIDATED to prevent re-entry on same reclaim.

        Transitions: ANY -> INVALIDATED

        Args:
            bar_idx: Bar index where stop-out occurred
        """
        if self.current_state == VWAPReclaimState.INVALIDATED:
            logger.debug(
                f"Stop-out called while already INVALIDATED at bar {bar_idx}. "
                "Ignoring."
            )
            return

        self._transition(
            to_state=VWAPReclaimState.INVALIDATED,
            bar_idx=bar_idx,
            reason="Stop-loss hit",
        )

        logger.info(
            f"VWAP reclaim stop-out at bar {bar_idx} (state machine invalidated)"
        )

    def can_execute(self) -> bool:
        """Check if reclaim can be executed.

        Returns:
            True only if current_state == CONFIRMED
        """
        return self.current_state == VWAPReclaimState.CONFIRMED

    def is_expired(self, current_bar_idx: int) -> bool:
        """Check if reclaim has expired.

        Args:
            current_bar_idx: Current bar index

        Returns:
            True if bars since detection > max_confirm_window
        """
        if self.detection_bar_idx is None:
            return False

        bars_since = current_bar_idx - self.detection_bar_idx
        return bars_since > self.max_confirm_window

    def bars_since_detection(self, current_bar_idx: int) -> int:
        """Calculate bars since reclaim detection.

        Args:
            current_bar_idx: Current bar index

        Returns:
            Number of bars since detection, or 0 if no detection
        """
        if self.detection_bar_idx is None:
            return 0
        return current_bar_idx - self.detection_bar_idx

    def reset(self) -> None:
        """Reset state machine to NONE.

        Clears current state but preserves transition history for diagnostics.
        """
        self._transition(
            to_state=VWAPReclaimState.NONE,
            bar_idx=self.detection_bar_idx or 0,
            reason="State machine reset",
        )

        self.detection_bar_idx = None
        self.reclaim_direction = None
        self.confirmations.clear()

        logger.debug("State machine reset to NONE")

    def _transition(
        self,
        to_state: VWAPReclaimState,
        bar_idx: int,
        reason: str,
    ) -> None:
        """Record state transition.

        Args:
            to_state: Target state
            bar_idx: Bar index of transition
            reason: Reason for transition
        """
        transition = StateTransition(
            from_state=self.current_state,
            to_state=to_state,
            bar_idx=bar_idx,
            reason=reason,
        )

        self.transition_history.append(transition)
        self.current_state = to_state

        logger.debug(
            f"State transition: {transition.from_state.value} -> {transition.to_state.value} "
            f"at bar {bar_idx} (reason: {reason})"
        )
