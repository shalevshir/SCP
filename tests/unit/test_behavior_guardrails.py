"""Tests for behavior guardrails state tracking and enforcement."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from validation import (
    BehaviorGuardrails,
    BehaviorState,
    BehaviorStateTracker,
    BufferPhase,
    EnforcerTier,
    GuardrailResult,
    HTFBias,
    SessionConstraints,
    TradeDirection,
    ValidationContext,
    ValidationEngine,
)


def _session_constraints(max_losses: int) -> SessionConstraints:
    return SessionConstraints(
        name="Test",
        window_start=time(10, 0),
        window_end=time(13, 0),
        allowed_tiers=frozenset({"Conservative"}),
        allowed_setups=frozenset({"continuation"}),
        min_score=8.0,
        max_losses=max_losses,
        dxy_correlation_max=-0.6,
    )


class TestBehaviorStateTracker:
    def test_record_trade_outcome_updates_loss_streak(self) -> None:
        tracker = BehaviorStateTracker()

        tracker.record_trade_outcome(won=False)
        tracker.record_trade_outcome(won=False)
        assert tracker.state.consecutive_losses == 2

        tracker.record_trade_outcome(won=True)
        assert tracker.state.consecutive_losses == 0

    def test_breakeven_trade_does_not_increment_loss_streak(self) -> None:
        """Test that breakeven trades (pnl == 0) don't increment loss streak.

        Per SOP, only losing trades (pnl < 0) should increment the streak.
        Breakeven trades (pnl == 0) should leave the streak unchanged.
        This prevents premature halts when breakeven trades occur.
        """
        tracker = BehaviorStateTracker()

        # Start with one loss
        tracker.record_trade_outcome(won=False)
        assert tracker.state.consecutive_losses == 1

        # Breakeven trade should not increment or reset
        tracker.record_trade_outcome(won=None)  # None indicates breakeven
        assert (
            tracker.state.consecutive_losses == 1
        ), "Breakeven trade should not increment loss streak"

        # Another breakeven
        tracker.record_trade_outcome(won=None)
        assert (
            tracker.state.consecutive_losses == 1
        ), "Multiple breakeven trades should not increment loss streak"

        # Win should reset
        tracker.record_trade_outcome(won=True)
        assert tracker.state.consecutive_losses == 0

    def test_fatigue_and_session_extension_flags(self) -> None:
        tracker = BehaviorStateTracker()
        tracker.set_fatigue_flag(True)
        tracker.mark_session_extension(True)

        assert tracker.state.fatigue_flag is True
        assert tracker.state.session_extended is True

    def test_reset_for_session_clears_state(self) -> None:
        tracker = BehaviorStateTracker()
        tracker.record_trade_outcome(won=False)
        tracker.set_fatigue_flag(True)
        tracker.mark_session_extension(True)

        tracker.reset_for_session(now=datetime(2025, 1, 1, tzinfo=ZoneInfo("UTC")))

        assert tracker.state.consecutive_losses == 0
        assert tracker.state.fatigue_flag is False
        assert tracker.state.session_extended is False


class TestBehaviorGuardrails:
    def test_loss_streak_blocks_at_threshold(self) -> None:
        guardrails = BehaviorGuardrails()
        state = BehaviorState(consecutive_losses=2)
        constraints = _session_constraints(max_losses=2)

        result = guardrails.evaluate(state, constraints)

        assert isinstance(result, GuardrailResult)
        assert result.allowed is False
        assert any("loss streak" in reason.lower() for reason in result.reasons)

    def test_loss_streak_uses_session_specific_limit(self) -> None:
        guardrails = BehaviorGuardrails()
        state = BehaviorState(consecutive_losses=1)
        constraints = _session_constraints(max_losses=1)

        result = guardrails.evaluate(state, constraints)

        assert result.allowed is False
        assert "max_losses=1" in " ".join(result.reasons)

    def test_fatigue_flag_blocks_immediately(self) -> None:
        guardrails = BehaviorGuardrails()
        state = BehaviorState(fatigue_flag=True)

        result = guardrails.evaluate(state, _session_constraints(max_losses=2))

        assert result.allowed is False
        assert any("fatigue" in reason.lower() for reason in result.reasons)

    def test_session_extension_blocks(self) -> None:
        guardrails = BehaviorGuardrails()
        state = BehaviorState(session_extended=True)

        result = guardrails.evaluate(state, _session_constraints(max_losses=2))

        assert result.allowed is False
        assert any("session" in reason.lower() for reason in result.reasons)

    def test_allows_when_no_guardrails_triggered(self) -> None:
        guardrails = BehaviorGuardrails()
        state = BehaviorState(consecutive_losses=0)

        result = guardrails.evaluate(state, _session_constraints(max_losses=2))

        assert result.allowed is True
        assert result.reasons == []

    def test_validation_engine_integration_blocks_on_guardrail(self) -> None:
        guardrails = BehaviorGuardrails()
        engine = ValidationEngine()
        constraints = _session_constraints(max_losses=1)

        guardrail_result = guardrails.evaluate(
            BehaviorState(consecutive_losses=2), constraints
        )

        context = ValidationContext(
            session_ok=True,
            tier_active=EnforcerTier.CONSERVATIVE,
            htf_bias=HTFBias.BULLISH,
            dxy_trending_clean=True,
            fatigue_flag=False,
            risk_allowed=True,
            news_ok=True,
            ceo_directive_active=False,
            buffer_phase=BufferPhase.STARTUP,
        )

        result = engine.validate(
            context=context,
            direction=TradeDirection.LONG,
            guardrail_result=guardrail_result,
        )

        assert result.valid is False
        assert any("Behavior guardrail" in err for err in result.errors)
