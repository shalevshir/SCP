"""Integration tests for RuleEngine module.

Tests the complete workflow from features to validated and logged signals.
"""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from rule_engine import (
    Signal,
    log_signal,
    score_signal,
    validate_signal,
)
from rule_engine.htf.types import HTFBias


def create_htf_bias_from_context(context: dict) -> HTFBias:
    """Helper to create HTFBias from context dict for integration tests."""
    bias = context.get("htf_bias", "neutral")
    direction = context.get("htf_direction", "neutral")
    score = context.get("htf_score", 6.5)

    if score >= 8.0:
        confidence = "high"
    elif score >= 6.0:
        confidence = "medium"
    else:
        confidence = "low"

    return HTFBias(
        bias=bias,
        direction=direction,
        score=score,
        confidence=confidence,
        dxy_alignment=True,
    )


class TestRuleEngineIntegration:
    """Test complete RuleEngine workflow."""

    def test_complete_signal_workflow(self, tmp_path: Path) -> None:
        """Test full workflow: features -> score -> validate -> log."""
        # Step 1: Create feature data
        features = pd.Series(
            {
                "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
            }
        )

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "htf_score": 9.0,
            "session_ok": True,
            "enforcer_tier": "Early Mild",
            "dxy_corr": -0.75,
        }

        # Step 2: Score signal
        htf_bias = create_htf_bias_from_context(context)
        signal = score_signal(features, htf_bias, context)

        assert isinstance(signal, Signal)
        assert signal.score >= 8.0
        assert signal.confidence == "A+"
        assert signal.symbol == "GC"
        assert signal.direction == "long"

        # Step 3: Validate signal
        validated_signal = validate_signal(signal, htf_bias, context)

        assert validated_signal.validation_flags["session_ok"] is True
        assert validated_signal.validation_flags["tier_ok"] is True
        assert validated_signal.validation_flags["htf_bias_ok"] is True
        assert validated_signal.confidence == "A+"

        # Step 4: Log signal
        log_dir = tmp_path / "logs" / "signals"
        log_signal(validated_signal, log_dir=str(log_dir))

        # Verify log file exists
        log_file = log_dir / "2025-01-01.jsonl"
        assert log_file.exists()

    def test_rejected_signal_workflow(self) -> None:
        """Test workflow with signal that gets rejected by validation."""
        # Features indicating a potential trade
        features = pd.Series(
            {
                "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
            }
        )

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "htf_score": 9.0,
            "session_ok": False,  # Invalid session
            "enforcer_tier": "Early Mild",
            "dxy_corr": -0.75,
        }

        # Score signal
        htf_bias = create_htf_bias_from_context(context)
        signal = score_signal(features, htf_bias, context)
        assert signal.confidence == "A+"  # Before validation

        # Validate signal (should reject due to invalid session)
        validated_signal = validate_signal(signal, htf_bias, context)
        assert validated_signal.confidence == "Reject"
        assert validated_signal.validation_flags["session_ok"] is False

    def test_multiple_signals_same_day(self, tmp_path: Path) -> None:
        """Test logging multiple signals to the same day file."""
        signals = []

        for hour in range(10, 13):
            features = pd.Series(
                {
                    "timestamp": datetime(2025, 1, 1, hour, 0, tzinfo=UTC),
                    "symbol": "GC",
                    "timeframe": "1m",
                    "close": 2650.0,
                    "vwap": 2645.0,
                    "rsi": 55.0,
                    "ema_9": 2648.0,
                    "ema_20": 2645.0,
                    "ema_50": 2640.0,
                    "dxy_corr": -0.75,
                }
            )

            context = {
                "htf_bias": "bullish",
                "htf_direction": "long",
                "session_ok": True,
                "enforcer_tier": "Early Mild",
            }

            htf_bias = create_htf_bias_from_context(context)
            signal = score_signal(features, htf_bias, context)
            validated_signal = validate_signal(signal, htf_bias, context)
            signals.append(validated_signal)

        # Log all signals
        log_dir = tmp_path / "logs" / "signals"
        for signal in signals:
            log_signal(signal, log_dir=str(log_dir))

        # Verify all logged to same file
        log_file = log_dir / "2025-01-01.jsonl"
        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) == 3

    def test_different_setup_types(self) -> None:
        """Test scoring different setup types."""
        # VWAP_RECLAIM setup
        features_reclaim = pd.Series(
            {
                "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
            }
        )

        context = {
            "htf_bias": "bullish",
            "htf_direction": "long",
            "session_ok": True,
            "enforcer_tier": "Mild",
        }

        htf_bias = create_htf_bias_from_context(context)
        signal_reclaim = score_signal(features_reclaim, htf_bias, context)
        assert signal_reclaim.setup_type == "VWAP_RECLAIM"

        # VWAP_FADE setup
        features_fade = pd.Series(
            {
                "timestamp": datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2600.0,  # Far from VWAP
                "vwap": 2645.0,
                "rsi": 28.0,  # Oversold
                "ema_9": 2610.0,
                "ema_20": 2615.0,
                "ema_50": 2620.0,
                "dxy_corr": -0.75,
            }
        )

        signal_fade = score_signal(features_fade, htf_bias, context)
        assert signal_fade.setup_type == "VWAP_FADE"

        # DXY_CONTINUATION setup
        features_dxy = pd.Series(
            {
                "timestamp": datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2648.0,
                "rsi": 55.0,
                "ema_9": 2649.0,
                "ema_20": 2647.0,
                "ema_50": 2645.0,
                "dxy_corr": -0.85,  # Very strong correlation
            }
        )

        signal_dxy = score_signal(features_dxy, htf_bias, context)
        assert signal_dxy.setup_type == "DXY_CONTINUATION"
