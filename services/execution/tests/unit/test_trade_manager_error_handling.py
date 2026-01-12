"""Unit tests for TradeManager error handling."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from scp_shared.database import DatabasePool

from execution_svc.broker import PaperBroker
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_manager import TradeManager
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository
from scp_shared.common.types import Candle
from scp_shared.execution.types import TradeRecord


@pytest.fixture
def mock_db_pool() -> DatabasePool:
    """Create mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def mock_broker() -> PaperBroker:
    """Create mock broker."""
    broker = MagicMock(spec=PaperBroker)
    broker.close_position = AsyncMock(return_value=MagicMock(status="filled"))
    broker.get_position = AsyncMock(return_value=None)
    return broker


@pytest.fixture
def mock_sm_manager() -> StateMachineManager:
    """Create mock state machine manager."""
    return MagicMock(spec=StateMachineManager)


@pytest.fixture
def mock_repo() -> TradeRepository:
    """Create mock trade repository."""
    repo = MagicMock(spec=TradeRepository)
    repo.close_trade = AsyncMock()
    return repo


@pytest.fixture
def mock_publisher() -> TradePublisher:
    """Create mock trade publisher."""
    publisher = MagicMock(spec=TradePublisher)
    publisher.publish_closed = AsyncMock()
    return publisher


@pytest.fixture
def sample_trade() -> TradeRecord:
    """Create sample trade."""
    return TradeRecord(
        trade_id="test-trade-1",
        signal_id="test-signal-1",
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


@pytest.fixture
def sample_candle() -> Candle:
    """Create sample candle that hits stop loss."""
    return Candle(
        timestamp=datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
        open=2648.0,
        high=2649.0,
        low=2644.0,  # Hits SL at 2645.0
        close=2648.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )


class TestTradeManagerHandlesTradeNotFound:
    """Test TradeManager error handling when trade not found in database."""
    
    @pytest.mark.asyncio
    async def test_close_trade_handles_not_found_error(
        self,
        mock_broker: PaperBroker,
        mock_sm_manager: StateMachineManager,
        mock_repo: TradeRepository,
        mock_publisher: TradePublisher,
        mock_db_pool: DatabasePool,
        sample_trade: TradeRecord,
        sample_candle: Candle,
    ) -> None:
        """Test that TradeManager handles ValueError from close_trade gracefully.
        
        This test verifies the fix: when TradeRepository.close_trade() raises
        ValueError (trade not found), TradeManager should:
        1. Catch the exception
        2. Clean up local state
        3. NOT publish a trade closed event (key fix)
        """
        # Configure repository to raise ValueError (trade not found)
        mock_repo.close_trade.side_effect = ValueError("Trade test-trade-1 not found")
        
        # Create TradeManager
        manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_sm_manager,
            trade_repository=mock_repo,
            trade_publisher=mock_publisher,
            db_pool=mock_db_pool,
            max_active_trades=1,
        )
        
        # Add trade to active tracking
        manager._active_trades[sample_trade.trade_id] = sample_trade
        manager._trade_entry_bars[sample_trade.trade_id] = 100
        
        # Call _close_trade (simulates SL/TP hit)
        await manager._close_trade(
            trade=sample_trade,
            exit_price=2645.0,
            exit_reason="SL_HIT",
            closed_at=datetime.now(timezone.utc),
        )
        
        # Verify repository was called
        assert mock_repo.close_trade.call_count == 1
        
        # Critical: Verify NO event was published (since DB update failed)
        mock_publisher.publish_closed.assert_not_called()
        
        # Verify local state was cleaned up (prevent memory leak)
        assert sample_trade.trade_id not in manager._active_trades
        assert sample_trade.trade_id not in manager._trade_entry_bars
    
    @pytest.mark.asyncio
    async def test_close_trade_publishes_event_on_success(
        self,
        mock_broker: PaperBroker,
        mock_sm_manager: StateMachineManager,
        mock_repo: TradeRepository,
        mock_publisher: TradePublisher,
        mock_db_pool: DatabasePool,
        sample_trade: TradeRecord,
    ) -> None:
        """Test that TradeManager publishes event when close succeeds.
        
        This ensures the fix doesn't break the happy path.
        """
        # Configure repository to succeed
        mock_repo.close_trade.return_value = None  # Success
        
        # Create TradeManager
        manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_sm_manager,
            trade_repository=mock_repo,
            trade_publisher=mock_publisher,
            db_pool=mock_db_pool,
            max_active_trades=1,
        )
        
        # Add trade to active tracking
        manager._active_trades[sample_trade.trade_id] = sample_trade
        
        # Call _close_trade
        await manager._close_trade(
            trade=sample_trade,
            exit_price=2660.0,
            exit_reason="TP_HIT",
            closed_at=datetime.now(timezone.utc),
        )
        
        # Verify event WAS published on success
        assert mock_publisher.publish_closed.call_count == 1
        
        # Verify local state was cleaned up
        assert sample_trade.trade_id not in manager._active_trades

