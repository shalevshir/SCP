"""Test that signal_id is correctly tracked through trade lifecycle.

This test verifies the fix for signal-trade correlation in Redis events.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from execution_svc.trade_manager import TradeManager
from execution_svc.trade_repository import TradeRepository
from scp_shared.database import DatabasePool
from scp_shared.execution.types import TradeRecord
from scp_shared.messaging.schemas import SignalMessage, TradeMessage


@pytest.fixture
def db_pool() -> DatabasePool:
    """Create mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def signal_message() -> SignalMessage:
    """Create sample signal message."""
    return SignalMessage(
        id=str(uuid4()),
        timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=9.5,
        confidence="A+",
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2662.0,
        factors={},
    )


class TestSignalTradeCorrelation:
    """Test that signal_id is correctly preserved through trade lifecycle."""
    
    @pytest.mark.asyncio
    async def test_trade_record_includes_signal_id(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test that TradeRecord loaded from DB includes signal_id.
        
        This is the core fix: TradeRecord must have a signal_id field
        populated from the database query result.
        """
        repo = TradeRepository(db_pool)
        
        signal_id = str(uuid4())
        trade_id = str(uuid4())
        
        # Mock database response with signal_id
        db_pool.fetchrow.return_value = {
            "id": trade_id,
            "signal_id": signal_id,
            "direction": "long",
            "setup_type": "VWAP_RECLAIM",
            "entry_price": 2650.0,
            "sl_price": 2645.0,
            "tp_price": 2662.0,
            "quantity": 1,
            "opened_at": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "closed_at": None,
            "exit_price": None,
            "exit_reason": None,
            "pnl_points": None,
            "entry_bar_idx": 100,
            "reached_1r": False,
        }
        
        # Get trade from repository
        trade = await repo.get_trade(trade_id)
        
        # Critical: signal_id must be populated
        assert trade is not None
        assert trade.signal_id == signal_id
        assert trade.trade_id == trade_id
        assert trade.signal_id != trade.trade_id  # Must be different!
    
    @pytest.mark.asyncio
    async def test_open_trades_include_signal_id(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test that get_open_trades() includes signal_id in results."""
        repo = TradeRepository(db_pool)
        
        signal_id_1 = str(uuid4())
        signal_id_2 = str(uuid4())
        trade_id_1 = str(uuid4())
        trade_id_2 = str(uuid4())
        
        # Mock multiple open trades
        db_pool.fetch.return_value = [
            {
                "id": trade_id_1,
                "signal_id": signal_id_1,
                "direction": "long",
                "setup_type": "VWAP_RECLAIM",
                "entry_price": 2650.0,
                "sl_price": 2645.0,
                "tp_price": 2662.0,
                "quantity": 1,
                "opened_at": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                "entry_bar_idx": 100,
                "reached_1r": False,
            },
            {
                "id": trade_id_2,
                "signal_id": signal_id_2,
                "direction": "short",
                "setup_type": "VWAP_FADE",
                "entry_price": 2655.0,
                "sl_price": 2660.0,
                "tp_price": 2640.0,
                "quantity": 1,
                "opened_at": datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
                "entry_bar_idx": 160,
                "reached_1r": False,
            },
        ]
        
        # Get open trades
        trades = await repo.get_open_trades()
        
        # Verify both trades have correct signal_ids
        assert len(trades) == 2
        assert trades[0].signal_id == signal_id_1
        assert trades[0].trade_id == trade_id_1
        assert trades[1].signal_id == signal_id_2
        assert trades[1].trade_id == trade_id_2
    
    @pytest.mark.asyncio
    async def test_published_trade_closed_event_has_correct_signal_id(
        self,
        signal_message: SignalMessage,
    ) -> None:
        """Test that trades.closed Redis event contains correct signal_id.
        
        This is the main bug: published events were using trade_id instead
        of signal_id, breaking downstream analytics.
        """
        # Mock dependencies
        mock_repo = MagicMock(spec=TradeRepository)
        mock_publisher = MagicMock()
        mock_publisher.publish_opened = AsyncMock()
        mock_publisher.publish_closed = AsyncMock()
        mock_broker = MagicMock()
        mock_broker.close_position = AsyncMock(return_value=MagicMock(
            status="filled",
            filled_price=2660.0,
            filled_at=datetime.now(timezone.utc),
        ))
        mock_sm_manager = MagicMock()
        mock_sm_manager._bar_counter = 100
        
        # Mock successful trade closure
        mock_repo.close_trade = AsyncMock()
        
        # Create manager
        db_pool = MagicMock(spec=DatabasePool)
        db_pool.fetch = AsyncMock(return_value=[])
        db_pool.execute = AsyncMock()
        
        manager = TradeManager(
            broker=mock_broker,
            state_machine_manager=mock_sm_manager,
            trade_repository=mock_repo,
            trade_publisher=mock_publisher,
            db_pool=db_pool,
            max_active_trades=1,
        )
        
        # Create a trade with signal_id and add to active trades
        trade_id = str(uuid4())
        trade = TradeRecord(
            trade_id=trade_id,
            signal_id=signal_message.id,  # Critical: signal_id is set
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
        manager._active_trades[trade_id] = trade
        
        # Close the trade
        await manager._close_trade(
            trade=trade,
            exit_price=2660.0,
            exit_reason="TP_HIT",
            closed_at=datetime.now(timezone.utc),
        )
        
        # Verify published event has correct signal_id
        mock_publisher.publish_closed.assert_called_once()
        published_trade: TradeMessage = mock_publisher.publish_closed.call_args[0][0]
        
        # Critical: signal_id must match original signal, not trade_id!
        assert published_trade.signal_id == signal_message.id
        assert published_trade.signal_id != trade_id
        assert published_trade.id == trade_id



