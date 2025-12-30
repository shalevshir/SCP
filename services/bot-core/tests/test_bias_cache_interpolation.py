"""Unit tests for HTF bias cache interpolation and TTL.

Tests for improved bias cache behavior:
- Exact timestamp matching
- Interpolation within TTL window
- Default bias when TTL exceeded
- Staleness detection

Following strict TDD - these tests are written FIRST and should FAIL until
interpolation is implemented.
"""

from datetime import datetime, timedelta, timezone

import pytest
from scp_shared.messaging.schemas import HTFBiasMessage


def utc_datetime(*args, **kwargs):
    """Create UTC timezone-aware datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


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


class TestHTFBiasCacheInterpolation:
    """Tests for HTF bias cache interpolation."""

    def test_exact_timestamp_match_returns_bias(self, base_bias):
        """Cache should return exact match when timestamp matches."""
        from bot_core_svc.bias_cache import HTFBiasCache
        
        cache = HTFBiasCache(ttl_seconds=300)
        cache.update(base_bias)
        
        # Query with exact timestamp
        result = cache.get_for_timestamp_or_default(base_bias.timestamp)
        
        assert result is not None
        assert result.timestamp == base_bias.timestamp
        assert result.bias == "bullish"

    def test_interpolation_within_ttl(self, base_bias):
        """Cache should return most recent bias when within TTL window."""
        from bot_core_svc.bias_cache import HTFBiasCache
        
        cache = HTFBiasCache(ttl_seconds=300)  # 5 minutes
        cache.update(base_bias)
        
        # Query 2 minutes after bias timestamp (within TTL)
        query_time = base_bias.timestamp + timedelta(minutes=2)
        result = cache.get_for_timestamp_or_default(query_time)
        
        assert result is not None
        assert result.bias == "bullish"  # Should return the cached bias

    def test_interpolation_expired_returns_default(self, base_bias):
        """Cache should return default bias when TTL exceeded."""
        from bot_core_svc.bias_cache import HTFBiasCache
        
        cache = HTFBiasCache(ttl_seconds=300)  # 5 minutes
        cache.update(base_bias)
        
        # Query 10 minutes after bias timestamp (beyond TTL)
        query_time = base_bias.timestamp + timedelta(minutes=10)
        result = cache.get_for_timestamp_or_default(query_time)
        
        # Should return None or default neutral bias
        assert result is None or result.bias == "neutral"

    def test_multiple_biases_returns_closest(self, base_bias):
        """Cache should return closest bias when multiple exist."""
        from bot_core_svc.bias_cache import HTFBiasCache
        
        cache = HTFBiasCache(ttl_seconds=300)
        
        # Add two biases
        bias1 = base_bias
        cache.update(bias1)
        
        bias2 = HTFBiasMessage(
            timestamp=base_bias.timestamp + timedelta(minutes=5),
            bias="bearish",
            score=7.0,
            confidence="A",
            dxy_aligned=True,
            chop_detected=False,
        )
        cache.update(bias2)
        
        # Query between them (closer to bias2)
        query_time = base_bias.timestamp + timedelta(minutes=4)
        result = cache.get_for_timestamp_or_default(query_time)
        
        # Should return the most recent bias before query_time
        assert result is not None
        assert result.timestamp <= query_time

    def test_future_bias_not_used(self, base_bias):
        """Cache should not return bias from future timestamps."""
        from bot_core_svc.bias_cache import HTFBiasCache
        
        cache = HTFBiasCache(ttl_seconds=300)
        cache.update(base_bias)
        
        # Query BEFORE the bias timestamp
        query_time = base_bias.timestamp - timedelta(minutes=5)
        result = cache.get_for_timestamp_or_default(query_time)
        
        # Should return None or default (not future bias)
        assert result is None or result.timestamp <= query_time


