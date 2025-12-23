"""Unit tests for trade repository."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from execution_svc.trade_repository import TradeRepository
from scp_shared.database import DatabasePool
from scp_shared.execution.types import TradeRecord


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
def sample_trade() -> TradeRecord:
    """Create sample trade record."""
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


class TestTradeRepositoryInsertTrade:
    """Test insert_trade method."""
    
    @pytest.mark.asyncio
    async def test_insert_trade_returns_trade_id(self, db_pool: DatabasePool) -> None:
        """Insert trade returns the generated trade ID."""
        trade_id = "550e8400-e29b-41d4-a716-446655440000"
        db_pool.fetchrow.return_value = {"id": UUID(trade_id)}
        
        repo = TradeRepository(db_pool)
        result = await repo.insert_trade(
            signal_id="550e8400-e29b-41d4-a716-446655440001",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            quantity=1,
            opened_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            entry_bar_idx=100,
        )
        
        assert result == trade_id
        db_pool.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_insert_trade_without_entry_bar_idx(self, db_pool: DatabasePool) -> None:
        """Insert trade works without entry_bar_idx."""
        trade_id = "550e8400-e29b-41d4-a716-446655440000"
        db_pool.fetchrow.return_value = {"id": UUID(trade_id)}
        
        repo = TradeRepository(db_pool)
        result = await repo.insert_trade(
            signal_id="550e8400-e29b-41d4-a716-446655440001",
            direction="short",
            setup_type="VWAP_FADE",
            entry_price=2640.0,
            sl_price=2645.0,
            tp_price=2620.0,
            quantity=1,
            opened_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        
        assert result == trade_id


class TestTradeRepositoryUpdateTrade:
    """Test update_trade method."""
    
    @pytest.mark.asyncio
    async def test_update_trade_single_field(self, db_pool: DatabasePool) -> None:
        """Update trade with single field."""
        repo = TradeRepository(db_pool)
        
        await repo.update_trade(
            trade_id="550e8400-e29b-41d4-a716-446655440000",
            updates={"reached_1r": True},
        )
        
        db_pool.execute.assert_called_once()
        call_args = db_pool.execute.call_args[0]
        assert "UPDATE trades" in call_args[0]
        assert "reached_1r = $1" in call_args[0]
    
    @pytest.mark.asyncio
    async def test_update_trade_multiple_fields(self, db_pool: DatabasePool) -> None:
        """Update trade with multiple fields."""
        repo = TradeRepository(db_pool)
        
        await repo.update_trade(
            trade_id="550e8400-e29b-41d4-a716-446655440000",
            updates={
                "exit_price": 2660.0,
                "exit_reason": "TP_HIT",
            },
        )
        
        db_pool.execute.assert_called_once()
        call_args = db_pool.execute.call_args[0]
        assert "UPDATE trades" in call_args[0]


class TestTradeRepositoryGetTrade:
    """Test get_trade method."""
    
    @pytest.mark.asyncio
    async def test_get_trade_returns_none_when_not_found(
        self, db_pool: DatabasePool
    ) -> None:
        """Get trade returns None when not found."""
        db_pool.fetchrow.return_value = None
        
        repo = TradeRepository(db_pool)
        result = await repo.get_trade("550e8400-e29b-41d4-a716-446655440000")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_trade_returns_trade_record(
        self, db_pool: DatabasePool
    ) -> None:
        """Get trade returns populated TradeRecord."""
        db_pool.fetchrow.return_value = {
            "id": UUID("550e8400-e29b-41d4-a716-446655440000"),
            "signal_id": UUID("550e8400-e29b-41d4-a716-446655440001"),
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
        
        repo = TradeRepository(db_pool)
        result = await repo.get_trade("550e8400-e29b-41d4-a716-446655440000")
        
        assert result is not None
        assert isinstance(result, TradeRecord)
        assert result.direction == "long"
        assert result.entry_price == 2650.0
        assert result.risk_amount == 5.0  # entry - sl = 2650 - 2645
        assert result.reward_amount == 12.0  # tp - entry = 2662 - 2650
    
    @pytest.mark.asyncio
    async def test_get_trade_short_direction_risk_calculation(
        self, db_pool: DatabasePool
    ) -> None:
        """Get trade calculates risk correctly for short direction."""
        db_pool.fetchrow.return_value = {
            "id": UUID("550e8400-e29b-41d4-a716-446655440000"),
            "signal_id": UUID("550e8400-e29b-41d4-a716-446655440001"),
            "direction": "short",
            "setup_type": "VWAP_FADE",
            "entry_price": 2650.0,
            "sl_price": 2655.0,  # SL above entry for short
            "tp_price": 2638.0,  # TP below entry for short
            "quantity": 1,
            "opened_at": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "closed_at": None,
            "exit_price": None,
            "exit_reason": None,
            "pnl_points": None,
            "entry_bar_idx": 100,
            "reached_1r": True,
        }
        
        repo = TradeRepository(db_pool)
        result = await repo.get_trade("550e8400-e29b-41d4-a716-446655440000")
        
        assert result is not None
        assert result.direction == "short"
        assert result.risk_amount == 5.0  # sl - entry = 2655 - 2650
        assert result.reward_amount == 12.0  # entry - tp = 2650 - 2638
        assert result.reached_1r is True


class TestTradeRepositoryGetOpenTrades:
    """Test get_open_trades method."""
    
    @pytest.mark.asyncio
    async def test_get_open_trades_returns_empty_list(
        self, db_pool: DatabasePool
    ) -> None:
        """Get open trades returns empty list when none exist."""
        db_pool.fetch.return_value = []
        
        repo = TradeRepository(db_pool)
        result = await repo.get_open_trades()
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_get_open_trades_returns_trade_list(
        self, db_pool: DatabasePool
    ) -> None:
        """Get open trades returns list of TradeRecord."""
        db_pool.fetch.return_value = [
            {
                "id": UUID("550e8400-e29b-41d4-a716-446655440000"),
                "signal_id": UUID("550e8400-e29b-41d4-a716-446655440001"),
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
                "id": UUID("550e8400-e29b-41d4-a716-446655440002"),
                "signal_id": UUID("550e8400-e29b-41d4-a716-446655440003"),
                "direction": "short",
                "setup_type": "VWAP_FADE",
                "entry_price": 2640.0,
                "sl_price": 2645.0,
                "tp_price": 2620.0,
                "quantity": 1,
                "opened_at": datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
                "entry_bar_idx": 130,
                "reached_1r": True,
            },
        ]
        
        repo = TradeRepository(db_pool)
        result = await repo.get_open_trades()
        
        assert len(result) == 2
        assert all(isinstance(t, TradeRecord) for t in result)
        assert result[0].direction == "long"
        assert result[1].direction == "short"


class TestTradeRepositoryCloseTrade:
    """Test close_trade method."""
    
    @pytest.mark.asyncio
    async def test_close_trade_raises_when_not_found(
        self,
        db_pool: DatabasePool,
    ) -> None:
        """Test that closing non-existent trade raises ValueError.
        
        This test demonstrates the bug fix: close_trade() should raise
        an exception when the trade is not found, rather than silently
        returning, so that callers can handle the error appropriately.
        """
        repo = TradeRepository(db_pool)
        
        # Mock get_trade to return None (trade not found)
        db_pool.fetchrow.return_value = None
        
        # Use a valid UUID format
        non_existent_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Attempt to close non-existent trade
        with pytest.raises(ValueError, match="Trade .* not found"):
            await repo.close_trade(
                trade_id=non_existent_id,
                exit_price=2660.0,
                exit_reason="TP_HIT",
                closed_at=datetime.now(timezone.utc),
            )
    
    @pytest.mark.asyncio
    async def test_close_trade_calculates_pnl_long(
        self, db_pool: DatabasePool
    ) -> None:
        """Close trade calculates P&L correctly for long position."""
        # First call for get_trade
        db_pool.fetchrow.return_value = {
            "id": UUID("550e8400-e29b-41d4-a716-446655440000"),
            "signal_id": UUID("550e8400-e29b-41d4-a716-446655440001"),
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
        
        repo = TradeRepository(db_pool)
        await repo.close_trade(
            trade_id="550e8400-e29b-41d4-a716-446655440000",
            exit_price=2660.0,
            exit_reason="TP_HIT",
            closed_at=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        )
        
        db_pool.execute.assert_called_once()
        call_args = db_pool.execute.call_args[0]
        # Check P&L is calculated: exit - entry = 2660 - 2650 = 10
        assert call_args[4] == 10.0  # pnl_points
    
    @pytest.mark.asyncio
    async def test_close_trade_calculates_pnl_short(
        self, db_pool: DatabasePool
    ) -> None:
        """Close trade calculates P&L correctly for short position."""
        db_pool.fetchrow.return_value = {
            "id": UUID("550e8400-e29b-41d4-a716-446655440000"),
            "signal_id": UUID("550e8400-e29b-41d4-a716-446655440001"),
            "direction": "short",
            "setup_type": "VWAP_FADE",
            "entry_price": 2650.0,
            "sl_price": 2655.0,
            "tp_price": 2638.0,
            "quantity": 1,
            "opened_at": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "closed_at": None,
            "exit_price": None,
            "exit_reason": None,
            "pnl_points": None,
            "entry_bar_idx": 100,
            "reached_1r": False,
        }
        
        repo = TradeRepository(db_pool)
        await repo.close_trade(
            trade_id="550e8400-e29b-41d4-a716-446655440000",
            exit_price=2640.0,
            exit_reason="TP_HIT",
            closed_at=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        )
        
        db_pool.execute.assert_called_once()
        call_args = db_pool.execute.call_args[0]
        # Check P&L is calculated: entry - exit = 2650 - 2640 = 10
        assert call_args[4] == 10.0  # pnl_points


class TestTradeRepositoryUpdateReached1R:
    """Test update_reached_1r method."""
    
    @pytest.mark.asyncio
    async def test_update_reached_1r(self, db_pool: DatabasePool) -> None:
        """Update reached_1r status."""
        repo = TradeRepository(db_pool)
        
        await repo.update_reached_1r(
            trade_id="550e8400-e29b-41d4-a716-446655440000",
            reached_1r=True,
        )
        
        db_pool.execute.assert_called_once()
        call_args = db_pool.execute.call_args[0]
        assert "UPDATE trades" in call_args[0]
        assert "reached_1r" in call_args[0]


class TestTradeRepositoryReconcilePositions:
    """Test reconcile_positions method."""
    
    @pytest.mark.asyncio
    async def test_reconcile_positions_returns_open_trades(
        self, db_pool: DatabasePool
    ) -> None:
        """Reconcile positions returns list of open trades."""
        db_pool.fetch.return_value = [
            {
                "id": UUID("550e8400-e29b-41d4-a716-446655440000"),
                "signal_id": UUID("550e8400-e29b-41d4-a716-446655440001"),
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
        ]
        
        repo = TradeRepository(db_pool)
        result = await repo.reconcile_positions()
        
        assert len(result) == 1
        assert result[0].direction == "long"


class TestTradeRepositoryGetTradesForDate:
    """Test get_trades_for_date method."""
    
    @pytest.mark.asyncio
    async def test_get_trades_for_date_returns_all_trades(
        self, db_pool: DatabasePool
    ) -> None:
        """Get trades for date returns both open and closed trades."""
        db_pool.fetch.return_value = [
            {
                "id": UUID("550e8400-e29b-41d4-a716-446655440000"),
                "signal_id": UUID("550e8400-e29b-41d4-a716-446655440001"),
                "direction": "long",
                "setup_type": "VWAP_RECLAIM",
                "entry_price": 2650.0,
                "sl_price": 2645.0,
                "tp_price": 2662.0,
                "quantity": 1,
                "opened_at": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                "closed_at": datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
                "exit_price": 2660.0,
                "exit_reason": "TP_HIT",
                "pnl_points": 10.0,
                "entry_bar_idx": 100,
                "reached_1r": True,
            },
        ]
        
        repo = TradeRepository(db_pool)
        result = await repo.get_trades_for_date(
            datetime(2025, 1, 15, tzinfo=timezone.utc)
        )
        
        assert len(result) == 1
        assert result[0].exit_price == 2660.0
        assert result[0].pnl == 10.0
    

