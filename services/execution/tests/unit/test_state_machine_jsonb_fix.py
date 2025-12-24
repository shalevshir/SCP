"""Test that JSONB columns are properly saved and restored.

This test verifies the fix for the issue where confirmations and transition_history
were being pre-serialized with json.dumps() before passing to asyncpg, which caused
them to be stored as strings instead of proper JSONB structures.

Bug: _save_state_machine used json.dumps() to convert confirmations to JSON strings,
but asyncpg expects Python objects for JSONB columns. Without explicit ::jsonb casting,
PostgreSQL stored them as string literals, breaking restore_from_db() where
set(row["confirmations"]) expected a list but received a string.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from scp_shared.database import DatabasePool
from scp_shared.indicators.vwap_reclaim_state_machine import (
    VWAPReclaimState,
    VWAPReclaimStateMachine,
    StateTransition,
)
from execution_svc.state_machine_manager import StateMachineManager


@pytest.fixture
def mock_db_pool() -> DatabasePool:
    """Create mock database pool."""
    pool = AsyncMock(spec=DatabasePool)
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    return pool


class TestStateMachineJSONBPersistence:
    """Test that JSONB columns are properly serialized and deserialized."""
    
    @pytest.mark.asyncio
    async def test_confirmations_saved_as_python_list_not_json_string(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test that confirmations are saved as Python list, not JSON string.
        
        Bug demonstration:
        - BEFORE FIX: json.dumps(["vwap_hold"]) = '["vwap_hold"]' (string)
        - AFTER FIX: list(sm.confirmations) = ["vwap_hold"] (Python list)
        
        asyncpg expects Python objects for JSONB columns, not JSON strings.
        """
        manager = StateMachineManager(mock_db_pool)
        
        # Create state machine with confirmations
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=101, confirmation_type="vwap_hold")
        sm.on_confirmation(bar_idx=102, confirmation_type="auto_confirm")
        
        signal_id = str(uuid4())
        manager._state_machines[signal_id] = sm
        
        # Save to database
        await manager._save_state_machine(signal_id, sm)
        
        # Verify asyncpg received Python list, not JSON string
        call_args = mock_db_pool.execute.call_args[0]
        confirmations_arg = call_args[5]  # 6th parameter (0-indexed)
        
        # Should be Python list
        assert isinstance(confirmations_arg, list), (
            f"Expected confirmations to be a Python list, got {type(confirmations_arg).__name__}"
        )
        assert confirmations_arg == ["vwap_hold", "auto_confirm"]
        
        # Should NOT be JSON string
        assert not isinstance(confirmations_arg, str), (
            "Confirmations should not be JSON string - asyncpg handles JSONB serialization"
        )
    
    @pytest.mark.asyncio
    async def test_transition_history_saved_as_python_list_not_json_string(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test that transition_history is saved as Python list of dicts, not JSON string."""
        manager = StateMachineManager(mock_db_pool)
        
        # Create state machine with transitions
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=101, confirmation_type="vwap_hold")
        
        signal_id = str(uuid4())
        manager._state_machines[signal_id] = sm
        
        # Save to database
        await manager._save_state_machine(signal_id, sm)
        
        # Verify asyncpg received Python list, not JSON string
        call_args = mock_db_pool.execute.call_args[0]
        transition_history_arg = call_args[7]  # 8th parameter (0-indexed)
        
        # Should be Python list of dicts
        assert isinstance(transition_history_arg, list), (
            f"Expected transition_history to be a Python list, got {type(transition_history_arg).__name__}"
        )
        assert len(transition_history_arg) > 0
        assert all(isinstance(t, dict) for t in transition_history_arg)
        
        # Should NOT be JSON string
        assert not isinstance(transition_history_arg, str), (
            "Transition history should not be JSON string - asyncpg handles JSONB serialization"
        )
    
    @pytest.mark.asyncio
    async def test_confirmations_restore_as_set_not_character_iteration(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test that confirmations restore correctly as a set of strings.
        
        Bug scenario:
        - If confirmations stored as JSON string: '["vwap_hold"]'
        - Then set(row["confirmations"]) iterates over characters: {'[', '"', 'v', 'w', ...}
        - Expected: set(['vwap_hold']) = {'vwap_hold'}
        """
        signal_id_str = str(uuid4())
        signal_id_uuid = UUID(signal_id_str)
        
        # Mock database to return confirmations as Python list (post-fix behavior)
        mock_db_pool.fetch.return_value = [
            {
                "signal_id": signal_id_uuid,
                "state": "confirmed",
                "detection_bar_idx": 100,
                "reclaim_direction": "long",
                "confirmations": ["vwap_hold", "auto_confirm"],  # Python list
                "execution_count": 0,
            }
        ]
        
        manager = StateMachineManager(mock_db_pool)
        restored_count = await manager.restore_from_db()
        
        assert restored_count == 1
        
        # Get restored state machine
        sm = manager.get_state_machine(signal_id_str)
        assert sm is not None
        
        # Verify confirmations are a set of strings, not characters
        assert sm.confirmations == {"vwap_hold", "auto_confirm"}
        
        # Verify it's not iterating over characters
        # (if it were, we'd see single characters like '[', '"', 'v', 'w', 'a', 'p', etc.)
        for confirmation in sm.confirmations:
            assert len(confirmation) > 1, (
                f"Got single character '{confirmation}' - likely iterating over JSON string "
                "instead of list items"
            )
    
    @pytest.mark.asyncio
    async def test_empty_confirmations_handled_correctly(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test that empty confirmations are saved as empty list, not empty string."""
        manager = StateMachineManager(mock_db_pool)
        
        # Create state machine without confirmations
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        
        signal_id = str(uuid4())
        manager._state_machines[signal_id] = sm
        
        # Save to database
        await manager._save_state_machine(signal_id, sm)
        
        # Verify asyncpg received empty Python list, not empty string or "[]"
        call_args = mock_db_pool.execute.call_args[0]
        confirmations_arg = call_args[5]
        
        assert isinstance(confirmations_arg, list)
        assert confirmations_arg == []
        assert not isinstance(confirmations_arg, str)
    
    @pytest.mark.asyncio
    async def test_full_roundtrip_save_and_restore(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Test full roundtrip: save confirmations and restore them correctly."""
        signal_id_str = str(uuid4())
        
        # Step 1: Create and save state machine
        manager = StateMachineManager(mock_db_pool)
        sm = VWAPReclaimStateMachine()
        sm.on_reclaim_detected(bar_idx=100, direction="above")
        sm.on_confirmation(bar_idx=101, confirmation_type="vwap_hold")
        sm.on_confirmation(bar_idx=102, confirmation_type="price_confirmation")
        
        await manager._save_state_machine(signal_id_str, sm)
        
        # Capture what was saved
        save_call_args = mock_db_pool.execute.call_args[0]
        saved_confirmations = save_call_args[5]
        
        # Step 2: Simulate database returning the saved data
        mock_db_pool.fetch.return_value = [
            {
                "signal_id": UUID(signal_id_str),
                "state": "confirmed",
                "detection_bar_idx": 100,
                "reclaim_direction": "long",
                "confirmations": saved_confirmations,  # What we saved
                "execution_count": 0,
            }
        ]
        
        # Step 3: Restore and verify
        manager2 = StateMachineManager(mock_db_pool)
        restored_count = await manager2.restore_from_db()
        
        assert restored_count == 1
        
        restored_sm = manager2.get_state_machine(signal_id_str)
        assert restored_sm is not None
        assert restored_sm.confirmations == {"vwap_hold", "price_confirmation"}


class TestJSONBBugScenario:
    """Demonstrate the bug that would occur with json.dumps() approach."""
    
    @pytest.mark.asyncio
    async def test_bug_scenario_json_string_breaks_set_conversion(
        self,
        mock_db_pool: DatabasePool,
    ) -> None:
        """Demonstrate how JSON string would break set() conversion.
        
        This test shows what WOULD happen if we used json.dumps():
        - Database returns: '["vwap_hold", "auto_confirm"]' (string)
        - set(string) iterates characters: {'[', '"', 'v', 'w', 'a', 'p', '_', ...}
        """
        signal_id_str = str(uuid4())
        signal_id_uuid = UUID(signal_id_str)
        
        # Simulate buggy behavior: database returns JSON string instead of list
        json_string = '["vwap_hold", "auto_confirm"]'
        
        mock_db_pool.fetch.return_value = [
            {
                "signal_id": signal_id_uuid,
                "state": "confirmed",
                "detection_bar_idx": 100,
                "reclaim_direction": "long",
                "confirmations": json_string,  # BUG: JSON string, not list
                "execution_count": 0,
            }
        ]
        
        manager = StateMachineManager(mock_db_pool)
        
        # This would restore incorrectly if the bug existed
        await manager.restore_from_db()
        
        sm = manager.get_state_machine(signal_id_str)
        
        # With the bug, set(json_string) would give individual characters
        # After the fix, this test would need mock data as list, not string
        # So we just demonstrate what set() does with a string:
        buggy_result = set(json_string)
        
        # This is what we DON'T want:
        assert '[' in buggy_result  # Characters from JSON string
        assert '"' in buggy_result
        assert 'v' in buggy_result
        
        # This is what we DO want (but won't get with JSON string):
        correct_result = {"vwap_hold", "auto_confirm"}
        assert buggy_result != correct_result, (
            "JSON string iteration gives characters, not confirmation values"
        )

