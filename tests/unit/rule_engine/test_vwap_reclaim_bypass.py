"""Tests for VWAP_RECLAIM bypassing strict structure rejections.

Verifies that VWAP_RECLAIM setups:
- Are not rejected by gold micro chop
- Get minimum base score even with low clarity
- Bypass chop hard rejections in structure scoring
"""

import pandas as pd
import pytest
from datetime import datetime, timezone

from rule_engine.htf.types import ChopSeverity, HTFBias
from rule_engine.htf.vwap.reclaim import validate_reclaim_prerequisites
from rule_engine.scoring import calculate_structure_alignment
from rule_engine.signal import Signal
from rule_engine.validation import validate_signal


class TestReclaimPrerequisitesLoosened:
    """Test loosened VWAP_RECLAIM prerequisites."""

    def test_reclaim_allowed_with_low_clarity(self):
        """Test reclaim passes with clarity 0.5 (was 0.7)."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.55,  # Above 0.5, below old 0.7 threshold
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=False,
        )

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is True
        assert reason is None

    def test_reclaim_allowed_with_chop(self):
        """Test reclaim passes even with chop detected (removed check)."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.7,
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=True,  # Chop present - should NOT block reclaim
        )

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is True
        assert reason is None

    def test_reclaim_still_requires_sweep(self):
        """Test reclaim still requires liquidity sweep."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=False,  # No sweep
            structure_clarity=0.7,
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=False,
        )

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is False
        assert "sweep" in reason.lower()

    def test_reclaim_still_requires_recent_bos(self):
        """Test reclaim still requires recent BOS."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.7,
            bos_detected=True,
            bars_since_bos=25,  # Too old (limit is now 20)
            chop_detected=False,
        )

        is_valid, reason = validate_reclaim_prerequisites(htf_bias)

        assert is_valid is False
        assert "stale" in reason.lower()


class TestReclaimBypassesStructureRejections:
    """Test VWAP_RECLAIM bypasses strict structure scoring rejections."""

    def test_reclaim_scores_with_chop(self):
        """Test VWAP_RECLAIM scores > 0 even with chop detected."""
        features = pd.Series({"close": 2650.0, "vwap": 2645.0})

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.6,
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=True,  # Chop present
        )

        score = calculate_structure_alignment(features, htf_bias, 2.5, "VWAP_RECLAIM")

        # Should get minimum base score (50% = 1.25), not 0
        assert score >= 1.25
        assert score > 0.0

    def test_reclaim_scores_with_low_clarity(self):
        """Test VWAP_RECLAIM scores > 0 with clarity below 0.6."""
        features = pd.Series({"close": 2650.0, "vwap": 2645.0})

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.4,  # Below 0.6 threshold
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=False,
        )

        score = calculate_structure_alignment(features, htf_bias, 2.5, "VWAP_RECLAIM")

        # Should get minimum base score, not 0
        assert score >= 1.25
        assert score > 0.0

    def test_continuation_still_rejected_by_chop(self):
        """Test DXY_CONTINUATION still has strict chop rejection."""
        features = pd.Series({"close": 2650.0, "vwap": 2645.0})

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.8,
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=True,  # Chop present
        )

        score = calculate_structure_alignment(
            features, htf_bias, 2.5, "DXY_CONTINUATION"
        )

        # Should be rejected (0 score)
        assert score == 0.0

    def test_fade_still_rejected_by_low_clarity(self):
        """Test VWAP_FADE still has strict clarity rejection."""
        features = pd.Series({"close": 2650.0, "vwap": 2645.0})

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
            structure_clarity=0.4,  # Below 0.6 threshold
            bos_detected=True,
            bars_since_bos=10,
            chop_detected=False,
        )

        score = calculate_structure_alignment(features, htf_bias, 2.5, "VWAP_FADE")

        # Should be rejected (0 score)
        assert score == 0.0


class TestChopValidationBySetupType:
    """Test that chop validation is setup-specific."""

    def test_fade_rejected_by_gold_chop(self):
        """Test VWAP_FADE is rejected by gold micro chop."""
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
            rationale="Test fade",
            validation_flags={},
            enforcer_tier="Mild",
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            chop_detected=True,  # Gold chop
            chop_severity=ChopSeverity.HARD_CHOP,  # Required for validation rejection
            liquidity_sweep_detected=False,  # No sweep = blocked in HARD_CHOP
            dxy_chop_5m=False,
            dxy_alignment=True,
            conflict_detected=False,
            dxy_chop_detected=False,
        )

        context = {"enforcer_tier": "Mild"}

        validated_signal = validate_signal(signal, htf_bias, context)

        assert validated_signal.confidence == "Reject"
        assert validated_signal.validation_flags["chop_ok"] is False

    def test_reclaim_allowed_with_gold_chop(self):
        """Test VWAP_RECLAIM is NOT rejected by gold micro chop."""
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
            rationale="Test reclaim",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            chop_detected=True,  # Gold chop - should be allowed for reclaim
            dxy_chop_5m=False,
            dxy_alignment=True,
            conflict_detected=False,
            dxy_chop_detected=False,
        )

        context = {"enforcer_tier": "EarlyMild"}

        validated_signal = validate_signal(signal, htf_bias, context)

        # Should pass chop check (VWAP_RECLAIM is structural, not momentum)
        assert validated_signal.validation_flags["chop_ok"] is True

    def test_continuation_still_rejected_by_gold_chop(self):
        """Test DXY_CONTINUATION still rejected by gold chop.
        
        Note: validation layer uses chop_severity, not chop_detected.
        DXY_CONTINUATION is blocked on ANY chop severity (SOFT or HARD).
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
            score=8.0,
            confidence="high",
            chop_detected=True,  # Gold chop
            chop_severity=ChopSeverity.SOFT_CHOP,  # Required for validation rejection
            dxy_chop_5m=False,
            dxy_alignment=True,
            conflict_detected=False,
            dxy_chop_detected=False,
        )

        context = {"enforcer_tier": "EarlyMild"}

        validated_signal = validate_signal(signal, htf_bias, context)

        assert validated_signal.confidence == "Reject"
        assert validated_signal.validation_flags["chop_ok"] is False
