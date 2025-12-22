"""Tests for BiasRepository."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from htf_bias_svc.repository import BiasRepository
from scp_shared.messaging.schemas import HTFBiasMessage, CandleMessage


class TestBiasRepository:
    """Test HTF bias persistence and loading."""
    
    @pytest.mark.asyncio
    async def test_save_bias_inserts_to_database(self):
        """save_bias() inserts bias message to htf_bias_history table."""
        # Mock database pool
        mock_db = AsyncMock()
        repo = BiasRepository(mock_db)
        
        bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            structure_15m="HH",
            structure_1h="HH",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        await repo.save_bias(bias)
        
        # Verify execute was called with correct query and parameters
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        
        # Check query contains INSERT
        assert "INSERT INTO htf_bias_history" in call_args[0][0]
        
        # Check parameters match bias message
        params = call_args[0][1:]
        assert params[0] == bias.timestamp
        assert params[1] == bias.bias
        assert params[2] == bias.score
        assert params[3] == bias.confidence
    
    @pytest.mark.asyncio
    async def test_save_bias_handles_conflict(self):
        """save_bias() uses ON CONFLICT DO UPDATE for duplicate timestamps."""
        mock_db = AsyncMock()
        repo = BiasRepository(mock_db)
        
        bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bearish",
            score=7.0,
            confidence="A",
            structure_15m="LL",
            structure_1h="LL",
            dxy_aligned=False,
            chop_detected=True,
        )
        
        await repo.save_bias(bias)
        
        # Verify query has ON CONFLICT clause
        call_args = mock_db.execute.call_args
        query = call_args[0][0]
        assert "ON CONFLICT" in query
        assert "DO UPDATE" in query
    
    @pytest.mark.asyncio
    async def test_load_recent_candles_fetches_from_database(self):
        """load_recent_candles() loads GC and DXY candles from candles table."""
        mock_db = AsyncMock()
        
        # Mock database results
        gc_row = {
            "timestamp": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "open": 2650.0,
            "high": 2655.0,
            "low": 2648.0,
            "close": 2652.0,
            "volume": 1000.0,
        }
        dxy_row = {
            "timestamp": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            "open": 104.5,
            "high": 104.6,
            "low": 104.4,
            "close": 104.55,
            "volume": 0.0,
        }
        
        # First call returns GC candles, second call returns DXY candles
        mock_db.fetch.side_effect = [[gc_row], [dxy_row]]
        
        repo = BiasRepository(mock_db)
        
        pairs = await repo.load_recent_candles(count=60)
        
        # Verify fetch was called twice (GC and DXY)
        assert mock_db.fetch.call_count == 2
        
        # Verify pairs returned correctly
        assert len(pairs) == 1
        gc_candle, dxy_candle = pairs[0]
        
        assert isinstance(gc_candle, CandleMessage)
        assert isinstance(dxy_candle, CandleMessage)
        assert gc_candle.symbol == "GC"
        assert dxy_candle.symbol == "DXY"
        assert gc_candle.timestamp == dxy_candle.timestamp
    
    @pytest.mark.asyncio
    async def test_load_recent_candles_pairs_by_timestamp(self):
        """load_recent_candles() pairs GC and DXY by matching timestamps."""
        mock_db = AsyncMock()
        
        # Mock multiple timestamps
        gc_rows = [
            {
                "timestamp": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                "open": 2650.0,
                "high": 2655.0,
                "low": 2648.0,
                "close": 2652.0,
                "volume": 1000.0,
            },
            {
                "timestamp": datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
                "open": 2652.0,
                "high": 2657.0,
                "low": 2650.0,
                "close": 2654.0,
                "volume": 1100.0,
            },
        ]
        dxy_rows = [
            {
                "timestamp": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                "open": 104.5,
                "high": 104.6,
                "low": 104.4,
                "close": 104.55,
                "volume": 0.0,
            },
            {
                "timestamp": datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
                "open": 104.55,
                "high": 104.65,
                "low": 104.45,
                "close": 104.60,
                "volume": 0.0,
            },
        ]
        
        mock_db.fetch.side_effect = [gc_rows, dxy_rows]
        
        repo = BiasRepository(mock_db)
        
        pairs = await repo.load_recent_candles(count=60)
        
        # Verify pairs returned in order
        assert len(pairs) == 2
        
        # Check first pair
        gc1, dxy1 = pairs[0]
        assert gc1.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert dxy1.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        
        # Check second pair
        gc2, dxy2 = pairs[1]
        assert gc2.timestamp == datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc)
        assert dxy2.timestamp == datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc)
    
    @pytest.mark.asyncio
    async def test_load_recent_candles_handles_missing_pairs(self):
        """load_recent_candles() only returns complete pairs (matching timestamps)."""
        mock_db = AsyncMock()
        
        # GC has 2 candles, DXY only has 1 (second timestamp missing)
        gc_rows = [
            {
                "timestamp": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                "open": 2650.0,
                "high": 2655.0,
                "low": 2648.0,
                "close": 2652.0,
                "volume": 1000.0,
            },
            {
                "timestamp": datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc),
                "open": 2652.0,
                "high": 2657.0,
                "low": 2650.0,
                "close": 2654.0,
                "volume": 1100.0,
            },
        ]
        dxy_rows = [
            {
                "timestamp": datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                "open": 104.5,
                "high": 104.6,
                "low": 104.4,
                "close": 104.55,
                "volume": 0.0,
            },
        ]
        
        mock_db.fetch.side_effect = [gc_rows, dxy_rows]
        
        repo = BiasRepository(mock_db)
        
        pairs = await repo.load_recent_candles(count=60)
        
        # Only 1 complete pair should be returned
        assert len(pairs) == 1
        gc, dxy = pairs[0]
        assert gc.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)

