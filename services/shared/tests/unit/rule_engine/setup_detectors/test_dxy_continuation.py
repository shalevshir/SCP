"""Tests for DXY continuation detector."""

import pandas as pd
import pytest

from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.setup_detectors.dxy_continuation import detect_dxy_continuation


class TestDXYContinuationDetector:
    """Test DXY continuation detection logic."""

    def test_valid_continuation_long(self):
        """Test valid DXY continuation for long setup."""
        # Create HTFBias with all required conditions met
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,  # Strong inverse
            dxy_corr_5m=-0.5,  # Strong inverse
            dxy_structure="LL",  # DXY bearish
            bars_since_bos=8,  # Recent BOS
            dxy_chop_5m=False,  # No chop
            chop_detected=False,  # No gold chop
        )

        # Create features with OHLC and ATR
        features = pd.Series(
            {
                "open": 100.0,
                "close": 105.0,
                "high": 105.5,
                "low": 99.5,
                "atr": 3.0,
                "structure_clarity": 0.7,  # Required for continuation
                "is_chop": False,  # No chop
            }
        )

        # Create DataFrame for micro structure
        df = pd.DataFrame(
            {
                "high": [102, 104, 103],
                "low": [98, 100, 101],  # HL pattern (ascending lows)
            }
        )

        # Should detect continuation
        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is True

    def test_weak_correlation_rejects(self):
        """Test that weak correlation rejects continuation."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.2,  # Too weak
            dxy_corr_5m=-0.5,
            dxy_structure="LL",
            bars_since_bos=8,
            dxy_chop_5m=False,
            chop_detected=False,
        )

        features = pd.Series(
            {"open": 100.0, "close": 105.0, "high": 105.5, "low": 99.5, "atr": 3.0}
        )

        result = detect_dxy_continuation(features, htf_bias)
        assert result is False

    def test_wrong_dxy_structure_rejects(self):
        """Test that wrong DXY structure rejects continuation."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_structure="HH",  # Wrong structure for long
            bars_since_bos=8,
            dxy_chop_5m=False,
            chop_detected=False,
        )

        features = pd.Series(
            {"open": 100.0, "close": 105.0, "high": 105.5, "low": 99.5, "atr": 3.0}
        )

        result = detect_dxy_continuation(features, htf_bias)
        assert result is False

    def test_stale_bos_rejects(self):
        """Test that stale BOS rejects continuation."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_structure="LL",
            bars_since_bos=15,  # Too old
            dxy_chop_5m=False,
            chop_detected=False,
        )

        features = pd.Series(
            {"open": 100.0, "close": 105.0, "high": 105.5, "low": 99.5, "atr": 3.0}
        )

        result = detect_dxy_continuation(features, htf_bias)
        assert result is False

    def test_dxy_chop_rejects(self):
        """Test that DXY 5M chop rejects continuation."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_structure="LL",
            bars_since_bos=8,
            dxy_chop_5m=True,  # Chop detected
            chop_detected=False,
        )

        features = pd.Series(
            {"open": 100.0, "close": 105.0, "high": 105.5, "low": 99.5, "atr": 3.0}
        )

        result = detect_dxy_continuation(features, htf_bias)
        assert result is False

    def test_gold_chop_rejects(self):
        """Test that gold micro chop rejects continuation."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_structure="LL",
            bars_since_bos=8,
            dxy_chop_5m=False,
            chop_detected=True,  # Gold chop
        )

        features = pd.Series(
            {"open": 100.0, "close": 105.0, "high": 105.5, "low": 99.5, "atr": 3.0}
        )

        result = detect_dxy_continuation(features, htf_bias)
        assert result is False

    def test_weak_displacement_rejects(self):
        """Test that weak displacement rejects continuation."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_structure="LL",
            bars_since_bos=8,
            dxy_chop_5m=False,
            chop_detected=False,
        )

        # Small body = weak displacement
        features = pd.Series(
            {
                "open": 100.0,
                "close": 101.0,  # Small body
                "high": 102.0,
                "low": 99.0,
                "atr": 3.0,  # Displacement = 1.0/3.0 = 0.33 < 1.2
            }
        )

        result = detect_dxy_continuation(features, htf_bias)
        assert result is False

    def test_valid_continuation_short(self):
        """Test valid DXY continuation for short setup."""
        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_structure="HH",  # DXY bullish
            bars_since_bos=8,
            dxy_chop_5m=False,
            chop_detected=False,
        )

        features = pd.Series(
            {
                "open": 105.0,
                "close": 100.0,
                "high": 106.0,
                "low": 99.5,
                "atr": 3.0,
                "structure_clarity": 0.7,  # Required for continuation
                "is_chop": False,  # No chop
            }
        )

        # LH pattern (descending highs)
        df = pd.DataFrame(
            {
                "high": [104, 102, 101],  # LH pattern
                "low": [98, 96, 95],
            }
        )

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is True


class TestNoiseZoneHandling:
    """Test that noise zone is handled via score penalty, not hard rejection.
    
    Per Shir Capital SOP: "Noise zone now handled as score penalty (not hard-block)"
    The detect_dxy_continuation function should NOT hard-reject based on noise zone.
    Noise handling is done via calculate_noise_penalty() in scoring.py.
    
    This test verifies the fix for the bug where is_noise_zone was checked as
    a hard gate but never computed in the feature engine.
    """

    def test_is_noise_zone_not_a_hard_rejection(self):
        """Test that is_noise_zone does NOT cause hard rejection.
        
        Noise zone detection should be handled via score penalty in scoring.py,
        not as a hard gate in the detector. Valid setups should pass detection
        regardless of is_noise_zone value.
        
        This is a regression test for the bug where is_noise_zone was checked
        but never computed in the feature engine (always defaulted to False).
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_structure="LL",
            bars_since_bos=8,
            dxy_chop_5m=False,
            chop_detected=False,
        )

        # Create features with is_noise_zone=True
        # If noise zone caused hard rejection, this would fail
        features = pd.Series(
            {
                "open": 100.0,
                "close": 105.0,
                "high": 105.5,
                "low": 99.5,
                "atr": 3.0,
                "structure_clarity": 0.7,
                "is_chop": False,
                "is_noise_zone": True,  # Noise zone should NOT cause hard rejection
                "last_structure_label": "HH",
            }
        )

        df = pd.DataFrame(
            {
                "high": [102, 104, 103],
                "low": [98, 100, 101],  # HL pattern
            }
        )

        # Should detect continuation even with is_noise_zone=True
        # Noise zone handling is done via score penalty in scoring.py
        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is True, (
            "Noise zone should be handled via score penalty, not hard rejection. "
            "See calculate_noise_penalty() in scoring.py for setup-aware noise handling."
        )
