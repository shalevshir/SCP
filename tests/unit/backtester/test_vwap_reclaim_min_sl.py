"""Test minimum stop-loss for VWAP_RECLAIM setups.

Following TDD: Write failing test first to verify 20-tick minimum SL buffer.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from common.types import Candle
from rule_engine.signal import Signal

from backtester.entry_model import EntryExecution
from backtester.trade import calculate_stop_loss, create_trade_from_entry

# Timezone for tests
UTC = ZoneInfo("UTC")


def test_vwap_reclaim_min_sl_enforced():
    """Test that VWAP_RECLAIM enforces 20-tick minimum SL distance.
    
    Scenario: Structure-based SL is only 5 ticks away (too tight).
    Expected: SL should be expanded to 20 ticks minimum.
    """
    # Create signal for VWAP_RECLAIM
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={},
        rationale="VWAP reclaim with structure",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )
    
    # Entry at 2650.0
    entry_execution = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )
    
    # Confirmation candle with low at 2649.5 (only 0.5 points = 5 ticks away)
    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        open=2649.8,
        high=2650.5,
        low=2649.5,  # Only 5 ticks below entry
        close=2650.2,
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )
    
    # BOS candle (not used for VWAP_RECLAIM in this test)
    bos_candle = None
    
    # Calculate stop loss
    config = {
        "assets": {
            "tick_sizes": {"GC": 0.1},
            "tick_values": {"GC": 10.0},
        }
    }
    
    # Act: Calculate stop loss with minimum enforcement
    sl, rationale, retest_protection = calculate_stop_loss(
        entry_execution, "long", confirmation_candle, bos_candle
    )
    
    # Assert: SL should be at least 20 ticks (2.0 points) below entry
    expected_min_sl = 2650.0 - (20 * 0.1)  # 2648.0
    assert sl <= expected_min_sl, (
        f"SL {sl} should be expanded to at least {expected_min_sl} "
        f"(20 ticks minimum for VWAP_RECLAIM)"
    )
    assert "20-tick minimum" in rationale.lower() or "padded" in rationale.lower()
    assert retest_protection is True, "VWAP_RECLAIM should have retest protection enabled"


def test_vwap_reclaim_structure_sl_sufficient():
    """Test that structure-based SL is kept when already >= 20 ticks.
    
    Scenario: Structure-based SL is 30 ticks away (sufficient).
    Expected: Use structure-based SL without modification.
    """
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={},
        rationale="VWAP reclaim with structure",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )
    
    entry_execution = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )
    
    # Confirmation candle with low at 2647.0 (30 ticks away)
    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        open=2649.0,
        high=2650.5,
        low=2647.0,  # 30 ticks below entry
        close=2650.2,
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )
    
    # Calculate stop loss
    sl, rationale, retest_protection = calculate_stop_loss(
        entry_execution, "long", confirmation_candle, None
    )
    
    # Assert: SL should be at confirmation low (structure-based)
    assert sl == 2647.0, f"SL {sl} should be at confirmation low 2647.0"
    assert "structure-based" in rationale.lower()
    assert retest_protection is True, "VWAP_RECLAIM should have retest protection"


def test_vwap_reclaim_short_min_sl_enforced():
    """Test that VWAP_RECLAIM short enforces 20-tick minimum SL distance.
    
    Scenario: Structure-based SL is only 5 ticks away (too tight) for short.
    Expected: SL should be expanded to 20 ticks minimum above entry.
    """
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="short",
        setup_type="VWAP_RECLAIM",
        htf_bias="bearish",
        score=8.5,
        confidence="A+",
        factors={},
        rationale="VWAP reclaim with structure",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )
    
    entry_execution = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )
    
    # Confirmation candle with high at 2650.5 (only 5 ticks above entry)
    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        open=2649.8,
        high=2650.5,  # Only 5 ticks above entry
        low=2649.0,
        close=2649.5,
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )
    
    # Calculate stop loss
    sl, rationale, retest_protection = calculate_stop_loss(
        entry_execution, "short", confirmation_candle, None
    )
    
    # Assert: SL should be at least 20 ticks (2.0 points) above entry
    expected_min_sl = 2650.0 + (20 * 0.1)  # 2652.0
    assert sl >= expected_min_sl, (
        f"SL {sl} should be expanded to at least {expected_min_sl} "
        f"(20 ticks minimum for VWAP_RECLAIM)"
    )
    assert "20-tick minimum" in rationale.lower() or "padded" in rationale.lower()
    assert retest_protection is True, "VWAP_RECLAIM should have retest protection"


def test_vwap_fade_has_15_tick_minimum_enforcement():
    """Test that VWAP_FADE setups have 15-tick minimum SL enforcement.
    
    Updated: VWAP_FADE now has MIN_SL_TICKS_VWAP_FADE = 15 (same as DXY_CONTINUATION).
    When candle extreme is within 15 ticks of entry, SL is expanded outward.
    """
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_FADE",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={},
        rationale="VWAP fade",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )
    
    entry_execution = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )
    
    # Sweep candle with low at 2649.5 (only 5 ticks away)
    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        open=2649.8,
        high=2650.5,
        low=2649.5,  # Only 5 ticks below entry (insufficient)
        close=2650.2,
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )
    
    config = {"assets": {"tick_sizes": {"GC": 0.1}}}
    
    # Calculate stop loss
    sl, rationale, retest_protection = calculate_stop_loss(
        entry_execution, "long", confirmation_candle, None, config
    )
    
    # Assert: SL should be expanded to 15 ticks below entry (not at candle low)
    # Entry: 2650.0, 15 ticks * 0.1 = 1.5 points, so SL = 2648.5
    expected_sl = 2650.0 - (15 * 0.1)
    assert sl == expected_sl, f"SL {sl} should be expanded to {expected_sl} (15-tick minimum)"
    assert "minimum" in rationale.lower() or "padded" in rationale.lower()
    assert retest_protection is False, "VWAP_FADE should NOT have retest protection"

