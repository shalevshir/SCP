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


def create_htf_bias_from_context(context: dict, setup_type: str = "VWAP_RECLAIM") -> HTFBias:
    """Helper to create HTFBias from context dict for integration tests.
    
    Creates an HTFBias with all required fields for setup detection to work.
    """
    bias = context.get("htf_bias", "neutral")
    direction = context.get("htf_direction", "neutral")
    score = context.get("htf_score", 6.5)

    if score >= 8.0:
        confidence = "high"
    elif score >= 6.0:
        confidence = "medium"
    else:
        confidence = "low"

    # Set up required fields based on setup type
    # For VWAP_RECLAIM: liquidity_sweep_detected, structure_clarity >= 0.5, 
    #                   bos_detected, bars_since_bos <= 15
    # For DXY_CONTINUATION: dxy_corr_1m < -0.3, dxy_corr_5m < -0.3,
    #                       dxy_structure, bars_since_bos <= 10, no chop
    
    return HTFBias(
        bias=bias,
        direction=direction,
        score=score,
        confidence=confidence,
        dxy_alignment=True,
        # Structure fields for VWAP_RECLAIM
        liquidity_sweep_detected=True,
        liquidity_sweep_type="bullish" if direction == "long" else "bearish",
        structure_clarity=0.8,  # Above 0.5 threshold
        bos_detected=True,
        bars_since_bos=5,  # Within 15-bar limit
        # DXY fields for DXY_CONTINUATION
        dxy_corr_1m=-0.5,  # Strong inverse correlation
        dxy_corr_5m=-0.5,  # Strong inverse correlation
        dxy_structure="LL" if direction == "long" else "HH",  # DXY bearish for gold longs
        dxy_chop_5m=False,
        chop_detected=False,
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
        """Test scoring different setup types.
        
        Note: Setup type detection follows this priority order in determine_setup_type:
        1. VWAP_FADE: RSI extreme (<30 or >70) AND VWAP deviation > 0.5%
        2. DXY_CONTINUATION: Strong inverse correlation, DXY structure, BOS recency
        3. VWAP_RECLAIM: Liquidity sweep, structure clarity, BOS detected
        
        With the comprehensive HTFBias (which includes all DXY fields), 
        DXY_CONTINUATION may match first if conditions are met.
        """
        # VWAP_FADE setup - RSI extreme with VWAP deviation (checked first)
        features_fade = pd.Series(
            {
                "timestamp": datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2600.0,  # Far from VWAP
                "vwap": 2645.0,
                "rsi": 28.0,  # Oversold (<30)
                "ema_9": 2610.0,
                "ema_20": 2615.0,
                "ema_50": 2620.0,
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
        signal_fade = score_signal(features_fade, htf_bias, context)
        assert signal_fade.setup_type == "VWAP_FADE"

        # DXY_CONTINUATION setup - normal RSI, strong DXY
        # With comprehensive HTFBias, DXY_CONTINUATION matches when RSI is normal
        features_dxy = pd.Series(
            {
                "timestamp": datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2648.0,
                "rsi": 55.0,  # Normal RSI (won't trigger VWAP_FADE)
                "ema_9": 2649.0,
                "ema_20": 2647.0,
                "ema_50": 2645.0,
                "dxy_corr": -0.85,
            }
        )

        signal_dxy = score_signal(features_dxy, htf_bias, context)
        assert signal_dxy.setup_type == "DXY_CONTINUATION"

        # VWAP_RECLAIM setup - need to disable DXY so it doesn't match DXY_CONTINUATION
        # Create HTFBias without DXY correlation data
        htf_bias_no_dxy = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            dxy_alignment=True,
            # Structure fields for VWAP_RECLAIM
            liquidity_sweep_detected=True,
            liquidity_sweep_type="bullish",
            structure_clarity=0.8,
            bos_detected=True,
            bars_since_bos=5,
            # DXY fields set to None to force VWAP_RECLAIM
            dxy_corr_1m=None,
            dxy_corr_5m=None,
            dxy_structure=None,
        )

        features_reclaim = pd.Series(
            {
                "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2650.0,
                "vwap": 2645.0,
                "rsi": 55.0,  # Normal RSI (won't trigger VWAP_FADE)
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
            }
        )

        signal_reclaim = score_signal(features_reclaim, htf_bias_no_dxy, context)
        assert signal_reclaim.setup_type == "VWAP_RECLAIM"
