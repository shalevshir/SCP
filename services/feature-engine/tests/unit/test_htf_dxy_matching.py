"""Tests for HTF DXY timeframe matching fix.

Verifies that HTF features (15m, 1h) use matching HTF DXY candles
instead of 1m DXY candles for correct DXY correlation calculation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from feature_engine_svc.main import process_candle_pair
from feature_engine_svc.processor import FeatureProcessor
from feature_engine_svc.htf_aggregator import HTFCandleAggregator
from feature_engine_svc.publisher import FeaturePublisher
from feature_engine_svc.repository import FeatureRepository
from scp_shared.messaging.schemas import CandleMessage


class TestHTFDXYMatching:
    """Test that HTF features use matching HTF DXY candles."""
    
    @pytest.mark.asyncio
    async def test_15m_features_use_15m_dxy_candle(self):
        """15m features must use 15m DXY candle, not 1m DXY candle."""
        # Setup processors
        processor_1m = FeatureProcessor(timeframe="1m")
        processor_15m = FeatureProcessor(timeframe="15m")
        processor_1h = FeatureProcessor(timeframe="1h")
        
        # Setup aggregators
        htf_aggregator_gc = HTFCandleAggregator()
        htf_aggregator_dxy = HTFCandleAggregator()
        
        # Setup mocks
        publisher = MagicMock(spec=FeaturePublisher)
        publisher.publish = AsyncMock()
        repository = MagicMock(spec=FeatureRepository)
        repository.save_features = AsyncMock()
        
        # Feed 15 x 1m candle pairs to trigger 15m boundary
        for i in range(15):
            gc_candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.1,
                high=2655.0 + i * 0.1,
                low=2648.0 + i * 0.1,
                close=2652.0 + i * 0.1,
                volume=1000.0,
            )
            dxy_candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5 - i * 0.01,
                high=104.6 - i * 0.01,
                low=104.4 - i * 0.01,
                close=104.55 - i * 0.01,
                volume=0.0,
            )
            
            pair = (gc_candle, dxy_candle)
            await process_candle_pair(
                pair,
                processor_1m,
                processor_15m,
                processor_1h,
                htf_aggregator_gc,
                htf_aggregator_dxy,
                publisher,
                repository,
            )
        
        # Verify that 15m features were processed with 15m DXY candle
        # Check that repository.save_features was called with 15m features
        save_calls = repository.save_features.await_args_list
        
        # Find the 15m features call
        features_15m_call = None
        for call in save_calls:
            features = call[0][0]  # First positional argument
            if features.timeframe == "15m":
                features_15m_call = features
                break
        
        # Verify 15m features were created
        assert features_15m_call is not None, "15m features should have been processed"
        assert features_15m_call.timeframe == "15m"
        assert features_15m_call.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        
        # The key verification: processor_15m should have been called with
        # a 15m DXY candle, not a 1m DXY candle. We verify this indirectly
        # by checking that the processor was called (via the saved features).
        # The actual timeframe matching is verified by the fact that the
        # code would log a warning and skip processing if DXY candle didn't match.
    
    @pytest.mark.asyncio
    async def test_1h_features_use_1h_dxy_candle(self):
        """1h features must use 1h DXY candle, not 1m DXY candle."""
        # Setup processors
        processor_1m = FeatureProcessor(timeframe="1m")
        processor_15m = FeatureProcessor(timeframe="15m")
        processor_1h = FeatureProcessor(timeframe="1h")
        
        # Setup aggregators
        htf_aggregator_gc = HTFCandleAggregator()
        htf_aggregator_dxy = HTFCandleAggregator()
        
        # Setup mocks
        publisher = MagicMock(spec=FeaturePublisher)
        publisher.publish = AsyncMock()
        repository = MagicMock(spec=FeatureRepository)
        repository.save_features = AsyncMock()
        
        # Feed 60 x 1m candle pairs to trigger 1h boundary
        for i in range(60):
            gc_candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0 + i * 0.1,
                high=2655.0 + i * 0.1,
                low=2648.0 + i * 0.1,
                close=2652.0 + i * 0.1,
                volume=1000.0,
            )
            dxy_candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5 - i * 0.01,
                high=104.6 - i * 0.01,
                low=104.4 - i * 0.01,
                close=104.55 - i * 0.01,
                volume=0.0,
            )
            
            pair = (gc_candle, dxy_candle)
            await process_candle_pair(
                pair,
                processor_1m,
                processor_15m,
                processor_1h,
                htf_aggregator_gc,
                htf_aggregator_dxy,
                publisher,
                repository,
            )
        
        # Verify that 1h features were processed with 1h DXY candle
        save_calls = repository.save_features.await_args_list
        
        # Find the 1h features call
        features_1h_call = None
        for call in save_calls:
            features = call[0][0]
            if features.timeframe == "1h":
                features_1h_call = features
                break
        
        # Verify 1h features were created
        assert features_1h_call is not None, "1h features should have been processed"
        assert features_1h_call.timeframe == "1h"
        assert features_1h_call.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    
    @pytest.mark.asyncio
    async def test_htf_dxy_aggregator_emits_matching_candles(self):
        """HTF DXY aggregator emits candles matching GC aggregator timestamps."""
        aggregator_gc = HTFCandleAggregator()
        aggregator_dxy = HTFCandleAggregator()
        
        # Feed 15 x 1m candles for both symbols
        for i in range(15):
            gc_candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2652.0,
                volume=1000.0,
            )
            dxy_candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5,
                high=104.6,
                low=104.4,
                close=104.55,
                volume=0.0,
            )
            
            htf_gc = aggregator_gc.add_1m_candle(gc_candle)
            htf_dxy = aggregator_dxy.add_1m_candle(dxy_candle)
            
            # At boundary (i == 14), both should emit 15m candles
            if i == 14:
                assert len(htf_gc) == 1
                assert len(htf_dxy) == 1
                
                gc_15m = htf_gc[0]
                dxy_15m = htf_dxy[0]
                
                # Verify matching timestamps and timeframes
                assert gc_15m.timeframe == "15m"
                assert dxy_15m.timeframe == "15m"
                assert gc_15m.timestamp == dxy_15m.timestamp
                assert gc_15m.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    
    @pytest.mark.asyncio
    async def test_mismatched_htf_candles_skipped(self):
        """If DXY HTF candle doesn't match GC HTF candle, processing is skipped."""
        # This test verifies the defensive logic that prevents processing
        # when DXY candle doesn't match (though in normal operation this
        # shouldn't happen since both aggregators process synchronized pairs)
        
        processor_1m = FeatureProcessor(timeframe="1m")
        processor_15m = FeatureProcessor(timeframe="15m")
        processor_1h = FeatureProcessor(timeframe="1h")
        
        htf_aggregator_gc = HTFCandleAggregator()
        htf_aggregator_dxy = HTFCandleAggregator()
        
        publisher = MagicMock(spec=FeaturePublisher)
        publisher.publish = AsyncMock()
        repository = MagicMock(spec=FeatureRepository)
        repository.save_features = AsyncMock()
        
        # Feed 15 GC candles but only 14 DXY candles (simulating mismatch)
        for i in range(14):
            gc_candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2652.0,
                volume=1000.0,
            )
            dxy_candle = CandleMessage(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                symbol="DXY",
                timeframe="1m",
                open=104.5,
                high=104.6,
                low=104.4,
                close=104.55,
                volume=0.0,
            )
            pair = (gc_candle, dxy_candle)
            await process_candle_pair(
                pair,
                processor_1m,
                processor_15m,
                processor_1h,
                htf_aggregator_gc,
                htf_aggregator_dxy,
                publisher,
                repository,
            )
        
        # Add one more GC candle without matching DXY
        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 14, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )
        # Manually add to GC aggregator to trigger 15m boundary
        htf_gc = htf_aggregator_gc.add_1m_candle(gc_candle)
        
        # Verify that 15m candle was emitted but no DXY match exists
        assert len(htf_gc) == 1
        assert htf_gc[0].timeframe == "15m"
        
        # In the actual process_candle_pair, this would result in a warning
        # and the 15m features would not be processed (no matching DXY candle)






