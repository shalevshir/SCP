"""Unit tests for bias cache."""

import time
from datetime import datetime, timezone

import pytest
from scp_shared.messaging.schemas import HTFBiasMessage

from bot_core_svc.bias_cache import HTFBiasCache


class TestHTFBiasCache:
    """Test HTF bias cache with TTL."""
    
    def test_cache_starts_empty(self) -> None:
        """Cache starts empty."""
        cache = HTFBiasCache(ttl_seconds=60)
        
        assert cache.is_empty
        assert cache.get() is None
    
    def test_update_stores_bias(self) -> None:
        """Update stores bias in cache."""
        cache = HTFBiasCache(ttl_seconds=60)
        
        bias = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A",
            structure_15m="HH",
            structure_1h="HL",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        cache.update(bias)
        
        assert not cache.is_empty
        assert cache.get() == bias
    
    def test_get_returns_none_after_ttl(self) -> None:
        """Get returns None after TTL expires."""
        cache = HTFBiasCache(ttl_seconds=1)  # 1 second TTL
        
        bias = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        cache.update(bias)
        assert cache.get() == bias
        
        # Wait for expiration
        time.sleep(1.1)
        
        assert cache.get() is None
        assert cache.is_expired
    
    def test_get_or_default_returns_neutral_when_empty(self) -> None:
        """get_or_default returns neutral default when cache empty."""
        cache = HTFBiasCache(ttl_seconds=60)
        
        bias = cache.get_or_default()
        
        assert bias.bias == "neutral"
        assert bias.score == 5.0
        assert bias.confidence == "C"
        assert bias.chop_detected is True
    
    def test_get_or_default_returns_cached_when_valid(self) -> None:
        """get_or_default returns cached bias when valid."""
        cache = HTFBiasCache(ttl_seconds=60)
        
        cached_bias = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        cache.update(cached_bias)
        bias = cache.get_or_default()
        
        assert bias == cached_bias
    
    def test_clear_empties_cache(self) -> None:
        """Clear empties the cache."""
        cache = HTFBiasCache(ttl_seconds=60)
        
        bias = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        cache.update(bias)
        assert not cache.is_empty
        
        cache.clear()
        
        assert cache.is_empty
        assert cache.get() is None
    
    def test_age_seconds_returns_age(self) -> None:
        """age_seconds returns cache age."""
        cache = HTFBiasCache(ttl_seconds=60)
        
        bias = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        cache.update(bias)
        time.sleep(0.1)
        
        age = cache.age_seconds
        assert age is not None
        assert age >= 0.1
    
    def test_age_seconds_returns_none_when_empty(self) -> None:
        """age_seconds returns None when cache is empty."""
        cache = HTFBiasCache(ttl_seconds=60)
        
        assert cache.age_seconds is None

