"""Unit tests for trade manager signal buffering and re-entry protection."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from execution_svc.trade_manager import TradeManager
from scp_shared.messaging.schemas import SignalMessage


@pytest.fixture
def mock_broker():
    """Create mock broker."""
    broker = AsyncMock()
    broker.place_order = AsyncMock()
    broker.close_position = AsyncMock()
    broker.get_position = AsyncMock(return_value=None)
    return broker


@pytest.fixture
def mock_sm_manager():
    """Create mock state machine manager."""
    sm_manager = AsyncMock()
    sm_manager.create_from_signal = AsyncMock()
    sm_manager.get_state_machine = MagicMock(return_value=None)
    sm_manager._bar_counter = 0
    sm_manager.increment_bar_counter = Mock()
    sm_manager.execute = AsyncMock()
    return sm_manager


@pytest.fixture
def mock_trade_repo():
    """Create mock trade repository."""
    repo = AsyncMock()
    repo.insert_trade = AsyncMock(return_value="test-trade-id-1")
    repo.save_trade = AsyncMock(return_value="test-trade-id-1")
    repo.update_trade = AsyncMock()
    repo.get_open_trades = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_trade_publisher():
    """Create mock trade publisher."""
    publisher = AsyncMock()
    publisher.publish_opened = AsyncMock()
    publisher.publish_closed = AsyncMock()
    return publisher


@pytest.fixture
def trade_manager(mock_broker, mock_sm_manager, mock_trade_repo, mock_trade_publisher):
    """Create trade manager instance."""
    return TradeManager(
        broker=mock_broker,
        state_machine_manager=mock_sm_manager,
        trade_repository=mock_trade_repo,
        trade_publisher=mock_trade_publisher,
        max_active_trades=1,
        pdll_limit=600.0,
        max_trades_per_day=2,
    )


def make_signal(
    direction: str = "long",
    setup_type: str = "VWAP_RECLAIM",
    entry_price: float = 2650.0,
    sl_price: float = 2645.0,
    tp_price: float = 2662.0,
) -> SignalMessage:
    """Helper to create test signal."""
    return SignalMessage(
        id="test-signal-1",
        timestamp=datetime.now(timezone.utc),
        direction=direction,
        setup_type=setup_type,
        score=8.5,
        confidence="A+",
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        factors={},
    )


class TestSignalBuffering:
    """Test signal buffering and next-bar-open execution."""
    
    @pytest.mark.asyncio
    async def test_on_signal_buffers_signal(self, trade_manager) -> None:
        """Test on_signal buffers signal instead of executing immediately."""
        signal = make_signal()
        
        await trade_manager.on_signal(signal)
        
        # Signal should be buffered
        assert len(trade_manager._pending_signals) == 1
        assert trade_manager._pending_signals[0] == signal
        
        # Should NOT have created active trade yet
        assert len(trade_manager._active_trades) == 0
    
    @pytest.mark.asyncio
    async def test_execute_pending_signals_executes_at_next_bar_open(
        self, trade_manager, mock_broker
    ) -> None:
        """Test execute_pending_signals executes buffered signals at next bar open."""
        from execution_svc.broker import OrderResult
        
        signal = make_signal(entry_price=2650.0)
        
        # Buffer signal
        await trade_manager.on_signal(signal)
        
        # Mock broker to return successful order
        mock_broker.place_order.return_value = OrderResult(
            order_id="order-1",
            symbol="GC",
            side="long",
            quantity=1,
            filled_price=2655.0,  # Next bar open
            filled_at=datetime.now(timezone.utc),
            status="filled",
        )
        
        # Execute at next bar open
        await trade_manager.execute_pending_signals(next_bar_open=2655.0)
        
        # Should have executed trade
        mock_broker.place_order.assert_called_once()
        call_args = mock_broker.place_order.call_args[1]
        assert call_args["price"] == 2655.0  # Executed at next bar open, not signal price
        
        # Pending signals should be cleared
        assert len(trade_manager._pending_signals) == 0
        
        # Should have active trade
        assert len(trade_manager._active_trades) == 1
    
    @pytest.mark.asyncio
    async def test_execute_pending_signals_processes_multiple_signals(
        self, trade_manager, mock_broker
    ) -> None:
        """Test execute_pending_signals processes all buffered signals."""
        from execution_svc.broker import OrderResult
        
        signal1 = make_signal()
        signal2 = make_signal()
        signal2.id = "test-signal-2"
        
        # Buffer two signals
        await trade_manager.on_signal(signal1)
        
        # Adjust max_active_trades to allow second signal
        trade_manager._max_active_trades = 2
        await trade_manager.on_signal(signal2)
        
        assert len(trade_manager._pending_signals) == 2
        
        # Mock broker
        mock_broker.place_order.return_value = OrderResult(
            order_id="order-1",
            symbol="GC",
            side="long",
            quantity=1,
            filled_price=2655.0,
            filled_at=datetime.now(timezone.utc),
            status="filled",
        )
        
        # Execute pending signals
        await trade_manager.execute_pending_signals(next_bar_open=2655.0)
        
        # Should have called broker twice
        assert mock_broker.place_order.call_count == 2
        
        # Pending signals cleared
        assert len(trade_manager._pending_signals) == 0


class TestDailyLimitsIntegration:
    """Test daily limits integration with buffered execution."""
    
    @pytest.mark.asyncio
    async def test_execute_pending_signals_respects_pdll(
        self, trade_manager, mock_broker
    ) -> None:
        """Test execute_pending_signals blocks execution when PDLL hit."""
        from execution_svc.broker import OrderResult
        
        signal = make_signal()
        
        # Hit PDLL
        trade_manager._daily_tracker.record_trade_closed(-700.0)
        
        # Buffer signal
        await trade_manager.on_signal(signal)
        
        # Try to execute
        await trade_manager.execute_pending_signals(next_bar_open=2655.0)
        
        # Should NOT have placed order
        mock_broker.place_order.assert_not_called()
        
        # Signal should be cleared (processed but blocked)
        assert len(trade_manager._pending_signals) == 0
    
    @pytest.mark.asyncio
    async def test_execute_pending_signals_respects_max_trades_per_day(
        self, trade_manager, mock_broker
    ) -> None:
        """Test execute_pending_signals blocks after max trades per day."""
        signal = make_signal()
        
        # Record max trades already opened today
        trade_manager._daily_tracker.record_trade_opened()
        trade_manager._daily_tracker.record_trade_opened()  # Max is 2
        
        # Buffer signal
        await trade_manager.on_signal(signal)
        
        # Try to execute
        await trade_manager.execute_pending_signals(next_bar_open=2655.0)
        
        # Should NOT have placed order
        mock_broker.place_order.assert_not_called()


class TestReentryProtection:
    """Test re-entry protection via can_execute check."""
    
    @pytest.mark.asyncio
    async def test_execute_entry_blocks_when_cannot_execute(
        self, trade_manager, mock_broker, mock_sm_manager
    ) -> None:
        """Test execute_entry blocks when state machine cannot execute."""
        signal = make_signal()
        
        # Mock state machine to block execution
        mock_sm = Mock()
        mock_sm.can_execute.return_value = False
        mock_sm.execution_count = 2
        mock_sm_manager.get_state_machine.return_value = mock_sm
        
        # Try to execute
        result = await trade_manager.execute_entry(signal, entry_price=2655.0)
        
        # Should be blocked
        assert result is None
        mock_broker.place_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_execute_entry_allows_when_can_execute(
        self, trade_manager, mock_broker, mock_sm_manager
    ) -> None:
        """Test execute_entry allows execution when state machine permits."""
        from execution_svc.broker import OrderResult
        
        signal = make_signal()
        
        # Mock state machine to allow execution
        mock_sm = Mock()
        mock_sm.can_execute.return_value = True
        mock_sm_manager.get_state_machine.return_value = mock_sm
        
        # Mock broker
        mock_broker.place_order.return_value = OrderResult(
            order_id="order-1",
            symbol="GC",
            side="long",
            quantity=1,
            filled_price=2655.0,
            filled_at=datetime.now(timezone.utc),
            status="filled",
        )
        
        # Execute
        result = await trade_manager.execute_entry(signal, entry_price=2655.0)
        
        # Should succeed
        assert result is not None
        mock_broker.place_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_entry_allows_when_no_state_machine(
        self, trade_manager, mock_broker, mock_sm_manager
    ) -> None:
        """Test execute_entry allows execution when no state machine exists."""
        from execution_svc.broker import OrderResult
        
        signal = make_signal()
        
        # No state machine found
        mock_sm_manager.get_state_machine.return_value = None
        
        # Mock broker
        mock_broker.place_order.return_value = OrderResult(
            order_id="order-1",
            symbol="GC",
            side="long",
            quantity=1,
            filled_price=2655.0,
            filled_at=datetime.now(timezone.utc),
            status="filled",
        )
        
        # Execute
        result = await trade_manager.execute_entry(signal, entry_price=2655.0)
        
        # Should succeed (no state machine = no restriction)
        assert result is not None
        mock_broker.place_order.assert_called_once()

