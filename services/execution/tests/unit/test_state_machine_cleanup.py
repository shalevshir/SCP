"""Unit tests for state machine cleanup (memory leak prevention)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution_svc.state_machine_manager import StateMachineManager
from scp_shared.database import DatabasePool
from scp_shared.indicators.vwap_reclaim_state_machine import (
    VWAPReclaimState,
    VWAPReclaimStateMachine,
)
from scp_shared.messaging.schemas import SignalMessage


@pytest.fixture
def db_pool() -> DatabasePool:
    """Create mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    return pool


@pytest.fixture
def sample_signal() -> SignalMessage:
    """Create sample signal message."""
    return SignalMessage(
        id="signal-1",
        timestamp="2025-01-15T10:00:00Z",
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=9.0,
        confidence="A+",
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2662.0,
        factors={},
    )


class TestStateMachineCleanup:
    """Test that state machines are properly cleaned up to prevent memory leaks."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_executed_state_machines(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test that EXECUTED state machines are removed by cleanup.

        This test demonstrates the bug fix: cleanup_old_state_machines()
        must remove EXECUTED state machines, not just EXPIRED/INVALIDATED.
        Otherwise, successful trades accumulate indefinitely in memory.
        """
        manager = StateMachineManager(db_pool)

        # Create state machine and mark as EXECUTED
        sm = VWAPReclaimStateMachine()
        sm.current_state = VWAPReclaimState.EXECUTED
        manager._state_machines["test-signal-1"] = sm

        # Verify it exists
        assert "test-signal-1" in manager._state_machines

        # Cleanup should remove EXECUTED state machines
        manager.cleanup_old_state_machines()

        # Verify it was removed
        assert "test-signal-1" not in manager._state_machines

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired_state_machines(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test that EXPIRED state machines are removed by cleanup."""
        manager = StateMachineManager(db_pool)

        # Create state machine and mark as EXPIRED
        sm = VWAPReclaimStateMachine()
        sm.current_state = VWAPReclaimState.EXPIRED
        manager._state_machines["test-signal-2"] = sm

        # Cleanup should remove it
        manager.cleanup_old_state_machines()

        assert "test-signal-2" not in manager._state_machines

    @pytest.mark.asyncio
    async def test_cleanup_removes_invalidated_state_machines(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test that INVALIDATED state machines are removed by cleanup."""
        manager = StateMachineManager(db_pool)

        # Create state machine and mark as INVALIDATED
        sm = VWAPReclaimStateMachine()
        sm.current_state = VWAPReclaimState.INVALIDATED
        manager._state_machines["test-signal-3"] = sm

        # Cleanup should remove it
        manager.cleanup_old_state_machines()

        assert "test-signal-3" not in manager._state_machines

    @pytest.mark.asyncio
    async def test_cleanup_preserves_active_state_machines(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test that active state machines are NOT removed by cleanup."""
        manager = StateMachineManager(db_pool)

        # Create state machines in various active states
        sm_pending = VWAPReclaimStateMachine()
        sm_pending.current_state = VWAPReclaimState.PENDING_ACCEPTANCE
        manager._state_machines["pending-signal"] = sm_pending

        sm_confirmed = VWAPReclaimStateMachine()
        sm_confirmed.current_state = VWAPReclaimState.CONFIRMED
        manager._state_machines["confirmed-signal"] = sm_confirmed

        sm_detected = VWAPReclaimStateMachine()
        sm_detected.current_state = VWAPReclaimState.DETECTED
        manager._state_machines["detected-signal"] = sm_detected

        # Cleanup should NOT remove active state machines
        manager.cleanup_old_state_machines()

        # Verify all active state machines still exist
        assert "pending-signal" in manager._state_machines
        assert "confirmed-signal" in manager._state_machines
        assert "detected-signal" in manager._state_machines

    @pytest.mark.asyncio
    async def test_cleanup_handles_mixed_states(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test cleanup with mix of active and terminal states."""
        manager = StateMachineManager(db_pool)

        # Create mix of state machines
        # Active (should keep)
        sm_pending = VWAPReclaimStateMachine()
        sm_pending.current_state = VWAPReclaimState.PENDING_ACCEPTANCE
        manager._state_machines["keep-1"] = sm_pending

        # Terminal (should remove)
        sm_executed = VWAPReclaimStateMachine()
        sm_executed.current_state = VWAPReclaimState.EXECUTED
        manager._state_machines["remove-1"] = sm_executed

        sm_expired = VWAPReclaimStateMachine()
        sm_expired.current_state = VWAPReclaimState.EXPIRED
        manager._state_machines["remove-2"] = sm_expired

        # Active (should keep)
        sm_confirmed = VWAPReclaimStateMachine()
        sm_confirmed.current_state = VWAPReclaimState.CONFIRMED
        manager._state_machines["keep-2"] = sm_confirmed

        # Terminal (should remove)
        sm_invalidated = VWAPReclaimStateMachine()
        sm_invalidated.current_state = VWAPReclaimState.INVALIDATED
        manager._state_machines["remove-3"] = sm_invalidated

        # Initial count: 5 state machines
        assert len(manager._state_machines) == 5

        # Cleanup
        manager.cleanup_old_state_machines()

        # Should have 2 active, 3 terminal removed
        assert len(manager._state_machines) == 2
        assert "keep-1" in manager._state_machines
        assert "keep-2" in manager._state_machines
        assert "remove-1" not in manager._state_machines
        assert "remove-2" not in manager._state_machines
        assert "remove-3" not in manager._state_machines


class TestStateMachineCleanupIntegration:
    """Test cleanup in realistic scenarios."""

    @pytest.mark.asyncio
    async def test_cleanup_after_trade_lifecycle(
        self,
        db_pool: DatabasePool,
        sample_signal: SignalMessage,
    ) -> None:
        """Test cleanup after complete trade lifecycle.

        Simulates realistic flow:
        1. Signal arrives → state machine created
        2. Signal confirmed
        3. Trade executed
        4. Cleanup removes executed state machine
        """
        manager = StateMachineManager(db_pool)

        # 1. Create state machine from signal
        signal_id = await manager.create_from_signal(sample_signal)
        assert signal_id in manager._state_machines

        # 2. Check confirmation (auto-confirms)
        manager.increment_bar_counter()
        is_confirmed = manager.check_confirmation(signal_id)
        assert is_confirmed

        # 3. Execute trade
        await manager.execute(signal_id, bar_idx=manager._bar_counter)
        sm = manager.get_state_machine(signal_id)
        assert sm is not None
        assert sm.current_state == VWAPReclaimState.EXECUTED

        # 4. Cleanup should remove executed state machine
        manager.cleanup_old_state_machines()

        # Verify state machine was removed (memory freed)
        assert signal_id not in manager._state_machines

    @pytest.mark.asyncio
    async def test_cleanup_prevents_memory_leak_with_many_trades(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test that cleanup prevents unbounded memory growth.

        Simulates production scenario with many trades over time.
        Without cleanup, all state machines would accumulate indefinitely.
        """
        manager = StateMachineManager(db_pool)

        # Simulate 100 trades across different 60-bar windows
        # (to avoid re-entry protection blocking)
        for i in range(100):
            # Set bar counter to different 60-bar window for each trade
            # to avoid re-entry protection (which limits 1 execution per 60-bar window)
            manager._bar_counter = i * 60

            # Use different dates to avoid re-entry protection (date-based context keys)
            signal_date = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc) + timedelta(
                days=i
            )
            signal = SignalMessage(
                id=f"signal-{i}",
                timestamp=signal_date.isoformat(),
                direction="long",
                setup_type="VWAP_RECLAIM",
                score=9.0,
                confidence="A+",
                entry_price=2650.0,
                sl_price=2645.0,
                tp_price=2662.0,
                factors={},
            )

            # Create state machine (at bar i*60)
            signal_id = await manager.create_from_signal(signal)

            # Confirm it (auto-confirm on next bar)
            manager.increment_bar_counter()
            is_confirmed = manager.check_confirmation(
                signal_id, bar_idx=manager._bar_counter
            )
            assert (
                is_confirmed
            ), f"State machine should be confirmed at bar {manager._bar_counter}"

            # Verify state is CONFIRMED before execution
            sm = manager.get_state_machine(signal_id)
            assert sm is not None
            assert (
                sm.current_state.value == "confirmed"
            ), f"State should be confirmed, got {sm.current_state.value}"

            # Execute trade
            await manager.execute(signal_id, bar_idx=manager._bar_counter)

        # Without cleanup: 100 state machines in memory
        assert len(manager._state_machines) == 100

        # Run cleanup
        manager.cleanup_old_state_machines()

        # After cleanup: 0 state machines (all were EXECUTED)
        assert len(manager._state_machines) == 0
