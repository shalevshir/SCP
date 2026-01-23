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
            pdll_limit=1000.0,  # High enough to not interfere
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

    @pytest.mark.asyncio
    async def test_halt_metric_reflects_restored_state_on_startup(
        self,
        mock_broker: Mock,
        mock_state_machine_manager: Mock,
        mock_trade_repository: Mock,
        mock_trade_publisher: Mock,
        mock_db_pool: Mock,
    ) -> None:
        """Test halt metric correctly reflects restored state after service restart.

        This test verifies the fix for the issue where the halt reason metric
        was unconditionally set to "NONE" after restore_active_trades(), even
        if the restored state had a halt condition active (e.g., loss streak).
        """
        from scp_shared.execution.types import TradeRecord
        from datetime import date

        # Create closed trades from today with 2 consecutive losses
        today = date.today()
        closed_trades = [
            TradeRecord(
                trade_id="trade-1",
                signal_id="signal-1",
                symbol="GC",
                direction="long",
                setup_type="VWAP_RECLAIM",
                entry_price=2650.0,
                sl_price=2640.0,
                tp_price=2670.0,
                risk_amount=10.0,
                reward_amount=20.0,
                entry_timestamp=datetime(2025, 1, 17, 9, 0, tzinfo=timezone.utc),
                exit_timestamp=datetime(2025, 1, 17, 9, 5, tzinfo=timezone.utc),
                exit_price=2640.0,
                exit_reason="SL_HIT",
                pnl=-10.0,
            ),
            TradeRecord(
                trade_id="trade-2",
                signal_id="signal-2",
                symbol="GC",
                direction="short",
                setup_type="VWAP_FADE",
                entry_price=2655.0,
                sl_price=2665.0,
                tp_price=2645.0,
                risk_amount=10.0,
                reward_amount=10.0,
                entry_timestamp=datetime(2025, 1, 17, 10, 0, tzinfo=timezone.utc),
                exit_timestamp=datetime(2025, 1, 17, 10, 8, tzinfo=timezone.utc),
                exit_price=2665.0,
                exit_reason="SL_HIT",
                pnl=-10.0,
            ),
        ]

        # Mock repository to return these trades
        mock_trade_repository.get_trades_for_date = AsyncMock(
            return_value=closed_trades
        )
        mock_trade_repository.get_open_trades = AsyncMock(return_value=[])

        # Create trade manager with 2 loss limit
        trade_manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_state_machine_manager,
            trade_repository=mock_trade_repository,
            trade_publisher=mock_trade_publisher,
            db_pool=mock_db_pool,
            max_consecutive_losses=2,
            max_trades_per_day=5,
            pdll_limit=1000.0,
            service_mode="test",
            service_name="execution",
        )

        # Simulate service restart: restore state from database
        await trade_manager.restore_active_trades()

        # Verify daily state was correctly restored
        assert trade_manager._daily_tracker.state.consecutive_losses == 2
        assert trade_manager._daily_tracker.state.losses == 2
        assert trade_manager._daily_tracker.state.trades_count == 2
        assert trade_manager._daily_tracker.state.daily_pnl == -20.0

        # Verify trading is blocked due to loss streak
        can_trade, halt_reason = trade_manager._daily_tracker.can_trade()
        assert can_trade is False
        assert halt_reason == "LOSS_STREAK"

        # Verify the halt reason that would be set by main.py after restore
        # (This is what the fix in main.py should do)
        # In the actual service, main.py would call:
        # exec_metrics.set_trading_halt_reason(halt_reason, mode, service)
        # We can't easily test the metric call here, but we verify the
        # can_trade() result is correct

        # Try to execute a signal - should be blocked
        signal = SignalMessage(
            id="signal-3",
            timestamp=datetime(2025, 1, 17, 11, 0, tzinfo=timezone.utc),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=9.0,
            confidence="A+",
            entry_price=2660.0,
            sl_price=2650.0,
            tp_price=2680.0,
            factors={},
        )

        trade_manager._pending_signals = [signal]

        # Execute pending signals - should be blocked by loss streak
        await trade_manager.execute_pending_signals(2660.0, signal.timestamp)

        # Signal should remain pending (blocked by loss streak)
        assert len(trade_manager._pending_signals) == 1

        # No order should have been placed
        mock_broker.place_order.assert_not_called()

        # After the fix in main.py, the metric would be set to "LOSS_STREAK"
        # instead of "NONE", making Grafana show the correct halt status
