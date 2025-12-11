"""Tests for DXY_CONTINUATION validation logic.

Verifies that validation.py properly rejects continuation setups based on:
- DXY 5M chop (dxy_chop_5m)
- Gold micro chop (chop_detected)
"""

import pytest
from datetime import datetime, timezone

from rule_engine.htf.types import HTFBias
from rule_engine.signal import Signal
from rule_engine.validation import validate_signal


class TestDXYContinuationValidation:
    """Test DXY_CONTINUATION validation chop filters."""

    def test_dxy_5m_chop_rejects_continuation(self):
        """Test that DXY 5M chop rejects DXY_CONTINUATION setups."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test continuation",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_chop_5m=True,  # DXY 5M chop detected
            chop_detected=False,  # Gold micro OK
        )

        context = {"enforcer_tier": "EarlyMild"}
        config = None  # Not needed for this test

        validated_signal = validate_signal(signal, htf_bias, context)

        assert validated_signal.confidence == "Reject"
        assert validated_signal.validation_flags["chop_ok"] is False

    def test_gold_micro_chop_rejects_continuation(self):
        """Test that gold micro chop rejects DXY_CONTINUATION setups.
        
        This test verifies the bug fix: chop_detected (gold micro chop)
        should also reject continuation setups, not just dxy_chop_5m.
        """
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test continuation",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_chop_5m=False,  # DXY 5M OK
            chop_detected=True,  # Gold micro chop detected
        )

        context = {"enforcer_tier": "EarlyMild"}
        config = None

        validated_signal = validate_signal(signal, htf_bias, context)

        assert validated_signal.confidence == "Reject"
        assert validated_signal.validation_flags["chop_ok"] is False

    def test_no_chop_allows_continuation(self):
        """Test that continuation passes validation when no chop detected."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test continuation",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_chop_5m=False,  # DXY 5M OK
            chop_detected=False,  # Gold micro OK
            dxy_alignment=True,
            conflict_detected=False,
            dxy_chop_detected=False,
        )

        context = {"enforcer_tier": "EarlyMild"}
        config = None

        validated_signal = validate_signal(signal, htf_bias, context)

        # Should pass chop checks (may still fail other validations)
        assert validated_signal.validation_flags["chop_ok"] is True

    def test_other_setups_ignore_chop_filters(self):
        """Test that non-continuation setups don't check dxy_chop_ok."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",  # Not continuation
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Test reclaim",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_chop_5m=True,  # DXY 5M chop (should be ignored)
            chop_detected=True,  # Gold micro chop (should be ignored)
            dxy_alignment=True,
            conflict_detected=False,
            dxy_chop_detected=False,
        )

        context = {"enforcer_tier": "EarlyMild"}
        config = None

        validated_signal = validate_signal(signal, htf_bias, context)

        # dxy_chop_ok should be True (not checked for non-continuation)
        assert validated_signal.validation_flags["chop_ok"] is True
