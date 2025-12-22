"""Unit tests for trade repository."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

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


class TestTradeRepositoryCloseTradeValidation:
    """Test that close_trade raises exception when trade not found."""
    
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
    

