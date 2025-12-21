"""Unit tests for invalidation symmetry fixes (Issues 6-7).

Tests cover:
- Issue 6: time_stop_protection (VWAP_RECLAIM + September only)
- Issue 7: DXY flip requires BOTH 1m AND 5m >= 0.0 with 3-bar persistence
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from backtester.entry_model import EntryExecution
from backtester.invalidations import InvalidationChecker
from backtester.trade import Trade
from common.types import Candle
from rule_engine.signal import Signal


def _make_test_trade(
    trade_id: str,
    setup_type: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    risk_amount: float,
    timestamp: datetime,
) -> Trade:
    """Helper to create Trade objects for invalidation tests."""
    # Create minimal Signal for EntryExecution
    signal = Signal(
        timestamp=timestamp,
        symbol="GC",
        timeframe="1m",
        setup_type=setup_type,
        direction=direction,
        htf_bias="bullish" if direction == "long" else "bearish",
        score=8.0,
        confidence="A+",
        rationale="Test signal",
        factors={},
        diagnostics={},
        validation_flags={"session_ok": True, "tier_ok": True, "htf_bias_ok": True},
        enforcer_tier="EarlyMild",
    )

    entry_execution = EntryExecution(
        signal_timestamp=timestamp,
        entry_timestamp=timestamp,
        entry_price=entry_price,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    return Trade(
        trade_id=trade_id,
        symbol="GC",
        timeframe="1m",
        entry_execution=entry_execution,
        entry_timestamp=timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp,
        entry_price=entry_price,
        direction=direction,
        setup_type=setup_type,
        stop_loss=stop_loss,
        take_profit=take_profit,
        sl_rationale="Test",
        tp_rationale="Test",
        risk_amount=risk_amount,
        reward_amount=abs(take_profit - entry_price),
        r_multiple=abs(take_profit - entry_price) / risk_amount,
        contracts=1,
        exit_timestamp=None,
        exit_price=None,
        exit_reason=None,
        pnl=None,
        pnl_percent=None,
        r_realized=None,
        pnl_dollars=None,
        pnl_net=None,
        slippage_cost=None,
        commission_cost=None,
        status="OPEN",
        duration_bars=None,
        invalidation_triggered=False,
        ignore_first_retest_bar=False,
    )


class TestTimeStopProtection:
    """Test Issue 6: time_stop_protection (VWAP_RECLAIM + September only)."""

    def test_time_stop_protection_triggers_september_vwap_reclaim(self):
        """Test protection triggers for VWAP_RECLAIM in September at -0.3R."""
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_001",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        # Candle at -0.3R (30 bars elapsed, half of 60 bar limit for VWAP_RECLAIM)
        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 30, tzinfo=timezone.utc),
            open=99.7,
            high=99.8,
            low=99.6,
            close=99.7,  # -0.3R from entry
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        is_invalid, reason = detector.check_no_1r_reached(
            trade, bars_elapsed=30, candle=candle, month=9
        )

        assert is_invalid is True
        assert "time_stop_protection" in reason
        assert "-0.3" in reason
        assert "September mode" in reason

    def test_time_stop_protection_not_triggered_above_threshold(self):
        """Test protection does NOT trigger if R > -0.2."""
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_002",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        # Candle at -0.1R (above -0.2R threshold)
        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 10, tzinfo=timezone.utc),
            open=99.9,
            high=100.0,
            low=99.8,
            close=99.9,  # -0.1R from entry
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        is_invalid, reason = detector.check_no_1r_reached(
            trade, bars_elapsed=10, candle=candle, month=9
        )

        assert is_invalid is False

    def test_time_stop_protection_not_triggered_before_halfway(self):
        """Test protection does NOT trigger before halfway point."""
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_003",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        # Candle at -0.3R but only 5 bars elapsed (< 30 bar halfway point for VWAP_RECLAIM)
        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 5, tzinfo=timezone.utc),
            open=99.7,
            high=99.8,
            low=99.6,
            close=99.7,  # -0.3R from entry
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        is_invalid, reason = detector.check_no_1r_reached(
            trade, bars_elapsed=5, candle=candle, month=9
        )

        assert is_invalid is False

    def test_time_stop_protection_not_triggered_non_september(self):
        """Test protection does NOT trigger outside September."""
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_004",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 10, 15, 10, 0),
        )

        # Candle at -0.3R in October (not September)
        candle = Candle(
            timestamp=datetime(2024, 10, 15, 10, 10, tzinfo=timezone.utc),
            open=99.7,
            high=99.8,
            low=99.6,
            close=99.7,  # -0.3R from entry
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        is_invalid, reason = detector.check_no_1r_reached(
            trade, bars_elapsed=10, candle=candle, month=10
        )

        assert is_invalid is False

    def test_time_stop_protection_not_triggered_non_vwap_reclaim(self):
        """Test protection does NOT trigger for non-VWAP_RECLAIM setups."""
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_005",
            setup_type="DXY_CONTINUATION",  # Not VWAP_RECLAIM
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        # Candle at -0.3R in September
        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 10, tzinfo=timezone.utc),
            open=99.7,
            high=99.8,
            low=99.6,
            close=99.7,  # -0.3R from entry
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        is_invalid, reason = detector.check_no_1r_reached(
            trade, bars_elapsed=10, candle=candle, month=9
        )

        assert is_invalid is False

    def test_time_stop_protection_short_direction(self):
        """Test protection works for SHORT direction."""
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_006",
            setup_type="VWAP_RECLAIM",
            direction="short",
            entry_price=100.0,
            stop_loss=101.0,
            take_profit=98.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        # Candle at -0.3R for short (price moved UP)
        # 30 bars elapsed = half of 60 bar limit for VWAP_RECLAIM
        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 30, tzinfo=timezone.utc),
            open=100.3,
            high=100.4,
            low=100.2,
            close=100.3,  # -0.3R from entry (100.3 - 100.0 = 0.3, risk = 1.0)
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        is_invalid, reason = detector.check_no_1r_reached(
            trade, bars_elapsed=30, candle=candle, month=9
        )

        assert is_invalid is True
        assert "time_stop_protection" in reason


class TestDXYFlipBothTimeframes:
    """Test Issue 7: DXY flip requires BOTH 1m AND 5m >= 0.0."""

    def test_dxy_flip_requires_3_consecutive_bars(self):
        """Test flip requires dxy_corr >= 0.0 for 3 consecutive bars.

        Note: VWAP_RECLAIM uses dxy_corr field (not dxy_corr_1m/5m which is for DXY_CONTINUATION).
        """
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_dxy_001",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 5, tzinfo=timezone.utc),
            open=100.5,
            high=100.6,
            low=100.4,
            close=100.5,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        # Bar 1: dxy_corr >= 0.0
        features_1 = {"dxy_corr": 0.1}
        is_invalid, reason = detector.check_dxy_flip(trade, candle, features_1)
        assert is_invalid is False  # Need 3 bars

        # Bar 2: dxy_corr >= 0.0
        features_2 = {"dxy_corr": 0.2}
        is_invalid, reason = detector.check_dxy_flip(trade, candle, features_2)
        assert is_invalid is False  # Need 3 bars

        # Bar 3: dxy_corr >= 0.0
        features_3 = {"dxy_corr": 0.1}
        is_invalid, reason = detector.check_dxy_flip(trade, candle, features_3)
        assert is_invalid is True  # 3 bars confirmed
        assert "DXY flip" in reason
        assert "3-bar confirmed" in reason

    def test_dxy_flip_not_triggered_with_negative_corr(self):
        """Test flip does NOT trigger if dxy_corr < 0.0.

        Note: VWAP_RECLAIM uses dxy_corr field. Flip requires dxy_corr >= 0.0.
        """
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_dxy_002",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 5, tzinfo=timezone.utc),
            open=100.5,
            high=100.6,
            low=100.4,
            close=100.5,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        # dxy_corr is negative - flip should not trigger
        for _ in range(3):
            features = {"dxy_corr": -0.5}
            is_invalid, reason = detector.check_dxy_flip(trade, candle, features)
            assert is_invalid is False

    def test_dxy_flip_not_triggered_missing_dxy_corr(self):
        """Test flip does NOT trigger if dxy_corr is missing.

        Note: VWAP_RECLAIM uses dxy_corr field. Missing data = no flip.
        """
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_dxy_003",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 5, tzinfo=timezone.utc),
            open=100.5,
            high=100.6,
            low=100.4,
            close=100.5,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        # dxy_corr is not present - flip should not trigger
        for _ in range(3):
            features = {}  # No dxy_corr field
            is_invalid, reason = detector.check_dxy_flip(trade, candle, features)
            assert is_invalid is False

    def test_dxy_flip_counter_resets_on_break(self):
        """Test flip counter resets if condition breaks.

        Note: VWAP_RECLAIM uses dxy_corr field. Counter resets when dxy_corr < 0.0.
        """
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_dxy_004",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 5, tzinfo=timezone.utc),
            open=100.5,
            high=100.6,
            low=100.4,
            close=100.5,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        # Bar 1: dxy_corr >= 0.0
        features_1 = {"dxy_corr": 0.1}
        is_invalid, _ = detector.check_dxy_flip(trade, candle, features_1)
        assert is_invalid is False

        # Bar 2: Condition breaks (dxy_corr goes negative)
        features_2 = {"dxy_corr": -0.5}
        is_invalid, _ = detector.check_dxy_flip(trade, candle, features_2)
        assert is_invalid is False

        # Bar 3: dxy_corr >= 0.0 again (counter should have reset)
        features_3 = {"dxy_corr": 0.1}
        is_invalid, _ = detector.check_dxy_flip(trade, candle, features_3)
        assert is_invalid is False  # Counter was reset, need 2 more bars

        # Bar 4: dxy_corr >= 0.0
        features_4 = {"dxy_corr": 0.1}
        is_invalid, _ = detector.check_dxy_flip(trade, candle, features_4)
        assert is_invalid is False

        # Bar 5: dxy_corr >= 0.0 (now 3 consecutive)
        features_5 = {"dxy_corr": 0.1}
        is_invalid, _ = detector.check_dxy_flip(trade, candle, features_5)
        assert is_invalid is True

    def test_dxy_flip_counter_resets_on_missing_data(self):
        """Test flip counter resets if dxy_corr data is missing.

        Note: VWAP_RECLAIM uses dxy_corr field. Missing data resets counter.
        """
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_dxy_005",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 5, tzinfo=timezone.utc),
            open=100.5,
            high=100.6,
            low=100.4,
            close=100.5,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        # Bar 1: dxy_corr >= 0.0
        features_1 = {"dxy_corr": 0.1}
        is_invalid, _ = detector.check_dxy_flip(trade, candle, features_1)
        assert is_invalid is False

        # Bar 2: Missing dxy_corr data
        features_2 = {}  # dxy_corr missing
        is_invalid, _ = detector.check_dxy_flip(trade, candle, features_2)
        assert is_invalid is False

        # Bar 3: dxy_corr >= 0.0 again (counter should have reset)
        features_3 = {"dxy_corr": 0.1}
        is_invalid, _ = detector.check_dxy_flip(trade, candle, features_3)
        assert is_invalid is False  # Counter was reset

    def test_dxy_flip_not_applied_to_non_vwap_reclaim(self):
        """Test BOTH-timeframe logic only applies to VWAP_RECLAIM."""
        detector = InvalidationChecker()

        trade = _make_test_trade(
            trade_id="test_dxy_006",
            setup_type="VWAP_FADE",  # Not VWAP_RECLAIM
            direction="long",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            risk_amount=1.0,
            timestamp=datetime(2024, 9, 15, 10, 0),
        )

        candle = Candle(
            timestamp=datetime(2024, 9, 15, 10, 5, tzinfo=timezone.utc),
            open=100.5,
            high=100.6,
            low=100.4,
            close=100.5,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="test",
        )

        # VWAP_FADE uses different logic (single dxy_corr field)
        features = {"dxy_corr": -0.2}  # Above -0.3 threshold for FADE
        is_invalid, reason = detector.check_dxy_flip(trade, candle, features)
        
        # VWAP_FADE should trigger with single field logic
        assert is_invalid is True
        assert "BOTH timeframes" not in reason

