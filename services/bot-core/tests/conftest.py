"""Pytest configuration and fixtures for bot-core tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage, SignalMessage
from scp_shared.rule_engine import Signal
from scp_shared.validation import SessionConstraints

from bot_core_svc.state_repository import DailyState


@pytest.fixture
def sample_context() -> dict:
    """Sample context for signal generation."""
    return {
        "session_ok": True,
        "enforcer_tier": "Conservative",
    }


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create mock Redis client for testing."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_db_pool() -> MagicMock:
    """Create mock database pool with acquire context manager."""
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    return pool


@pytest.fixture
def sample_features_message() -> FeaturesMessage:
    """Standard FeaturesMessage with all fields."""
    return FeaturesMessage(
        timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        close=2050.0,
        vwap=2045.0,
        rsi=55.0,
        ema_9=2048.0,
        ema_20=2045.0,
        ema_50=2040.0,
        dxy_correlation=-0.75,
        structure_label="HH",
        vwap_deviation=0.5,
    )


@pytest.fixture
def sample_htf_bias_message() -> HTFBiasMessage:
    """Standard HTFBiasMessage."""
    return HTFBiasMessage(
        timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
        bias="bullish",
        score=8.5,
        confidence="A+",
        structure_15m="HH",
        structure_1h="HL",
        dxy_aligned=True,
        chop_detected=False,
    )


@pytest.fixture
def sample_signal() -> Signal:
    """Standard Signal fixture with all required fields."""
    return Signal(
        timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={
            "structure_alignment": 2.0,
            "vwap_relation": 2.0,
            "htf_aligned": True,
            "dxy_aligned": True,
        },
        rationale="VWAP reclaim with HTF alignment",
        validation_flags={"session_ok": True},
        enforcer_tier="Conservative",
    )


@pytest.fixture
def sample_signal_message() -> SignalMessage:
    """Standard SignalMessage fixture."""
    return SignalMessage(
        id="test-signal-123",
        timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=8.5,
        confidence="A+",
        entry_price=2050.0,
        sl_price=2045.0,
        tp_price=2065.0,
        factors={
            "htf_bias": "bullish",
            "rationale": "VWAP reclaim with HTF alignment",
        },
    )


@pytest.fixture
def sample_session_constraints() -> SessionConstraints:
    """SessionConstraints fixture."""
    from datetime import time
    
    return SessionConstraints(
        name="Default",
        window_start=time(9, 0),
        window_end=time(17, 0),
        allowed_tiers=frozenset(["Conservative", "Moderate", "Aggressive"]),
        allowed_setups=frozenset(["VWAP_RECLAIM", "VWAP_FADE", "DXY_CONTINUATION"]),
        min_score=8.0,
        max_losses=3,
        dxy_correlation_max=0.8,
    )


@pytest.fixture
def sample_daily_state() -> DailyState:
    """DailyState fixture with some activity."""
    from datetime import date
    
    return DailyState(
        date=date(2024, 3, 15),
        loss_streak=1,
        daily_loss=-100.0,
        trades_count=3,
        wins=2,
        losses=1,
        pdll_hits=0,
    )

