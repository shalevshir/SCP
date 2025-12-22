"""Unit tests for trade state persistence across service restarts.

Tests verify that critical state for SOP validation is preserved:
- bars_elapsed (via entry_bar_idx)
- reached_1r status

Without persistence, trades can bypass time limits and lose +1R protection.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution_svc.broker import PaperBroker
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_manager import TradeManager
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository
from scp_shared.common.types import Candle
from scp_shared.execution.types import TradeRecord


@pytest.fixture
def mock_broker() -> PaperBroker:
    """Create mock broker."""
    broker = MagicMock(spec=PaperBroker)
    broker.close_position = AsyncMock(return_value=MagicMock(status="filled"))
    broker.reconcile_positions = AsyncMock()
    return broker


@pytest.fixture
def mock_sm_manager() -> StateMachineManager:
    """Create mock state machine manager."""
    manager = MagicMock(spec=StateMachineManager)
    manager._bar_counter = 0
    manager.increment_bar_counter = MagicMock(
        side_effect=lambda: setattr(manager, "_bar_counter", manager._bar_counter + 1)
    )
    return manager


@pytest.fixture
def mock_repo() -> TradeRepository:
    """Create mock trade repository."""
    repo = MagicMock(spec=TradeRepository)
    repo.get_open_trades = AsyncMock(return_value=[])
    repo.close_trade = AsyncMock()
    return repo


@pytest.fixture
def mock_publisher() -> TradePublisher:
    """Create mock trade publisher."""
    publisher = MagicMock(spec=TradePublisher)
    publisher.publish_closed = AsyncMock()
    return publisher


class TestBarsElapsedPersistence:
    """Test that bars_elapsed is persisted and restored correctly."""
    
    @pytest.mark.asyncio
    async def test_entry_bar_restored_from_database(
        self,
        mock_broker: PaperBroker,
        mock_sm_manager: StateMachineManager,
        mock_repo: TradeRepository,
        mock_publisher: TradePublisher,
    ) -> None:
        """Test that entry_bar is correctly restored from database after fix.
        
        After fix:
        - entry_bar should be restored from database (e.g., 100)
        - bars_elapsed should be calculated correctly
        """
        # Create trade that was opened at bar 100
        trade = TradeRecord(
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
            entry_bar_idx=100,  # FIX: Now included in database
            reached_1r=False,
        )
        
        # Mock repository to return the trade with entry_bar_idx
        mock_repo.get_open_trades.return_value = [trade]
        
        # Create TradeManager (simulates service restart)
        manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_sm_manager,
            trade_repository=mock_repo,
            trade_publisher=mock_publisher,
            max_active_trades=1,
        )
        
        # Restore trades from database
        await manager.restore_active_trades()
        
        # FIX VERIFICATION: entry_bar is correctly restored
        assert manager._trade_entry_bars["trade-1"] == 100


class TestReached1RPersistence:
    """Test that reached_1r status is persisted and restored correctly."""
    
    @pytest.mark.asyncio
    async def test_reached_1r_state_restored_from_database(
        self,
        mock_broker: PaperBroker,
        mock_sm_manager: StateMachineManager,
        mock_repo: TradeRepository,
        mock_publisher: TradePublisher,
    ) -> None:
        """Test that reached_1r state is correctly restored from database after fix.
        
        After fix:
        - reached_1r=True should be restored from database
        - Trade should maintain +1R protection across restarts
        """
        # Create trade that already reached +1R before restart
        trade = TradeRecord(
            trade_id="trade-2",
            signal_id="signal-2",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,  # Risk: 5 points
            tp_price=2662.0,  # Reward: 12 points
            risk_amount=5.0,
            reward_amount=12.0,
            entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            entry_bar_idx=100,
            reached_1r=True,  # FIX: Now included in database
        )
        # Note: +1R price = 2650 + 5 = 2655.0
        
        # Mock repository to return trade with reached_1r=True
        mock_repo.get_open_trades.return_value = [trade]
        
        # Create TradeManager (simulates service restart)
        manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_sm_manager,
            trade_repository=mock_repo,
            trade_publisher=mock_publisher,
            max_active_trades=1,
        )
        
        # Restore trades from database
        await manager.restore_active_trades()
        
        # FIX VERIFICATION: InvalidationChecker state is correctly restored
        trade_state = manager._invalidation_checker._trade_states.get("trade-2", {})
        assert trade_state.get("reached_1r", False) is True


class TestFullRecoveryScenario:
    """Integration test for complete state recovery on restart."""
    
    @pytest.mark.asyncio
    async def test_trade_with_correct_state_after_restart(
        self,
        mock_broker: PaperBroker,
        mock_sm_manager: StateMachineManager,
        mock_repo: TradeRepository,
        mock_publisher: TradePublisher,
    ) -> None:
        """Test that trades are restored with correct state after restart.
        
        Expected behavior after fix:
        1. Trade opened at bar 100, reached +1R at bar 110
        2. Service restarts at bar 160
        3. Trade restored with entry_bar_idx=100, reached_1r=True
        4. bars_elapsed correctly calculated as 60
        5. Trade remains open (has +1R protection)
        """
        # Create trade that was opened at bar 100 and reached +1R at bar 110
        trade_with_full_state = TradeRecord(
            trade_id="trade-3",
            signal_id="signal-3",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            risk_amount=5.0,
            reward_amount=12.0,
            entry_timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            entry_bar_idx=100,  # FIX: Persisted in database
            reached_1r=True,  # FIX: Persisted in database
        )
        
        # Mock repository to return trade with persisted state
        mock_repo.get_open_trades.return_value = [trade_with_full_state]
        
        # Simulate service restart at bar 160
        mock_sm_manager._bar_counter = 160
        
        # Create TradeManager
        manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_sm_manager,
            trade_repository=mock_repo,
            trade_publisher=mock_publisher,
            max_active_trades=1,
        )
        
        # Restore trades
        await manager.restore_active_trades()
        
        # FIX VERIFICATION: State is restored correctly
        assert manager._trade_entry_bars["trade-3"] == 100
        assert manager._invalidation_checker._trade_states["trade-3"]["reached_1r"] is True
        
        # Process more candles
        for _ in range(10):
            mock_sm_manager.increment_bar_counter()
            
            candle = Candle(
                timestamp=datetime(2025, 1, 15, 11, 10, tzinfo=timezone.utc),
                open=2657.0,
                high=2658.0,
                low=2656.0,
                close=2657.0,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
            
            features = {
                "vwap": 2649.0,
                "rsi": 60.0,
                "structure_label": "HH",
            }
            
            trade = manager._active_trades.get("trade-3")
            if trade:
                await manager._check_trade_exit(trade, candle, features)
        
        # FIX VERIFICATION: Trade remains open (has +1R protection)
        assert "trade-3" in manager._active_trades
        assert mock_repo.close_trade.call_count == 0

