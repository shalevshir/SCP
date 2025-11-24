"""End-to-end integration tests for validation layer.

Tests the complete pipeline: raw candle → features → validation → scoring → signal.
"""

import json
from datetime import datetime, time, timezone
from pathlib import Path

import pandas as pd
import pytest

from feature_engine.integration import process_features_with_validation
from rule_engine.htf.types import HTFBias
from rule_engine.signal_logger import log_signal, signal_to_dict
from validation.config_loader import load_session_config
from validation.guardrails import BehaviorGuardrails, BehaviorStateTracker
from validation.schema import BufferPhase, EnforcerTier
from validation.session_validator import SessionConstraints, SessionValidator


def create_htf_bias_from_market_state(market_state: dict) -> HTFBias:
    """Helper to create HTFBias from market_state dict for e2e tests."""
    bias = market_state.get("htf_bias", "neutral")
    direction = market_state.get("htf_direction", "neutral")
    score = market_state.get("htf_score", 6.5)
    
    if score >= 8.0:
        confidence = "high"
    elif score >= 6.0:
        confidence = "medium"
    else:
        confidence = "low"
    
    return HTFBias(
        bias=bias if bias else ("bullish" if direction == "long" else "bearish" if direction == "short" else "neutral"),
        direction=direction,
        score=score,
        confidence=confidence,
        dxy_alignment=market_state.get("dxy_corr", -0.7) < -0.6,
    )


class TestE2EValidationPipeline:
    """Test end-to-end validation pipeline."""

    def test_full_pipeline_accepted_signal(self, tmp_path: Path) -> None:
        """Test full pipeline with signal that passes validation."""
        # Step 1: Create feature data
        features = pd.Series({
            "timestamp": datetime(2024, 11, 15, 10, 30, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
            "structure_type": "HH",
        })

        # Step 2: Build market state
        market_state = {
            "buffer_phase": "0-5k",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
            "session_ok": True,
            "htf_direction": "long",
            "htf_score": 9.0,
        }

        # Step 3: Create session constraints (November - favorable)
        session_constraints = SessionConstraints(
            name="November-December Trend Window",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative", "EarlyMild", "Mild", "Offensive"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION", "VWAP_FADE"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        # Step 4: No guardrail issues
        guardrail_result = None

        # Step 5: Process through pipeline
        htf_bias = create_htf_bias_from_market_state(market_state)
        signal = process_features_with_validation(
            features,
            htf_bias,
            market_state,
            session_constraints,
            guardrail_result,
            log_signals=True,
            log_dir=str(tmp_path / "signals"),
        )

        # Step 6: Verify signal passed validation
        assert signal.confidence == "A+"
        assert signal.validation_flags["session_ok"] is True
        assert signal.score >= 8.0

        # Step 7: Verify signal was logged
        log_file = tmp_path / "signals" / "2024-11-15.jsonl"
        assert log_file.exists()

        with open(log_file, "r") as f:
            logged_signal = json.loads(f.read().strip())
            assert logged_signal["confidence"] == "A+"
            assert logged_signal["symbol"] == "GC"

    def test_full_pipeline_rejected_signal_low_score(self, tmp_path: Path) -> None:
        """Test full pipeline with signal rejected for low score in September."""
        # Step 1: Create feature data with weak signals (will score < 9.0)
        features = pd.Series({
            "timestamp": datetime(2024, 9, 15, 10, 30, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2640.0,  # Below VWAP (weak for long)
            "vwap": 2645.0,
            "rsi": 35.0,  # Oversold (weak for long continuation)
            "ema_9": 2642.0,  # Flat/mixed EMAs (no clear trend)
            "ema_20": 2643.0,
            "ema_50": 2641.0,
            "dxy_corr": -0.65,  # Weak correlation
            "structure_type": "LL",  # Bearish structure (wrong for long)
        })

        # Step 2: Build market state
        market_state = {
            "buffer_phase": "0-5k",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
            "session_ok": True,
            "htf_direction": "long",
            "htf_score": 7.5,  # Low HTF score
        }

        # Step 3: September constraints (min_score=9.0)
        session_constraints = SessionConstraints(
            name="September Defensive",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative", "EarlyMild"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION"]),
            min_score=9.0,
            max_losses=1,
            dxy_correlation_max=-0.7,
        )

        # Step 4: Process through pipeline
        htf_bias = create_htf_bias_from_market_state(market_state)
        signal = process_features_with_validation(
            features,
            htf_bias,
            market_state,
            session_constraints,
            None,
            log_signals=True,
            log_dir=str(tmp_path / "signals"),
        )

        # Step 5: Verify signal was rejected
        assert signal.confidence == "Reject"
        assert "below seasonal minimum" in signal.rationale

        # Step 6: Verify rejection was logged
        log_file = tmp_path / "signals" / "2024-09-15.jsonl"
        assert log_file.exists()

        with open(log_file, "r") as f:
            logged_signal = json.loads(f.read().strip())
            assert logged_signal["confidence"] == "Reject"
            assert "REJECTED" in logged_signal["rationale"]

    def test_full_pipeline_rejected_signal_loss_streak(self, tmp_path: Path) -> None:
        """Test full pipeline with signal rejected for loss streak."""
        from validation.guardrails import BehaviorGuardrails, BehaviorState

        # Step 1: Create feature data
        features = pd.Series({
            "timestamp": datetime(2024, 9, 15, 10, 30, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
            "structure_type": "HH",
        })

        # Step 2: Build market state
        market_state = {
            "buffer_phase": "0-5k",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
            "session_ok": True,
            "htf_direction": "long",
            "htf_score": 9.5,
        }

        # Step 3: September constraints (max_losses=1)
        session_constraints = SessionConstraints(
            name="September Defensive",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative", "EarlyMild"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION"]),
            min_score=9.0,
            max_losses=1,
            dxy_correlation_max=-0.7,
        )

        # Step 4: Simulate 1 loss (should halt in September)
        state = BehaviorState(consecutive_losses=1)
        guardrails = BehaviorGuardrails()
        guardrail_result = guardrails.evaluate(state, session_constraints)

        # Step 5: Process through pipeline
        htf_bias = create_htf_bias_from_market_state(market_state)
        signal = process_features_with_validation(
            features,
            htf_bias,
            market_state,
            session_constraints,
            guardrail_result,
            log_signals=True,
            log_dir=str(tmp_path / "signals"),
        )

        # Step 6: Verify signal was rejected
        assert signal.confidence == "Reject"

    def test_full_pipeline_dxy_unavailable_handling(self, tmp_path: Path) -> None:
        """Test full pipeline with DXY data unavailable."""
        # Step 1: Create feature data WITHOUT DXY
        features = pd.Series({
            "timestamp": datetime(2024, 11, 15, 10, 30, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": None,  # DXY unavailable
            "structure_type": "HH",
        })

        # Step 2: Build market state
        market_state = {
            "buffer_phase": "0-5k",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
            "session_ok": True,
            "htf_direction": "long",
            "htf_score": 9.0,
        }

        # Step 3: November constraints
        session_constraints = SessionConstraints(
            name="November-December Trend Window",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative"]),
            allowed_setups=frozenset(["VWAP_RECLAIM"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        # Step 4: Process through pipeline (should reject VWAP_RECLAIM without DXY)
        htf_bias = create_htf_bias_from_market_state(market_state)
        signal = process_features_with_validation(
            features,
            htf_bias,
            market_state,
            session_constraints,
            None,
            log_signals=True,
            log_dir=str(tmp_path / "signals"),
        )

        # Step 5: Verify rejection due to DXY unavailability
        assert signal.confidence == "Reject"
        assert "requires DXY data" in signal.rationale

    def test_logging_includes_validation_details(self, tmp_path: Path) -> None:
        """Test that logged signals include full validation context."""
        from validation.engine import ValidationEngine, ValidationResult
        from validation.guardrails import BehaviorState

        # Create signal
        features = pd.Series({
            "timestamp": datetime(2024, 11, 15, 10, 30, tzinfo=timezone.utc),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2645.0,
            "rsi": 55.0,
            "ema_9": 2648.0,
            "ema_20": 2645.0,
            "ema_50": 2640.0,
            "dxy_corr": -0.75,
            "structure_type": "HH",
        })

        market_state = {
            "buffer_phase": "0-5k",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
            "session_ok": True,
            "htf_direction": "long",
            "htf_score": 9.0,
        }

        session_constraints = SessionConstraints(
            name="November-December Trend Window",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        # Process signal
        htf_bias = create_htf_bias_from_market_state(market_state)
        signal = process_features_with_validation(
            features,
            htf_bias,
            market_state,
            session_constraints,
            None,
            log_signals=False,  # Manual logging
        )

        # Create validation result and behavior state for logging
        validation_result = ValidationResult(
            valid=True,
            errors=[],
            enforced_tier="Conservative",
        )

        behavior_state = BehaviorState(
            consecutive_losses=0,
            fatigue_flag=False,
            session_extended=False,
        )

        # Log with validation details
        log_signal(
            signal,
            log_dir=str(tmp_path / "signals"),
            validation_result=validation_result,
            session_constraints=session_constraints,
            behavior_state=behavior_state,
        )

        # Verify logged data includes validation details
        log_file = tmp_path / "signals" / "2024-11-15.jsonl"
        assert log_file.exists()

        with open(log_file, "r") as f:
            logged_data = json.loads(f.read().strip())

            # Check validation_result
            assert "validation_result" in logged_data
            assert logged_data["validation_result"]["valid"] is True
            assert logged_data["validation_result"]["enforced_tier"] == "Conservative"

            # Check session_constraints
            assert "session_constraints" in logged_data
            assert logged_data["session_constraints"]["name"] == "November-December Trend Window"
            assert logged_data["session_constraints"]["min_score"] == 8.0
            assert logged_data["session_constraints"]["max_losses"] == 2

            # Check guardrail_state
            assert "guardrail_state" in logged_data
            assert logged_data["guardrail_state"]["consecutive_losses"] == 0
            assert logged_data["guardrail_state"]["fatigue_flag"] is False

    def test_state_persistence_across_candles(self) -> None:
        """Test behavior state persistence across multiple candles."""
        from validation.guardrails import BehaviorStateTracker

        tracker = BehaviorStateTracker()

        # Record first loss
        tracker.record_trade_outcome(won=False)
        assert tracker.state.consecutive_losses == 1

        # Record second loss
        tracker.record_trade_outcome(won=False)
        assert tracker.state.consecutive_losses == 2

        # Record win (should reset)
        tracker.record_trade_outcome(won=True)
        assert tracker.state.consecutive_losses == 0

    def test_session_reset_behavior(self) -> None:
        """Test that behavior state resets at session start."""
        from validation.guardrails import BehaviorStateTracker

        tracker = BehaviorStateTracker()

        # Record losses
        tracker.record_trade_outcome(won=False)
        tracker.record_trade_outcome(won=False)
        assert tracker.state.consecutive_losses == 2

        # Reset for new session
        tracker.reset_for_session(datetime(2024, 11, 16, 10, 0, tzinfo=timezone.utc))
        assert tracker.state.consecutive_losses == 0
        assert tracker.state.last_reset is not None

