"""Unit tests for validation schema definitions.

Tests cover:
- Enum validation (BufferPhase, EnforcerTier, HTFBias)
- ValidationContext field requirements and types
- SOP cross-field validation (EarlyMild + CEO directive)
- Serialization and deserialization
- Edge cases and error handling
"""

import pytest
from pydantic import ValidationError

from validation.schema import BufferPhase, EnforcerTier, HTFBias, ValidationContext


class TestBufferPhase:
    """Test BufferPhase enum validation."""

    def test_valid_buffer_phases(self) -> None:
        """All four buffer phases should be valid."""
        assert BufferPhase.STARTUP == "0-5k"
        assert BufferPhase.GROWTH == "5-15k"
        assert BufferPhase.SCALING == "15-40k"
        assert BufferPhase.INSTITUTIONAL == "40k+"

    def test_buffer_phase_string_values(self) -> None:
        """Buffer phases should have correct string representations."""
        assert BufferPhase.STARTUP.value == "0-5k"
        assert BufferPhase.GROWTH.value == "5-15k"
        assert BufferPhase.SCALING.value == "15-40k"
        assert BufferPhase.INSTITUTIONAL.value == "40k+"

    def test_invalid_buffer_phase_rejected(self) -> None:
        """Invalid buffer phase values should be rejected."""
        with pytest.raises(ValueError, match="is not a valid BufferPhase"):
            BufferPhase("invalid")

    def test_buffer_phase_case_sensitive(self) -> None:
        """Buffer phase values are case-sensitive."""
        with pytest.raises(ValueError):
            BufferPhase("0-5K")  # uppercase K


class TestEnforcerTier:
    """Test EnforcerTier enum validation."""

    def test_valid_enforcer_tiers(self) -> None:
        """All four enforcer tiers should be valid."""
        assert EnforcerTier.CONSERVATIVE == "Conservative"
        assert EnforcerTier.EARLY_MILD == "EarlyMild"
        assert EnforcerTier.MILD == "Mild"
        assert EnforcerTier.OFFENSIVE == "Offensive"

    def test_enforcer_tier_string_values(self) -> None:
        """Enforcer tiers should have correct string representations."""
        assert EnforcerTier.CONSERVATIVE.value == "Conservative"
        assert EnforcerTier.EARLY_MILD.value == "EarlyMild"
        assert EnforcerTier.MILD.value == "Mild"
        assert EnforcerTier.OFFENSIVE.value == "Offensive"

    def test_invalid_enforcer_tier_rejected(self) -> None:
        """Invalid enforcer tier values should be rejected."""
        with pytest.raises(ValueError, match="is not a valid EnforcerTier"):
            EnforcerTier("invalid")

    def test_enforcer_tier_case_sensitive(self) -> None:
        """Enforcer tier values are case-sensitive."""
        with pytest.raises(ValueError):
            EnforcerTier("conservative")  # lowercase


class TestHTFBias:
    """Test HTFBias enum validation."""

    def test_valid_htf_bias_values(self) -> None:
        """All three HTF bias values should be valid."""
        assert HTFBias.BULLISH == "bullish"
        assert HTFBias.BEARISH == "bearish"
        assert HTFBias.NEUTRAL == "neutral"

    def test_htf_bias_string_values(self) -> None:
        """HTF bias should have correct string representations."""
        assert HTFBias.BULLISH.value == "bullish"
        assert HTFBias.BEARISH.value == "bearish"
        assert HTFBias.NEUTRAL.value == "neutral"

    def test_invalid_htf_bias_rejected(self) -> None:
        """Invalid HTF bias values should be rejected."""
        with pytest.raises(ValueError, match="is not a valid HTFBias"):
            HTFBias("invalid")

    def test_htf_bias_case_sensitive(self) -> None:
        """HTF bias values are case-sensitive."""
        with pytest.raises(ValueError):
            HTFBias("BULLISH")  # uppercase


class TestValidationContext:
    """Test ValidationContext model validation and behavior."""

    def test_valid_context_creation(self) -> None:
        """Valid context with all required fields should be accepted."""
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

        assert context.session_ok is True
        assert context.tier_active == EnforcerTier.CONSERVATIVE
        assert context.htf_bias == HTFBias.BULLISH
        assert context.dxy_trending_clean is True
        assert context.fatigue_flag is False
        assert context.risk_allowed is True
        assert context.news_ok is True
        assert context.ceo_directive_active is False
        assert context.buffer_phase == BufferPhase.STARTUP

    def test_early_mild_requires_active_ceo_directive(self) -> None:
        """EarlyMild tier must have active CEO directive."""
        with pytest.raises(ValidationError) as exc_info:
            ValidationContext(
                session_ok=True,
                tier_active=EnforcerTier.EARLY_MILD,
                htf_bias=HTFBias.BULLISH,
                dxy_trending_clean=True,
                fatigue_flag=False,
                risk_allowed=True,
                news_ok=True,
                ceo_directive_active=False,  # This should fail
                buffer_phase=BufferPhase.STARTUP,
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "EarlyMild tier requires active CEO directive" in str(errors[0]["msg"])

    def test_early_mild_with_active_directive_succeeds(self) -> None:
        """EarlyMild tier with active CEO directive should succeed."""
        context = ValidationContext(
            session_ok=True,
            tier_active=EnforcerTier.EARLY_MILD,
            htf_bias=HTFBias.BULLISH,
            dxy_trending_clean=True,
            fatigue_flag=False,
            risk_allowed=True,
            news_ok=True,
            ceo_directive_active=True,  # This is required
            buffer_phase=BufferPhase.STARTUP,
        )

        assert context.tier_active == EnforcerTier.EARLY_MILD
        assert context.ceo_directive_active is True

    def test_other_tiers_do_not_require_ceo_directive(self) -> None:
        """Conservative, Mild, and Offensive can run without CEO directive."""
        for tier in [
            EnforcerTier.CONSERVATIVE,
            EnforcerTier.MILD,
            EnforcerTier.OFFENSIVE,
        ]:
            context = ValidationContext(
                session_ok=True,
                tier_active=tier,
                htf_bias=HTFBias.BULLISH,
                dxy_trending_clean=True,
                fatigue_flag=False,
                risk_allowed=True,
                news_ok=True,
                ceo_directive_active=False,
                buffer_phase=BufferPhase.STARTUP,
            )
            assert context.tier_active == tier

    def test_missing_required_field_rejected(self) -> None:
        """Missing required fields should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ValidationContext(
                session_ok=True,
                tier_active=EnforcerTier.CONSERVATIVE,
                htf_bias=HTFBias.BULLISH,
                dxy_trending_clean=True,
                fatigue_flag=False,
                risk_allowed=True,
                news_ok=True,
                ceo_directive_active=False,
                # buffer_phase is missing
            )

        errors = exc_info.value.errors()
        assert any(error["type"] == "missing" for error in errors)

    def test_invalid_field_type_rejected(self) -> None:
        """Invalid field types should raise ValidationError."""
        with pytest.raises(ValidationError):
            ValidationContext(
                session_ok="yes",  # Should be bool
                tier_active=EnforcerTier.CONSERVATIVE,
                htf_bias=HTFBias.BULLISH,
                dxy_trending_clean=True,
                fatigue_flag=False,
                risk_allowed=True,
                news_ok=True,
                ceo_directive_active=False,
                buffer_phase=BufferPhase.STARTUP,
            )

    def test_invalid_enum_value_rejected(self) -> None:
        """Invalid enum values should raise ValidationError."""
        with pytest.raises(ValidationError):
            ValidationContext(
                session_ok=True,
                tier_active="InvalidTier",  # Invalid enum value
                htf_bias=HTFBias.BULLISH,
                dxy_trending_clean=True,
                fatigue_flag=False,
                risk_allowed=True,
                news_ok=True,
                ceo_directive_active=False,
                buffer_phase=BufferPhase.STARTUP,
            )

    def test_model_dict_serialization(self) -> None:
        """ValidationContext should serialize to dict correctly."""
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

        data = context.model_dump()

        assert data["session_ok"] is True
        assert data["tier_active"] == "Conservative"
        assert data["htf_bias"] == "bullish"
        assert data["dxy_trending_clean"] is True
        assert data["fatigue_flag"] is False
        assert data["risk_allowed"] is True
        assert data["news_ok"] is True
        assert data["ceo_directive_active"] is False
        assert data["buffer_phase"] == "0-5k"

    def test_model_dict_deserialization(self) -> None:
        """ValidationContext should deserialize from dict correctly."""
        data = {
            "session_ok": True,
            "tier_active": EnforcerTier.CONSERVATIVE,
            "htf_bias": HTFBias.BULLISH,
            "dxy_trending_clean": True,
            "fatigue_flag": False,
            "risk_allowed": True,
            "news_ok": True,
            "ceo_directive_active": False,
            "buffer_phase": BufferPhase.STARTUP,
        }

        context = ValidationContext(**data)

        assert context.session_ok is True
        assert context.tier_active == EnforcerTier.CONSERVATIVE
        assert context.htf_bias == HTFBias.BULLISH
        assert context.buffer_phase == BufferPhase.STARTUP

    def test_blocking_flags_combinations(self) -> None:
        """Test various combinations of blocking flags."""
        # All blocking flags True (worst case)
        context = ValidationContext(
            session_ok=False,
            tier_active=EnforcerTier.CONSERVATIVE,
            htf_bias=HTFBias.NEUTRAL,
            dxy_trending_clean=False,
            fatigue_flag=True,
            risk_allowed=False,
            news_ok=False,
            ceo_directive_active=False,
            buffer_phase=BufferPhase.STARTUP,
        )

        assert context.session_ok is False
        assert context.fatigue_flag is True
        assert context.risk_allowed is False
        assert context.news_ok is False

    def test_all_buffer_phases_accepted(self) -> None:
        """All buffer phases should be valid in ValidationContext."""
        for phase in BufferPhase:
            context = ValidationContext(
                session_ok=True,
                tier_active=EnforcerTier.CONSERVATIVE,
                htf_bias=HTFBias.BULLISH,
                dxy_trending_clean=True,
                fatigue_flag=False,
                risk_allowed=True,
                news_ok=True,
                ceo_directive_active=False,
                buffer_phase=phase,
            )
            assert context.buffer_phase == phase

    def test_all_htf_bias_values_accepted(self) -> None:
        """All HTF bias values should be valid in ValidationContext."""
        for bias in HTFBias:
            context = ValidationContext(
                session_ok=True,
                tier_active=EnforcerTier.CONSERVATIVE,
                htf_bias=bias,
                dxy_trending_clean=True,
                fatigue_flag=False,
                risk_allowed=True,
                news_ok=True,
                ceo_directive_active=False,
                buffer_phase=BufferPhase.STARTUP,
            )
            assert context.htf_bias == bias

    def test_model_json_serialization(self) -> None:
        """ValidationContext should serialize to JSON correctly."""
        context = ValidationContext(
            session_ok=True,
            tier_active=EnforcerTier.EARLY_MILD,
            htf_bias=HTFBias.BEARISH,
            dxy_trending_clean=True,
            fatigue_flag=False,
            risk_allowed=True,
            news_ok=True,
            ceo_directive_active=True,
            buffer_phase=BufferPhase.GROWTH,
        )

        json_str = context.model_dump_json()

        assert "session_ok" in json_str
        assert "EarlyMild" in json_str
        assert "bearish" in json_str
        assert "5-15k" in json_str

    def test_none_values_rejected(self) -> None:
        """None values should be rejected for required fields."""
        with pytest.raises(ValidationError):
            ValidationContext(
                session_ok=None,  # Should be bool
                tier_active=EnforcerTier.CONSERVATIVE,
                htf_bias=HTFBias.BULLISH,
                dxy_trending_clean=True,
                fatigue_flag=False,
                risk_allowed=True,
                news_ok=True,
                ceo_directive_active=False,
                buffer_phase=BufferPhase.STARTUP,
            )
