"""Test daily state restoration after service restart.

This test verifies that daily P&L and trade count are restored from historical trades
when the service restarts, ensuring PDLL and trade limit enforcement remains consistent.
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from unittest.mock import MagicMock

from execution_svc.daily_state import DailyStateTracker
from execution_svc.trade_manager import TradeManager
from execution_svc.trade_repository import TradeRepository
from scp_shared.database import DatabasePool
from scp_shared.execution.types import TradeRecord


@pytest.fixture
def mock_db_pool():
    """Mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def mock_broker():
    """Mock broker client."""
    broker = AsyncMock()
    broker.place_order = AsyncMock(return_value=AsyncMock(status="filled", fill_price=2660.0))
    broker.close_position = AsyncMock(return_value=True)
    broker.reconcile_positions = AsyncMock()
    return broker


@pytest.fixture
def mock_state_machine_manager():
    """Mock state machine manager."""
    sm_mgr = AsyncMock()
    sm_mgr._bar_counter = 100
    sm_mgr.get_state_machine = AsyncMock(return_value=None)
    return sm_mgr


@pytest.fixture
def mock_trade_repository():
    """Mock trade repository."""
    repo = AsyncMock(spec=TradeRepository)
    return repo


@pytest.fixture
def mock_trade_publisher():
    """Mock trade publisher."""
    publisher = AsyncMock()
    return publisher


@pytest.mark.asyncio
async def test_daily_state_restored_on_startup(
    mock_broker,
    mock_state_machine_manager,
    mock_trade_repository,
    mock_trade_publisher,
    mock_db_pool,
):
    """Test that daily state (P&L and trade count) is restored from database on startup.
    
    Scenario:
        1. Service starts at 9am, executes 1 trade (loss of 50 points)
        2. Service restarts at 10am (same trading day)
        3. Daily state should be restored: trades_count=1, daily_pnl=-50
        4. Should respect daily limits (max_trades_per_day=2, so only 1 more trade allowed)
        5. Should have correct PDLL balance (600 - 50 = 550 points remaining)
    """
    # SETUP: Mock today's historical trades in database
    today = date.today()
    now = datetime.combine(today, datetime.now().time())
    
    # Trade 1: Closed with -50 point loss (opened at 9am, closed at 9:05am)
    trade1 = TradeRecord(
        trade_id="11111111-1111-1111-1111-111111111111",
        signal_id="22222222-2222-2222-2222-222222222222",
        symbol="GC",
        direction="long",
        setup_type="VWAP_RECLAIM",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2670.0,
        risk_amount=10.0,
        reward_amount=20.0,
        entry_timestamp=now - timedelta(hours=1),  # 9am
        exit_timestamp=now - timedelta(minutes=55),  # 9:05am
        exit_price=2640.0,  # Hit SL
        exit_reason="SL_HIT",
        pnl=-50.0,  # Loss of 50 points
        entry_bar_idx=50,
        reached_1r=False,
    )
    
    # Trade 2: Still open (opened at 9:30am)
    trade2 = TradeRecord(
        trade_id="33333333-3333-3333-3333-333333333333",
        signal_id="44444444-4444-4444-4444-444444444444",
        symbol="GC",
        direction="short",
        setup_type="VWAP_RECLAIM",
        entry_price=2660.0,
        sl_price=2670.0,
        tp_price=2640.0,
        risk_amount=10.0,
        reward_amount=20.0,
        entry_timestamp=now - timedelta(minutes=30),  # 9:30am
        entry_bar_idx=75,
        reached_1r=False,
    )
    
    # Mock repository to return today's trades
    mock_trade_repository.get_open_trades.return_value = [trade2]
    mock_trade_repository.get_trades_for_date.return_value = [trade1, trade2]
    
    # ACT: Create TradeManager and restore state (simulates service restart)
    trade_manager = TradeManager(
        broker=mock_broker,
        state_machine_manager=mock_state_machine_manager,
        trade_repository=mock_trade_repository,
        trade_publisher=mock_trade_publisher,
        db_pool=mock_db_pool,
        max_active_trades=1,
        pdll_limit=600.0,
        max_trades_per_day=2,
    )
    
    # This should restore both active trades AND daily state
    await trade_manager.restore_active_trades()
    
    # ASSERT: Daily state should be restored correctly
    daily_state = trade_manager._daily_tracker.state
    
    # Should have 2 trades today (1 closed, 1 open)
    assert daily_state.trades_count == 2, (
        f"Expected trades_count=2 (1 closed + 1 open), got {daily_state.trades_count}"
    )
    
    # Should have -50 points P&L (from closed trade)
    assert daily_state.daily_pnl == -50.0, (
        f"Expected daily_pnl=-50.0 (from closed trade), got {daily_state.daily_pnl}"
    )
    
    # Should have correct date
    assert daily_state.date == today, (
        f"Expected date={today}, got {daily_state.date}"
    )
    
    # Should NOT hit PDLL (600 - 50 = 550 remaining)
    assert not daily_state.pdll_hit, "PDLL should not be hit with -50 points loss"
    
    # ASSERT: Should block new trades (already at max_trades_per_day=2)
    can_trade, reason = trade_manager._daily_tracker.can_trade()
    assert not can_trade, "Should not be able to trade after reaching max_trades_per_day"
    assert reason == "MAX_TRADES", f"Expected MAX_TRADES halt code, got: {reason}"


@pytest.mark.asyncio
async def test_daily_state_allows_trading_below_pdll(
    mock_broker,
    mock_state_machine_manager,
    mock_trade_repository,
    mock_trade_publisher,
    mock_db_pool,
):
    """Test that trading is allowed when below PDLL limit after restoration."""
    today = date.today()
    now = datetime.combine(today, datetime.now().time())
    
    # Trade 1: Closed with -100 point loss (well below PDLL of 600)
    trade1 = TradeRecord(
        trade_id="11111111-1111-1111-1111-111111111111",
        signal_id="22222222-2222-2222-2222-222222222222",
        symbol="GC",
        direction="long",
        setup_type="VWAP_RECLAIM",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2670.0,
        risk_amount=10.0,
        reward_amount=20.0,
        entry_timestamp=now - timedelta(hours=1),
        exit_timestamp=now - timedelta(minutes=55),
        exit_price=2640.0,
        exit_reason="SL_HIT",
        pnl=-100.0,
        entry_bar_idx=50,
        reached_1r=False,
    )
    
    # Mock repository
    mock_trade_repository.get_open_trades.return_value = []
    mock_trade_repository.get_trades_for_date.return_value = [trade1]
    
    # Create and restore
    trade_manager = TradeManager(
        broker=mock_broker,
        state_machine_manager=mock_state_machine_manager,
        trade_repository=mock_trade_repository,
        trade_publisher=mock_trade_publisher,
        db_pool=mock_db_pool,
        max_active_trades=1,
        pdll_limit=600.0,
        max_trades_per_day=2,
    )
    
    await trade_manager.restore_active_trades()
    
    # Should allow trading (1 trade today, -100 points, both below limits)
    can_trade, reason = trade_manager._daily_tracker.can_trade()
    assert can_trade, f"Should allow trading below PDLL, but blocked: {reason}"
    
    # Check daily state
    daily_state = trade_manager._daily_tracker.state
    assert daily_state.trades_count == 1
    assert daily_state.daily_pnl == -100.0
    assert not daily_state.pdll_hit


@pytest.mark.asyncio
async def test_daily_state_blocks_trading_at_pdll(
    mock_broker,
    mock_state_machine_manager,
    mock_trade_repository,
    mock_trade_publisher,
    mock_db_pool,
):
    """Test that trading is blocked when PDLL is hit after restoration."""
    today = date.today()
    now = datetime.combine(today, datetime.now().time())
    
    # Trade 1: Closed with -600 point loss (exactly at PDLL limit)
    trade1 = TradeRecord(
        trade_id="11111111-1111-1111-1111-111111111111",
        signal_id="22222222-2222-2222-2222-222222222222",
        symbol="GC",
        direction="long",
        setup_type="VWAP_RECLAIM",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2670.0,
        risk_amount=10.0,
        reward_amount=20.0,
        entry_timestamp=now - timedelta(hours=1),
        exit_timestamp=now - timedelta(minutes=55),
        exit_price=2640.0,
        exit_reason="SL_HIT",
        pnl=-600.0,  # Exactly at PDLL limit
        entry_bar_idx=50,
        reached_1r=False,
    )
    
    # Mock repository
    mock_trade_repository.get_open_trades.return_value = []
    mock_trade_repository.get_trades_for_date.return_value = [trade1]
    
    # Create and restore
    trade_manager = TradeManager(
        broker=mock_broker,
        state_machine_manager=mock_state_machine_manager,
        trade_repository=mock_trade_repository,
        trade_publisher=mock_trade_publisher,
        db_pool=mock_db_pool,
        max_active_trades=1,
        pdll_limit=600.0,
        max_trades_per_day=2,
    )
    
    await trade_manager.restore_active_trades()
    
    # Should block trading (PDLL hit)
    can_trade, reason = trade_manager._daily_tracker.can_trade()
    assert not can_trade, "Should block trading when PDLL is hit"
    assert "PDLL" in reason, f"Expected PDLL reason, got: {reason}"
    
    # Check daily state
    daily_state = trade_manager._daily_tracker.state
    assert daily_state.trades_count == 1
    assert daily_state.daily_pnl == -600.0
    # Note: pdll_hit flag is set on first can_trade() check





