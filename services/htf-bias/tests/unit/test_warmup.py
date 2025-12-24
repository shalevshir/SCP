"""Unit tests for HTF Bias warmup functionality."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scp_shared.messaging.schemas import CandleMessage

from htf_bias_svc.processor import HTFBiasProcessor
from htf_bias_svc.repository import BiasRepository


class TestWarmupProcessor:
    """Test warmup_processor function."""
    
    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        repo = MagicMock(spec=BiasRepository)
        repo.load_recent_candles = AsyncMock(return_value=[])
        return repo
    
    @pytest.fixture
    def mock_processor(self) -> MagicMock:
        """Create mock processor."""
        processor = MagicMock(spec=HTFBiasProcessor)
        processor.process = MagicMock(return_value=None)
        return processor
    
    @pytest.mark.asyncio
    async def test_warmup_skipped_when_disabled(
        self,
        mock_processor: MagicMock,
        mock_repository: MagicMock,
    ) -> None:
        """Warmup is skipped when disabled in config."""
        with patch("htf_bias_svc.main.config") as mock_config:
            mock_config.enable_warmup = False
            
            from htf_bias_svc.main import warmup_processor
            
            await warmup_processor(mock_processor, mock_repository)
            
            mock_repository.load_recent_candles.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_warmup_loads_candles_from_repository(
        self,
        mock_processor: MagicMock,
        mock_repository: MagicMock,
    ) -> None:
        """Warmup loads candles from repository."""
        ts = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        gc_candle = CandleMessage(
            timestamp=ts,
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2654.0,
            volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=ts,
            symbol="DXY",
            timeframe="1m",
            open=103.5,
            high=103.7,
            low=103.4,
            close=103.6,
            volume=500.0,
        )
        mock_repository.load_recent_candles = AsyncMock(
            return_value=[(gc_candle, dxy_candle)]
        )
        
        with patch("htf_bias_svc.main.config") as mock_config:
            mock_config.enable_warmup = True
            mock_config.warmup_candles = 60
            
            from htf_bias_svc.main import warmup_processor
            
            await warmup_processor(mock_processor, mock_repository)
            
            mock_repository.load_recent_candles.assert_called_once_with(count=60)
            mock_processor.process.assert_called_once_with(gc_candle, dxy_candle)
    
    @pytest.mark.asyncio
    async def test_warmup_processes_all_candles(
        self,
        mock_processor: MagicMock,
        mock_repository: MagicMock,
    ) -> None:
        """Warmup processes all loaded candle pairs."""
        candle_pairs = []
        for i in range(5):
            ts = datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc)
            gc = CandleMessage(
                timestamp=ts, symbol="GC", timeframe="1m",
                open=2650.0+i, high=2655.0+i, low=2648.0+i, close=2654.0+i, volume=1000.0,
            )
            dxy = CandleMessage(
                timestamp=ts, symbol="DXY", timeframe="1m",
                open=103.5, high=103.7, low=103.4, close=103.6, volume=500.0,
            )
            candle_pairs.append((gc, dxy))
        
        mock_repository.load_recent_candles = AsyncMock(return_value=candle_pairs)
        
        with patch("htf_bias_svc.main.config") as mock_config:
            mock_config.enable_warmup = True
            mock_config.warmup_candles = 60
            
            from htf_bias_svc.main import warmup_processor
            
            await warmup_processor(mock_processor, mock_repository)
            
            assert mock_processor.process.call_count == 5
    
    @pytest.mark.asyncio
    async def test_warmup_handles_empty_database(
        self,
        mock_processor: MagicMock,
        mock_repository: MagicMock,
    ) -> None:
        """Warmup handles empty database gracefully."""
        mock_repository.load_recent_candles = AsyncMock(return_value=[])
        
        with patch("htf_bias_svc.main.config") as mock_config:
            mock_config.enable_warmup = True
            mock_config.warmup_candles = 60
            
            from htf_bias_svc.main import warmup_processor
            
            # Should not raise
            await warmup_processor(mock_processor, mock_repository)
            
            mock_processor.process.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_warmup_handles_database_error(
        self,
        mock_processor: MagicMock,
        mock_repository: MagicMock,
    ) -> None:
        """Warmup handles database errors gracefully."""
        mock_repository.load_recent_candles = AsyncMock(
            side_effect=Exception("Database connection failed")
        )
        
        with patch("htf_bias_svc.main.config") as mock_config:
            mock_config.enable_warmup = True
            mock_config.warmup_candles = 60
            
            from htf_bias_svc.main import warmup_processor
            
            # Should not raise, continues without warmup
            await warmup_processor(mock_processor, mock_repository)
            
            mock_processor.process.assert_not_called()


class TestProcessCandlePair:
    """Test process_candle_pair helper function."""
    
    @pytest.mark.asyncio
    async def test_process_candle_pair_publishes_when_bias_computed(self) -> None:
        """Process candle pair publishes bias when computed."""
        from htf_bias_svc.main import process_candle_pair
        from scp_shared.messaging.schemas import HTFBiasMessage
        
        # Create mock bias
        mock_bias = MagicMock(spec=HTFBiasMessage)
        mock_bias.bias = "bullish"
        mock_bias.score = 8.5
        mock_bias.confidence = "A+"
        
        mock_processor = MagicMock()
        mock_processor.process = MagicMock(return_value=mock_bias)
        
        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        
        mock_repository = MagicMock()
        mock_repository.save_bias = AsyncMock()
        
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0, high=2655.0, low=2648.0, close=2654.0, volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=103.5, high=103.7, low=103.4, close=103.6, volume=500.0,
        )
        
        # Pass pair as tuple as expected by the function
        await process_candle_pair(
            (gc_candle, dxy_candle), mock_processor, mock_publisher, mock_repository
        )
        
        mock_processor.process.assert_called_once_with(gc_candle, dxy_candle)
        mock_publisher.publish.assert_called_once_with(mock_bias)
        mock_repository.save_bias.assert_called_once_with(mock_bias)
    
    @pytest.mark.asyncio
    async def test_process_candle_pair_skips_when_no_bias(self) -> None:
        """Process candle pair skips publishing when no bias computed."""
        from htf_bias_svc.main import process_candle_pair
        
        mock_processor = MagicMock()
        mock_processor.process = MagicMock(return_value=None)  # No bias
        
        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        
        mock_repository = MagicMock()
        mock_repository.save_bias = AsyncMock()
        
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC", timeframe="1m",
            open=2650.0, high=2655.0, low=2648.0, close=2654.0, volume=1000.0,
        )
        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY", timeframe="1m",
            open=103.5, high=103.7, low=103.4, close=103.6, volume=500.0,
        )
        
        # Pass pair as tuple as expected by the function
        await process_candle_pair(
            (gc_candle, dxy_candle), mock_processor, mock_publisher, mock_repository
        )
        
        mock_publisher.publish.assert_not_called()
        mock_repository.save_bias.assert_not_called()
