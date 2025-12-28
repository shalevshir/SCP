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
    async def test_place_order_auto_closes_orphaned_position(self) -> None:
        """Test that placing order with existing position auto-closes the orphan."""
        broker = PaperBroker()
        
        # Create first position
        await broker.place_order("GC", "long", 1, price=2650.0)
        assert len(broker.get_all_positions()) == 1
        
        # Second order should auto-close the first and create new position
        await broker.place_order("GC", "short", 1, price=2660.0)
        
        # Should have exactly one position (the new one)
        positions = broker.get_all_positions()
        assert len(positions) == 1
        assert positions[0].side == "short"
        assert positions[0].entry_price == 2660.0
    
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

    @pytest.mark.asyncio
    async def test_place_order_rejects_invalid_price(self) -> None:
        """Test that invalid price is rejected."""
        broker = PaperBroker()
        
        with pytest.raises(ValueError, match="Price must be positive"):
            await broker.place_order("GC", "long", 1, price=-100.0)

    @pytest.mark.asyncio
    async def test_cancel_order_returns_false(self) -> None:
        """Test that cancel order returns False (immediate execution)."""
        broker = PaperBroker()
        
        result = await broker.cancel_order("test-order-id")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_close_position_requires_price(self) -> None:
        """Test that close position requires explicit price."""
        broker = PaperBroker()
        await broker.place_order("GC", "long", 1, price=2650.0)
        
        with pytest.raises(ValueError, match="requires explicit price"):
            await broker.close_position("GC", price=None)

    @pytest.mark.asyncio
    async def test_close_position_rejects_invalid_price(self) -> None:
        """Test that close position rejects invalid price."""
        broker = PaperBroker()
        await broker.place_order("GC", "long", 1, price=2650.0)
        
        with pytest.raises(ValueError, match="Price must be positive"):
            await broker.close_position("GC", price=-100.0)

    @pytest.mark.asyncio
    async def test_get_all_positions(self) -> None:
        """Test getting all positions."""
        broker = PaperBroker()
        
        # Initially empty
        assert broker.get_all_positions() == []
        
        # Open position
        await broker.place_order("GC", "long", 1, price=2650.0)
        
        positions = broker.get_all_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "GC"

    @pytest.mark.asyncio
    async def test_get_order_history(self) -> None:
        """Test getting order history."""
        broker = PaperBroker()
        
        # Initially empty
        assert broker.get_order_history() == []
        
        # Place and close order
        await broker.place_order("GC", "long", 1, price=2650.0)
        await broker.close_position("GC", price=2660.0)
        
        history = broker.get_order_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_reconcile_positions_restores_positions(self) -> None:
        """Test reconciling positions from trade records."""
        broker = PaperBroker()
        
        trades = [
            ("GC", "long", 2650.0, 1),
            ("SI", "short", 30.0, 2),
        ]
        
        await broker.reconcile_positions(trades)
        
        gc_pos = await broker.get_position("GC")
        assert gc_pos is not None
        assert gc_pos.side == "long"
        assert gc_pos.entry_price == 2650.0
        
        si_pos = await broker.get_position("SI")
        assert si_pos is not None
        assert si_pos.side == "short"
        assert si_pos.quantity == 2

    @pytest.mark.asyncio
    async def test_reconcile_positions_skips_existing(self) -> None:
        """Test reconciling skips existing positions."""
        broker = PaperBroker()
        
        # Create existing position
        await broker.place_order("GC", "short", 2, price=2700.0)
        
        # Try to reconcile with different position
        trades = [("GC", "long", 2650.0, 1)]
        await broker.reconcile_positions(trades)
        
        # Should keep existing position
        position = await broker.get_position("GC")
        assert position is not None
        assert position.side == "short"
        assert position.entry_price == 2700.0

    @pytest.mark.asyncio
    async def test_get_position_returns_none_for_unknown_symbol(self) -> None:
        """Test get_position returns None for unknown symbol."""
        broker = PaperBroker()
        
        position = await broker.get_position("UNKNOWN")
        
        assert position is None



