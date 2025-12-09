"""Unit tests for ValidationEngine.

Tests cover:
- ValidationResult dataclass structure
- ValidationEngine initialization
- All SOP validation rules (20+ cases)
- HTF bias alignment checks
- Error message formatting
- Logging output
"""

import logging
from unittest.mock import patch

import pytest
from validation import (
    BufferPhase,
    EnforcerTier,
    HTFBias,
    TradeDirection,
    ValidationContext,
    ValidationEngine,
    ValidationResult,
)


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_creation(self) -> None:
        """ValidationResult should be created with required fields."""
        result = ValidationResult(valid=True, errors=[], enforced_tier="Conservative")

        assert result.valid is True
        assert result.errors == []
        assert result.enforced_tier == "Conservative"

    def test_validation_result_with_errors(self) -> None:
        """ValidationResult should store multiple error messages."""
        errors = ["Error 1", "Error 2", "Error 3"]
        result = ValidationResult(valid=False, errors=errors, enforced_tier="EarlyMild")

        assert result.valid is False
        assert len(result.errors) == 3
        assert result.errors == errors
        assert result.enforced_tier == "EarlyMild"

    def test_validation_result_immutable(self) -> None:
        """ValidationResult should be immutable (frozen dataclass)."""
        result = ValidationResult(valid=True, errors=[], enforced_tier="Mild")

        with pytest.raises(AttributeError):
            result.valid = False  # type: ignore


class TestTradeDirection:
    """Test TradeDirection enum."""

    def test_trade_direction_values(self) -> None:
        """TradeDirection should have LONG and SHORT values."""
        assert TradeDirection.LONG == "long"
        assert TradeDirection.SHORT == "short"

    def test_invalid_trade_direction_rejected(self) -> None:
        """Invalid trade direction values should be rejected."""
        with pytest.raises(ValueError):
            TradeDirection("invalid")


class TestValidationEngine:
    """Test ValidationEngine validation logic."""

    def _create_valid_context(self) -> ValidationContext:
        """Helper to create a valid ValidationContext."""
        return ValidationContext(
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

    def test_engine_initialization(self) -> None:
        """ValidationEngine should initialize without errors."""
        engine = ValidationEngine()
        assert engine is not None

    def test_valid_setup_passes(self) -> None:
        """Valid setup with all conditions met should pass validation."""
        engine = ValidationEngine()
        context = self._create_valid_context()

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is True
        assert result.errors == []
        assert result.enforced_tier == "Conservative"

    def test_session_not_ok_fails(self) -> None:
        """Validation should fail if session_ok is False."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(**{**context.model_dump(), "session_ok": False})

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is False
        assert len(result.errors) >= 1
        assert any("session not active" in err.lower() for err in result.errors)
        assert any("outside permitted hours" in err.lower() for err in result.errors)

    def test_fatigue_flag_set_fails(self) -> None:
        """Validation should fail if fatigue_flag is True."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(**{**context.model_dump(), "fatigue_flag": True})

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is False
        assert any("fatigue flag" in err.lower() for err in result.errors)

    def test_risk_not_allowed_fails(self) -> None:
        """Validation should fail if risk_allowed is False."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(**{**context.model_dump(), "risk_allowed": False})

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is False
        assert any("risk budget" in err.lower() for err in result.errors)
        assert any("daily loss limit" in err.lower() for err in result.errors)

    def test_news_not_ok_fails(self) -> None:
        """Validation should fail if news_ok is False."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(**{**context.model_dump(), "news_ok": False})

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is False
        assert any("news event" in err.lower() for err in result.errors)

    def test_dxy_not_clean_fails(self) -> None:
        """Validation should fail if dxy_trending_clean is False for continuation setups."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(
            **{**context.model_dump(), "dxy_trending_clean": False}
        )

        result = engine.validate(
            context, TradeDirection.LONG, setup_type="VWAP_RECLAIM"
        )

        assert result.valid is False
        assert any("dxy structure" in err.lower() for err in result.errors)
        assert any("continuation setups" in err.lower() for err in result.errors)

    def test_htf_bullish_long_passes(self) -> None:
        """LONG trade with BULLISH HTF bias should pass."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        # HTF is already BULLISH in _create_valid_context

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is True
        assert result.errors == []

    def test_htf_bearish_short_passes(self) -> None:
        """SHORT trade with BEARISH HTF bias should pass."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(
            **{**context.model_dump(), "htf_bias": HTFBias.BEARISH}
        )

        result = engine.validate(context, TradeDirection.SHORT)

        assert result.valid is True
        assert result.errors == []

    def test_htf_bullish_short_fails(self) -> None:
        """SHORT trade with BULLISH HTF bias should fail (counter-trend)."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        # HTF is BULLISH, direction is SHORT

        result = engine.validate(context, TradeDirection.SHORT)

        assert result.valid is False
        assert any("htf bias" in err.lower() for err in result.errors)
        assert any("bullish" in err.lower() for err in result.errors)
        assert any("short" in err.lower() for err in result.errors)

    def test_htf_bearish_long_fails(self) -> None:
        """LONG trade with BEARISH HTF bias should fail (counter-trend)."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(
            **{**context.model_dump(), "htf_bias": HTFBias.BEARISH}
        )

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is False
        assert any("htf bias" in err.lower() for err in result.errors)
        assert any("bearish" in err.lower() for err in result.errors)
        assert any("long" in err.lower() for err in result.errors)

    def test_htf_neutral_allows_both_directions(self) -> None:
        """NEUTRAL HTF bias should allow both LONG and SHORT."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(
            **{**context.model_dump(), "htf_bias": HTFBias.NEUTRAL}
        )

        result_long = engine.validate(context, TradeDirection.LONG)
        result_short = engine.validate(context, TradeDirection.SHORT)

        assert result_long.valid is True
        assert result_short.valid is True

    def test_multiple_violations_accumulate(self) -> None:
        """Multiple validation failures should accumulate all errors."""
        engine = ValidationEngine()
        context = ValidationContext(
            session_ok=False,
            tier_active=EnforcerTier.CONSERVATIVE,
            htf_bias=HTFBias.BULLISH,
            dxy_trending_clean=False,
            fatigue_flag=True,
            risk_allowed=False,
            news_ok=False,
            ceo_directive_active=False,
            buffer_phase=BufferPhase.STARTUP,
        )

        result = engine.validate(
            context, TradeDirection.SHORT, setup_type="VWAP_RECLAIM"
        )

        assert result.valid is False
        # Should have errors for: session, fatigue, risk, news, dxy, htf bias
        assert len(result.errors) >= 6

    def test_enforced_tier_reflects_context_tier(self) -> None:
        """Enforced tier in result should match context tier."""
        engine = ValidationEngine()

        for tier in EnforcerTier:
            if tier == EnforcerTier.EARLY_MILD:
                # EarlyMild requires CEO directive
                context = ValidationContext(
                    session_ok=True,
                    tier_active=tier,
                    htf_bias=HTFBias.BULLISH,
                    dxy_trending_clean=True,
                    fatigue_flag=False,
                    risk_allowed=True,
                    news_ok=True,
                    ceo_directive_active=True,
                    buffer_phase=BufferPhase.STARTUP,
                )
            else:
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

            result = engine.validate(context, TradeDirection.LONG)
            assert result.enforced_tier == tier.value

    def test_all_buffer_phases_accepted(self) -> None:
        """All buffer phases should be valid in validation."""
        engine = ValidationEngine()

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

            result = engine.validate(context, TradeDirection.LONG)
            assert result.valid is True

    @patch("validation.engine.logger")
    def test_logging_on_success(self, mock_logger: logging.Logger) -> None:
        """Successful validation should log info message."""
        engine = ValidationEngine()
        context = self._create_valid_context()

        engine.validate(context, TradeDirection.LONG)

        mock_logger.info.assert_called_once()
        call_args = str(mock_logger.info.call_args)
        assert "validation passed" in call_args.lower()
        assert "conservative" in call_args.lower()

    @patch("validation.engine.logger")
    def test_logging_on_session_failure(self, mock_logger: logging.Logger) -> None:
        """Session failure should log warning with 'Rejected by ValidationEngine'."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(**{**context.model_dump(), "session_ok": False})

        engine.validate(context, TradeDirection.LONG)

        mock_logger.warning.assert_called()
        warnings = [str(call) for call in mock_logger.warning.call_args_list]
        assert any(
            "rejected by validationengine" in w.lower() and "session" in w.lower()
            for w in warnings
        )

    @patch("validation.engine.logger")
    def test_logging_on_fatigue_failure(self, mock_logger: logging.Logger) -> None:
        """Fatigue failure should log warning with specific message."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        context = ValidationContext(**{**context.model_dump(), "fatigue_flag": True})

        engine.validate(context, TradeDirection.LONG)

        warnings = [str(call) for call in mock_logger.warning.call_args_list]
        assert any(
            "rejected by validationengine" in w.lower() and "fatigue" in w.lower()
            for w in warnings
        )

    @patch("validation.engine.logger")
    def test_logging_on_htf_bias_failure(self, mock_logger: logging.Logger) -> None:
        """HTF bias mismatch should log warning with bias and direction."""
        engine = ValidationEngine()
        context = self._create_valid_context()
        # HTF is BULLISH, direction is SHORT

        engine.validate(context, TradeDirection.SHORT)

        warnings = [str(call) for call in mock_logger.warning.call_args_list]
        assert any(
            "rejected by validationengine" in w.lower()
            and "htf bias" in w.lower()
            and "bullish" in w.lower()
            and "short" in w.lower()
            for w in warnings
        )

    def test_error_messages_are_descriptive(self) -> None:
        """Error messages should be clear and actionable."""
        engine = ValidationEngine()
        context = ValidationContext(
            session_ok=False,
            tier_active=EnforcerTier.CONSERVATIVE,
            htf_bias=HTFBias.BEARISH,
            dxy_trending_clean=False,
            fatigue_flag=True,
            risk_allowed=False,
            news_ok=False,
            ceo_directive_active=False,
            buffer_phase=BufferPhase.STARTUP,
        )

        result = engine.validate(context, TradeDirection.LONG)

        # All error messages should have actionable information
        for error in result.errors:
            assert len(error) > 20  # Descriptive messages
            assert error[0].isupper()  # Proper capitalization

    def test_conservative_tier_validation(self) -> None:
        """Conservative tier with valid setup should pass."""
        engine = ValidationEngine()
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

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is True
        assert result.enforced_tier == "Conservative"

    def test_early_mild_tier_validation(self) -> None:
        """EarlyMild tier with CEO directive should pass."""
        engine = ValidationEngine()
        context = ValidationContext(
            session_ok=True,
            tier_active=EnforcerTier.EARLY_MILD,
            htf_bias=HTFBias.BULLISH,
            dxy_trending_clean=True,
            fatigue_flag=False,
            risk_allowed=True,
            news_ok=True,
            ceo_directive_active=True,
            buffer_phase=BufferPhase.STARTUP,
        )

        result = engine.validate(context, TradeDirection.LONG)

        assert result.valid is True
        assert result.enforced_tier == "EarlyMild"

    def test_mild_tier_validation(self) -> None:
        """Mild tier with valid setup should pass."""
        engine = ValidationEngine()
        context = ValidationContext(
            session_ok=True,
            tier_active=EnforcerTier.MILD,
            htf_bias=HTFBias.BEARISH,
            dxy_trending_clean=True,
            fatigue_flag=False,
            risk_allowed=True,
            news_ok=True,
            ceo_directive_active=False,
            buffer_phase=BufferPhase.GROWTH,
        )

        result = engine.validate(context, TradeDirection.SHORT)

        assert result.valid is True
        assert result.enforced_tier == "Mild"

    def test_offensive_tier_validation(self) -> None:
        """Offensive tier with valid setup should pass."""
        engine = ValidationEngine()
        context = ValidationContext(
            session_ok=True,
            tier_active=EnforcerTier.OFFENSIVE,
            htf_bias=HTFBias.NEUTRAL,
            dxy_trending_clean=True,
            fatigue_flag=False,
            risk_allowed=True,
            news_ok=True,
            ceo_directive_active=False,
            buffer_phase=BufferPhase.INSTITUTIONAL,
        )

        result = engine.validate(context, TradeDirection.SHORT)

        assert result.valid is True
        assert result.enforced_tier == "Offensive"
