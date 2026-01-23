"""Tests for structure-based validation in setup detectors.

This module tests Step 9 of Structure Engine v2.0:
- Noise zone rejection for all setup types
- Gold structure label validation for DXY_CONTINUATION
"""

import pandas as pd
import pytest

from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.htf.vwap.reclaim import validate_reclaim_prerequisites
from scp_shared.rule_engine.scoring import determine_setup_type
from scp_shared.rule_engine.setup_detectors.dxy_continuation import (
    detect_dxy_continuation,
)
from scp_shared.rule_engine.setup_detectors.vwap_fade import detect_vwap_fade


class TestStructuralChopHandling:
    """Test that structural chop is handled via score penalty, not hard rejection.

    Per Shir Capital SOP: Noise means structural disorder, not low volatility.
    ATR compression is a supporting filter, not a primary gate.
    """

    def test_vwap_fade_not_rejected_by_low_atr_alone(self):
        """Test that VWAP_FADE is NOT rejected by low ATR alone."""
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
                "is_structural_chop": False,  # No structural chop
                "atr_compression_ratio": 0.3,  # Low ATR but clean structure
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

        # Should pass - low ATR alone doesn't block trades
        result = detect_vwap_fade(features, htf_bias)
        assert result is True, "Low ATR alone should not reject VWAP_FADE"

    def test_dxy_continuation_not_rejected_by_low_atr_alone(self):
        """Test that DXY_CONTINUATION is NOT rejected by low ATR alone."""
        features = pd.Series(
            {
                "open": 100.0,
                "close": 105.0,
                "high": 105.5,
                "low": 99.5,
                "atr": 3.0,
                "structure_clarity": 0.7,
                "is_chop": False,
                "is_structural_chop": False,  # No structural chop
                "atr_compression_ratio": 0.3,  # Low ATR but clean structure
                "last_structure_label": "HH",
            }
        )

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

        df = pd.DataFrame(
            {
                "high": [102, 104, 103],
                "low": [98, 100, 101],
            }
        )

        # Should pass - low ATR alone doesn't block trades
        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is True, "Low ATR alone should not reject DXY_CONTINUATION"

    def test_vwap_reclaim_not_rejected_by_low_atr_alone(self):
        """Test that VWAP_RECLAIM is NOT rejected by low ATR alone."""
        features = pd.Series(
            {
                "bos_direction": "bullish",
                "choch_detected": False,
                "structure_conflict_flag": False,
                "is_structural_chop": False,  # No structural chop
                "atr_compression_ratio": 0.3,  # Low ATR but clean structure
            }
        )

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            bos_detected=True,
            structure_clarity=0.8,
            bars_since_bos=5,
            liquidity_sweep_detected=True,
            chop_detected=False,
        )

        # Should pass - low ATR alone doesn't block trades
        is_valid, reason = validate_reclaim_prerequisites(htf_bias, features)
        assert is_valid is True, "Low ATR alone should not reject VWAP_RECLAIM"
        assert reason is None


class TestDXYContinuationStructureLabel:
    """Test gold structure label validation for DXY_CONTINUATION."""

    def create_base_features(self, structure_label="HH"):
        """Create base features for DXY_CONTINUATION tests."""
        return pd.Series(
            {
                "open": 100.0,
                "close": 105.0,
                "high": 105.5,
                "low": 99.5,
                "atr": 3.0,
                "structure_clarity": 0.7,
                "is_chop": False,
                "is_noise_zone": False,
                "last_structure_label": structure_label,
            }
        )

    def create_base_htf_bias(self, direction="long"):
        """Create base HTF bias for DXY_CONTINUATION tests."""
        return HTFBias(
            bias="bullish" if direction == "long" else "bearish",
            direction=direction,
            score=8.5,
            confidence="high",
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_structure="LL" if direction == "long" else "HH",
            bars_since_bos=8,
            dxy_chop_5m=False,
            chop_detected=False,
        )

    def test_long_continuation_accepted_with_hh_structure(self):
        """Test that long DXY_CONTINUATION is accepted with HH structure."""
        features = self.create_base_features("HH")
        htf_bias = self.create_base_htf_bias("long")
        df = pd.DataFrame({"high": [102, 104, 103], "low": [98, 100, 101]})

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is True

    def test_long_continuation_accepted_with_hl_structure(self):
        """Test that long DXY_CONTINUATION is accepted with HL structure."""
        features = self.create_base_features("HL")
        htf_bias = self.create_base_htf_bias("long")
        df = pd.DataFrame({"high": [102, 104, 103], "low": [98, 100, 101]})

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is True

    def test_long_continuation_rejected_with_lh_structure(self):
        """Test that long DXY_CONTINUATION is rejected with LH structure."""
        features = self.create_base_features("LH")
        htf_bias = self.create_base_htf_bias("long")
        df = pd.DataFrame({"high": [102, 104, 103], "low": [98, 100, 101]})

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is False

    def test_long_continuation_rejected_with_ll_structure(self):
        """Test that long DXY_CONTINUATION is rejected with LL structure."""
        features = self.create_base_features("LL")
        htf_bias = self.create_base_htf_bias("long")
        df = pd.DataFrame({"high": [102, 104, 103], "low": [98, 100, 101]})

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is False

    def test_short_continuation_accepted_with_lh_structure(self):
        """Test that short DXY_CONTINUATION is accepted with LH structure."""
        features = self.create_base_features("LH")
        htf_bias = self.create_base_htf_bias("short")
        df = pd.DataFrame({"high": [104, 102, 101], "low": [98, 96, 95]})

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is True

    def test_short_continuation_accepted_with_ll_structure(self):
        """Test that short DXY_CONTINUATION is accepted with LL structure."""
        features = self.create_base_features("LL")
        htf_bias = self.create_base_htf_bias("short")
        df = pd.DataFrame({"high": [104, 102, 101], "low": [98, 96, 95]})

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is True

    def test_short_continuation_rejected_with_hh_structure(self):
        """Test that short DXY_CONTINUATION is rejected with HH structure."""
        features = self.create_base_features("HH")
        htf_bias = self.create_base_htf_bias("short")
        df = pd.DataFrame({"high": [104, 102, 101], "low": [98, 96, 95]})

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is False

    def test_short_continuation_rejected_with_hl_structure(self):
        """Test that short DXY_CONTINUATION is rejected with HL structure."""
        features = self.create_base_features("HL")
        htf_bias = self.create_base_htf_bias("short")
        df = pd.DataFrame({"high": [104, 102, 101], "low": [98, 96, 95]})

        result = detect_dxy_continuation(features, htf_bias, df)
        assert result is False

    def test_continuation_allows_none_structure_label(self):
        """Test that DXY_CONTINUATION allows None structure label (no data yet)."""
        features = self.create_base_features(None)
        htf_bias = self.create_base_htf_bias("long")
        df = pd.DataFrame({"high": [102, 104, 103], "low": [98, 100, 101]})

        result = detect_dxy_continuation(features, htf_bias, df)
        # Should pass since None means no structure data available yet
        assert result is True
