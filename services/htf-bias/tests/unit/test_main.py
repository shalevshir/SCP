"""Tests for HTF Bias Service main lifecycle."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from htf_bias_svc.main import (
    warmup_processor,
    process_candle_pair,
)
from htf_bias_svc.processor import HTFBiasProcessor
from htf_bias_svc.publisher import BiasPublisher
from htf_bias_svc.repository import BiasRepository
from scp_shared.messaging.schemas import CandleMessage, HTFBiasMessage


class TestWarmupProcessor:
    """Test processor warmup logic."""
    
    @pytest.mark.asyncio
    async def test_warmup_loads_candles_from_database(self):
        """warmup_processor() loads recent candles and replays through processor."""
        # Mock repository
        mock_repo = AsyncMock(spec=BiasRepository)
        
        # Mock candle pairs
        candle_pairs = [
            (
                CandleMessage(
                    timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                    symbol="GC",
                    timeframe="1m",
                    open=2650.0,
                    high=2655.0,
                    low=2648.0,
                    close=2652.0,
                    volume=1000.0,
                ),
                CandleMessage(
                    timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                    symbol="DXY",
                    timeframe="1m",
                    open=104.5,
                    high=104.6,
                    low=104.4,
                    close=104.55,
                    volume=0.0,
                ),
            )
        ]
        mock_repo.load_recent_candles.return_value = candle_pairs
        
        # Create processor
        processor = HTFBiasProcessor()
        
        # Warmup
        await warmup_processor(processor, mock_repo)
        
        # Verify load_recent_candles was called
        mock_repo.load_recent_candles.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_warmup_handles_empty_database(self):
        """warmup_processor() handles case where database is empty."""
        mock_repo = AsyncMock(spec=BiasRepository)
        mock_repo.load_recent_candles.return_value = []
        
        processor = HTFBiasProcessor()
        
        # Should not raise error
        await warmup_processor(processor, mock_repo)
    
    @pytest.mark.asyncio
    async def test_warmup_handles_database_error(self):
        """warmup_processor() handles database errors gracefully."""
        mock_repo = AsyncMock(spec=BiasRepository)
        mock_repo.load_recent_candles.side_effect = Exception("Database connection failed")
        
        processor = HTFBiasProcessor()
        
        # Should not raise error (logs and continues)
        await warmup_processor(processor, mock_repo)


class TestProcessCandlePair:
    """Test candle pair processing logic."""
    
    @pytest.mark.asyncio
    async def test_process_candle_pair_publishes_when_bias_computed(self):
        """process_candle_pair() publishes and persists when bias is computed."""
        # Create real processor
        processor = HTFBiasProcessor()
        
        # Mock publisher and repository
        mock_publisher = AsyncMock(spec=BiasPublisher)
        mock_repo = AsyncMock(spec=BiasRepository)
        
        # Create candle pair
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        # Feed enough data to get a bias (this may return None due to warmup)
        # We'll mock the processor to return a bias
        mock_bias = HTFBiasMessage(
            timestamp=gc_candle.timestamp,
            bias="bullish",
            score=8.5,
            confidence="A+",
            structure_15m="HH",
            structure_1h="HH",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        with patch.object(processor, 'process', return_value=mock_bias):
            await process_candle_pair(
                (gc_candle, dxy_candle),
                processor,
                mock_publisher,
                mock_repo,
            )
        
        # Verify publish and save were called
        mock_publisher.publish.assert_called_once_with(mock_bias)
        mock_repo.save_bias.assert_called_once_with(mock_bias)
    
    @pytest.mark.asyncio
    async def test_process_candle_pair_skips_when_no_bias(self):
        """process_candle_pair() skips publish/persist when no bias computed."""
        processor = HTFBiasProcessor()
        mock_publisher = AsyncMock(spec=BiasPublisher)
        mock_repo = AsyncMock(spec=BiasRepository)
        
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=104.5,
            high=104.6,
            low=104.4,
            close=104.55,
            volume=0.0,
        )
        
        # Mock processor to return None (no bias yet)
        with patch.object(processor, 'process', return_value=None):
            await process_candle_pair(
                (gc_candle, dxy_candle),
                processor,
                mock_publisher,
                mock_repo,
            )
        
        # Verify publish and save were NOT called
        mock_publisher.publish.assert_not_called()
        mock_repo.save_bias.assert_not_called()


