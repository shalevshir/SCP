"""Unit tests for VWAP_RECLAIM hard fixes.

Tests required per user specification:

1) VWAP_RECLAIM trade where:
   - micro structure breaks
   - VWAP still holds
   - HTF still holds
   → Trade MUST HOLD (no invalidation)

2) VWAP_RECLAIM trade where:
   - micro break + VWAP invalidation
   → Trade MUST EXIT

3) Any VWAP_RECLAIM signal with:
   - structure_label missing
   → MUST be rejected before execution

4) Any execution-hour signal with:
   - structure_1h == null
   → MUST be rejected, not traded
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from backtester.invalidations import InvalidationChecker
from common.types import Candle
from rule_engine.htf.types import HTFBias
from rule_engine.htf.vwap.reclaim import validate_reclaim_context


class MockTrade:
    """Mock Trade for testing without full Trade class."""

    def __init__(
        self,
        trade_id: str = "test_001",
        setup_type: str = "VWAP_RECLAIM",
        direction: str = "long",
        entry_price: float = 100.0,
        risk_amount: float = 1.0,
    ):
        self.trade_id = trade_id
        self.setup_type = setup_type
        self.direction = direction
        self.entry_price = entry_price
        self.risk_amount = risk_amount


class TestMicroInvalidationScoping:
    """Test Issue A: Micro invalidation scoping for VWAP_RECLAIM."""

    def test_micro_break_vwap_holds_must_hold(self):
        """Test 1: Micro breaks but VWAP holds → Trade MUST HOLD."""
        checker = InvalidationChecker()

        trade = MockTrade(
            trade_id="test_hold_001",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
        )

        candle = Candle(
            timestamp=datetime(2024, 11, 6, 7, 20, tzinfo=timezone.utc),
            open=101.0,
            high=101.5,
            low=100.5,
            close=101.0,  # ABOVE VWAP (VWAP holds)
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Features: micro break (LL) but price ABOVE VWAP
        features = {
            "structure_label": "LL",  # Micro break
            "vwap": 100.0,  # Current VWAP
            "timeframe": "1m",
        }

        # Should NOT invalidate - micro alone is not sufficient
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )

        assert is_invalid is False, "Trade MUST HOLD when micro breaks but VWAP holds"
        assert reason is None

    def test_micro_break_plus_vwap_loss_must_exit(self):
        """Test 2: Micro break + VWAP loss → Trade MUST EXIT."""
        checker = InvalidationChecker()

        trade = MockTrade(
            trade_id="test_exit_001",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
        )

        candle = Candle(
            timestamp=datetime(2024, 11, 6, 7, 20, tzinfo=timezone.utc),
            open=99.0,
            high=99.5,
            low=98.5,
            close=99.0,  # BELOW VWAP (VWAP lost)
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Features: micro break (LL) AND price BELOW VWAP
        features = {
            "structure_label": "LL",  # Micro break
            "vwap": 100.0,  # Current VWAP
            "timeframe": "1m",
        }

        # Should invalidate - micro break + VWAP confirmation
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )

        assert is_invalid is True, "Trade MUST EXIT when micro breaks AND VWAP lost"
        assert "VWAP loss" in reason

    def test_micro_break_plus_htf_break_must_exit(self):
        """Test: Micro break + HTF structure break → Trade MUST EXIT."""
        checker = InvalidationChecker()

        trade = MockTrade(
            trade_id="test_exit_002",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
        )

        candle = Candle(
            timestamp=datetime(2024, 11, 6, 7, 20, tzinfo=timezone.utc),
            open=101.0,
            high=101.5,
            low=100.5,
            close=101.0,  # ABOVE VWAP (VWAP holds)
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Features: micro break (LL) AND HTF structure break
        features = {
            "structure_label": "LL",  # Micro break
            "vwap": 100.0,  # Current VWAP
            "htf_structure_label": "LL",  # HTF also broke
            "timeframe": "1m",
        }

        # Should invalidate - micro break + HTF confirmation
        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )

        assert is_invalid is True, "Trade MUST EXIT when micro breaks AND HTF breaks"
        assert "HTF break" in reason

    def test_no_micro_break_must_not_invalidate(self):
        """Test: No micro break → MUST return (False, None)."""
        checker = InvalidationChecker()

        trade = MockTrade(
            trade_id="test_no_break",
            setup_type="VWAP_RECLAIM",
            direction="long",
            entry_price=100.0,
        )

        candle = Candle(
            timestamp=datetime(2024, 11, 6, 7, 20, tzinfo=timezone.utc),
            open=101.0,
            high=101.5,
            low=100.5,
            close=101.0,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Features: bullish structure (HH) - no micro break for long
        features = {
            "structure_label": "HH",  # Bullish - no break for long
            "vwap": 100.0,
            "timeframe": "1m",
        }

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )

        assert is_invalid is False
        assert reason is None

    def test_non_vwap_reclaim_immediate_invalidation(self):
        """Test: Non-VWAP_RECLAIM setups use immediate micro invalidation."""
        checker = InvalidationChecker()

        trade = MockTrade(
            trade_id="test_other",
            setup_type="VWAP_FADE",  # Not VWAP_RECLAIM
            direction="long",
            entry_price=100.0,
        )

        candle = Candle(
            timestamp=datetime(2024, 11, 6, 7, 20, tzinfo=timezone.utc),
            open=101.0,
            high=101.5,
            low=100.5,
            close=101.0,  # ABOVE VWAP
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Features: micro break (LL) - VWAP holds but should still invalidate
        features = {
            "structure_label": "LL",  # Micro break
            "vwap": 100.0,
            "timeframe": "1m",
        }

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )

        # Non-VWAP_RECLAIM should invalidate immediately on micro break
        assert is_invalid is True
        assert "Micro structure break" in reason

    def test_short_micro_break_vwap_holds_must_hold(self):
        """Test: SHORT micro break (HH) but VWAP holds → Trade MUST HOLD."""
        checker = InvalidationChecker()

        trade = MockTrade(
            trade_id="test_short_hold",
            setup_type="VWAP_RECLAIM",
            direction="short",
            entry_price=100.0,
        )

        candle = Candle(
            timestamp=datetime(2024, 11, 6, 7, 20, tzinfo=timezone.utc),
            open=99.0,
            high=99.5,
            low=98.5,
            close=99.0,  # BELOW VWAP (VWAP holds for short)
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Features: micro break (HH) but price BELOW VWAP (VWAP still holds for short)
        features = {
            "structure_label": "HH",  # Micro break for short
            "vwap": 100.0,  # Current VWAP
            "timeframe": "1m",
        }

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )

        assert is_invalid is False, "SHORT trade MUST HOLD when micro breaks but VWAP holds"

    def test_short_micro_break_plus_vwap_regain_must_exit(self):
        """Test: SHORT micro break (HH) + VWAP regain → Trade MUST EXIT."""
        checker = InvalidationChecker()

        trade = MockTrade(
            trade_id="test_short_exit",
            setup_type="VWAP_RECLAIM",
            direction="short",
            entry_price=100.0,
        )

        candle = Candle(
            timestamp=datetime(2024, 11, 6, 7, 20, tzinfo=timezone.utc),
            open=101.0,
            high=101.5,
            low=100.5,
            close=101.0,  # ABOVE VWAP (VWAP regained - bad for short)
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Features: micro break (HH) AND price ABOVE VWAP (regained)
        features = {
            "structure_label": "HH",  # Micro break for short
            "vwap": 100.0,  # Current VWAP
            "timeframe": "1m",
        }

        is_invalid, reason = checker.check_micro_structure_invalidation(
            trade, candle, features
        )

        assert is_invalid is True, "SHORT trade MUST EXIT when micro breaks AND VWAP regained"
        assert "VWAP regain" in reason


class TestStructureLabelMandatory:
    """Test Issue B: Structure label mandatory at decision time."""

    def test_missing_structure_label_rejected(self):
        """Test 3: Missing structure_label → MUST be rejected."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="high",
            structure_1h="HH",
            structure_15m="HH",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
        )

        # Features WITHOUT structure_label
        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                # structure_label is MISSING
            }
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is False
        assert "HARD REJECT" in result.reason or "No structure label" in result.reason

    def test_nan_structure_label_rejected(self):
        """Test: NaN structure_label → MUST be rejected."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="high",
            structure_1h="HH",
            structure_15m="HH",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
        )

        # Features with NaN structure_label
        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                "structure_label": pd.NA,  # NaN
            }
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is False
        assert "HARD REJECT" in result.reason or "No structure label" in result.reason

    def test_features_none_still_rejects(self):
        """Test: features=None → MUST still reject (structure_label missing)."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="high",
            structure_1h="HH",
            structure_15m="HH",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
        )

        # No features at all
        result = validate_reclaim_context(htf_bias, features=None)

        assert result.context_valid is False
        assert "HARD REJECT" in result.reason or "No structure label" in result.reason


class TestStructure1HNullRejection:
    """Test Issue C: structure_1h null → HARD REJECT."""

    def test_structure_1h_null_rejected(self):
        """Test 4: structure_1h == null → MUST be rejected."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=5.0,  # Lower score since 1H not voting
            confidence="low",
            structure_1h=None,  # NULL
            structure_15m="HH",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
        )

        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                "structure_label": "HH",
            }
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is False
        assert "structure_1h_null" in result.reason

    def test_structure_1h_empty_string_rejected(self):
        """Test: structure_1h == "" → MUST be rejected."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=5.0,
            confidence="low",
            structure_1h="",  # Empty string (same as null)
            structure_15m="HH",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
        )

        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                "structure_label": "HH",
            }
        )

        result = validate_reclaim_context(htf_bias, features)

        assert result.context_valid is False
        assert "structure_1h_null" in result.reason

    def test_structure_1h_valid_passes(self):
        """Test: Valid structure_1h passes this check."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.5,
            confidence="high",
            structure_1h="HH",  # Valid
            structure_15m="HH",
            liquidity_sweep_detected=True,
            structure_clarity=0.85,
            chop_detected=False,
            bos_detected=True,
        )

        features = pd.Series(
            {
                "close": 102.0,
                "vwap": 101.0,
                "vwap_deviation": 1.0,
                "structure_label": "HH",
                "bos_direction": "bullish",
            }
        )

        result = validate_reclaim_context(htf_bias, features)

        # Should pass 1H check (may fail on other checks, but not 1H null)
        if not result.context_valid:
            assert "structure_1h_null" not in result.reason

