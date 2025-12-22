"""Unit tests for paper broker."""

import pytest

from execution_svc.broker import PaperBroker


class TestPaperBroker:
    """Test paper trading broker."""
    
    @pytest.mark.asyncio
    async def test_place_order_long(self) -> None:
        """Test placing a long order."""
        broker = PaperBroker()
        
        result = await broker.place_order("GC", "long", 1, price=2650.0)
        
        assert result.status == "filled"
        assert result.symbol == "GC"
        assert result.side == "long"
        assert result.quantity == 1
        assert result.filled_price == 2650.0
        assert result.order_id is not None
    
    @pytest.mark.asyncio
    async def test_place_order_short(self) -> None:
        """Test placing a short order."""
        broker = PaperBroker()
        
        result = await broker.place_order("GC", "short", 1, price=2650.0)
        
        assert result.status == "filled"
        assert result.side == "short"
    
    @pytest.mark.asyncio
    async def test_place_order_creates_position(self) -> None:
        """Test that placing order creates position."""
        broker = PaperBroker()
        
        await broker.place_order("GC", "long", 1, price=2650.0)
        
        position = await broker.get_position("GC")
        assert position is not None
        assert position.symbol == "GC"
        assert position.side == "long"
        assert position.quantity == 1
        assert position.entry_price == 2650.0
    
    @pytest.mark.asyncio
    async def test_place_order_rejects_duplicate_position(self) -> None:
        """Test that placing order with existing position raises error."""
        broker = PaperBroker()
        
        await broker.place_order("GC", "long", 1, price=2650.0)
        
        with pytest.raises(ValueError, match="Position already exists"):
            await broker.place_order("GC", "long", 1, price=2655.0)
    
    @pytest.mark.asyncio
    async def test_close_position_long_profit(self) -> None:
        """Test closing long position with profit."""
        broker = PaperBroker()
        
        # Open position
        await broker.place_order("GC", "long", 1, price=2650.0)
        
        # Close position
        result = await broker.close_position("GC", price=2660.0)
        
        assert result.status == "filled"
        assert result.side == "short"  # Closing long = short order
        assert result.filled_price == 2660.0
        
        # Position should be removed
        position = await broker.get_position("GC")
        assert position is None
    
    @pytest.mark.asyncio
    async def test_close_position_short_profit(self) -> None:
        """Test closing short position with profit."""
        broker = PaperBroker()
        
        # Open position
        await broker.place_order("GC", "short", 1, price=2650.0)
        
        # Close position
        result = await broker.close_position("GC", price=2640.0)
        
        assert result.status == "filled"
        assert result.side == "long"  # Closing short = long order
        assert result.filled_price == 2640.0
    
    @pytest.mark.asyncio
    async def test_close_position_no_position_raises_error(self) -> None:
        """Test closing non-existent position raises error."""
        broker = PaperBroker()
        
        with pytest.raises(ValueError, match="No position exists"):
            await broker.close_position("GC", price=2650.0)
    
    @pytest.mark.asyncio
    async def test_place_order_requires_price(self) -> None:
        """Test that paper broker requires explicit price."""
        broker = PaperBroker()
        
        with pytest.raises(ValueError, match="requires explicit price"):
            await broker.place_order("GC", "long", 1, price=None)
    
    @pytest.mark.asyncio
    async def test_place_order_rejects_invalid_quantity(self) -> None:
        """Test that invalid quantity is rejected."""
        broker = PaperBroker()
        
        with pytest.raises(ValueError, match="Quantity must be positive"):
            await broker.place_order("GC", "long", 0, price=2650.0)


