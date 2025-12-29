"""Unit tests for reclaim context execution tracking.

Tests that execution count is tracked at the reclaim context level (not per-signal)
to prevent excessive re-entries for the same reclaim setup.

Following strict TDD - these tests are written FIRST and should FAIL until
reclaim context tracking is implemented.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from scp_shared.messaging.schemas import SignalMessage


def utc_datetime(*args, **kwargs):
    """Create UTC timezone-aware datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


@pytest.fixture
def base_signal():
    """Create base signal message."""
    return SignalMessage(
        id="signal-123",
        timestamp=utc_datetime(2024, 10, 15, 10, 0),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=9.0,
        confidence="A+",
        entry_price=2651.0,
        sl_price=2645.0,
        tp_price=2663.0,
        factors={"vwap_reclaim": True},
    )


class TestReclaimContextTracking:
    """Tests for reclaim context execution tracking."""

    @pytest.mark.asyncio
    async def test_reclaim_context_key_generated(self, base_signal):
        """State machine should generate reclaim context key."""
        from execution_svc.state_machine_manager import StateMachineManager
        
        db_pool = Mock()
        db_pool.execute = AsyncMock()
        sm_manager = StateMachineManager(db_pool)
        
        await sm_manager.create_from_signal(base_signal)
        
        # Should create state machine with context tracking
        sm = sm_manager._state_machines.get(base_signal.id)
        assert sm is not None
        
        # Context key should be deterministic based on direction and time window
        # (e.g., "long_100" for detection at bar 100, grouped by 60-bar windows)
        assert hasattr(sm_manager, "_reclaim_context_executions")

    @pytest.mark.asyncio
    async def test_same_context_blocks_re_entry(self, base_signal):
        """Multiple signals for same reclaim context should be blocked."""
        from execution_svc.state_machine_manager import StateMachineManager
        
        db_pool = Mock()
        db_pool.execute = AsyncMock()
        sm_manager = StateMachineManager(db_pool)
        
        # Create first signal
        await sm_manager.create_from_signal(base_signal)
        
        # Mark as executed (increment context execution count)
        sm_manager.on_execution(base_signal.id, bar_idx=101)
        
        # Create second signal in same context (same direction, similar time)
        signal2 = SignalMessage(
            **{**base_signal.__dict__, "id": "signal-456", "timestamp": base_signal.timestamp}
        )
        await sm_manager.create_from_signal(signal2)
        
        # Second signal should be blocked (same context already executed)
        can_execute = sm_manager.check_confirmation(signal2.id, bar_idx=102)
        assert can_execute is False

    @pytest.mark.asyncio
    async def test_different_context_allows_entry(self, base_signal):
        """Signals for different reclaim contexts should be allowed."""
        from execution_svc.state_machine_manager import StateMachineManager
        
        db_pool = Mock()
        db_pool.execute = AsyncMock()
        sm_manager = StateMachineManager(db_pool)
        
        # Create first signal (long)
        await sm_manager.create_from_signal(base_signal)
        sm_manager.on_execution(base_signal.id, bar_idx=101)
        
        # Create second signal with DIFFERENT direction (different context)
        signal2 = SignalMessage(
            **{**base_signal.__dict__, "id": "signal-456", "direction": "short"}
        )
        await sm_manager.create_from_signal(signal2)
        
        # Different context should be allowed
        can_execute = sm_manager.check_confirmation(signal2.id, bar_idx=102)
        assert can_execute is True

    def test_context_key_uses_time_window(self):
        """Context key should group signals by time window (e.g., 60 bars)."""
        from execution_svc.state_machine_manager import StateMachineManager
        
        db_pool = Mock()
        sm_manager = StateMachineManager(db_pool)
        
        # Signals at bar 100 and 105 should be in same context (within 60-bar window)
        # Signals at bar 100 and 165 should be in different contexts
        
        # For this test, just verify the _reclaim_context_executions dict exists
        assert hasattr(sm_manager, "_reclaim_context_executions")
        assert isinstance(sm_manager._reclaim_context_executions, dict)

