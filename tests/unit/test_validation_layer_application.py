"""Comprehensive validation layer application tests.

Tests 20+ scenarios covering seasonality, session windows, loss streaks,
tier restrictions, DXY handling, HTF bias, CEO directives, and more.
"""

from datetime import date, datetime, time, timezone

import pandas as pd
import pytest

from rule_engine.signal import Signal
from rule_engine.validation import validate_signal_with_sop
from validation.context_builder import ValidationContextBuilder
from validation.guardrails import BehaviorGuardrails, BehaviorState
from validation.schema import BufferPhase, EnforcerTier, HTFBias, ValidationContext
from validation.session_validator import (
    SeasonRule,
    SessionConfig,
    SessionConstraints,
    SessionValidator,
)


class BaseValidationTest:
    """Base class with shared helper methods for validation tests."""

    def _create_test_signal(
        self,
        score: float = 9.0,
        confidence: str = "A+",
        setup_type: str = "VWAP_RECLAIM",
        direction: str = "long",
    ) -> Signal:
        """Create test signal."""
        return Signal(
            timestamp=datetime(2024, 9, 15, 10, 30, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction=direction,
            setup_type=setup_type,
            htf_bias="bullish",
            score=score,
            confidence=confidence,
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Conservative",
        )

    def _create_default_context(self) -> tuple[pd.Series, dict, SessionConstraints]:
        """Create default test context."""
        features = pd.Series({
            "close": 2650.0,
            "vwap": 2645.0,
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
        }

        constraints = SessionConstraints(
            name="Default",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative", "EarlyMild", "Mild", "Offensive"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        return features, market_state, constraints

    def _create_september_context(self) -> tuple[pd.Series, dict, SessionConstraints]:
        """Create September defensive context."""
        features, market_state, _ = self._create_default_context()

        constraints = SessionConstraints(
            name="September Defensive",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative", "EarlyMild"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION"]),
            min_score=9.0,
            max_losses=1,
            dxy_correlation_max=-0.7,
        )

        return features, market_state, constraints

    def _create_october_context(self) -> tuple[pd.Series, dict, SessionConstraints]:
        """Create October reconstruction context."""
        features, market_state, _ = self._create_default_context()

        constraints = SessionConstraints(
            name="October Base/Reconstruction",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative", "EarlyMild", "Mild"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION", "VWAP_FADE"]),
            min_score=8.5,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        return features, market_state, constraints

    def _create_november_context(self) -> tuple[pd.Series, dict, SessionConstraints]:
        """Create November trend window context."""
        features, market_state, _ = self._create_default_context()

        constraints = SessionConstraints(
            name="November-December Trend Window",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative", "EarlyMild", "Mild", "Offensive"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION", "VWAP_FADE"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        return features, market_state, constraints

    def _create_december_context(self) -> tuple[pd.Series, dict, SessionConstraints]:
        """Create December trend window context (same as November)."""
        return self._create_november_context()

    def _create_session_result(self, constraints: SessionConstraints):
        """Create SessionResult from constraints."""
        from validation.session_validator import SessionResult

        return SessionResult(
            session_ok=True,
            constraints=constraints,
        )


class TestSeasonalityRules(BaseValidationTest):
    """Test seasonality enforcement."""

    def test_september_defensive_blocks_low_scores(self) -> None:
        """September requires min_score=9.0."""
        signal = self._create_test_signal(score=8.5, confidence="A+")
        features, market_state, constraints = self._create_september_context()

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "Reject"
        assert "below seasonal minimum" in validated.rationale

    def test_september_defensive_allows_high_scores(self) -> None:
        """September allows score >= 9.0."""
        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_september_context()

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "A+"

    def test_october_reconstruction_allows_8_5_scores(self) -> None:
        """October allows min_score=8.5."""
        signal = self._create_test_signal(score=8.5, confidence="A+")
        features, market_state, constraints = self._create_october_context()

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "A+"

    def test_november_trend_window_allows_8_0_scores(self) -> None:
        """November-December allows min_score=8.0."""
        signal = self._create_test_signal(score=8.0, confidence="A+")
        features, market_state, constraints = self._create_november_context()

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "A+"

    def test_december_trend_window_allows_all_setups(self) -> None:
        """December allows all setup types."""
        signal = self._create_test_signal(
            score=9.0, confidence="A+", setup_type="VWAP_FADE"
        )
        features, market_state, constraints = self._create_december_context()

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "A+"


class TestSessionWindowEnforcement(BaseValidationTest):
    """Test session window blocking."""

    def test_session_window_blocks_outside_hours(self) -> None:
        """Trading blocked outside 10:00-13:00 London."""
        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_default_context()

        # Override session_ok to False (simulating outside hours)
        market_state["session_ok"] = False

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "Reject"
        assert validated.validation_flags["session_ok"] is False

    def test_session_window_allows_inside_hours(self) -> None:
        """Trading allowed during 10:00-13:00 London."""
        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_default_context()

        # Override session_ok to True (simulating inside hours)
        market_state["session_ok"] = True

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "A+"
        assert validated.validation_flags["session_ok"] is True


class TestLossStreakHalts(BaseValidationTest):
    """Test loss streak enforcement."""

    def test_september_halts_after_1_loss(self) -> None:
        """September halts after 1 consecutive loss."""
        from validation.guardrails import BehaviorState, BehaviorGuardrails, GuardrailResult

        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_september_context()

        # Simulate 1 loss
        state = BehaviorState(consecutive_losses=1)
        guardrails = BehaviorGuardrails()
        guardrail_result = guardrails.evaluate(state, constraints)

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, guardrail_result
        )

        assert validated.confidence == "Reject"

    def test_october_allows_1_loss_but_halts_at_2(self) -> None:
        """October halts after 2 consecutive losses."""
        from validation.guardrails import BehaviorState, BehaviorGuardrails

        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_october_context()

        # 1 loss should be OK
        state_1_loss = BehaviorState(consecutive_losses=1)
        guardrails = BehaviorGuardrails()
        guardrail_result_1 = guardrails.evaluate(state_1_loss, constraints)

        validated_1 = validate_signal_with_sop(
            signal, features, market_state, constraints, guardrail_result_1
        )

        assert validated_1.confidence == "A+"

        # 2 losses should halt
        state_2_loss = BehaviorState(consecutive_losses=2)
        guardrail_result_2 = guardrails.evaluate(state_2_loss, constraints)

        validated_2 = validate_signal_with_sop(
            signal, features, market_state, constraints, guardrail_result_2
        )

        assert validated_2.confidence == "Reject"


class TestTierRestrictions(BaseValidationTest):
    """Test enforcer tier restrictions."""

    def test_conservative_blocks_vwap_fade(self) -> None:
        """Conservative tier blocks VWAP_FADE."""
        signal = self._create_test_signal(
            score=9.0, confidence="A+", setup_type="VWAP_FADE"
        )
        features, market_state, constraints = self._create_default_context()
        market_state["tier_active"] = "Conservative"

        # Update constraints to Conservative allowed setups
        constraints = SessionConstraints(
            name="Default",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "Reject"
        assert "not allowed in" in validated.rationale

    def test_offensive_allows_all_setups(self) -> None:
        """Offensive tier allows all setup types."""
        signal = self._create_test_signal(
            score=9.0, confidence="A+", setup_type="VWAP_FADE"
        )
        features, market_state, constraints = self._create_default_context()
        market_state["tier_active"] = "Offensive"

        # Update constraints to Offensive allowed setups
        constraints = SessionConstraints(
            name="Default",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Offensive"]),
            allowed_setups=frozenset(
                ["VWAP_RECLAIM", "DXY_CONTINUATION", "VWAP_FADE"]
            ),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "A+"


class TestDXYHandling(BaseValidationTest):
    """Test DXY unavailability handling."""

    def test_dxy_unavailable_rejects_reclaim(self) -> None:
        """DXY unavailable rejects VWAP_RECLAIM."""
        signal = self._create_test_signal(
            score=9.0, confidence="A+", setup_type="VWAP_RECLAIM"
        )
        features, market_state, constraints = self._create_default_context()

        # Remove DXY correlation
        features["dxy_corr"] = None

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "Reject"
        assert "requires DXY data" in validated.rationale

    def test_dxy_unavailable_rejects_continuation(self) -> None:
        """DXY unavailable rejects DXY_CONTINUATION."""
        signal = self._create_test_signal(
            score=9.0, confidence="A+", setup_type="DXY_CONTINUATION"
        )
        features, market_state, constraints = self._create_default_context()

        # Remove DXY correlation
        features["dxy_corr"] = None

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "Reject"

    def test_dxy_unavailable_allows_fade_with_warning(self) -> None:
        """DXY unavailable allows VWAP_FADE with warning."""
        signal = self._create_test_signal(
            score=9.0, confidence="A+", setup_type="VWAP_FADE"
        )
        features, market_state, constraints = self._create_default_context()

        # Remove DXY correlation
        features["dxy_corr"] = None

        # Update constraints to allow VWAP_FADE
        constraints = SessionConstraints(
            name="Default",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Offensive"]),
            allowed_setups=frozenset(["VWAP_FADE"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "A+"
        assert "WARNING" in validated.rationale


class TestHTFBiasAlignment(BaseValidationTest):
    """Test HTF bias alignment."""

    def test_htf_bias_mismatch_rejected(self) -> None:
        """HTF bias mismatch causes rejection."""
        signal = self._create_test_signal(score=9.0, confidence="A+", direction="long")
        features, market_state, constraints = self._create_default_context()

        # Set HTF bias to bearish (mismatch with long direction)
        features["structure_type"] = "LL"
        features["ema_9"] = 2640.0
        features["ema_20"] = 2645.0
        features["ema_50"] = 2650.0
        features["close"] = 2635.0

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        # HTF bias mismatch should be flagged
        assert validated.validation_flags["htf_bias_ok"] is False


class TestCEODirective(BaseValidationTest):
    """Test CEO Early Mild directive requirements."""

    def test_early_mild_requires_directive(self) -> None:
        """Early Mild tier requires active CEO directive."""
        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_default_context()

        market_state["tier_active"] = "EarlyMild"
        market_state["ceo_directive_active"] = False

        # This should raise ValueError when building ValidationContext
        with pytest.raises(ValueError, match="EarlyMild tier requires active CEO directive"):
            builder = ValidationContextBuilder()
            builder.build_context(
                features,
                market_state,
                self._create_session_result(constraints),
                None
            )

    def test_early_mild_allowed_with_directive(self) -> None:
        """Early Mild tier allowed with active CEO directive."""
        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_default_context()

        market_state["tier_active"] = "EarlyMild"
        market_state["ceo_directive_active"] = True

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "A+"


class TestFatigueFlag(BaseValidationTest):
    """Test fatigue flag blocking."""

    def test_fatigue_flag_blocks_all_trading(self) -> None:
        """Fatigue flag blocks all trading."""
        from validation.guardrails import BehaviorState, BehaviorGuardrails

        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_default_context()

        # Set fatigue flag
        state = BehaviorState(fatigue_flag=True)
        guardrails = BehaviorGuardrails()
        guardrail_result = guardrails.evaluate(state, constraints)

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, guardrail_result
        )

        assert validated.confidence == "Reject"


class TestUSHolidays(BaseValidationTest):
    """Test US holiday blocking."""

    def test_holiday_blocks_trading(self) -> None:
        """US holidays block all trading."""
        signal = self._create_test_signal(score=9.0, confidence="A+")
        features, market_state, constraints = self._create_default_context()

        # Simulate holiday by setting session_ok to False
        market_state["session_ok"] = False

        validated = validate_signal_with_sop(
            signal, features, market_state, constraints, None
        )

        assert validated.confidence == "Reject"
        assert validated.validation_flags["session_ok"] is False

