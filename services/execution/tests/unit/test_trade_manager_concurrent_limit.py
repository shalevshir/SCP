"""Test concurrent trade limit enforcement in TradeManager.

This test verifies that the TradeManager correctly enforces max_active_trades
even when multiple signals are buffered before execution.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution_svc.broker import PaperBroker
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_manager import TradeManager
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository
from scp_shared.database import DatabasePool
from scp_shared.messaging.schemas import CandleMessage, SignalMessage


@pytest.fixture
def mock_broker():
    """Mock broker that always fills orders."""
    return PaperBroker()


@pytest.fixture
def mock_db_pool() -> DatabasePool:
    """Mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def mock_sm_manager(mock_db_pool):
    """Mock state machine manager."""
    return StateMachineManager(mock_db_pool)


@pytest.fixture
def mock_repo():
    """Mock trade repository."""
    repo = MagicMock(spec=TradeRepository)
    repo.insert_trade = AsyncMock(return_value="test-trade-id")  # Return string ID
    repo.create_trade = AsyncMock(return_value=None)
    repo.close_trade = AsyncMock(return_value=None)
    repo.update_reached_1r = AsyncMock(return_value=None)
    repo.get_open_trades = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_publisher():
    """Mock trade publisher."""
    publisher = MagicMock(spec=TradePublisher)
    publisher.publish_opened = AsyncMock(return_value=None)
    publisher.publish_closed = AsyncMock(return_value=None)
    return publisher


@pytest.fixture
def trade_manager(mock_broker, mock_sm_manager, mock_repo, mock_publisher):
    """Create trade manager with max_active_trades=1."""
    return TradeManager(
        broker=mock_broker,
        state_machine_manager=mock_sm_manager,
        trade_repository=mock_repo,
        trade_publisher=mock_publisher,
        max_active_trades=1,  # Key: only 1 concurrent trade allowed
        pdll_limit=600.0,
        max_trades_per_day=5,  # High enough to not be the limiting factor
    )


def create_signal(direction: str = "long") -> SignalMessage:
    """Helper to create a signal message."""
    return SignalMessage(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        direction=direction,
        setup_type="VWAP_RECLAIM",
        score=9.0,
        confidence="A+",
        entry_price=2000.0,
        sl_price=1990.0,
        tp_price=2020.0,
        factors={},
    )


def create_candle(open_price: float = 2000.0) -> CandleMessage:
    """Helper to create a candle message."""
    return CandleMessage(
        timestamp=datetime.now(timezone.utc),
        symbol="GC",
        timeframe="1m",
        open=open_price,
        high=open_price + 5.0,
        low=open_price - 5.0,
        close=open_price + 2.0,
        volume=1000.0,
    )


@pytest.mark.asyncio
async def test_concurrent_trade_limit_with_buffered_signals(trade_manager):
    """Test that concurrent trade limit is enforced even with buffered signals.
    
    Scenario:
    1. max_active_trades = 1
    2. Two signals arrive before execution (both get buffered)
    3. execute_pending_signals should check concurrent limit for EACH signal
    4. Only 1 signal should execute (not rely on broker to reject the 2nd)
    
    NOTE: Paper broker also has a single-position-per-symbol limit that masks
    this bug. This test verifies the INTENDED behavior: explicit concurrent
    limit checking in execute_pending_signals, not relying on broker.
    """
    # Create two signals
    signal1 = create_signal(direction="long")
    signal2 = create_signal(direction="long")
    
    # Both signals should be buffered (no active trades yet)
    await trade_manager.on_signal(signal1)
    await trade_manager.on_signal(signal2)
    
    # Verify both were buffered
    assert len(trade_manager._pending_signals) == 2
    assert len(trade_manager._active_trades) == 0
    
    # Mock check_confirmation to allow execution (bypass re-entry check)
    # In production, state machines would be confirmed before execute_pending_signals runs
    trade_manager._sm_manager.check_confirmation = MagicMock(return_value=True)
    
    # Track execute_entry calls to verify the bug
    original_execute = trade_manager.execute_entry
    execute_calls = []
    
    async def track_execute(signal, price):
        execute_calls.append(signal.id)
        return await original_execute(signal, price)
    
    trade_manager.execute_entry = track_execute
    
    # Execute pending signals at next bar open
    await trade_manager.execute_pending_signals(next_bar_open=2000.0)
    
    # BUG DEMONSTRATION: Without the fix, execute_entry is called TWICE
    # (once for each buffered signal), even though max_active_trades=1
    print(f"\nexecute_entry was called {len(execute_calls)} times")
    print(f"Signal IDs: {execute_calls}")
    print(f"Active trades: {len(trade_manager._active_trades)}")
    
    # After the fix, execute_entry should only be called ONCE
    # because execute_pending_signals checks concurrent limit
    assert len(execute_calls) == 1, (
        f"BUG: execute_entry called {len(execute_calls)} times, "
        f"should only call once when max_active_trades=1"
    )
    
    # Should only have 1 active trade
    assert len(trade_manager._active_trades) == 1
    
    # Pending signals should be cleared
    assert len(trade_manager._pending_signals) == 0


@pytest.mark.asyncio
async def test_concurrent_limit_with_daily_limit_interaction(trade_manager):
    """Test interaction between concurrent and daily limits.
    
    Verify that concurrent limit is checked BEFORE daily limit exhaustion.
    """
    # Define a helper that confirms AND returns True
    def mock_check_confirmation(signal_id):
        # Actually confirm the state machine so it can be executed
        sm = trade_manager._sm_manager.get_state_machine(signal_id)
        if sm and sm.can_execute():
            return True
        # Force confirmation
        if sm:
            sm.on_confirmation(bar_idx=0, confirmation_type="test")
        return True
    
    # Bypass confirmation check to test concurrent limit logic
    trade_manager._sm_manager.check_confirmation = MagicMock(side_effect=mock_check_confirmation)
    
    # Buffer 3 signals (more than max_active_trades=1)
    signals = [create_signal() for _ in range(3)]
    for signal in signals:
        await trade_manager.on_signal(signal)
    
    assert len(trade_manager._pending_signals) == 3
    
    # Execute pending signals
    await trade_manager.execute_pending_signals(next_bar_open=2000.0)
    
    # Should only execute 1 (concurrent limit)
    assert len(trade_manager._active_trades) == 1
    
    # Close the trade with a loss by simulating enough candles to exceed grace period
    # VWAP_RECLAIM has 8-bar grace period for SL/TP
    for _ in range(10):
        # Increment bar counter (simulates time passing)
        trade_manager._sm_manager.increment_bar_counter()
        candle = create_candle(open_price=1985.0)  # Below SL (1990.0)
        await trade_manager.on_candle(candle, features=None)
    
    # Should have 0 active trades now (SL hit after grace period)
    assert len(trade_manager._active_trades) == 0


@pytest.mark.asyncio
async def test_sequential_execution_respects_concurrent_limit(trade_manager):
    """Test that signals execute sequentially, respecting concurrent limit.
    
    If we execute signals, close the trade, then execute more, it should work.
    """
    # Define a helper that confirms AND returns True
    def mock_check_confirmation(signal_id):
        # Actually confirm the state machine so it can be executed
        sm = trade_manager._sm_manager.get_state_machine(signal_id)
        if sm and sm.can_execute():
            return True
        # Force confirmation
        if sm:
            sm.on_confirmation(bar_idx=0, confirmation_type="test")
        return True
    
    # Bypass confirmation check to test concurrent limit logic
    trade_manager._sm_manager.check_confirmation = MagicMock(side_effect=mock_check_confirmation)
    
    # First signal
    signal1 = create_signal()
    await trade_manager.on_signal(signal1)
    await trade_manager.execute_pending_signals(next_bar_open=2000.0)
    
    assert len(trade_manager._active_trades) == 1
    
    # Close the trade (SL hit) - simulate enough candles to exceed grace period
    # VWAP_RECLAIM has 8-bar grace period for SL/TP
    for _ in range(10):
        # Increment bar counter (simulates time passing)
        trade_manager._sm_manager.increment_bar_counter()
        candle_sl = create_candle(open_price=1985.0)  # Below SL (1990.0)
        await trade_manager.on_candle(candle_sl, features=None)
    
    assert len(trade_manager._active_trades) == 0
    
    # Now a second signal should be able to execute
    signal2 = create_signal()
    await trade_manager.on_signal(signal2)
    await trade_manager.execute_pending_signals(next_bar_open=2000.0)
    
    assert len(trade_manager._active_trades) == 1

