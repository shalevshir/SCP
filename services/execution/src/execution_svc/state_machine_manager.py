"""State machine manager for VWAP reclaim lifecycle tracking."""

import json
from datetime import datetime

from scp_shared.common.logger import get_logger
from scp_shared.database import DatabasePool
from scp_shared.indicators.vwap_reclaim_state_machine import (
    VWAPReclaimState,
    VWAPReclaimStateMachine,
)
from scp_shared.messaging.schemas import SignalMessage

logger = get_logger(__name__)


class StateMachineManager:
    """Manages multiple VWAPReclaimStateMachine instances with DB persistence.

    Tracks state machines for each signal, persists state for recovery,
    and provides methods to check confirmation/expiration.

    Example:
        >>> manager = StateMachineManager(db_pool)
        >>> await manager.restore_from_db()
        >>> signal_id = await manager.create_from_signal(signal_msg)
        >>> if manager.check_confirmation(signal_id, candle):
        ...     await manager.execute(signal_id, bar_idx)
    """

    def __init__(self, db_pool: DatabasePool) -> None:
        """Initialize state machine manager.

        Args:
            db_pool: Database connection pool
        """
        self._db_pool = db_pool
        self._state_machines: dict[str, VWAPReclaimStateMachine] = {}
        self._bar_counter = 0  # Global bar counter for expiration tracking

    async def create_from_signal(
        self, signal: SignalMessage, auto_confirm: bool = False
    ) -> str:
        """Create state machine from signal.

        Args:
            signal: Signal message from Bot Core
            auto_confirm: If True, immediately confirm the state machine.
                         Used for late signals where execution candle is already known.

        Returns:
            Signal ID
        """
        # Create state machine
        sm = VWAPReclaimStateMachine(max_confirm_window=10)

        # Detect reclaim (signal already represents detected reclaim)
        direction = "above" if signal.direction == "long" else "below"
        sm.on_reclaim_detected(bar_idx=self._bar_counter, direction=direction)

        # For late signals, immediately confirm since we've verified the execution candle exists
        if auto_confirm:
            sm.on_confirmation(
                bar_idx=self._bar_counter, confirmation_type="late_signal_auto"
            )
            logger.info(
                f"Auto-confirmed late signal {signal.id} at bar {self._bar_counter}"
            )

        # Store state machine
        self._state_machines[signal.id] = sm

        # Persist to DB
        await self._save_state_machine(signal.id, sm)

        logger.info(
            f"Created state machine for signal {signal.id} "
            f"(direction={signal.direction}, setup={signal.setup_type})"
        )

        return signal.id

    def check_confirmation(self, signal_id: str, bar_idx: int | None = None) -> bool:
        """Check if signal is confirmed and ready for execution.

        For Phase 6 simplification, we auto-confirm on the next bar.
        In production, this would check actual confirmation criteria.

        The state machine's own execution count (MAX_EXECUTIONS_PER_RECLAIM)
        prevents re-entry on the same reclaim event, matching backtester behavior.

        Args:
            signal_id: Signal identifier
            bar_idx: Bar index (uses current if None)

        Returns:
            True if confirmed and can execute
        """
        sm = self._state_machines.get(signal_id)
        if sm is None:
            return False

        # Auto-confirm on next bar (simplified for Phase 6)
        if sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE:
            if bar_idx is None:
                bar_idx = self._bar_counter

            # Confirm after 1 bar
            if sm.detection_bar_idx is not None and bar_idx > sm.detection_bar_idx:
                sm.on_confirmation(bar_idx=bar_idx, confirmation_type="auto_confirm")
                logger.info(f"Auto-confirmed signal {signal_id} at bar {bar_idx}")

        # State machine's can_execute() checks MAX_EXECUTIONS_PER_RECLAIM
        # to prevent re-entry on the same reclaim event
        can_exec = sm.can_execute()

        return can_exec

    def check_expiration(self, signal_id: str, bar_idx: int | None = None) -> bool:
        """Check if signal has expired.

        Args:
            signal_id: Signal identifier
            bar_idx: Bar index (uses current if None)

        Returns:
            True if expired
        """
        sm = self._state_machines.get(signal_id)
        if sm is None:
            return False

        if bar_idx is None:
            bar_idx = self._bar_counter

        if sm.is_expired(bar_idx):
            sm.on_expiration(bar_idx)
            logger.info(f"Signal {signal_id} expired at bar {bar_idx}")
            return True

        return False

    async def execute(self, signal_id: str, bar_idx: int) -> None:
        """Mark signal as executed.

        The state machine's on_execution() increments execution_count,
        which enforces MAX_EXECUTIONS_PER_RECLAIM to prevent re-entry
        on the same reclaim event (matching backtester behavior).

        Args:
            signal_id: Signal identifier
            bar_idx: Bar index where execution occurred
        """
        sm = self._state_machines.get(signal_id)
        if sm is None:
            logger.warning(f"Cannot execute: state machine not found for {signal_id}")
            return

        sm.on_execution(bar_idx)
        await self._save_state_machine(signal_id, sm)

        logger.info(f"Executed signal {signal_id} at bar {bar_idx}")

    async def invalidate(self, signal_id: str, bar_idx: int, reason: str) -> None:
        """Mark signal as invalidated.

        Args:
            signal_id: Signal identifier
            bar_idx: Bar index where invalidation occurred
            reason: Invalidation reason
        """
        sm = self._state_machines.get(signal_id)
        if sm is None:
            logger.warning(
                f"Cannot invalidate: state machine not found for {signal_id}"
            )
            return

        sm.on_invalidation(bar_idx, reason)
        await self._save_state_machine(signal_id, sm)

        logger.info(f"Invalidated signal {signal_id} at bar {bar_idx}: {reason}")

    def get_state_machine(self, signal_id: str) -> VWAPReclaimStateMachine | None:
        """Get state machine by signal ID.

        Args:
            signal_id: Signal identifier

        Returns:
            State machine if exists, None otherwise
        """
        return self._state_machines.get(signal_id)

    def increment_bar_counter(self) -> None:
        """Increment global bar counter (call on each new candle)."""
        self._bar_counter += 1

    async def restore_from_db(self) -> int:
        """Restore state machines from database on startup.

        Returns:
            Number of state machines restored
        """
        query = """
            SELECT signal_id, state, detection_bar_idx, reclaim_direction,
                   confirmations, execution_count, transition_history
            FROM state_machine_snapshots
            WHERE state IN ('pending', 'confirmed', 'executed')
            ORDER BY created_at DESC
        """

        rows = await self._db_pool.fetch(query)

        restored = 0
        for row in rows:
            try:
                # Create state machine
                sm = VWAPReclaimStateMachine()

                # Restore state (simplified - would need full deserialization in production)
                sm.current_state = VWAPReclaimState(row["state"])
                sm.detection_bar_idx = row["detection_bar_idx"]
                # Map DB format ("long"/"short") back to internal format ("above"/"below")
                db_direction = row["reclaim_direction"]
                sm.reclaim_direction = "above" if db_direction == "long" else "below"
                sm.execution_count = row["execution_count"] or 0

                # Restore confirmations - parse JSON string back to list
                if row["confirmations"]:
                    # asyncpg returns the JSONB as-is; since we stored a JSON string,
                    # we get a string back that needs to be parsed
                    confirmations_data = row["confirmations"]
                    if isinstance(confirmations_data, str):
                        confirmations_list = json.loads(confirmations_data)
                    else:
                        confirmations_list = confirmations_data  # Already parsed
                    sm.confirmations = set(confirmations_list)

                # Convert UUID to string for consistent key type
                # (asyncpg returns UUID objects, but all lookups use strings)
                self._state_machines[str(row["signal_id"])] = sm
                restored += 1

                logger.debug(f"Restored state machine for signal {row['signal_id']}")

            except Exception as e:
                logger.error(
                    f"Failed to restore state machine for signal {row['signal_id']}: {e}"
                )

        logger.info(f"Restored {restored} state machines from database")
        return restored

    async def _save_state_machine(
        self, signal_id: str, sm: VWAPReclaimStateMachine
    ) -> None:
        """Persist state machine to database.

        Args:
            signal_id: Signal identifier
            sm: State machine to save
        """
        query = """
            INSERT INTO state_machine_snapshots (
                signal_id, state, detection_bar_idx, reclaim_direction,
                confirmations, execution_count, transition_history
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (signal_id)
            DO UPDATE SET
                state = EXCLUDED.state,
                detection_bar_idx = EXCLUDED.detection_bar_idx,
                reclaim_direction = EXCLUDED.reclaim_direction,
                confirmations = EXCLUDED.confirmations,
                execution_count = EXCLUDED.execution_count,
                transition_history = EXCLUDED.transition_history,
                updated_at = NOW()
        """

        # Convert confirmations to JSON string for JSONB column
        # Use json.dumps() to ensure consistent serialization across asyncpg versions
        confirmations_list = list(sm.confirmations) if sm.confirmations else []
        confirmations_json = json.dumps(confirmations_list)

        # Convert transition history to JSON string for JSONB column
        transition_history_list = [
            {
                "from_state": t.from_state.value,
                "to_state": t.to_state.value,
                "bar_idx": t.bar_idx,
                "reason": t.reason,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in sm.transition_history
        ]
        transition_history_json = json.dumps(transition_history_list)

        # Map internal direction ("above"/"below") to DB format ("long"/"short")
        # State machine uses "above"/"below" for VWAP position,
        # DB constraint expects "long"/"short" for trade direction
        db_direction = "long" if sm.reclaim_direction == "above" else "short"

        await self._db_pool.execute(
            query,
            signal_id,
            sm.current_state.value,
            sm.detection_bar_idx,
            db_direction,
            confirmations_json,  # JSON string for JSONB column
            sm.execution_count,
            transition_history_json,  # JSON string for JSONB column
        )

    def cleanup_old_state_machines(self) -> None:
        """Remove terminal state machines from memory to prevent leaks.

        Removes state machines in terminal states (EXECUTED, EXPIRED, INVALIDATED)
        to prevent unbounded memory growth as trades accumulate over time.
        Active state machines (PENDING, CONFIRMED, etc.) are preserved.
        """
        to_remove = []

        for signal_id, sm in self._state_machines.items():
            # Remove terminal states: EXECUTED, EXPIRED, INVALIDATED
            if sm.current_state in (
                VWAPReclaimState.EXECUTED,
                VWAPReclaimState.EXPIRED,
                VWAPReclaimState.INVALIDATED,
            ):
                to_remove.append(signal_id)

        for signal_id in to_remove:
            del self._state_machines[signal_id]
            logger.debug(f"Cleaned up state machine for signal {signal_id}")

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} terminal state machines")
