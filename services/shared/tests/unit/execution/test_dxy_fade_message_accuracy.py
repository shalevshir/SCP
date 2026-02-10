"""Unit tests for VWAP_FADE DXY invalidation message accuracy.

Tests that the error message threshold matches the actual code threshold
for VWAP_FADE long and short trades.

Following strict TDD - these tests verify the message is accurate and informative.
"""

from datetime import datetime, timezone

import pytest
from scp_shared.common.types import Candle
from scp_shared.execution.invalidation import InvalidationChecker
from scp_shared.execution.types import TradeRecord


def utc_datetime(*args, **kwargs):
    """Create UTC timezone-aware datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


@pytest.fixture
def checker():
    """Create InvalidationChecker instance."""
    return InvalidationChecker()


@pytest.fixture
def base_candle():
    """Create base candle."""
    return Candle(
        timestamp=utc_datetime(2024, 10, 15, 10, 0),
        open=2651.0,
        high=2653.0,
        low=2649.0,
        close=2652.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )


@pytest.fixture
def base_trade_long():
    """Create base VWAP_FADE long trade."""
    return TradeRecord(
        trade_id="FADE-LONG-123",
        signal_id="SIGNAL-LONG-123",
        symbol="GC",
        direction="long",
        setup_type="VWAP_FADE",
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2662.0,
        risk_amount=5.0,
        reward_amount=12.0,
        quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
    )


@pytest.fixture
def base_trade_short():
    """Create base VWAP_FADE short trade."""
    return TradeRecord(
        trade_id="FADE-SHORT-123",
        signal_id="SIGNAL-SHORT-123",
        symbol="GC",
        direction="short",
        setup_type="VWAP_FADE",
        entry_price=2650.0,
        sl_price=2655.0,
        tp_price=2638.0,
        risk_amount=5.0,
        reward_amount=12.0,
        quantity=1,
        entry_timestamp=utc_datetime(2024, 10, 15, 10, 0),
    )


class TestVWAPFadeDXYMessageAccuracy:
    """Tests for VWAP_FADE DXY invalidation message accuracy."""

    def test_long_fade_message_matches_threshold_at_boundary(
        self, checker, base_trade_long, base_candle
    ):
        """Long VWAP_FADE message should reference actual threshold (-0.3)."""
        # Test at exact boundary: -0.3 (should NOT invalidate, > -0.3 invalidates)
        features = {"dxy_corr": -0.3}
        is_invalid, reason = checker.check_dxy_flip(
            base_trade_long, base_candle, features
        )

        # At exact threshold, should not invalidate (need > -0.3)
        assert is_invalid is False

    def test_long_fade_message_matches_threshold_just_above(
        self, checker, base_trade_long, base_candle
    ):
        """Long VWAP_FADE message should reference actual threshold when triggered."""
        # Test just above threshold: -0.29 (should invalidate)
        features = {"dxy_corr": -0.29}
        is_invalid, reason = checker.check_dxy_flip(
            base_trade_long, base_candle, features
        )

        assert is_invalid is True
        assert reason is not None

        # Message should mention the ACTUAL threshold (-0.3), not the old -0.6
        # CRITICAL: This test should FAIL until message is fixed
        assert (
            "-0.3" in reason
        ), f"Expected message to reference actual threshold -0.3, got: {reason}"
        # Message should NOT mention -0.6 (old/incorrect threshold)
        assert (
            "-0.6" not in reason
        ), f"Message should not reference incorrect threshold -0.6, got: {reason}"

    def test_long_fade_correlation_value_in_message(
        self, checker, base_trade_long, base_candle
    ):
        """Message should include actual correlation value for debugging."""
        features = {"dxy_corr": -0.2}
        is_invalid, reason = checker.check_dxy_flip(
            base_trade_long, base_candle, features
        )

        assert is_invalid is True
        assert reason is not None
        # Message should include actual correlation value
        assert "-0.200" in reason or "-0.2" in reason

    def test_short_fade_message_matches_threshold_at_boundary(
        self, checker, base_trade_short, base_candle
    ):
        """Short VWAP_FADE message should reference actual threshold (-0.6)."""
        # Test at exact boundary: -0.6 (should NOT invalidate, < -0.6 invalidates)
        features = {"dxy_corr": -0.6}
        is_invalid, reason = checker.check_dxy_flip(
            base_trade_short, base_candle, features
        )

        # At exact threshold, should not invalidate (need < -0.6)
        assert is_invalid is False

    def test_short_fade_message_matches_threshold_just_below(
        self, checker, base_trade_short, base_candle
    ):
        """Short VWAP_FADE message should reference actual threshold when triggered."""
        # Test just below threshold: -0.61 (should invalidate)
        features = {"dxy_corr": -0.61}
        is_invalid, reason = checker.check_dxy_flip(
            base_trade_short, base_candle, features
        )

        assert is_invalid is True
        assert reason is not None

        # Message should mention the ACTUAL threshold (-0.6)
        assert (
            "-0.6" in reason
        ), f"Expected message to reference actual threshold -0.6, got: {reason}"

    def test_long_fade_threshold_logic_symmetry(
        self, checker, base_trade_long, base_candle
    ):
        """Long VWAP_FADE should invalidate when correlation becomes weak/positive."""
        test_cases = [
            (-0.5, False, "Strong negative correlation should NOT invalidate"),
            (-0.3, False, "At boundary should NOT invalidate"),
            (-0.29, True, "Just above boundary should invalidate"),
            (-0.1, True, "Weak negative correlation should invalidate"),
            (0.0, True, "Zero correlation should invalidate"),
            (0.3, True, "Positive correlation should invalidate"),
        ]

        for dxy_corr, should_invalidate, description in test_cases:
            features = {"dxy_corr": dxy_corr}
            is_invalid, _ = checker.check_dxy_flip(
                base_trade_long, base_candle, features
            )
            assert is_invalid == should_invalidate, (
                f"{description}: dxy_corr={dxy_corr}, "
                f"expected invalidate={should_invalidate}, got {is_invalid}"
            )

    def test_short_fade_threshold_logic_symmetry(
        self, checker, base_trade_short, base_candle
    ):
        """Short VWAP_FADE should invalidate when correlation becomes too negative."""
        test_cases = [
            (0.5, False, "Positive correlation should NOT invalidate"),
            (-0.3, False, "Weak negative correlation should NOT invalidate"),
            (-0.6, False, "At boundary should NOT invalidate"),
            (-0.61, True, "Just below boundary should invalidate"),
            (-0.8, True, "Strong negative correlation should invalidate"),
        ]

        for dxy_corr, should_invalidate, description in test_cases:
            features = {"dxy_corr": dxy_corr}
            is_invalid, _ = checker.check_dxy_flip(
                base_trade_short, base_candle, features
            )
            assert is_invalid == should_invalidate, (
                f"{description}: dxy_corr={dxy_corr}, "
                f"expected invalidate={should_invalidate}, got {is_invalid}"
            )
