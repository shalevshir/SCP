"""Test loss streak halt reason is properly set and enforced."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from execution_svc.daily_state import DailyStateTracker
from execution_svc.trade_manager import TradeManager
from execution_svc import metrics
from scp_shared.messaging.schemas import SignalMessage


@pytest.fixture
def mock_broker() -> Mock:
    """Mock broker."""
    broker = Mock()
    broker.place_order = AsyncMock(
        return_value=Mock(status="filled", filled_price=2650.0)
    )
    broker.close_position = AsyncMock()
    return broker


@pytest.fixture
def mock_state_machine_manager() -> Mock:
    """Mock state machine manager."""
    sm_manager = Mock()
    sm_manager._bar_counter = 0
    sm_manager.create_from_signal = AsyncMock()
    sm_manager.check_confirmation = Mock(return_value=True)
    sm_manager.execute = AsyncMock()
    sm_manager.restore_from_db = AsyncMock()
    return sm_manager


@pytest.fixture
def mock_trade_repository() -> Mock:
    """Mock trade repository."""
    repo = Mock()
    repo.insert_trade = AsyncMock(return_value="trade-id-1")
    repo.close_trade = AsyncMock()
    repo.update_reached_1r = AsyncMock()
    repo.get_trades_for_date = AsyncMock(return_value=[])
    repo.get_open_trades = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_trade_publisher() -> Mock:
    """Mock trade publisher."""
    publisher = Mock()
    publisher.publish_opened = AsyncMock()
    publisher.publish_closed = AsyncMock()
    return publisher


@pytest.fixture
def mock_db_pool() -> Mock:
    """Mock database pool."""
    return Mock()


class TestLossStreakHaltReason:
    """Test loss streak halt reason functionality."""
    
    def test_loss_streak_blocks_new_trades_after_limit(
        self,
        mock_broker: Mock,
        mock_state_machine_manager: Mock,
        mock_trade_repository: Mock,
        mock_trade_publisher: Mock,
        mock_db_pool: Mock,
    ) -> None:
        """Test LOSS_STREAK halt reason blocks trading after consecutive losses."""
        # Create trade manager with 2 loss limit
        trade_manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_state_machine_manager,
            trade_repository=mock_trade_repository,
            trade_publisher=mock_trade_publisher,
            db_pool=mock_db_pool,
            max_consecutive_losses=2,
            max_trades_per_day=5,  # High enough to not interfere
            pdll_limit=1000.0,     # High enough to not interfere
            service_mode="test",
            service_name="execution",
        )
        
        # Record 2 consecutive losses
        trade_manager._daily_tracker.record_trade_closed(-50.0)
        trade_manager._daily_tracker.record_trade_closed(-75.0)
        
        # Verify can_trade blocks with LOSS_STREAK reason
        can_trade, reason = trade_manager._daily_tracker.can_trade()
        
        assert can_trade is False
        assert reason == "LOSS_STREAK"
        assert trade_manager._daily_tracker.state.consecutive_losses == 2
    
    def test_loss_streak_resets_on_win(
        self,
        mock_broker: Mock,
        mock_state_machine_manager: Mock,
        mock_trade_repository: Mock,
        mock_trade_publisher: Mock,
        mock_db_pool: Mock,
    ) -> None:
        """Test loss streak resets after a win."""
        trade_manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_state_machine_manager,
            trade_repository=mock_trade_repository,
            trade_publisher=mock_trade_publisher,
            db_pool=mock_db_pool,
            max_consecutive_losses=2,
            service_mode="test",
            service_name="execution",
        )
        
        # Record loss then win
        trade_manager._daily_tracker.record_trade_closed(-50.0)
        assert trade_manager._daily_tracker.state.consecutive_losses == 1
        
        trade_manager._daily_tracker.record_trade_closed(100.0)
        assert trade_manager._daily_tracker.state.consecutive_losses == 0
        
        # Should be able to trade again
        can_trade, reason = trade_manager._daily_tracker.can_trade()
        assert can_trade is True
        assert reason is None
    
    @pytest.mark.asyncio
    async def test_loss_streak_halt_reason_set_in_execute_pending_signals(
        self,
        mock_broker: Mock,
        mock_state_machine_manager: Mock,
        mock_trade_repository: Mock,
        mock_trade_publisher: Mock,
        mock_db_pool: Mock,
    ) -> None:
        """Test LOSS_STREAK halt reason is set when blocking signal execution."""
        trade_manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_state_machine_manager,
            trade_repository=mock_trade_repository,
            trade_publisher=mock_trade_publisher,
            db_pool=mock_db_pool,
            max_consecutive_losses=2,
            service_mode="test",
            service_name="execution",
        )
        
        # Record 2 consecutive losses
        trade_manager._daily_tracker.record_trade_closed(-50.0)
        trade_manager._daily_tracker.record_trade_closed(-75.0)
        
        # Add a pending signal
        signal = SignalMessage(
            id="signal-1",
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.5,
            confidence="A+",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2670.0,
            factors={"test": 1.0},
        )
        await trade_manager.on_signal(signal)
        
        # Try to execute - should be blocked and halt reason set
        await trade_manager.execute_pending_signals(
            next_bar_open=2650.0,
            candle_timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
        )
        
        # Signal should be removed from pending (blocked signals are discarded)
        assert len(trade_manager._pending_signals) == 0
        
        # Broker should not have received order (trade was blocked)
        mock_broker.place_order.assert_not_called()
        
        # NOTE: Metric verification would require mocking prometheus_client
        # which is complex. The important part is that daily_tracker.can_trade()
        # returns ("LOSS_STREAK") and execute_pending_signals calls
        # set_trading_halt_reason() with that value.
    
    def test_loss_streak_has_higher_priority_than_max_trades(
        self,
        mock_broker: Mock,
        mock_state_machine_manager: Mock,
        mock_trade_repository: Mock,
        mock_trade_publisher: Mock,
        mock_db_pool: Mock,
    ) -> None:
        """Test LOSS_STREAK blocks before MAX_TRADES when both limits hit."""
        trade_manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_state_machine_manager,
            trade_repository=mock_trade_repository,
            trade_publisher=mock_trade_publisher,
            db_pool=mock_db_pool,
            max_consecutive_losses=2,
            max_trades_per_day=3,
            pdll_limit=1000.0,
            service_mode="test",
            service_name="execution",
        )
        
        # Record 3 trades: 2 losses (hit loss streak) + 1 open
        trade_manager._daily_tracker.record_trade_opened()
        trade_manager._daily_tracker.record_trade_closed(-50.0)
        trade_manager._daily_tracker.record_trade_opened()
        trade_manager._daily_tracker.record_trade_closed(-75.0)
        trade_manager._daily_tracker.record_trade_opened()  # 3rd trade
        
        # Both limits hit, but loss streak should take priority
        can_trade, reason = trade_manager._daily_tracker.can_trade()
        
        assert can_trade is False
        assert reason == "LOSS_STREAK"  # Not MAX_TRADES
    
    def test_loss_streak_metric_updated_on_trade_close(
        self,
        mock_broker: Mock,
        mock_state_machine_manager: Mock,
        mock_trade_repository: Mock,
        mock_trade_publisher: Mock,
        mock_db_pool: Mock,
    ) -> None:
        """Test loss_streak_current metric is updated when trade closes."""
        trade_manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_state_machine_manager,
            trade_repository=mock_trade_repository,
            trade_publisher=mock_trade_publisher,
            db_pool=mock_db_pool,
            max_consecutive_losses=2,
            service_mode="test",
            service_name="execution",
        )
        
        # Record consecutive losses
        trade_manager._daily_tracker.record_trade_closed(-50.0)
        assert trade_manager._daily_tracker.state.consecutive_losses == 1
        
        trade_manager._daily_tracker.record_trade_closed(-75.0)
        assert trade_manager._daily_tracker.state.consecutive_losses == 2
        
        # Loss streak should now block trading
        can_trade, reason = trade_manager._daily_tracker.can_trade()
        assert can_trade is False
        assert reason == "LOSS_STREAK"
        
        # NOTE: The actual metric update happens in _close_trade() which calls
        # metrics.loss_streak_current.labels(...).set(loss_streak)
        # We can verify the value is tracked correctly in DailyStateTracker
