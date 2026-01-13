"""Unit tests for IBPaperBroker and IBClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from execution_svc.broker.ib_paper import IBPaperBroker
from execution_svc.broker.base import OrderResult, Position


@pytest.fixture
def mock_ib_client():
    """Mock IBClient for testing without real IB connection."""
    with patch('execution_svc.broker.ib_paper.IBClient') as mock_client_class:
        mock_client = MagicMock()
        mock_client.connect_async = AsyncMock()
        mock_client.disconnect_async = AsyncMock()
        mock_client.place_order_async = AsyncMock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.mark.asyncio
async def test_ib_paper_broker_connect(mock_ib_client):
    """Test connecting to IB."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    await broker.connect()
    
    mock_ib_client.connect_async.assert_called_once()


@pytest.mark.asyncio
async def test_ib_paper_broker_disconnect(mock_ib_client):
    """Test disconnecting from IB."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    await broker.disconnect()
    
    mock_ib_client.disconnect_async.assert_called_once()


@pytest.mark.asyncio
async def test_place_order_success(mock_ib_client):
    """Test successful order placement through IB."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    # Mock successful order fill
    mock_ib_client.place_order_async.return_value = OrderResult(
        order_id="123",
        symbol="GC",
        side="long",
        quantity=1,
        filled_price=2650.0,
        filled_at=datetime.utcnow(),
        status="filled",
    )
    
    result = await broker.place_order("GC", "long", 1, 2650.0)
    
    assert result.status == "filled"
    assert result.filled_price == 2650.0
    assert result.symbol == "GC"
    assert result.side == "long"
    
    # Verify position was tracked internally
    position = await broker.get_position("GC")
    assert position is not None
    assert position.side == "long"
    assert position.quantity == 1
    assert position.entry_price == 2650.0


@pytest.mark.asyncio
async def test_place_order_rejected(mock_ib_client):
    """Test order rejection from IB."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    # Mock rejected order
    mock_ib_client.place_order_async.return_value = OrderResult(
        order_id="124",
        symbol="GC",
        side="long",
        quantity=1,
        status="rejected",
    )
    
    result = await broker.place_order("GC", "long", 1, 2650.0)
    
    assert result.status == "rejected"
    
    # Verify no position was created
    position = await broker.get_position("GC")
    assert position is None


@pytest.mark.asyncio
async def test_close_position_success(mock_ib_client):
    """Test closing a position through IB."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    # First, place an order to create a position
    mock_ib_client.place_order_async.return_value = OrderResult(
        order_id="125",
        symbol="GC",
        side="long",
        quantity=1,
        filled_price=2650.0,
        filled_at=datetime.utcnow(),
        status="filled",
    )
    await broker.place_order("GC", "long", 1, 2650.0)
    
    # Now close the position
    mock_ib_client.place_order_async.return_value = OrderResult(
        order_id="126",
        symbol="GC",
        side="short",
        quantity=1,
        filled_price=2660.0,
        filled_at=datetime.utcnow(),
        status="filled",
    )
    
    result = await broker.close_position("GC", 2660.0)
    
    assert result.status == "filled"
    assert result.filled_price == 2660.0
    
    # Verify position was removed
    position = await broker.get_position("GC")
    assert position is None


@pytest.mark.asyncio
async def test_close_position_no_position():
    """Test closing a non-existent position raises error."""
    with patch('execution_svc.broker.ib_paper.IBClient'):
        broker = IBPaperBroker("127.0.0.1", 7497, 1)
        
        with pytest.raises(ValueError, match="No position exists"):
            await broker.close_position("GC", 2650.0)


@pytest.mark.asyncio
async def test_place_order_invalid_quantity():
    """Test placing order with invalid quantity."""
    with patch('execution_svc.broker.ib_paper.IBClient'):
        broker = IBPaperBroker("127.0.0.1", 7497, 1)
        
        with pytest.raises(ValueError, match="Quantity must be positive"):
            await broker.place_order("GC", "long", 0, 2650.0)


@pytest.mark.asyncio
async def test_place_order_invalid_price():
    """Test placing order with invalid price."""
    with patch('execution_svc.broker.ib_paper.IBClient'):
        broker = IBPaperBroker("127.0.0.1", 7497, 1)
        
        with pytest.raises(ValueError, match="Price must be positive"):
            await broker.place_order("GC", "long", 1, -100.0)


@pytest.mark.asyncio
async def test_get_all_positions(mock_ib_client):
    """Test getting all positions."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    # Place an order to create a position
    mock_ib_client.place_order_async.return_value = OrderResult(
        order_id="127",
        symbol="GC",
        side="long",
        quantity=1,
        filled_price=2650.0,
        filled_at=datetime.utcnow(),
        status="filled",
    )
    await broker.place_order("GC", "long", 1, 2650.0)
    
    positions = broker.get_all_positions()
    
    assert len(positions) == 1
    assert positions[0].symbol == "GC"
    assert positions[0].side == "long"


@pytest.mark.asyncio
async def test_reconcile_positions(mock_ib_client):
    """Test reconciling positions on startup."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    # Reconcile a position from database
    trades = [("GC", "long", 2650.0, 1)]
    await broker.reconcile_positions(trades)
    
    # Verify position was restored
    position = await broker.get_position("GC")
    assert position is not None
    assert position.side == "long"
    assert position.entry_price == 2650.0
    assert position.quantity == 1


@pytest.mark.asyncio
async def test_reset_state(mock_ib_client):
    """Test resetting broker state."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    # Place an order to create a position
    mock_ib_client.place_order_async.return_value = OrderResult(
        order_id="128",
        symbol="GC",
        side="long",
        quantity=1,
        filled_price=2650.0,
        filled_at=datetime.utcnow(),
        status="filled",
    )
    await broker.place_order("GC", "long", 1, 2650.0)
    
    # Reset state
    broker.reset_state()
    
    # Verify position was cleared
    position = await broker.get_position("GC")
    assert position is None


@pytest.mark.asyncio
async def test_cancel_order_not_supported():
    """Test that cancel order is not supported."""
    with patch('execution_svc.broker.ib_paper.IBClient'):
        broker = IBPaperBroker("127.0.0.1", 7497, 1)
        
        result = await broker.cancel_order("123")
        
        assert result is False


@pytest.mark.asyncio
async def test_place_order_auto_closes_existing_position(mock_ib_client):
    """Test that placing an order auto-closes existing position."""
    broker = IBPaperBroker("127.0.0.1", 7497, 1)
    
    # Place first order
    mock_ib_client.place_order_async.return_value = OrderResult(
        order_id="129",
        symbol="GC",
        side="long",
        quantity=1,
        filled_price=2650.0,
        filled_at=datetime.utcnow(),
        status="filled",
    )
    await broker.place_order("GC", "long", 1, 2650.0)
    
    # Place second order for same symbol (should auto-close first)
    mock_ib_client.place_order_async.side_effect = [
        # First call: close existing position
        OrderResult(
            order_id="130",
            symbol="GC",
            side="short",
            quantity=1,
            filled_price=2660.0,
            filled_at=datetime.utcnow(),
            status="filled",
        ),
        # Second call: open new position
        OrderResult(
            order_id="131",
            symbol="GC",
            side="long",
            quantity=1,
            filled_price=2660.0,
            filled_at=datetime.utcnow(),
            status="filled",
        ),
    ]
    
    result = await broker.place_order("GC", "long", 1, 2660.0)
    
    assert result.status == "filled"
    assert mock_ib_client.place_order_async.call_count == 3  # Original + close + reopen
