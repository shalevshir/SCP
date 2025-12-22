"""Unit tests for TradePublisher with zero P&L handling."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis

from execution_svc.trade_publisher import TradePublisher
from scp_shared.messaging.schemas import TradeMessage


@pytest.fixture
def mock_redis_client() -> redis.Redis:
    """Create mock Redis client."""
    client = MagicMock(spec=redis.Redis)
    return client


@pytest.fixture
def mock_publisher() -> MagicMock:
    """Create mock RedisStreamPublisher."""
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value="test-message-id")
    return publisher


class TestTradePublisherZeroPnL:
    """Test that zero P&L is correctly formatted in logs."""
    
    @pytest.mark.asyncio
    async def test_publish_closed_with_zero_pnl(
        self,
        mock_redis_client: redis.Redis,
        mock_publisher: MagicMock,
    ) -> None:
        """Test that trades with 0.0 P&L show '0.00 points' not 'N/A'.
        
        Bug: The condition `if trade.pnl_points` is falsy for 0.0,
        causing trades that close at entry price to log 'N/A' instead
        of '0.00 points'.
        
        Expected: Zero P&L should be formatted as '0.00 points'.
        """
        # Create trade message with zero P&L
        trade = TradeMessage(
            id="test-trade-1",
            signal_id="test-signal-1",
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            quantity=1,
            opened_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            closed_at=datetime(2025, 1, 15, 10, 5, tzinfo=timezone.utc),
            exit_price=2650.0,  # Exited at entry price
            pnl_points=0.0,  # Zero P&L (not None!)
            exit_reason="MANUAL_EXIT",
        )
        
        # Create publisher
        publisher = TradePublisher(mock_redis_client)
        publisher._publisher = mock_publisher
        
        # Publish trade with logging captured
        with patch("execution_svc.trade_publisher.logger") as mock_logger:
            await publisher.publish_closed(trade)
            
            # Verify log was called
            assert mock_logger.info.called
            
            # Get the log message
            log_call = mock_logger.info.call_args[0][0]
            
            # BUG VERIFICATION: Currently logs 'pnl=N/A' for zero P&L
            # Should log 'pnl=0.00 points' instead
            assert "pnl=0.00 points" in log_call, (
                f"Expected 'pnl=0.00 points' but got: {log_call}"
            )
    
    @pytest.mark.asyncio
    async def test_publish_closed_with_positive_pnl(
        self,
        mock_redis_client: redis.Redis,
        mock_publisher: MagicMock,
    ) -> None:
        """Test that positive P&L is correctly formatted."""
        trade = TradeMessage(
            id="test-trade-2",
            signal_id="test-signal-2",
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            quantity=1,
            opened_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            closed_at=datetime(2025, 1, 15, 10, 5, tzinfo=timezone.utc),
            exit_price=2660.0,  # +10 points
            pnl_points=10.0,
            exit_reason="TP_HIT",
        )
        
        publisher = TradePublisher(mock_redis_client)
        publisher._publisher = mock_publisher
        
        with patch("execution_svc.trade_publisher.logger") as mock_logger:
            await publisher.publish_closed(trade)
            
            log_call = mock_logger.info.call_args[0][0]
            assert "pnl=10.00 points" in log_call
    
    @pytest.mark.asyncio
    async def test_publish_closed_with_negative_pnl(
        self,
        mock_redis_client: redis.Redis,
        mock_publisher: MagicMock,
    ) -> None:
        """Test that negative P&L is correctly formatted."""
        trade = TradeMessage(
            id="test-trade-3",
            signal_id="test-signal-3",
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            quantity=1,
            opened_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            closed_at=datetime(2025, 1, 15, 10, 5, tzinfo=timezone.utc),
            exit_price=2645.0,  # -5 points (SL hit)
            pnl_points=-5.0,
            exit_reason="SL_HIT",
        )
        
        publisher = TradePublisher(mock_redis_client)
        publisher._publisher = mock_publisher
        
        with patch("execution_svc.trade_publisher.logger") as mock_logger:
            await publisher.publish_closed(trade)
            
            log_call = mock_logger.info.call_args[0][0]
            assert "pnl=-5.00 points" in log_call
    
    @pytest.mark.asyncio
    async def test_publish_closed_with_none_pnl(
        self,
        mock_redis_client: redis.Redis,
        mock_publisher: MagicMock,
    ) -> None:
        """Test that None P&L is correctly formatted as 'N/A'."""
        trade = TradeMessage(
            id="test-trade-4",
            signal_id="test-signal-4",
            direction="long",
            entry_price=2650.0,
            sl_price=2645.0,
            tp_price=2662.0,
            quantity=1,
            opened_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            closed_at=datetime(2025, 1, 15, 10, 5, tzinfo=timezone.utc),
            exit_price=2650.0,
            pnl_points=None,  # Missing P&L
            exit_reason="ERROR",
        )
        
        publisher = TradePublisher(mock_redis_client)
        publisher._publisher = mock_publisher
        
        with patch("execution_svc.trade_publisher.logger") as mock_logger:
            await publisher.publish_closed(trade)
            
            log_call = mock_logger.info.call_args[0][0]
            assert "pnl=N/A" in log_call


