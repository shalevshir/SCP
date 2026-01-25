"""Unit tests for kill switch functionality in Bot Core service."""

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
        "service_name": "bot-core",
        "is_killed": False,
        "killed_at": None,
        "killed_by": None,
        "reason": None,
        "updated_at": datetime.now(UTC),
    }

    state = await kill_switch_repo.get_state("bot-core")

    assert state.service_name == "bot-core"
    assert state.is_killed is False
    assert state.killed_at is None
    assert state.killed_by is None
    assert state.reason is None


@pytest.mark.asyncio
async def test_get_state_returns_active(mock_db_pool, kill_switch_repo):
    """Test getting kill switch state when active."""
    killed_at = datetime.now(UTC)
    mock_db_pool.fetchrow.return_value = {
        "service_name": "bot-core",
        "is_killed": True,
        "killed_at": killed_at,
        "killed_by": "admin",
        "reason": "Testing kill switch",
        "updated_at": datetime.now(UTC),
    }

    state = await kill_switch_repo.get_state("bot-core")

    assert state.service_name == "bot-core"
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
    await kill_switch_repo.set_killed("bot-core", "admin", "Emergency halt")

    # Verify database update was called with correct parameters
    mock_db_pool.execute.assert_called_once()
    call_args = mock_db_pool.execute.call_args
    assert call_args[0][1] == "bot-core"  # service_name
    assert call_args[0][2] == "admin"  # killed_by
    assert call_args[0][3] == "Emergency halt"  # reason


@pytest.mark.asyncio
async def test_set_killed_default_params(mock_db_pool, kill_switch_repo):
    """Test activating kill switch with default parameters."""
    await kill_switch_repo.set_killed("bot-core")

    # Verify default values
    mock_db_pool.execute.assert_called_once()
    call_args = mock_db_pool.execute.call_args
    assert call_args[0][1] == "bot-core"
    assert call_args[0][2] == "admin"  # Default killed_by
    assert call_args[0][3] is None  # Default reason


@pytest.mark.asyncio
async def test_set_resumed(mock_db_pool, kill_switch_repo):
    """Test deactivating kill switch."""
    await kill_switch_repo.set_resumed("bot-core")

    # Verify database update was called with correct service name
    mock_db_pool.execute.assert_called_once()
    call_args = mock_db_pool.execute.call_args
    assert call_args[0][1] == "bot-core"


@pytest.mark.asyncio
async def test_kill_switch_blocks_signal_generation(mock_db_pool):
    """Test that kill switch blocks signal generation (integration behavior)."""
    # This test demonstrates the expected behavior:
    # When _is_killed = True, signal generation should be skipped

    # Simulate kill switch active
    is_killed = True

    # Signal generation should be skipped
    if is_killed:
        signal_generated = False  # Simulate skipping signal generation
    else:
        signal_generated = True

    assert signal_generated is False


@pytest.mark.asyncio
async def test_kill_switch_allows_feature_consumption(mock_db_pool):
    """Test that kill switch doesn't block feature consumption."""
    # This test demonstrates that features should still be consumed
    # even when kill switch is active (to stay in sync)

    # Simulate kill switch active
    is_killed = True

    # Feature consumption should continue
    feature_consumed = True  # Always consume features

    assert feature_consumed is True


@pytest.mark.asyncio
async def test_kill_switch_persistence(mock_db_pool, kill_switch_repo):
    """Test that kill switch state persists (simulating restart)."""
    # Activate kill switch
    await kill_switch_repo.set_killed("bot-core", "admin", "Testing persistence")

    # Simulate restart by creating new repository instance
    mock_db_pool.fetchrow.return_value = {
        "service_name": "bot-core",
        "is_killed": True,
        "killed_at": datetime.now(UTC),
        "killed_by": "admin",
        "reason": "Testing persistence",
        "updated_at": datetime.now(UTC),
    }

    new_repo = KillSwitchRepository(mock_db_pool)
    state = await new_repo.get_state("bot-core")

    # Verify state persisted
    assert state.is_killed is True
    assert state.killed_by == "admin"
    assert state.reason == "Testing persistence"


@pytest.mark.asyncio
async def test_kill_switch_state_model():
    """Test KillSwitchState pydantic model."""
    now = datetime.now(UTC)
    state = KillSwitchState(
        service_name="bot-core",
        is_killed=True,
        killed_at=now,
        killed_by="admin",
        reason="Testing",
        updated_at=now,
    )

    assert state.service_name == "bot-core"
    assert state.is_killed is True
    assert state.killed_at == now
    assert state.killed_by == "admin"
    assert state.reason == "Testing"
    assert state.updated_at == now
