"""Unit tests for TradeManager."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scp_shared.common.types import Candle
from scp_shared.execution.types import TradeRecord
from scp_shared.messaging.schemas import (
    CandleMessage,
    FeaturesMessage,
    SignalMessage,
)

from execution_svc.broker import BaseBroker
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_manager import TradeManager
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository


@pytest.fixture
def mock_broker() -> MagicMock:
    """Create mock broker."""
    broker = MagicMock(spec=BaseBroker)
    broker.place_order = AsyncMock(return_value=MagicMock(status="filled"))
    broker.close_position = AsyncMock()
    broker.reconcile_positions = AsyncMock()
    return broker


@pytest.fixture
def mock_sm_manager() -> MagicMock:
    """Create mock state machine manager."""
    manager = MagicMock(spec=StateMachineManager)
    manager.create_from_signal = AsyncMock()
    manager.get_state_machine = MagicMock(return_value=None)
    manager.execute = AsyncMock()
    manager.increment_bar_counter = MagicMock()
    manager._bar_counter = 100
    return manager


@pytest.fixture
def mock_trade_repo() -> MagicMock:
    """Create mock trade repository."""
    repo = MagicMock(spec=TradeRepository)
    repo.insert_trade = AsyncMock(return_value="trade-123")
    repo.close_trade = AsyncMock()
    repo.get_open_trades = AsyncMock(return_value=[])
    repo.get_trades_for_date = AsyncMock(return_value=[])
    repo.update_reached_1r = AsyncMock()
    return repo


@pytest.fixture
def mock_publisher() -> MagicMock:
    """Create mock trade publisher."""
    publisher = MagicMock(spec=TradePublisher)
    publisher.publish_opened = AsyncMock()
    publisher.publish_closed = AsyncMock()
    return publisher


@pytest.fixture
def trade_manager(
    mock_broker: MagicMock,
    mock_sm_manager: MagicMock,
    mock_trade_repo: MagicMock,
    mock_publisher: MagicMock,
) -> TradeManager:
    """Create trade manager with mocks."""
    return TradeManager(
        broker=mock_broker,
        state_machine_manager=mock_sm_manager,
        trade_repository=mock_trade_repo,
        trade_publisher=mock_publisher,
        max_active_trades=1,
        pdll_limit=600.0,
        max_trades_per_day=2,
    )


@pytest.fixture
def sample_signal() -> SignalMessage:
    """Create sample signal."""
    return SignalMessage(
        id="signal-123",
        timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=8.5,
        confidence="A+",
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2662.0,
        factors={"structure_alignment": 2.0},
    )


@pytest.fixture
def sample_candle() -> CandleMessage:
    """Create sample candle."""
    return CandleMessage(
        timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        open=2650.0,
        high=2655.0,
        low=2648.0,
        close=2654.0,
        volume=1000.0,
    )


class TestTradeManagerOnSignal:
    """Test on_signal method."""
    
    @pytest.mark.asyncio
    async def test_on_signal_buffers_signal(
        self,
        trade_manager: TradeManager,
        mock_sm_manager: MagicMock,
        sample_signal: SignalMessage,
    ) -> None:
        """Signal is buffered for next bar execution."""
        await trade_manager.on_signal(sample_signal)
        
        assert len(trade_manager._pending_signals) == 1
        assert trade_manager._pending_signals[0] == sample_signal
        mock_sm_manager.create_from_signal.assert_called_once_with(sample_signal)
    
    @pytest.mark.asyncio
    async def test_on_signal_rejects_when_max_trades_reached(
        self,
        trade_manager: TradeManager,
        sample_signal: SignalMessage,
    ) -> None:
        """Signal is rejected when max active trades reached."""
        # Simulate existing active trade
        trade_manager._active_trades["trade-1"] = MagicMock()
        
        await trade_manager.on_signal(sample_signal)
        
        # Signal should not be buffered
        assert len(trade_manager._pending_signals) == 0


class TestTradeManagerExecutePendingSignals:
    """Test execute_pending_signals method."""
    
    @pytest.mark.asyncio
    async def test_execute_pending_signals_executes_entry(
        self,
        trade_manager: TradeManager,
        mock_broker: MagicMock,
        mock_trade_repo: MagicMock,
        mock_publisher: MagicMock,
        sample_signal: SignalMessage,
    ) -> None:
        """Pending signals are executed at next bar open."""
        trade_manager._pending_signals.append(sample_signal)
        
        await trade_manager.execute_pending_signals(next_bar_open=2651.0)
        
        mock_broker.place_order.assert_called_once()
        mock_trade_repo.insert_trade.assert_called_once()
        mock_publisher.publish_opened.assert_called_once()
        assert len(trade_manager._active_trades) == 1
        assert len(trade_manager._pending_signals) == 0
    
    @pytest.mark.asyncio
    async def test_execute_pending_signals_clears_buffer(
        self,
        trade_manager: TradeManager,
        sample_signal: SignalMessage,
    ) -> None:
        """Pending signals buffer is cleared after execution."""
        trade_manager._pending_signals.append(sample_signal)
        
        await trade_manager.execute_pending_signals(next_bar_open=2651.0)
        
        assert len(trade_manager._pending_signals) == 0
    
    @pytest.mark.asyncio
    async def test_execute_pending_signals_respects_concurrent_limit(
        self,
        trade_manager: TradeManager,
        sample_signal: SignalMessage,
    ) -> None:
        """Signals are blocked when concurrent limit is reached."""
        # Simulate existing active trade
        trade_manager._active_trades["trade-1"] = MagicMock()
        trade_manager._pending_signals.append(sample_signal)
        
        await trade_manager.execute_pending_signals(next_bar_open=2651.0)
        
        # Signal should not be executed
        assert len(trade_manager._active_trades) == 1  # Still just the original
    
    @pytest.mark.asyncio
    async def test_execute_pending_signals_respects_pdll_limit(
        self,
        trade_manager: TradeManager,
        sample_signal: SignalMessage,
    ) -> None:
        """Signals are blocked when PDLL limit is reached."""
        # Simulate PDLL hit by setting state.pdll_hit
        trade_manager._daily_tracker._state.pdll_hit = True
        trade_manager._pending_signals.append(sample_signal)
        
        await trade_manager.execute_pending_signals(next_bar_open=2651.0)
        
        # Signal should not be executed
        assert len(trade_manager._active_trades) == 0


class TestTradeManagerOnCandle:
    """Test on_candle method."""
    
    @pytest.mark.asyncio
    async def test_on_candle_checks_active_trades(
        self,
        trade_manager: TradeManager,
        sample_candle: CandleMessage,
    ) -> None:
        """Candle processing checks active trades for exit."""
        # Add active trade
        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-123",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            risk_amount=5.0,
            reward_amount=12.0,
            entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        trade_manager._active_trades["trade-123"] = trade
        
        await trade_manager.on_candle(sample_candle)
        
        # Trade should still be active (no exit triggered)
        assert "trade-123" in trade_manager._active_trades


class TestTradeManagerCheckSessionReset:
    """Test check_session_reset method."""
    
    def test_check_session_reset_resets_daily_tracker(
        self,
        trade_manager: TradeManager,
    ) -> None:
        """Session reset resets daily tracker state."""
        # Record some trades
        trade_manager._daily_tracker.record_trade_opened()
        trade_manager._daily_tracker.record_trade_closed(pnl=-100.0)
        
        # Reset for new day
        new_day = datetime(2025, 1, 16, 10, 0, tzinfo=timezone.utc)
        trade_manager.check_session_reset(new_day)
        
        # State should be reset
        can_trade, _ = trade_manager._daily_tracker.can_trade()
        assert can_trade is True


class TestTradeManagerExecuteEntry:
    """Test execute_entry method."""
    
    @pytest.mark.asyncio
    async def test_execute_entry_creates_trade(
        self,
        trade_manager: TradeManager,
        mock_broker: MagicMock,
        mock_trade_repo: MagicMock,
        mock_publisher: MagicMock,
        mock_sm_manager: MagicMock,
        sample_signal: SignalMessage,
    ) -> None:
        """Execute entry creates trade and publishes event."""
        result = await trade_manager.execute_entry(sample_signal, entry_price=2651.0)
        
        assert result is not None
        assert result.entry_price == 2651.0
        assert result.direction == "long"
        mock_broker.place_order.assert_called_once()
        mock_trade_repo.insert_trade.assert_called_once()
        mock_publisher.publish_opened.assert_called_once()
        mock_sm_manager.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_entry_calculates_risk_reward_long(
        self,
        trade_manager: TradeManager,
        sample_signal: SignalMessage,
    ) -> None:
        """Execute entry calculates risk/reward correctly for long."""
        result = await trade_manager.execute_entry(sample_signal, entry_price=2651.0)
        
        assert result is not None
        assert result.risk_amount == 2651.0 - 2645.0  # entry - sl
        assert result.reward_amount == 2662.0 - 2651.0  # tp - entry
    
    @pytest.mark.asyncio
    async def test_execute_entry_handles_order_failure(
        self,
        trade_manager: TradeManager,
        mock_broker: MagicMock,
        sample_signal: SignalMessage,
    ) -> None:
        """Execute entry handles order failure gracefully."""
        mock_broker.place_order.return_value = MagicMock(status="rejected")
        
        result = await trade_manager.execute_entry(sample_signal, entry_price=2651.0)
        
        assert result is None
        assert len(trade_manager._active_trades) == 0
    
    @pytest.mark.asyncio
    async def test_execute_entry_blocks_max_executions(
        self,
        trade_manager: TradeManager,
        mock_sm_manager: MagicMock,
        sample_signal: SignalMessage,
    ) -> None:
        """Execute entry blocks when state machine has max executions."""
        # Mock check_confirmation to return False (signal not ready for execution)
        mock_sm_manager.check_confirmation.return_value = False
        
        # Mock state machine for logging purposes
        sm = MagicMock()
        sm.execution_count = 1
        mock_sm_manager.get_state_machine.return_value = sm
        
        result = await trade_manager.execute_entry(sample_signal, entry_price=2651.0)
        
        assert result is None
        mock_sm_manager.check_confirmation.assert_called_once_with(sample_signal.id)


class TestTradeManagerRestoreActiveTrades:
    """Test restore_active_trades method."""
    
    @pytest.mark.asyncio
    async def test_restore_active_trades_loads_from_database(
        self,
        trade_manager: TradeManager,
        mock_trade_repo: MagicMock,
        mock_broker: MagicMock,
    ) -> None:
        """Restore loads active trades from database."""
        mock_trade_repo.get_open_trades.return_value = [
            TradeRecord(
                trade_id="trade-123",
                signal_id="signal-123",
                symbol="GC",
                direction="long",
                setup_type="VWAP_RECLAIM",
                entry_price=2650.0,
                sl_price=2645.0,
                tp_price=2662.0,
                risk_amount=5.0,
                reward_amount=12.0,
                entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                entry_bar_idx=100,
                reached_1r=False,
            ),
        ]
        
        await trade_manager.restore_active_trades()
        
        assert len(trade_manager._active_trades) == 1
        assert "trade-123" in trade_manager._active_trades
        mock_broker.reconcile_positions.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_restore_active_trades_restores_daily_state(
        self,
        trade_manager: TradeManager,
        mock_trade_repo: MagicMock,
    ) -> None:
        """Restore also restores daily state from today's trades."""
        mock_trade_repo.get_trades_for_date.return_value = [
            TradeRecord(
                trade_id="trade-1",
                signal_id="signal-1",
                symbol="GC",
                direction="long",
                setup_type="VWAP_RECLAIM",
                entry_price=2650.0,
                sl_price=2645.0,
                tp_price=2662.0,
                risk_amount=5.0,
                reward_amount=12.0,
                entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                exit_timestamp=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
                exit_price=2655.0,
                pnl=5.0,
            ),
        ]
        mock_trade_repo.get_open_trades.return_value = []
        
        await trade_manager.restore_active_trades()
        
        # Daily state should be restored
        mock_trade_repo.get_trades_for_date.assert_called_once()


class TestTradeManagerCloseTrade:
    """Test _close_trade method."""
    
    @pytest.mark.asyncio
    async def test_close_trade_publishes_event(
        self,
        trade_manager: TradeManager,
        mock_broker: MagicMock,
        mock_trade_repo: MagicMock,
        mock_publisher: MagicMock,
    ) -> None:
        """Close trade publishes closed event."""
        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-123",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            risk_amount=5.0,
            reward_amount=12.0,
            entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        trade_manager._active_trades["trade-123"] = trade
        
        await trade_manager._close_trade(
            trade=trade,
            exit_price=2660.0,
            exit_reason="TP_HIT",
            closed_at=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        )
        
        mock_broker.close_position.assert_called_once()
        mock_trade_repo.close_trade.assert_called_once()
        mock_publisher.publish_closed.assert_called_once()
        assert "trade-123" not in trade_manager._active_trades
    
    @pytest.mark.asyncio
    async def test_close_trade_handles_orphaned_position(
        self,
        trade_manager: TradeManager,
        mock_broker: MagicMock,
        mock_trade_repo: MagicMock,
        mock_publisher: MagicMock,
    ) -> None:
        """Close trade handles orphaned position gracefully."""
        # Broker doesn't have the position
        mock_broker.close_position.side_effect = ValueError("Position not found")
        
        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-123",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            risk_amount=5.0,
            reward_amount=12.0,
            entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        trade_manager._active_trades["trade-123"] = trade
        
        await trade_manager._close_trade(
            trade=trade,
            exit_price=2660.0,
            exit_reason="TP_HIT",
            closed_at=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        )
        
        # Should still close trade in database and publish event
        mock_trade_repo.close_trade.assert_called_once()
        mock_publisher.publish_closed.assert_called_once()
        assert "trade-123" not in trade_manager._active_trades
    
    @pytest.mark.asyncio
    async def test_close_trade_updates_daily_tracker(
        self,
        trade_manager: TradeManager,
        mock_broker: MagicMock,
        mock_trade_repo: MagicMock,
    ) -> None:
        """Close trade updates daily tracker with P&L."""
        trade = TradeRecord(
            trade_id="trade-123",
            signal_id="signal-123",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            risk_amount=5.0,
            reward_amount=12.0,
            entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        trade_manager._active_trades["trade-123"] = trade
        
        await trade_manager._close_trade(
            trade=trade,
            exit_price=2660.0,  # Profit of 10 points
            exit_reason="TP_HIT",
            closed_at=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        )
        
        # Daily tracker should have recorded the P&L
        assert trade_manager._daily_tracker.state.daily_pnl == 10.0


class TestTradeManagerShortPositions:
    """Test trade manager with short positions."""
    
    @pytest.fixture
    def short_signal(self) -> SignalMessage:
        """Create short signal."""
        return SignalMessage(
            id="signal-short-123",
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            direction="short",
            setup_type="VWAP_FADE",
            score=8.5,
            confidence="A+",
            entry_price=2650.0,
            sl_price=2655.0,  # SL above entry for short
            tp_price=2638.0,  # TP below entry for short
            factors={"rejection_candle": 2.0},
        )
    
    @pytest.mark.asyncio
    async def test_execute_entry_short_position(
        self,
        trade_manager: TradeManager,
        short_signal: SignalMessage,
    ) -> None:
        """Execute entry for short position calculates correctly."""
        result = await trade_manager.execute_entry(short_signal, entry_price=2649.0)
        
        assert result is not None
        assert result.direction == "short"
        assert result.risk_amount == 2655.0 - 2649.0  # sl - entry
        assert result.reward_amount == 2649.0 - 2638.0  # entry - tp
