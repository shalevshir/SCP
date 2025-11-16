"""RuleEngine validation layer for SOP compliance.

This module validates signals against SOP requirements including session checks,
tier restrictions, DXY alignment, and HTF bias validation.
"""

from dataclasses import replace

from rule_engine.config_loader import load_scoring_config
from rule_engine.signal import Signal


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

