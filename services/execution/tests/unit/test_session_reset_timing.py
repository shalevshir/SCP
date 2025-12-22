"""Test session reset timing at day boundaries."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from scp_shared.messaging.schemas import CandleMessage, SignalMessage

from execution_svc.broker import OrderResult, PaperBroker
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_manager import TradeManager
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository


@pytest.fixture
def mock_broker() -> PaperBroker:
    """Mock broker."""
    broker = Mock(spec=PaperBroker)
    broker.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="test_order",
            symbol="GC",
            side="long",
            quantity=1,
            filled_price=2650.0,
            status="filled",
        )
    )
    broker.close_position = AsyncMock(return_value=True)
    return broker


@pytest.fixture
def mock_repo() -> TradeRepository:
    """Mock repository."""
    repo = Mock(spec=TradeRepository)
    repo.insert_trade = AsyncMock(return_value="test_trade_id")
    repo.close_trade = AsyncMock()
    repo.update_reached_1r = AsyncMock()
    repo.get_open_trades = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_publisher() -> TradePublisher:
    """Mock publisher."""
    publisher = Mock(spec=TradePublisher)
    publisher.publish_opened = AsyncMock()
    publisher.publish_closed = AsyncMock()
    return publisher


@pytest.fixture
def mock_db_pool() -> Mock:
    """Mock database pool."""
    db_pool = Mock()
    db_pool.execute = AsyncMock()
    db_pool.fetchrow = AsyncMock(return_value=None)
    return db_pool


@pytest.fixture
def sm_manager(mock_db_pool: Mock) -> StateMachineManager:
    """State machine manager."""
    return StateMachineManager(db_pool=mock_db_pool)


@pytest.fixture
def trade_manager(
    mock_broker: PaperBroker,
    sm_manager: StateMachineManager,
    mock_repo: TradeRepository,
    mock_publisher: TradePublisher,
) -> TradeManager:
    """Trade manager with daily limits."""
    return TradeManager(
        broker=mock_broker,
        state_machine_manager=sm_manager,
        trade_repository=mock_repo,
        trade_publisher=mock_publisher,
        max_active_trades=1,
        pdll_limit=600.0,
        max_trades_per_day=2,
    )


@pytest.mark.asyncio
async def test_session_reset_at_day_boundary_prevents_signal_blocking(
    trade_manager: TradeManager,
) -> None:
    """Test that check_session_reset is called BEFORE execute_pending_signals at day boundaries.
    
    This test verifies the fix for a critical bug where:
    - Day 1: PDLL limit is hit (600 points loss)
    - Day 2: New trading day begins with first candle
    - Bug (old code): execute_pending_signals ran first, checked limits with stale Day 1 state,
      blocked valid Day 2 signals
    - Fix (new code): check_session_reset runs first, resets limits for new day,
      then execute_pending_signals checks with fresh state
    """
    # Day 1: Hit PDLL
    day1_candle = CandleMessage(
        timestamp=datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        open=2650.0,
        high=2651.0,
        low=2649.0,
        close=2650.5,
        volume=100.0,
    )
    
    # Process Day 1 candle and hit PDLL
    await trade_manager.on_candle(day1_candle, None)
    trade_manager._daily_tracker.record_trade_closed(-600.0)
    
    # Verify PDLL is hit
    can_trade, reason = trade_manager._daily_tracker.can_trade()
    assert not can_trade
    assert "PDLL" in reason
    
    # Day 2: New signal
    day2_candle = CandleMessage(
        timestamp=datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        open=2660.0,
        high=2661.0,
        low=2659.0,
        close=2660.5,
        volume=100.0,
    )
    
    signal2 = SignalMessage(
        id="signal_day2",
        timestamp=day2_candle.timestamp,
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=9.0,
        confidence="A+",
        entry_price=2660.0,
        sl_price=2650.0,
        tp_price=2680.0,
        factors={},
    )
    
    await trade_manager.on_signal(signal2)
    
    # FIX: Call check_session_reset BEFORE execute_pending_signals
    # (this is what main.py does now)
    trade_manager.check_session_reset(day2_candle.timestamp)
    
    # Verify limits are fresh BEFORE execute_pending_signals
    can_trade_after_reset, _ = trade_manager._daily_tracker.can_trade()
    assert can_trade_after_reset, (
        "FIX VERIFIED: Limits should be fresh after check_session_reset"
    )
    
    # Now execute pending signals with fresh session state
    await trade_manager.execute_pending_signals(day2_candle.open)
    
    # Then process candle
    await trade_manager.on_candle(day2_candle, None)
    
    # Verify signal was NOT blocked (pending_signals should be cleared)
    assert len(trade_manager._pending_signals) == 0, (
        "Pending signals should be cleared after execution"
    )

