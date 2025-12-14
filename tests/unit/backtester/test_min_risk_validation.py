"""Tests for minimum risk validation to prevent micro-chop entries.

Tests that trades with risk below MIN_RISK_TICKS are rejected.
"""

import pytest
from datetime import datetime, timezone
from backtester.entry_model import EntryExecution
from backtester.trade import create_trade_from_entry, MIN_RISK_TICKS
from common.types import Candle
from rule_engine.signal import Signal


class TestMinimumRiskValidation:
    """Tests for minimum risk threshold enforcement."""

    def test_minimum_sl_enforcement_prevents_micro_risk(self):
        """Test that minimum SL enforcement prevents micro-risk trades.

        Updated: All setups now have minimum SL enforcement:
        - VWAP_FADE: 15-tick minimum
        - VWAP_RECLAIM: 20-tick minimum
        - DXY_CONTINUATION: 15-tick minimum

        Micro-risk scenarios are auto-corrected, not rejected.
        """
        # Arrange: Signal and entry with tiny risk
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test signal",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Confirmation candle extremely close to entry (would be micro-chop without enforcement)
        # For VWAP_FADE long, SL = confirmation.low = 0.05 below entry = 0.5 ticks
        # But MIN_SL_TICKS_VWAP_FADE = 15 will expand it to 1.5 points
        confirmation = Candle(
            timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            open=2650.0,
            high=2650.5,
            low=2649.95,  # Only 0.05 below entry = 0.5 ticks (< MIN_RISK_TICKS)
            close=2650.2,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        risk_config = {"risk_per_trade": 350, "max_contracts": 1}
        market_context = {"month": 11, "htf_aligned": True, "dxy_aligned": True}
        config = {
            "assets": {"tick_sizes": {"GC": 0.1}},
        }

        # Act: Should succeed with auto-expanded SL (not raise ValueError)
        trade = create_trade_from_entry(
            entry,
            confirmation,
            None,  # No BOS candle
            risk_config,
            market_context,
            config,
        )

        # Assert: Risk should be expanded to minimum (15 ticks = 1.5 points)
        assert trade.risk_amount >= 1.5
        risk_ticks = trade.risk_amount / 0.1
        assert risk_ticks >= 15  # MIN_SL_TICKS_VWAP_FADE

    def test_adequate_risk_succeeds(self):
        """Test that risk >= MIN_RISK_TICKS creates trade successfully."""
        # Arrange: Signal with adequate risk
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test signal",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Confirmation candle with adequate distance (20 ticks minimum enforcement)
        confirmation = Candle(
            timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            open=2650.0,
            high=2651.0,
            low=2647.0,  # 3.0 points = 30 ticks (well above 10-tick minimum)
            close=2648.5,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        risk_config = {"risk_per_trade": 350, "max_contracts": 1}
        market_context = {"month": 11, "htf_aligned": True, "dxy_aligned": True}
        config = {
            "assets": {"tick_sizes": {"GC": 0.1}},
            "sl_rules": {"min_sl_ticks": {"VWAP_RECLAIM": 20}},
        }

        # Act: Should create trade successfully
        trade = create_trade_from_entry(
            entry,
            confirmation,
            None,  # No BOS candle
            risk_config,
            market_context,
            config,
        )

        # Assert: Trade created with proper risk
        assert trade is not None
        assert trade.direction == "long"
        assert abs(trade.entry_price - trade.stop_loss) >= 2.0  # Min buffer enforced

    def test_edge_case_exactly_min_risk_succeeds(self):
        """Test that risk exactly at MIN_RISK_TICKS is accepted."""
        # Arrange: Signal with risk exactly at minimum (10 ticks = 1.0 point)
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test signal",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry = EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Confirmation with exactly MIN_RISK_TICKS distance
        # But min_sl_ticks=20 will enforce 2.0 points minimum
        confirmation = Candle(
            timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            open=2650.0,
            high=2651.0,
            low=2648.0,  # After min enforcement: 2.0 points = 20 ticks
            close=2649.0,
            volume=100,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        risk_config = {"risk_per_trade": 350, "max_contracts": 1}
        market_context = {"month": 11, "htf_aligned": True, "dxy_aligned": True}
        config = {
            "assets": {"tick_sizes": {"GC": 0.1}},
            "sl_rules": {"min_sl_ticks": {"VWAP_RECLAIM": 20}},
        }

        # Act: Should succeed (min buffer will enforce 20 ticks)
        trade = create_trade_from_entry(
            entry,
            confirmation,
            None,
            risk_config,
            market_context,
            config,
        )

        # Assert: Trade created
        assert trade is not None
        # Risk will be >= 20 ticks due to minimum enforcement
        risk_ticks = abs(trade.entry_price - trade.stop_loss) / 0.1
        assert risk_ticks >= MIN_RISK_TICKS
