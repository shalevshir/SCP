"""RuleEngine validation layer for SOP compliance.

This module validates signals against SOP requirements including session checks,
tier restrictions, DXY alignment, and HTF bias validation.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pandas as pd

from common.logger import get_logger
from rule_engine.config_loader import load_scoring_config
from rule_engine.signal import Signal
from validation.context_builder import (
    ValidationContextBuilder,
    check_dxy_handling_for_setup,
)
from validation.engine import TradeDirection, ValidationEngine

if TYPE_CHECKING:
    from validation.guardrails import GuardrailResult
    from validation.session_validator import SessionConstraints

logger = get_logger(__name__)


def validate_signal(signal: Signal, context: dict) -> Signal:
    """Validate signal against SOP compliance rules.

    Checks:
        - session_ok: Whether current trading session is valid
        - tier_ok: Whether setup type is allowed for current enforcer tier
        - dxy_alignment_ok: Whether DXY correlation meets threshold (< -0.6)
        - htf_bias_ok: Whether signal direction matches HTF direction

    If any validation fails, confidence is downgraded to "Reject".

    Args:
        signal: Signal object to validate
        context: Dict containing:
            - session_ok: Boolean indicating if session is valid
            - enforcer_tier: Current enforcer tier name
            - htf_direction: HTF direction ("long", "short", "neutral")
            - dxy_corr: Optional DXY correlation value

    Returns:
        New Signal object with updated validation_flags and confidence

    Example:
        >>> signal = Signal(...)  # A+ signal
        >>> context = {"session_ok": False, ...}
        >>> validated = validate_signal(signal, context)
        >>> assert validated.confidence == "Reject"
    """
    # Load scoring config for tier restrictions
    config = load_scoring_config()

    # Initialize validation flags with current values
    validation_flags = dict(signal.validation_flags)

    # Check session validity
    session_ok = context.get("session_ok", True)
    validation_flags["session_ok"] = session_ok

    # Check tier restrictions
    enforcer_tier = context.get("enforcer_tier", signal.enforcer_tier)
    tier_ok = check_tier_allowed(signal.setup_type, enforcer_tier, config)
    validation_flags["tier_ok"] = tier_ok

    # Check DXY alignment
    dxy_corr = context.get("dxy_corr", None)
    if dxy_corr is not None:
        dxy_alignment_ok = dxy_corr < -0.6
    else:
        # Keep existing flag if no new data
        dxy_alignment_ok = validation_flags.get("dxy_alignment_ok", True)
    validation_flags["dxy_alignment_ok"] = dxy_alignment_ok

    # Check HTF bias alignment
    htf_direction = context.get("htf_direction", "neutral")
    htf_bias_ok = signal.direction == htf_direction
    validation_flags["htf_bias_ok"] = htf_bias_ok

    # Determine if any validation failed
    any_failed = not all([
        validation_flags["session_ok"],
        validation_flags["tier_ok"],
        validation_flags["htf_bias_ok"],
    ])

    # Downgrade confidence if validation failed
    confidence = signal.confidence
    if any_failed:
        confidence = "Reject"

    # Create and return new Signal with updated validation
    return replace(
        signal,
        confidence=confidence,
        validation_flags=validation_flags,
    )


def check_tier_allowed(setup_type: str, tier: str, config) -> bool:
    """Check if setup type is allowed for the given enforcer tier.

    Args:
        setup_type: Setup type name (e.g., "VWAP_RECLAIM")
        tier: Enforcer tier name (e.g., "Conservative")
        config: Scoring configuration object

    Returns:
        True if setup is allowed for tier, False otherwise
    """
    # Get tier configuration
    if tier not in config.validation["tiers"]:
        # If tier not found, default to allowing all setups
        return True

    tier_config = config.validation["tiers"][tier]
    allowed_setups = tier_config.get("allowed_setups", [])

    return setup_type in allowed_setups


def validate_signal_with_sop(
    signal: Signal,
    features: pd.Series,
    market_state: dict,
    session_constraints: SessionConstraints,
    guardrail_result: GuardrailResult | None = None,
) -> Signal:
    """Validate signal with full SOP integration.

    This is the comprehensive validation function that integrates:
    - ValidationEngine (SOP compliance)
    - SessionValidator (time windows, seasonality)
    - BehaviorGuardrails (loss streaks, fatigue)
    - DXY unavailability handling

    Args:
        signal: Signal object to validate
        features: Feature series containing technical indicators
        market_state: Dict with market context (buffer_phase, tier_active, etc.)
        session_constraints: SessionConstraints from SessionValidator
        guardrail_result: Optional GuardrailResult from BehaviorGuardrails

    Returns:
        Updated Signal with validation results applied

    Example:
        >>> signal = score_signal(features, context)
        >>> validated = validate_signal_with_sop(
        ...     signal, features, market_state, session_constraints, guardrail_result
        ... )
        >>> if validated.confidence == "Reject":
        ...     logger.info(f"Rejected: {validated.rationale}")
    """
    # Build session result from constraints
    from validation.session_validator import SessionResult

    session_result = SessionResult(
        session_ok=market_state.get("session_ok", True),
        constraints=session_constraints,
        reason=None,
    )

    # Build ValidationContext
    context_builder = ValidationContextBuilder()
    validation_context = context_builder.build_context(
        features=features,
        market_state=market_state,
        session_result=session_result,
        guardrail_result=guardrail_result,
    )

    # Determine trade direction from signal
    direction_map = {
        "long": TradeDirection.LONG,
        "short": TradeDirection.SHORT,
    }
    direction = direction_map.get(signal.direction, TradeDirection.LONG)

    # Check DXY availability for setup type
    dxy_available = features.get("dxy_corr") is not None and not pd.isna(
        features.get("dxy_corr")
    )
    dxy_allowed, dxy_warning = check_dxy_handling_for_setup(
        signal.setup_type, dxy_available
    )

    # Run ValidationEngine
    validation_engine = ValidationEngine()
    validation_result = validation_engine.validate(
        context=validation_context,
        direction=direction,
        guardrail_result=guardrail_result,
        setup_type=signal.setup_type,
    )

    # Check if score meets minimum for season
    score_meets_minimum = signal.score >= session_constraints.min_score
    
    logger.debug(
        f"Score validation: signal.score={signal.score:.2f}, "
        f"min_score={session_constraints.min_score}, "
        f"meets_minimum={score_meets_minimum}"
    )

    # Check if setup is allowed in current season
    setup_allowed_in_season = signal.setup_type in session_constraints.allowed_setups

    # Update validation flags
    validation_flags = dict(signal.validation_flags)
    validation_flags["session_ok"] = validation_context.session_ok
    validation_flags["tier_ok"] = validation_context.tier_active.value in session_constraints.allowed_tiers
    validation_flags["dxy_alignment_ok"] = dxy_allowed
    validation_flags["htf_bias_ok"] = signal.htf_bias == validation_context.htf_bias.value
    validation_flags["score_meets_minimum"] = score_meets_minimum
    validation_flags["setup_allowed_in_season"] = setup_allowed_in_season

    # Determine final confidence
    confidence = signal.confidence

    # Collect all rejection reasons
    rejection_reasons = []

    if not validation_result.valid:
        rejection_reasons.extend(validation_result.errors)

    if not dxy_allowed:
        rejection_reasons.append(dxy_warning or "DXY data unavailable for this setup")

    if not score_meets_minimum:
        rejection_reasons.append(
            f"Score {signal.score:.1f} below seasonal minimum {session_constraints.min_score}"
        )

    if not setup_allowed_in_season:
        rejection_reasons.append(
            f"Setup {signal.setup_type} not allowed in {session_constraints.name} season"
        )

    # Downgrade to Reject if any validations failed
    if rejection_reasons:
        confidence = "Reject"
        logger.warning(
            f"Signal rejected: {'; '.join(rejection_reasons)} | "
            f"setup={signal.setup_type}, score={signal.score:.1f}, "
            f"season={session_constraints.name}"
        )

    # Add rejection reasons to rationale
    enhanced_rationale = signal.rationale
    if rejection_reasons:
        rejection_summary = " | REJECTED: " + "; ".join(rejection_reasons)
        enhanced_rationale += rejection_summary
    elif dxy_warning:
        # Add warning even if allowed
        enhanced_rationale += f" | WARNING: {dxy_warning}"

    # Return updated signal
    return replace(
        signal,
        confidence=confidence,
        validation_flags=validation_flags,
        rationale=enhanced_rationale,
        enforcer_tier=validation_result.enforced_tier,
    )

