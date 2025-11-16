"""Unit tests for RuleEngine scoring functions.

Tests the core scoring logic, signal classification, and confidence determination
according to SOP requirements.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from rule_engine.scoring import (
    classify_confidence,
    determine_setup_type,
    score_signal,
)
from rule_engine.signal import Signal


class TestScoreSignal:
    """Test main score_signal function."""

    def test_score_signal_high_quality_long(self) -> None:
        """Test scoring a high-quality long setup (A+ confidence)."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
        })

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, context)

        assert isinstance(signal, Signal)
        assert signal.score >= 8.0
        assert signal.confidence == "A+"
        assert signal.direction == "long"
        assert signal.symbol == "GC"

    def test_score_signal_high_quality_short(self) -> None:
        """Test scoring a high-quality short setup (A+ confidence)."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2640.0,
            "vwap": 2645.0,
            "rsi": 45.0,
            "ema_9": 2642.0,
            "ema_20": 2645.0,
            "ema_50": 2650.0,
            "dxy_corr": -0.75,
        })

        context = {
            "htf_bias": "bearish",
            "htf_direction": "short",
            "session_ok": True,
            "enforcer_tier": "Mild",
        }

        signal = score_signal(features, context)

        assert signal.score >= 8.0
        assert signal.confidence == "A+"
        assert signal.direction == "short"

    def test_score_signal_watchlist_quality(self) -> None:
        """Test scoring a watchlist setup (6-7 score)."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,  # Above VWAP - 2 pts
            "rsi": 52.0,  # Mid-reset - 2 pts
            "ema_9": 2649.0,
            "ema_20": 2647.0,  # Partial alignment - 1 pt
            "ema_50": 2652.0,
            "dxy_corr": -0.55,  # Weak correlation - 0 pts
        })

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, context)

        # Should get: structure=2, vwap=2, rsi=2, ema=1 = 7 pts (no dxy_corr)
        assert 6.0 <= signal.score < 8.0
        assert signal.confidence == "Watch"

    def test_score_signal_reject_quality(self) -> None:
        """Test scoring a rejected setup (< 6 score)."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2640.0,
            "rsi": 75.0,  # Overbought in wrong direction
            "ema_9": 2645.0,
            "ema_20": 2642.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.3,  # Poor correlation
        })

        context = {
            "htf_bias": "bearish",  # Mismatch
            "htf_direction": "short",
            "session_ok": True,
            "enforcer_tier": "Conservative",
        }

        signal = score_signal(features, context)

        assert signal.score < 6.0
        assert signal.confidence == "Reject"

    def test_score_signal_includes_rationale(self) -> None:
        """Test that signal includes human-readable rationale."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
        })

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, context)

        assert signal.rationale is not None
        assert len(signal.rationale) > 0
        assert isinstance(signal.rationale, str)

    def test_score_signal_includes_factor_breakdown(self) -> None:
        """Test that signal includes detailed factor scoring."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
        })

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, context)

        assert isinstance(signal.factors, dict)
        assert len(signal.factors) > 0
        # Check that score equals sum of factors
        assert signal.score == sum(signal.factors.values())


class TestDetermineSetupType:
    """Test setup type classification logic."""

    def test_determine_vwap_reclaim_long(self) -> None:
        """Test identifying VWAP_RECLAIM setup for long."""
        features = pd.Series({
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "dxy_corr": -0.75,
        })

        context = {"htf_direction": "long"}

        setup_type = determine_setup_type(features, context)

        assert setup_type == "VWAP_RECLAIM"

    def test_determine_vwap_reclaim_short(self) -> None:
        """Test identifying VWAP_RECLAIM setup for short."""
        features = pd.Series({
            "close": 2640.0,
            "vwap": 2645.0,
            "rsi": 45.0,
            "dxy_corr": -0.75,
        })

        context = {"htf_direction": "short"}

        setup_type = determine_setup_type(features, context)

        assert setup_type == "VWAP_RECLAIM"

    def test_determine_vwap_fade_long(self) -> None:
        """Test identifying VWAP_FADE setup."""
        features = pd.Series({
            "close": 2600.0,
            "vwap": 2645.0,
            "rsi": 28.0,  # Oversold
            "dxy_corr": -0.75,
        })

        context = {"htf_direction": "long"}

        setup_type = determine_setup_type(features, context)

        assert setup_type == "VWAP_FADE"

    def test_determine_dxy_continuation(self) -> None:
        """Test identifying DXY_CONTINUATION setup."""
        features = pd.Series({
            "close": 2650.0,
            "vwap": 2648.0,
            "rsi": 55.0,
            "dxy_corr": -0.85,  # Strong correlation
        })

        context = {"htf_direction": "long"}

        setup_type = determine_setup_type(features, context)

        assert setup_type == "DXY_CONTINUATION"


class TestClassifyConfidence:
    """Test confidence classification logic."""

    def test_classify_a_plus_at_threshold(self) -> None:
        """Test A+ classification at minimum threshold (8.0)."""
        confidence = classify_confidence(8.0, "VWAP_RECLAIM")

        assert confidence == "A+"

    def test_classify_a_plus_above_threshold(self) -> None:
        """Test A+ classification above threshold."""
        confidence = classify_confidence(9.5, "VWAP_RECLAIM")

        assert confidence == "A+"

    def test_classify_watch_upper_bound(self) -> None:
        """Test Watch classification at upper bound (7.9)."""
        confidence = classify_confidence(7.9, "VWAP_RECLAIM")

        assert confidence == "Watch"

    def test_classify_watch_lower_bound(self) -> None:
        """Test Watch classification at lower bound (6.0)."""
        confidence = classify_confidence(6.0, "VWAP_RECLAIM")

        assert confidence == "Watch"

    def test_classify_reject_below_watch(self) -> None:
        """Test Reject classification below Watch threshold."""
        confidence = classify_confidence(5.5, "VWAP_RECLAIM")

        assert confidence == "Reject"

    def test_classify_reject_zero_score(self) -> None:
        """Test Reject classification at zero score."""
        confidence = classify_confidence(0.0, "VWAP_RECLAIM")

        assert confidence == "Reject"

    def test_classify_fade_requires_higher_threshold(self) -> None:
        """Test VWAP_FADE requires score >= 9 for A+."""
        # Score of 8 is A+ for continuations but Watch for fades
        confidence_8 = classify_confidence(8.0, "VWAP_FADE")
        assert confidence_8 == "Watch"

        # Score of 9 is A+ for fades
        confidence_9 = classify_confidence(9.0, "VWAP_FADE")
        assert confidence_9 == "A+"


class TestScoringScenariosFromSpec:
    """Test specific scenarios from the specification."""

    def test_perfect_vwap_reclaim_setup(self) -> None:
        """Test perfect VWAP reclaim hitting 10/10."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
        })

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "htf_score": 9.0,  # For HTF bonus
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, context)

        # Should get all factors (10 points possible with bonus)
        assert signal.score >= 8.0
        assert signal.confidence == "A+"
        assert signal.setup_type == "VWAP_RECLAIM"

    def test_minimum_a_plus_continuation(self) -> None:
        """Test minimum viable A+ continuation setup (exactly 8/10)."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 50.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.65,
        })

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "htf_score": 7.0,  # Below HTF bonus threshold
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, context)

        assert signal.score >= 8.0
        assert signal.confidence == "A+"

    def test_htf_bias_mismatch_reduces_score(self) -> None:
        """Test that HTF bias mismatch reduces score significantly."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
        })

        context = {
            "htf_bias": "bearish",  # Mismatch with bullish indicators
            "htf_direction": "short",
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        signal = score_signal(features, context)

        # Structure alignment should fail, reducing score below threshold
        assert signal.score < 8.0

    def test_dxy_correlation_strength_impact(self) -> None:
        """Test that stronger DXY correlation produces higher scores."""
        # Base features
        base_features = {
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
        }

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        # Strong correlation (meets threshold)
        features_strong = pd.Series({**base_features, "dxy_corr": -0.72})
        signal_strong = score_signal(features_strong, context)

        # Weak correlation (below threshold)
        features_weak = pd.Series({**base_features, "dxy_corr": -0.20})
        signal_weak = score_signal(features_weak, context)

        # Strong correlation should produce higher score
        assert signal_strong.score > signal_weak.score
        # Specifically, should be 2 points higher (dxy_corr factor weight)
        assert signal_strong.score == signal_weak.score + 2.0

    def test_yaml_weight_modification_impact(self) -> None:
        """Test that modifying YAML weights changes signal scores appropriately."""
        features = pd.Series({
            "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
        })

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "session_ok": True,
            "enforcer_tier": "Early Mild",
        }

        # Get baseline score with default config
        signal_baseline = score_signal(features, context)
        baseline_dxy_factor = signal_baseline.factors.get("dxy_corr", 0)

        # Verify the DXY factor is present and contributing
        assert baseline_dxy_factor == 2.0  # Default weight from config

        # The score should include this factor
        assert "dxy_corr" in signal_baseline.factors
        
        # Note: To truly test dynamic reweighting, we would need to modify
        # the config and reload, which is tested in the config_loader tests.
        # Here we verify that the factor weights from config are applied.
        total_from_factors = sum(signal_baseline.factors.values())
        assert signal_baseline.score == min(total_from_factors, 10.0)

