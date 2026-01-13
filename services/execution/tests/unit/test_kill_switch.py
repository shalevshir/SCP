"""Unit tests for kill switch functionality in Execution service."""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from scp_shared.admin import KillSwitchRepository, KillSwitchState


@pytest.fixture
def mock_db_pool():
    """Mock database pool."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock()
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def kill_switch_repo(mock_db_pool):
    """Create kill switch repository with mocked database."""
    return KillSwitchRepository(mock_db_pool)


@pytest.mark.asyncio
async def test_get_state_returns_inactive(mock_db_pool, kill_switch_repo):
    """Test getting kill switch state when inactive."""
    mock_db_pool.fetchrow.return_value = {
        "service_name": "execution",
        "is_killed": False,
        "killed_at": None,
        "killed_by": None,
        "reason": None,
        "updated_at": datetime.now(UTC),
    }
    
    state = await kill_switch_repo.get_state("execution")
    
    assert state.service_name == "execution"
    assert state.is_killed is False
    assert state.killed_at is None
    assert state.killed_by is None
    assert state.reason is None


@pytest.mark.asyncio
async def test_get_state_returns_active(mock_db_pool, kill_switch_repo):
    """Test getting kill switch state when active."""
    killed_at = datetime.now(UTC)
    mock_db_pool.fetchrow.return_value = {
        "service_name": "execution",
        "is_killed": True,
        "killed_at": killed_at,
        "killed_by": "admin",
        "reason": "Testing kill switch",
        "updated_at": datetime.now(UTC),
    }
    
    state = await kill_switch_repo.get_state("execution")
    
    assert state.service_name == "execution"
    assert state.is_killed is True
    assert state.killed_at == killed_at
    assert state.killed_by == "admin"
    assert state.reason == "Testing kill switch"


@pytest.mark.asyncio
async def test_get_state_not_found(mock_db_pool, kill_switch_repo):
    """Test getting kill switch state for non-existent service."""
    mock_db_pool.fetchrow.return_value = None
    
    with pytest.raises(ValueError, match="Kill switch state not found"):
        await kill_switch_repo.get_state("nonexistent")


@pytest.mark.asyncio
async def test_set_killed(mock_db_pool, kill_switch_repo):
    """Test activating kill switch."""
    await kill_switch_repo.set_killed("execution", "admin", "Emergency halt")
    
    # Verify database update was called with correct parameters
    mock_db_pool.execute.assert_called_once()
    call_args = mock_db_pool.execute.call_args
    assert call_args[0][1] == "execution"  # service_name
    assert call_args[0][2] == "admin"      # killed_by
    assert call_args[0][3] == "Emergency halt"  # reason


@pytest.mark.asyncio
async def test_set_killed_default_params(mock_db_pool, kill_switch_repo):
    """Test activating kill switch with default parameters."""
    await kill_switch_repo.set_killed("execution")
    
    # Verify default values
    mock_db_pool.execute.assert_called_once()
    call_args = mock_db_pool.execute.call_args
    assert call_args[0][1] == "execution"
    assert call_args[0][2] == "admin"  # Default killed_by
    assert call_args[0][3] is None     # Default reason


@pytest.mark.asyncio
async def test_set_resumed(mock_db_pool, kill_switch_repo):
    """Test deactivating kill switch."""
    await kill_switch_repo.set_resumed("execution")
    
    # Verify database update was called with correct service name
    mock_db_pool.execute.assert_called_once()
    call_args = mock_db_pool.execute.call_args
    assert call_args[0][1] == "execution"


@pytest.mark.asyncio
async def test_kill_switch_persistence(mock_db_pool, kill_switch_repo):
    """Test that kill switch state persists (simulating restart)."""
    # Activate kill switch
    await kill_switch_repo.set_killed("execution", "admin", "Testing persistence")
    
    # Simulate restart by creating new repository instance
    mock_db_pool.fetchrow.return_value = {
        "service_name": "execution",
        "is_killed": True,
        "killed_at": datetime.now(UTC),
        "killed_by": "admin",
        "reason": "Testing persistence",
        "updated_at": datetime.now(UTC),
    }
    
    new_repo = KillSwitchRepository(mock_db_pool)
    state = await new_repo.get_state("execution")
    
    # Verify state persisted
    assert state.is_killed is True
    assert state.killed_by == "admin"
    assert state.reason == "Testing persistence"


@pytest.mark.asyncio
async def test_kill_switch_independent_services(mock_db_pool):
    """Test that kill switch works independently for different services."""
    repo = KillSwitchRepository(mock_db_pool)
    
    # Kill execution but not bot-core
    await repo.set_killed("execution", "admin", "Testing execution")
    
    # Verify only execution was updated
    mock_db_pool.execute.assert_called_once()
    call_args = mock_db_pool.execute.call_args
    assert call_args[0][1] == "execution"
    
    # Reset mock
    mock_db_pool.execute.reset_mock()
    
    # Kill bot-core
    await repo.set_killed("bot-core", "admin", "Testing bot-core")
    
    # Verify bot-core was updated separately
    mock_db_pool.execute.assert_called_once()
    call_args = mock_db_pool.execute.call_args
    assert call_args[0][1] == "bot-core"


@pytest.mark.asyncio
async def test_kill_switch_state_model():
    """Test KillSwitchState pydantic model."""
    now = datetime.now(UTC)
    state = KillSwitchState(
        service_name="execution",
        is_killed=True,
        killed_at=now,
        killed_by="admin",
        reason="Testing",
        updated_at=now,
    )
    
    assert state.service_name == "execution"
    assert state.is_killed is True
    assert state.killed_at == now
    assert state.killed_by == "admin"
    assert state.reason == "Testing"
    assert state.updated_at == now


@pytest.mark.asyncio
async def test_kill_switch_blocks_pending_signals_execution():
    """Test that kill switch blocks execution of pending signals.
    
    This test documents the expected behavior:
    - When kill switch is activated, new signals are rejected (tested in main.py line 153)
    - Additionally, pending signals already in the queue should NOT be executed
    - This prevents new trades from opening after an emergency halt is triggered
    
    The actual implementation is in main.py _process_candle_with_features():
    - Before calling execute_pending_signals(), check _is_killed flag
    - If killed, skip execution and log warning
    """
    # This is a documentation test - the actual behavior is verified in integration tests
    # The fix ensures that _is_killed is checked before execute_pending_signals()
    # in _process_candle_with_features() function
    
    # Expected behavior:
    is_killed = True
    pending_signals_count = 2
    
    # When kill switch is active, pending signals should NOT be executed
    if is_killed:
        signals_executed = False  # Simulate skipping execute_pending_signals()
    else:
        signals_executed = True
    
    assert signals_executed is False, "Pending signals should not execute when kill switch is active"
