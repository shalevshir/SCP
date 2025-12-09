"""Validation engine for SCP trading bot.

This module implements the ValidationEngine that evaluates whether
trade signals satisfy SOP requirements, CEO directives, and risk
management rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from common.logger import get_logger

from validation.schema import HTFBias, ValidationContext

if TYPE_CHECKING:
    from validation.guardrails import GuardrailResult

logger = get_logger(__name__)


class TradeDirection(str, Enum):
    """Trade direction for validation against HTF bias."""

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class ValidationResult:
    """Result of validation engine evaluation.

    Attributes:
        valid: Whether the validation passed (True) or failed (False)
        errors: List of validation error messages (empty if valid)
        enforced_tier: The tier that was enforced during validation

    Example:
        >>> result = ValidationResult(
        ...     valid=False,
        ...     errors=["Fatigue flag is set - trading blocked"],
        ...     enforced_tier="Conservative"
        ... )
    """

    valid: bool
    errors: list[str]
    enforced_tier: str


class ValidationEngine:
    """Engine for validating trade setups against SOP rules.

    The ValidationEngine evaluates whether a trade signal satisfies:
    - Session time requirements (London 10:00-13:00)
    - CEO directive alignment
    - HTF bias alignment with trade direction
    - DXY structure requirements
    - Fatigue and behavioral guardrails
    - Risk budget availability
    - News event restrictions

    Per SOP, validation failures result in trade rejection regardless
    of signal scoring.
    """

    def validate(
        self,
        context: ValidationContext,
        direction: TradeDirection,
        guardrail_result: GuardrailResult | None = None,
        setup_type: str | None = None,
    ) -> ValidationResult:
        """Validate a trade setup against SOP requirements.

        Args:
            context: ValidationContext containing market state and constraints
            direction: Intended trade direction (long/short)
            guardrail_result: Optional behavior guardrail evaluation result
            setup_type: Optional setup type to apply setup-specific validation rules

        Returns:
            ValidationResult indicating pass/fail with error details

        Example:
            >>> engine = ValidationEngine()
            >>> context = ValidationContext(...)
            >>> result = engine.validate(context, TradeDirection.LONG, setup_type="VWAP_RECLAIM")
            >>> if not result.valid:
            ...     print(f"Rejected: {result.errors}")
        """
        errors: list[str] = []

        # Behavior guardrails check (if provided)
        if guardrail_result and not guardrail_result.allowed:
            for reason in guardrail_result.reasons:
                errors.append(f"Behavior guardrail: {reason}")
            logger.warning(
                "Rejected by ValidationEngine: behavior guardrails blocked trade"
            )

        # Session time validation
        if not context.session_ok:
            errors.append(
                "Trading session not active - outside permitted hours "
                "(default: London 10:00-13:00)"
            )
            logger.warning("Rejected by ValidationEngine: session not active")

        # Fatigue flag check
        if context.fatigue_flag:
            errors.append("Fatigue flag is set - trading blocked for safety")
            logger.warning("Rejected by ValidationEngine: fatigue flag set")

        # Risk budget check
        if not context.risk_allowed:
            errors.append(
                "Risk budget exhausted - no new positions allowed "
                "(check daily loss limit)"
            )
            logger.warning("Rejected by ValidationEngine: risk not allowed")

        # News event check
        if not context.news_ok:
            errors.append("High-impact news event active - trading blocked per SOP")
            logger.warning("Rejected by ValidationEngine: news event blocking")

        # HTF bias alignment check
        htf_direction_mismatch = self._check_htf_bias_alignment(
            context.htf_bias, direction
        )
        if htf_direction_mismatch:
            errors.append(htf_direction_mismatch)
            logger.warning(
                f"Rejected by ValidationEngine: HTF bias mismatch "
                f"(bias={context.htf_bias.value}, direction={direction.value})"
            )

        # DXY structure check for continuation setups only
        # VWAP_FADE is allowed without DXY per SOP (with warning handled in validate_signal_with_sop)
        continuation_setups = ("VWAP_RECLAIM", "DXY_CONTINUATION")
        if setup_type in continuation_setups and not context.dxy_trending_clean:
            errors.append(
                "DXY structure not clean - continuation setups require "
                "clear DXY trend alignment"
            )
            logger.warning("Rejected by ValidationEngine: DXY structure unclear")

        # Log successful validation
        if not errors:
            logger.info(
                f"Validation passed: tier={context.tier_active.value}, "
                f"direction={direction.value}, "
                f"buffer_phase={context.buffer_phase.value}"
            )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            enforced_tier=context.tier_active.value,
        )

    def _check_htf_bias_alignment(
        self, htf_bias: HTFBias, direction: TradeDirection
    ) -> str | None:
        """Check if trade direction aligns with HTF bias.

        Args:
            htf_bias: Higher timeframe bias
            direction: Intended trade direction

        Returns:
            Error message if misaligned, None if aligned or neutral
        """
        # Neutral bias allows both directions
        if htf_bias == HTFBias.NEUTRAL:
            return None

        # Check for directional conflicts
        if htf_bias == HTFBias.BULLISH and direction == TradeDirection.SHORT:
            return (
                "HTF bias is BULLISH but trade direction is SHORT - "
                "counter-trend trades require explicit confirmation"
            )

        if htf_bias == HTFBias.BEARISH and direction == TradeDirection.LONG:
            return (
                "HTF bias is BEARISH but trade direction is LONG - "
                "counter-trend trades require explicit confirmation"
            )

        return None
