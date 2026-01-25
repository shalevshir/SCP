"""Tests for VWAP_FADE setup detector."""

import pandas as pd
import pytest

from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.setup_detectors.vwap_fade import detect_vwap_fade


class TestVWAPFadeDetector:
    """Test VWAP_FADE setup detection with structure requirements."""

    def create_base_features(self, direction="long"):
        """Create base features that meet most requirements."""
        return pd.Series(
            {
                "open": 100.0,
                "high": 102.0 if direction == "long" else 105.0,
                "low": 96.0 if direction == "long" else 99.0,
                "close": 100.6,  # 0.6% VWAP deviation (>0.5% threshold)
                "vwap": 100.0,
                "rsi": 25.0 if direction == "long" else 75.0,
                "structure_clarity": 0.7,
                "is_chop": False,
                "choch_detected": True,
                "trend_confidence": 0.4,
                "last_structure_label": "LH" if direction == "long" else "HL",
            }
        )

    def create_base_htf_bias(self, direction="long"):
        """Create base HTF bias."""
        return HTFBias(
            bias="bullish" if direction == "long" else "bearish",
            direction=direction,
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
        )

    def test_fade_requires_liquidity_sweep(self):
        """Test that fade requires liquidity sweep."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # With sweep: should pass
        htf_bias.liquidity_sweep_detected = True
        assert detect_vwap_fade(features, htf_bias) is True

        # Without sweep: should fail
        htf_bias.liquidity_sweep_detected = False
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_requires_rejection_candle(self):
        """Test that fade requires rejection candle with strong wick."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # With strong lower wick for long: should pass
        features["high"] = 102.0
        features["low"] = 96.0  # 4 point wick
        features["open"] = 100.0
        features["close"] = 100.6  # 0.6 point body (>0.5% VWAP deviation)
        assert detect_vwap_fade(features, htf_bias) is True

        # Without rejection wick: should fail
        features["low"] = 99.5  # No significant wick
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_requires_clarity_threshold(self):
        """Test that fade requires structure clarity >= 0.4 (loosened threshold)."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # With sufficient clarity (>= 0.4): should pass
        features["structure_clarity"] = 0.6
        assert detect_vwap_fade(features, htf_bias) is True

        # At threshold (0.4): should pass (threshold is inclusive)
        features["structure_clarity"] = 0.4
        assert detect_vwap_fade(features, htf_bias) is True

        # Below threshold (< 0.4): should fail
        features["structure_clarity"] = 0.3
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_blocked_by_chop(self):
        """Test fade chop handling.

        UPDATED: VWAP_FADE is now explicitly allowed during chop (preferred environment).
        The is_chop check was removed from detect_vwap_fade().
        Validation layer handles HARD_CHOP confirmation requirement.
        """
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # NEW BEHAVIOR: is_chop flag no longer blocks VWAP_FADE
        features["is_chop"] = False
        assert detect_vwap_fade(features, htf_bias) is True

        features["is_chop"] = True
        # Still passes - chop doesn't block fades anymore
        assert detect_vwap_fade(features, htf_bias) is True

    def test_fade_requires_choch_or_weakening(self):
        """Test that fade requires CHoCH or trend weakening signal."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # With CHoCH: should pass
        features["choch_detected"] = True
        features["trend_confidence"] = 0.8
        assert detect_vwap_fade(features, htf_bias) is True

        # With low trend confidence: should pass
        features["choch_detected"] = False
        features["trend_confidence"] = 0.3
        assert detect_vwap_fade(features, htf_bias) is True

        # Without either: should fail
        features["choch_detected"] = False
        features["trend_confidence"] = 0.8
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_long_requires_lh_structure(self):
        """Test that long fade requires LH (Lower High) structure."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # With LH: should pass
        features["last_structure_label"] = "LH"
        assert detect_vwap_fade(features, htf_bias) is True

        # With HH: should fail (trend is strengthening, not weakening)
        features["last_structure_label"] = "HH"
        assert detect_vwap_fade(features, htf_bias) is False

        # With HL: should fail (wrong direction)
        features["last_structure_label"] = "HL"
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_short_requires_hl_structure(self):
        """Test that short fade requires HL (Higher Low) structure."""
        features = self.create_base_features("short")
        htf_bias = self.create_base_htf_bias("short")

        # With HL: should pass
        features["last_structure_label"] = "HL"
        assert detect_vwap_fade(features, htf_bias) is True

        # With LL: should fail (trend is strengthening, not weakening)
        features["last_structure_label"] = "LL"
        assert detect_vwap_fade(features, htf_bias) is False

        # With LH: should fail (wrong direction)
        features["last_structure_label"] = "LH"
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_requires_rsi_extreme(self):
        """Test that fade requires RSI extreme (loosened: < 40 for long, > 60 for short)."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # Oversold (< 40): should pass
        features["rsi"] = 25.0
        assert detect_vwap_fade(features, htf_bias) is True

        # Just below threshold (39): should pass
        features["rsi"] = 39.0
        assert detect_vwap_fade(features, htf_bias) is True

        # Neutral RSI: should fail
        features["rsi"] = 50.0
        assert detect_vwap_fade(features, htf_bias) is False

        # Borderline (35 is < 40): should pass now
        features["rsi"] = 35.0
        assert detect_vwap_fade(features, htf_bias) is True

    def test_fade_requires_vwap_deviation(self):
        """Test that fade requires significant VWAP deviation (>0.25%, loosened from 0.5%)."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # Sufficient deviation: should pass
        features["close"] = 100.6
        features["vwap"] = 100.0
        # Deviation = 0.6%, > 0.25%
        assert detect_vwap_fade(features, htf_bias) is True

        # At threshold: should pass
        features["close"] = 100.26
        features["vwap"] = 100.0
        # Deviation = 0.26%, > 0.25%
        assert detect_vwap_fade(features, htf_bias) is True

        # Insufficient deviation: should fail
        features["close"] = 100.2
        features["vwap"] = 100.0
        # Deviation = 0.2%, < 0.25%
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_passes_all_requirements(self):
        """Integration test: fade with all requirements met."""
        # Long fade setup
        features = pd.Series(
            {
                "open": 100.0,
                "high": 102.0,
                "low": 96.0,
                "close": 100.6,
                "vwap": 100.0,
                "rsi": 25.0,
                "structure_clarity": 0.7,
                "is_chop": False,
                "choch_detected": True,
                "trend_confidence": 0.4,
                "last_structure_label": "LH",
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            liquidity_sweep_detected=True,
        )

        # All requirements met: should pass
        assert detect_vwap_fade(features, htf_bias) is True

    def test_fade_rejected_with_missing_requirements(self):
        """Test various combinations of missing requirements."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # Missing sweep
        htf_bias.liquidity_sweep_detected = False
        assert detect_vwap_fade(features, htf_bias) is False
        htf_bias.liquidity_sweep_detected = True

        # Missing rejection wick
        features["low"] = 99.5
        assert detect_vwap_fade(features, htf_bias) is False
        features["low"] = 96.0

        # Low clarity (< 0.4 threshold)
        features["structure_clarity"] = 0.3
        assert detect_vwap_fade(features, htf_bias) is False
        features["structure_clarity"] = 0.7

        # Chop detected - UPDATED: Chop no longer blocks VWAP_FADE
        # features["is_chop"] = True
        # assert detect_vwap_fade(features, htf_bias) is False
        # features["is_chop"] = False
        # (Chop check removed from detect_vwap_fade per chop refactor)

        # Wrong structure label
        features["last_structure_label"] = "HH"
        assert detect_vwap_fade(features, htf_bias) is False
        features["last_structure_label"] = "LH"

        # RSI not extreme
        features["rsi"] = 50.0
        assert detect_vwap_fade(features, htf_bias) is False
        features["rsi"] = 25.0

        # Insufficient VWAP deviation (< 0.25%)
        features["close"] = 100.2  # 0.2% deviation
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_rejects_invalid_direction(self):
        """Test that fade rejects invalid direction."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # Valid direction: should pass
        htf_bias.direction = "long"
        assert detect_vwap_fade(features, htf_bias) is True

        # Invalid direction: should fail
        htf_bias.direction = "neutral"
        assert detect_vwap_fade(features, htf_bias) is False

    def test_fade_handles_doji_candles(self):
        """Test that fade handles doji-like candles (very small body)."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # Doji with significant wick: should pass
        features["open"] = 100.0
        features["close"] = 100.6  # Small body but sufficient VWAP deviation
        features["high"] = 102.0
        features["low"] = 96.0  # Significant lower wick
        assert detect_vwap_fade(features, htf_bias) is True

    def test_fade_rejects_invalid_ohlc(self):
        """Test that fade rejects invalid OHLC data."""
        features = self.create_base_features("long")
        htf_bias = self.create_base_htf_bias("long")

        # Invalid: high < low
        features["high"] = 95.0
        features["low"] = 100.0
        assert detect_vwap_fade(features, htf_bias) is False

        # Invalid: zero prices
        features["high"] = 0
        features["low"] = 0
        assert detect_vwap_fade(features, htf_bias) is False
