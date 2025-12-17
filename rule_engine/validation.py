"""RuleEngine validation layer for SOP compliance.

This module validates signals against SOP requirements including session checks,
tier restrictions, DXY alignment, and HTF bias validation.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pandas as pd
from common.logger import get_logger
from validation.context_builder import (
    ValidationContextBuilder,
    check_dxy_handling_for_setup,
)
from validation.engine import TradeDirection, ValidationEngine

from rule_engine.config_loader import load_scoring_config
from rule_engine.htf.types import ChopSeverity, HTFBias
from rule_engine.signal import Signal

if TYPE_CHECKING:
    from validation.guardrails import GuardrailResult
    from validation.session_validator import SessionConstraints

logger = get_logger(__name__)


def _evaluate_chop_for_setup(
    setup_type: str, htf_bias: HTFBias
) -> tuple[bool, str | None]:
    """Evaluate chop constraints per setup type (setup-aware filtering).
    
    This function implements the core principle: "Chop is information, not prohibition."
    Different setups have different chop tolerance based on their nature.
    
    Args:
        setup_type: Setup type name ("VWAP_FADE", "VWAP_RECLAIM", "DXY_CONTINUATION")
        htf_bias: HTFBias object containing chop severity classification
    
    Returns:
        Tuple of (is_allowed, rejection_reason):
        - is_allowed: True if setup is allowed given chop conditions
        - rejection_reason: Description of rejection, or None if allowed
    
    Logic:
        VWAP_FADE (counter-trend, benefits from chop):
        - SOFT_CHOP: Allowed (preferred environment)
        - HARD_CHOP: Allowed with confirmation (liquidity sweep required)
        
        VWAP_RECLAIM (structural, tolerates some chop):
        - SOFT_CHOP: Allowed (score penalty applied in scoring.py)
        - HARD_CHOP: Hard-blocked (too chaotic for structural setup)
        
        DXY_CONTINUATION (momentum, requires clean trends):
        - ANY chop: Hard-blocked (continuation needs directional clarity)
    
    Example:
        >>> is_ok, reason = _evaluate_chop_for_setup("VWAP_FADE", htf_bias)
        >>> if not is_ok:
        ...     logger.info(f"Setup blocked: {reason}")
    """
    severity = htf_bias.chop_severity
    
    if setup_type == "VWAP_FADE":
        # VWAP_FADE allowed in SOFT_CHOP (preferred), requires confirmation in HARD_CHOP
        if severity == ChopSeverity.HARD_CHOP:
            # Require liquidity sweep for HARD_CHOP confirmation
            if not htf_bias.liquidity_sweep_detected:
                return (
                    False,
                    f"VWAP_FADE blocked: HARD_CHOP requires sweep confirmation "
                    f"(consecutive={htf_bias.chop_consecutive_count})",
                )
        # SOFT_CHOP or NONE always allowed for fades
        return True, None
    
    elif setup_type == "DXY_CONTINUATION":
        # DXY_CONTINUATION hard-blocked on any chop (momentum setup)
        if severity != ChopSeverity.NONE:
            return (
                False,
                f"DXY_CONTINUATION blocked: {severity.value} chop detected "
                f"(consecutive={htf_bias.chop_consecutive_count})",
            )
        return True, None
    
    elif setup_type == "VWAP_RECLAIM":
        # VWAP_RECLAIM allowed in SOFT_CHOP (with score penalty), blocked in HARD_CHOP
        if severity == ChopSeverity.HARD_CHOP:
            return (
                False,
                f"VWAP_RECLAIM blocked: HARD_CHOP detected "
                f"(consecutive={htf_bias.chop_consecutive_count})",
            )
        # SOFT_CHOP allowed (score penalty applied in scoring.py)
        return True, None
    
    # Unknown setup type - allow by default (conservative)
    return True, None


def validate_signal(signal: Signal, htf_bias: HTFBias, context: dict) -> Signal:
    """Validate signal against SOP compliance rules.

    Checks:
        - session_ok: Whether current trading session is valid
        - tier_ok: Whether setup type is allowed for current enforcer tier
        - dxy_alignment_ok: Whether DXY alignment is strong
        - htf_bias_ok: Whether signal direction matches HTF direction
        - htf_valid: Whether HTF validation passed (no conflicts/chop)

    If any validation fails, confidence is downgraded to "Reject".

    Args:
        signal: Signal object to validate
        htf_bias: HTFBias object containing HTF analysis
        context: Dict containing:
            - session_ok: Boolean indicating if session is valid
            - enforcer_tier: Current enforcer tier name

    Returns:
        New Signal object with updated validation_flags and confidence

    Example:
        >>> signal = Signal(...)  # A+ signal
        >>> htf_bias = HTFBias(...)
        >>> context = {"session_ok": False, ...}
        >>> validated = validate_signal(signal, htf_bias, context)
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

    # Check DXY alignment from HTFBias
    dxy_alignment_ok = htf_bias.dxy_alignment
    validation_flags["dxy_alignment_ok"] = dxy_alignment_ok

    # Setup-aware chop validation (replaces binary chop blocking)
    chop_ok, chop_rejection_reason = _evaluate_chop_for_setup(
        signal.setup_type, htf_bias
    )
    validation_flags["chop_severity"] = htf_bias.chop_severity.value
    
    # Also check DXY 5M chop for DXY_CONTINUATION (separate from gold chop)
    if signal.setup_type == "DXY_CONTINUATION" and htf_bias.dxy_chop_5m:
        chop_ok = False
        chop_rejection_reason = (
            f"DXY_CONTINUATION blocked: DXY 5M chop detected "
            f"(dxy_chop_5m={htf_bias.dxy_chop_5m})"
        )
        logger.info(chop_rejection_reason)
    
    # Update chop_ok flag AFTER all chop checks
    validation_flags["chop_ok"] = chop_ok

    # Check HTF bias alignment
    htf_bias_ok = signal.direction == htf_bias.direction
    validation_flags["htf_bias_ok"] = htf_bias_ok

    # Check HTF validity (no conflicts or chop)
    htf_valid = not htf_bias.conflict_detected and not htf_bias.dxy_chop_detected
    validation_flags["htf_valid"] = htf_valid

    # Determine if any validation failed
    any_failed = not all(
        [
            validation_flags["session_ok"],
            validation_flags["tier_ok"],
            validation_flags["htf_bias_ok"],
            validation_flags["htf_valid"],
            validation_flags["chop_ok"],
        ]
    )

    # Downgrade confidence if validation failed
    confidence = signal.confidence
    if any_failed:
        confidence = "Reject"

        # Build rejection reason
        rejection_reasons = []
        if not validation_flags["session_ok"]:
            rejection_reasons.append("Invalid session")
        if not validation_flags["tier_ok"]:
            rejection_reasons.append(f"Setup not allowed for tier {enforcer_tier}")
        if not validation_flags["htf_bias_ok"]:
            rejection_reasons.append(
                f"Signal direction conflicts with HTF {htf_bias.direction}"
            )
        if not validation_flags["htf_valid"]:
            if htf_bias.conflict_detected:
                rejection_reasons.append(f"HTF conflict: {htf_bias.conflict_reason}")
            if htf_bias.dxy_chop_detected:
                rejection_reasons.append("DXY in chop mode")
        if not validation_flags["chop_ok"]:
            # Use the specific rejection reason from setup-aware evaluation
            if chop_rejection_reason:
                rejection_reasons.append(chop_rejection_reason)
            else:
                # Fallback for unexpected cases
                rejection_reasons.append(
                    f"Chop validation failed for {signal.setup_type}"
                )

        logger.info(f"Signal validation failed: {'; '.join(rejection_reasons)}")

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
    session_constraints: SessionConstraints | None = None,
    guardrail_result: GuardrailResult | None = None,
    htf_bias: HTFBias | None = None,
) -> Signal:
    """Validate signal with full SOP integration.

    This is the comprehensive validation function that integrates:
    - ValidationEngine (SOP compliance)
    - SessionValidator (time windows, seasonality)
    - BehaviorGuardrails (loss streaks, fatigue)
    - DXY unavailability handling
    - HTF conflict and DXY chop detection

    Args:
        signal: Signal object to validate
        features: Feature series containing technical indicators
        market_state: Dict with market context (buffer_phase, tier_active, etc.)
        session_constraints: Optional SessionConstraints from SessionValidator.
            If None, creates permissive defaults (validation disabled mode).
        guardrail_result: Optional GuardrailResult from BehaviorGuardrails
        htf_bias: Optional HTFBias object for conflict/chop detection

    Returns:
        Updated Signal with validation results applied

    Example:
        >>> htf_bias = compute_htf_bias(features_1h, features_15m)
        >>> signal = score_signal(features, htf_bias, context)
        >>> validated = validate_signal_with_sop(
        ...     signal, features, market_state, session_constraints, guardrail_result, htf_bias
        ... )
        >>> if validated.confidence == "Reject":
        ...     logger.info(f"Rejected: {validated.rationale}")
    """
    # Create default session constraints if validation disabled
    if session_constraints is None:
        from datetime import time

        from validation.session_validator import SessionConstraints

        logger.debug(
            "No session constraints provided - using permissive defaults "
            "(validation disabled mode)"
        )
        session_constraints = SessionConstraints(
            name="Default",
            window_start=time(0, 0),
            window_end=time(23, 59),
            allowed_tiers=frozenset(["Conservative", "EarlyMild", "Mild", "Offensive"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION", "VWAP_FADE"]),
            min_score=0.0,  # Permissive: allow all scores
            max_losses=999,  # Permissive: no loss limit
            dxy_correlation_max=1.0,  # Permissive: allow any correlation
        )

    # Build session result from constraints
    from validation.session_validator import SessionResult

    session_result = SessionResult(
        session_ok=market_state.get("session_ok", True),
        constraints=session_constraints,
        reason=None,
    )

    # #region agent log
    import json as _json
    _log_path = "/Users/shalev/Code/SCP/.cursor/debug.log"
    _htf_direction = htf_bias.direction if htf_bias else "None"
    _log_data = {"location": "validation.py:validate_signal_with_sop", "message": "HTF bias received", "hypothesisId": "B", "timestamp": int(pd.Timestamp.now().timestamp() * 1000), "sessionId": "debug-session", "data": {"htf_bias_present": htf_bias is not None, "htf_direction": _htf_direction, "signal_direction": signal.direction, "signal_setup_type": signal.setup_type}}
    with open(_log_path, "a") as _f: _f.write(_json.dumps(_log_data) + "\n")
    # #endregion

    # Build ValidationContext
    context_builder = ValidationContextBuilder()
    validation_context = context_builder.build_context(
        features=features,
        market_state=market_state,
        session_result=session_result,
        guardrail_result=guardrail_result,
        htf_bias=htf_bias,  # Pass the HTF calculator's bias to ensure consistency
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
    validation_flags["tier_ok"] = (
        validation_context.tier_active.value in session_constraints.allowed_tiers
    )
    validation_flags["dxy_alignment_ok"] = dxy_allowed
    validation_flags["htf_bias_ok"] = (
        signal.htf_bias == validation_context.htf_bias.value
    )
    validation_flags["score_meets_minimum"] = score_meets_minimum
    validation_flags["setup_allowed_in_season"] = setup_allowed_in_season

    # Check HTF validity (no conflicts or chop) if HTFBias provided
    if htf_bias is not None:
        htf_valid = not htf_bias.conflict_detected and not htf_bias.dxy_chop_detected
        validation_flags["htf_valid"] = htf_valid
    else:
        # If HTFBias not provided, assume valid (for backward compatibility)
        htf_valid = True
        validation_flags["htf_valid"] = True

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

    # Check HTF conflicts and DXY chop
    if htf_bias is not None:
        if htf_bias.conflict_detected:
            rejection_reasons.append(f"HTF conflict: {htf_bias.conflict_reason}")
        if htf_bias.dxy_chop_detected:
            rejection_reasons.append("DXY in chop mode")

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
