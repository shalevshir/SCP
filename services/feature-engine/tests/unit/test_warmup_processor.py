"""Tests for warmup_processor edge cases."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from feature_engine_svc.main import warmup_processor
from feature_engine_svc.processor import FeatureProcessor
from scp_shared.common.types import Candle


@pytest.mark.unit
@pytest.mark.asyncio
async def test_warmup_processor_handles_none_on_final_iteration():
    """
    Test that warmup_processor preserves valid features when final process() returns None.
    
    Regression test for: If processor.process() returns None on the final candle
    (e.g., due to insufficient data or processing error), the valid features from
    earlier iterations should be preserved for metrics updates.
    """
    # Create mock processor that returns valid features, then None on final iteration
    processor = MagicMock(spec=FeatureProcessor)
    processor.timeframe = "1m"
    processor.bar_count = 3
    
    valid_features = {
        "timestamp": datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc),
        "close": 2650.0,
        "vwap": 2649.5,
        "rsi": 55.0,
    }
    
    # Simulate: first 2 calls return valid features, last call returns None
    processor.process.side_effect = [
        valid_features,  # First candle
        valid_features,  # Second candle
        None,  # Third candle returns None (edge case)
    ]
    
    def is_warmed_up_side_effect():
        return processor.bar_count >= 2
    
    processor.is_warmed_up.side_effect = is_warmed_up_side_effect
    
    # Create mock repository that returns candle pairs
    mock_repository = AsyncMock()
    candle_pairs = [
        (
            Candle(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2650.0 + i,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            ),
            Candle(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                open=107.0,
                high=107.1,
                low=106.9,
                close=107.0,
                volume=500.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            ),
        )
        for i in range(3)
    ]
    mock_repository.load_recent_candles.return_value = candle_pairs
    
    # Mock config
    with patch("feature_engine_svc.main.config") as mock_config:
        mock_config.service_mode = "replay"
        mock_config.service_name = "feature-engine"
        mock_config.enable_warmup = True
        mock_config.warmup_candles = 60
        
        # Mock metrics
        with patch("feature_engine_svc.main.engine_metrics") as mock_metrics:
            # Run warmup
            await warmup_processor(processor, mock_repository, "1m")
            
            # Verify processor.process was called 3 times
            assert processor.process.call_count == 3
            
            # CRITICAL: Metrics should be updated with valid_features from iteration 2,
            # NOT with None from iteration 3
            mock_metrics.update_feature_metrics.assert_called_once_with(
                valid_features, "replay", "feature-engine"
            )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_warmup_processor_handles_all_none_returns():
    """
    Test that warmup_processor handles case where all process() calls return None.
    
    Edge case: processor not ready yet, all returns are None.
    Metrics should not be updated.
    """
    processor = MagicMock(spec=FeatureProcessor)
    processor.timeframe = "1m"
    processor.bar_count = 0
    processor.process.return_value = None  # Always returns None
    processor.is_warmed_up.return_value = False
    
    mock_repository = AsyncMock()
    candle_pairs = [
        (
            Candle(
                timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2650.0,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            ),
            Candle(
                timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
                open=107.0,
                high=107.1,
                low=106.9,
                close=107.0,
                volume=500.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            ),
        )
    ]
    mock_repository.load_recent_candles.return_value = candle_pairs
    
    with patch("feature_engine_svc.main.config") as mock_config:
        mock_config.service_mode = "replay"
        mock_config.service_name = "feature-engine"
        mock_config.enable_warmup = True
        mock_config.warmup_candles = 60
        
        with patch("feature_engine_svc.main.engine_metrics") as mock_metrics:
            await warmup_processor(processor, mock_repository, "1m")
            
            # Metrics should NOT be updated since last_features is None
            mock_metrics.update_feature_metrics.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_warmup_processor_all_valid_features():
    """
    Test normal case where all process() calls return valid features.
    
    Metrics should be updated with the last valid features.
    """
    processor = MagicMock(spec=FeatureProcessor)
    processor.timeframe = "1m"
    processor.bar_count = 2
    
    features_list = [
        {
            "timestamp": datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
            "close": 2650.0 + i,
            "vwap": 2649.5 + i,
            "rsi": 50.0 + i,
        }
        for i in range(2)
    ]
    
    processor.process.side_effect = features_list
    processor.is_warmed_up.return_value = True
    
    mock_repository = AsyncMock()
    candle_pairs = [
        (
            Candle(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                open=2650.0,
                high=2655.0,
                low=2648.0,
                close=2650.0 + i,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            ),
            Candle(
                timestamp=datetime(2025, 1, 15, 10, i, tzinfo=timezone.utc),
                open=107.0,
                high=107.1,
                low=106.9,
                close=107.0,
                volume=500.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            ),
        )
        for i in range(2)
    ]
    mock_repository.load_recent_candles.return_value = candle_pairs
    
    with patch("feature_engine_svc.main.config") as mock_config:
        mock_config.service_mode = "replay"
        mock_config.service_name = "feature-engine"
        mock_config.enable_warmup = True
        mock_config.warmup_candles = 60
        
        with patch("feature_engine_svc.main.engine_metrics") as mock_metrics:
            await warmup_processor(processor, mock_repository, "1m")
            
            # Metrics should be updated with the LAST valid features
            mock_metrics.update_feature_metrics.assert_called_once_with(
                features_list[-1], "replay", "feature-engine"
            )
