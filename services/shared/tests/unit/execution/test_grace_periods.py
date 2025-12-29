"""Unit tests for SL/TP grace periods.

Tests setup-specific grace periods that prevent premature stop-outs:
- VWAP_RECLAIM: 8 bars for SL/TP, 8 bars for invalidation
- DXY_CONTINUATION: 6 bars for SL/TP, 6 bars for invalidation
- VWAP_FADE: 0 bars for SL/TP (immediate), 3 bars for invalidation

Following strict TDD - these tests are written FIRST and should FAIL until
grace periods are implemented.
"""

from datetime import datetime, timezone

import pytest
from scp_shared.common.types import Candle
from scp_shared.execution import InvalidationChecker
from scp_shared.execution.types import TradeRecord


def utc_datetime(*args, **kwargs):
    """Create UTC timezone-aware datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


@pytest.fixture
def checker():
    """Create invalidation checker instance."""
    return InvalidationChecker()


class TestSLTPGracePeriods:
    """Tests for SL/TP grace periods."""

    def test_grace_VWAP_RECLAIM_8bars_sl_skip(self, checker):
        """VWAP_RECLAIM should skip SL check for first 8 bars."""
        trade = TradeRecord(
            trade_id="test-123",
            signal_id="signal-123",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2670.0,
            risk_amount=10.0,
            reward_amount=20.0,
            entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            entry_bar_idx=100,
        )
        
        # Candle that would hit SL (low at SL price)
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 5),
            open=2645.0,
            high=2646.0,
            low=2640.0,  # Touches SL
            close=2645.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Check at bar 5 (within grace period)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=5)
        
        assert should_exit is False  # Grace period active
        assert reason is None

    def test_grace_VWAP_RECLAIM_bar9_sl_active(self, checker):
        """VWAP_RECLAIM should check SL after grace period (bar 9+)."""
        trade = TradeRecord(
            trade_id="test-123",
            signal_id="signal-123",
            symbol="GC",
            direction="long",
            setup_type="VWAP_RECLAIM",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2670.0,
            risk_amount=10.0,
            reward_amount=20.0,
            entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            entry_bar_idx=100,
        )
        
        # Candle that hits SL
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 15),
            open=2645.0,
            high=2646.0,
            low=2640.0,  # Touches SL
            close=2645.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Check at bar 9 (grace period expired)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=9)
        
        assert should_exit is True  # SL check active
        assert "SL_HIT" in reason

    def test_grace_DXY_CONTINUATION_6bars_skip(self, checker):
        """DXY_CONTINUATION should skip SL check for first 6 bars."""
        trade = TradeRecord(
            trade_id="test-456",
            signal_id="signal-456",
            symbol="GC",
            direction="long",
            setup_type="DXY_CONTINUATION",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2670.0,
            risk_amount=10.0,
            reward_amount=20.0,
            entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            entry_bar_idx=100,
        )
        
        # Candle that would hit SL
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 5),
            open=2645.0,
            high=2646.0,
            low=2640.0,  # Touches SL
            close=2645.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Check at bar 5 (within grace period)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=5)
        
        assert should_exit is False
        assert reason is None

    def test_grace_VWAP_FADE_immediate_sl(self, checker):
        """VWAP_FADE should check SL immediately (no grace period)."""
        trade = TradeRecord(
            trade_id="test-789",
            signal_id="signal-789",
            symbol="GC",
            direction="long",
            setup_type="VWAP_FADE",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2670.0,
            risk_amount=10.0,
            reward_amount=20.0,
            entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            entry_bar_idx=100,
        )
        
        # Candle that hits SL
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 1),
            open=2645.0,
            high=2646.0,
            low=2640.0,  # Touches SL
            close=2645.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Check at bar 1 (no grace period)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=1)
        
        assert should_exit is True  # No grace period
        assert "SL_HIT" in reason

    def test_grace_invalidation_separate_from_sl(self, checker):
        """Invalidation grace should be independent from SL/TP grace."""
        trade = TradeRecord(
            trade_id="test-grace",
            signal_id="signal-grace",
            symbol="GC",
            direction="long",
            setup_type="VWAP_FADE",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2670.0,
            risk_amount=10.0,
            reward_amount=20.0,
            entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            entry_bar_idx=100,
        )
        
        # VWAP_FADE has 0 bars for SL/TP, but 3 bars for invalidation
        # Test that micro structure check is skipped during invalidation grace
        
        features = {"structure_label": "LL"}  # Would trigger micro invalidation
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 2),
            open=2651.0,
            high=2653.0,
            low=2649.0,
            close=2652.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Check at bar 2 (within 3-bar invalidation grace)
        is_invalid, reason = checker.check_all(
            trade, candle, bars_elapsed=2, features=features
        )
        
        assert is_invalid is False  # Invalidation grace active
        assert reason is None

    def test_grace_default_setup_uses_2bars(self, checker):
        """Unknown setup types should use default 2-bar grace period."""
        trade = TradeRecord(
            trade_id="test-unknown",
            signal_id="signal-unknown",
            symbol="GC",
            direction="long",
            setup_type="UNKNOWN_SETUP",
            entry_price=2650.0,
            sl_price=2640.0,
            tp_price=2670.0,
            risk_amount=10.0,
            reward_amount=20.0,
            entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
            entry_bar_idx=100,
        )
        
        # Candle that hits SL
        candle = Candle(
            timestamp=utc_datetime(2024, 10, 15, 10, 1),
            open=2645.0,
            high=2646.0,
            low=2640.0,  # Touches SL
            close=2645.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        # Check at bar 1 (within default grace)
        should_exit, reason = checker.check_sl_tp(trade, candle, bars_elapsed=1)
        
        assert should_exit is False  # Default grace active
        assert reason is None

