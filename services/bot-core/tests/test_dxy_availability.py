"""Unit tests for DXY availability check in Bot Core.

Tests that signal generation is skipped when DXY data is unavailable.

Following strict TDD - these tests are written FIRST and should FAIL until
the DXY availability check is implemented.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage


def utc_datetime(*args, **kwargs):
    """Create UTC timezone-aware datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


@pytest.fixture
def base_features():
    """Create base features message."""
    return FeaturesMessage(
        timestamp=utc_datetime(2024, 10, 15, 10, 0),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        vwap=2649.5,
        rsi=55.0,
        dxy_correlation=-0.75,
    )


@pytest.fixture
def base_bias():
    """Create base HTF bias message."""
    return HTFBiasMessage(
        timestamp=utc_datetime(2024, 10, 15, 10, 0),
        bias="bullish",
        score=8.5,
        confidence="A+",
        dxy_aligned=True,
        chop_detected=False,
    )


class TestDXYAvailabilityCheck:
    """Tests for DXY availability check."""

    @pytest.mark.asyncio
    async def test_dxy_none_skips_signal(self, base_features, base_bias):
        """Signal generation should be skipped when DXY correlation is None."""
        # Import here to avoid circular dependencies
        from bot_core_svc.main import process_feature_message
        from bot_core_svc.bias_cache import HTFBiasCache
        from bot_core_svc.signal_engine import SignalEngine
        
        # Create mocks
        bias_cache = HTFBiasCache(ttl_seconds=300)
        bias_cache.update(base_bias)
        signal_engine = Mock(spec=SignalEngine)
        signal_engine.generate = Mock(return_value=None)
        signal_publisher = AsyncMock()
        guardrails_service = Mock()
        guardrails_service.evaluate = Mock(return_value=Mock(allowed=True))
        session_service = Mock()
        session_service.evaluate = Mock(
            return_value=Mock(session_ok=True, constraints={})
        )
        
        # Create features with DXY unavailable
        features = FeaturesMessage(
            **{**base_features.__dict__, "dxy_correlation": None, "dxy_corr": None}
        )
        
        # Process feature message (skip warmup by setting counter > warmup_bars)
        await process_feature_message(
            features,
            bias_cache,
            signal_engine,
            signal_publisher,
            guardrails_service,
            session_service,
            warmup_bar_count=100,  # Already past warmup
            warmup_bars=60,
        )
        
        # signal_engine.generate should NOT be called
        signal_engine.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_dxy_present_allows_signal(self, base_features, base_bias):
        """Signal generation should proceed when DXY correlation is present."""
        from bot_core_svc.main import process_feature_message
        from bot_core_svc.bias_cache import HTFBiasCache
        from bot_core_svc.signal_engine import SignalEngine
        
        # Create mocks
        bias_cache = HTFBiasCache(ttl_seconds=300)
        bias_cache.update(base_bias)
        signal_engine = Mock(spec=SignalEngine)
        signal_engine.generate = Mock(return_value=None)  # No signal generated
        signal_publisher = AsyncMock()
        guardrails_service = Mock()
        guardrails_service.evaluate = Mock(return_value=Mock(allowed=True))
        session_service = Mock()
        session_service.evaluate = Mock(
            return_value=Mock(session_ok=True, constraints={})
        )
        
        # Process feature message with DXY available (skip warmup by setting counter > warmup_bars)
        await process_feature_message(
            base_features,
            bias_cache,
            signal_engine,
            signal_publisher,
            guardrails_service,
            session_service,
            warmup_bar_count=100,  # Already past warmup
            warmup_bars=60,
        )
        
        # signal_engine.generate SHOULD be called
        signal_engine.generate.assert_called_once()



