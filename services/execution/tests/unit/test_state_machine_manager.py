"""Unit tests for StateMachineManager."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from execution_svc.state_machine_manager import StateMachineManager
from scp_shared.indicators.vwap_reclaim_state_machine import VWAPReclaimState
from scp_shared.messaging.schemas import SignalMessage


def create_signal_message(direction: str = "long") -> SignalMessage:
    """Create a test signal message."""
    return SignalMessage(
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        direction=direction,
        setup_type="VWAP_RECLAIM",
        score=8.5,
        confidence="A+",
        entry_price=2000.0,
        sl_price=1995.0 if direction == "long" else 2005.0,
        tp_price=2010.0 if direction == "long" else 1990.0,
        factors={},
    )


class TestStateMachineManagerCreate:
    """Tests for create_from_signal."""

    @pytest.mark.asyncio
    async def test_creates_state_machine(self) -> None:
        """Creates state machine from signal."""
        mock_db_pool = AsyncMock()
        mock_db_pool.execute = AsyncMock()

        manager = StateMachineManager(mock_db_pool)
        signal = create_signal_message(direction="long")

        result = await manager.create_from_signal(signal)

        assert result == signal.id
        assert signal.id in manager._state_machines

        sm = manager.get_state_machine(signal.id)
        assert sm is not None
        assert sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE
        assert sm.reclaim_direction == "above"

    @pytest.mark.asyncio
    async def test_creates_short_state_machine(self) -> None:
        """Creates state machine for short signal."""
        mock_db_pool = AsyncMock()
        mock_db_pool.execute = AsyncMock()

        manager = StateMachineManager(mock_db_pool)
        signal = create_signal_message(direction="short")

        await manager.create_from_signal(signal)

        sm = manager.get_state_machine(signal.id)
        assert sm is not None
        assert sm.reclaim_direction == "below"


class TestStateMachineManagerConfirmation:
    """Tests for check_confirmation."""

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_signal(self) -> None:
        """Returns False for unknown signal."""
        mock_db_pool = AsyncMock()
        manager = StateMachineManager(mock_db_pool)

        result = manager.check_confirmation("unknown-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_auto_confirms_after_one_bar(self) -> None:
        """Auto-confirms after one bar."""
        mock_db_pool = AsyncMock()
        mock_db_pool.execute = AsyncMock()

        manager = StateMachineManager(mock_db_pool)
        manager._bar_counter = 10

        signal = create_signal_message()
        await manager.create_from_signal(signal)

        # At detection bar, not confirmed
        result = manager.check_confirmation(signal.id, bar_idx=10)
        assert result is False

        # After one bar, should auto-confirm
        result = manager.check_confirmation(signal.id, bar_idx=11)
        assert result is True


class TestStateMachineManagerExpiration:
    """Tests for check_expiration."""

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_signal(self) -> None:
        """Returns False for unknown signal."""
        mock_db_pool = AsyncMock()
        manager = StateMachineManager(mock_db_pool)

        result = manager.check_expiration("unknown-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_expires_after_window(self) -> None:
        """Expires after max confirm window."""
        mock_db_pool = AsyncMock()
        mock_db_pool.execute = AsyncMock()

        manager = StateMachineManager(mock_db_pool)
        manager._bar_counter = 0

        signal = create_signal_message()
        await manager.create_from_signal(signal)

        # Not expired at detection
        result = manager.check_expiration(signal.id, bar_idx=0)
        assert result is False

        # Expired after window (10 bars + 1)
        result = manager.check_expiration(signal.id, bar_idx=15)
        assert result is True


class TestStateMachineManagerExecute:
    """Tests for execute."""

    @pytest.mark.asyncio
    async def test_execute_marks_executed(self) -> None:
        """Execute marks state machine as executed."""
        mock_db_pool = AsyncMock()
        mock_db_pool.execute = AsyncMock()

        manager = StateMachineManager(mock_db_pool)
        signal = create_signal_message()
        await manager.create_from_signal(signal)

        # Confirm first
        manager.check_confirmation(signal.id, bar_idx=1)

        # Execute
        await manager.execute(signal.id, bar_idx=2)

        sm = manager.get_state_machine(signal.id)
        assert sm is not None
        assert sm.current_state == VWAPReclaimState.EXECUTED

    @pytest.mark.asyncio
    async def test_execute_unknown_signal_logs_warning(self) -> None:
        """Execute with unknown signal logs warning."""
        mock_db_pool = AsyncMock()
        manager = StateMachineManager(mock_db_pool)

        # Should not raise, just log warning
        await manager.execute("unknown-id", bar_idx=1)


class TestStateMachineManagerInvalidate:
    """Tests for invalidate."""

    @pytest.mark.asyncio
    async def test_invalidate_marks_invalidated(self) -> None:
        """Invalidate marks state machine as invalidated."""
        mock_db_pool = AsyncMock()
        mock_db_pool.execute = AsyncMock()

        manager = StateMachineManager(mock_db_pool)
        signal = create_signal_message()
        await manager.create_from_signal(signal)

        await manager.invalidate(signal.id, bar_idx=1, reason="HTF_BREAK")

        sm = manager.get_state_machine(signal.id)
        assert sm is not None
        assert sm.current_state == VWAPReclaimState.INVALIDATED

    @pytest.mark.asyncio
    async def test_invalidate_unknown_signal_logs_warning(self) -> None:
        """Invalidate with unknown signal logs warning."""
        mock_db_pool = AsyncMock()
        manager = StateMachineManager(mock_db_pool)

        # Should not raise, just log warning
        await manager.invalidate("unknown-id", bar_idx=1, reason="TEST")


class TestStateMachineManagerBarCounter:
    """Tests for bar counter."""

    def test_increment_bar_counter(self) -> None:
        """Increments bar counter."""
        mock_db_pool = MagicMock()
        manager = StateMachineManager(mock_db_pool)

        assert manager._bar_counter == 0

        manager.increment_bar_counter()
        assert manager._bar_counter == 1

        manager.increment_bar_counter()
        assert manager._bar_counter == 2


class TestStateMachineManagerGetStateMachine:
    """Tests for get_state_machine."""

    def test_returns_none_for_unknown(self) -> None:
        """Returns None for unknown signal."""
        mock_db_pool = MagicMock()
        manager = StateMachineManager(mock_db_pool)

        result = manager.get_state_machine("unknown-id")

        assert result is None
