"""Unit tests for state machine UUID key mismatch bug."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from execution_svc.state_machine_manager import StateMachineManager
from scp_shared.database import DatabasePool


@pytest.fixture
def mock_db_pool() -> DatabasePool:
    """Create mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


class TestStateMachineUUIDKeyMismatch:
    """Test that restored state machines are accessible after restart.
    
    Bug: restore_from_db uses UUID objects as keys, but all lookup methods
    expect string keys, causing restored state machines to be inaccessible.
    """
    
    @pytest.mark.asyncio
    async def test_restored_state_machine_accessible_by_string_key(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test that state machines restored from DB are accessible using string signal_id.
        
        Bug demonstration:
        1. Database returns signal_id as UUID object (asyncpg behavior)
        2. restore_from_db stores using UUID as key: _state_machines[uuid_obj] = sm
        3. All lookup methods pass string signal_id
        4. get_state_machine(signal_id_str) fails because uuid_obj != signal_id_str
        
        Expected after fix:
        - State machines should be stored with string keys
        - Lookup by string signal_id should succeed
        """
        # Create signal ID (as it would be in messages)
        signal_id_str = str(uuid4())
        signal_id_uuid = UUID(signal_id_str)
        
        # Mock database to return state machine row with UUID type
        # (this is what asyncpg does for UUID columns)
        mock_db_pool.fetch.return_value = [
            {
                "signal_id": signal_id_uuid,  # UUID object, not string!
                "state": "pending",  # VWAPReclaimState.PENDING_ACCEPTANCE value
                "detection_bar_idx": 100,
                "reclaim_direction": "long",  # DB format: "long"/"short", not "above"/"below"
                "confirmations": [],
                "execution_count": 0,
            }
        ]
        
        # Create manager and restore state machines
        manager = StateMachineManager(mock_db_pool)
        restored_count = await manager.restore_from_db()
        
        assert restored_count == 1
        
        # BUG VERIFICATION: Try to access state machine using string key
        # This is how all other methods access state machines
        sm = manager.get_state_machine(signal_id_str)
        
        # This should NOT be None after the fix
        assert sm is not None, (
            f"State machine not accessible with string key '{signal_id_str}'. "
            f"Keys in dict: {list(manager._state_machines.keys())}"
        )
        
        # Verify it's the correct state machine
        assert sm.detection_bar_idx == 100
        assert sm.reclaim_direction == "above"
    
    @pytest.mark.asyncio
    async def test_check_confirmation_works_after_restore(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test that check_confirmation works with restored state machines.
        
        This is a real-world scenario: after restart, we need to check
        if restored signals are confirmed.
        """
        signal_id_str = str(uuid4())
        signal_id_uuid = UUID(signal_id_str)
        
        mock_db_pool.fetch.return_value = [
            {
                "signal_id": signal_id_uuid,
                "state": "pending",
                "detection_bar_idx": 100,
                "reclaim_direction": "long",  # DB format: "long"/"short"
                "confirmations": [],
                "execution_count": 0,
            }
        ]
        
        manager = StateMachineManager(mock_db_pool)
        manager._bar_counter = 101  # One bar after detection
        
        await manager.restore_from_db()
        
        # Try to check confirmation using string signal_id
        # This should work after the fix
        is_confirmed = manager.check_confirmation(signal_id_str, bar_idx=101)
        
        # Should be able to check (not raise exception or return False due to missing key)
        # The actual confirmation logic will run
        assert is_confirmed is not None  # At minimum, shouldn't crash
    
    @pytest.mark.asyncio
    async def test_execute_works_after_restore(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test that execute works with restored state machines."""
        signal_id_str = str(uuid4())
        signal_id_uuid = UUID(signal_id_str)
        
        mock_db_pool.fetch.return_value = [
            {
                "signal_id": signal_id_uuid,
                "state": "confirmed",  # Ready to execute
                "detection_bar_idx": 100,
                "reclaim_direction": "long",  # DB format: "long"/"short"
                "confirmations": ["vwap_hold"],
                "execution_count": 0,
            }
        ]
        
        manager = StateMachineManager(mock_db_pool)
        await manager.restore_from_db()
        
        # Try to execute using string signal_id
        # This should work after the fix
        await manager.execute(signal_id_str, bar_idx=102)
        
        # Verify execution was tracked
        sm = manager.get_state_machine(signal_id_str)
        assert sm is not None
        assert sm.execution_count == 1
    
    @pytest.mark.asyncio
    async def test_multiple_restored_state_machines_all_accessible(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test that multiple restored state machines are all accessible."""
        signal_ids = [
            (str(uuid4()), UUID(str(uuid4())))
            for _ in range(3)
        ]
        
        # Use the same UUID for both string and UUID versions
        signal_ids = [
            (str(uuid_val), uuid_val)
            for uuid_val in [uuid4(), uuid4(), uuid4()]
        ]
        
        mock_db_pool.fetch.return_value = [
            {
                "signal_id": uuid_obj,
                "state": "pending",
                "detection_bar_idx": 100 + i,
                "reclaim_direction": "long",  # DB format: "long"/"short"
                "confirmations": [],
                "execution_count": 0,
            }
            for i, (str_id, uuid_obj) in enumerate(signal_ids)
        ]
        
        manager = StateMachineManager(mock_db_pool)
        restored_count = await manager.restore_from_db()
        
        assert restored_count == 3
        
        # All should be accessible by their string IDs
        for str_id, uuid_obj in signal_ids:
            sm = manager.get_state_machine(str_id)
            assert sm is not None, f"Signal {str_id} not accessible"

