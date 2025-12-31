"""HTF Bias validation and scoring adjustments.

This module provides validation and score adjustment logic for integrating
HTF bias into signal scoring. These functions are used by the Bot Core service
to validate and adjust signals based on higher-timeframe market context.
"""

from __future__ import annotations

from scp_shared.common.logger import get_logger
from scp_shared.rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


def validate_signal_with_htf(
    signal_direction: str,
    htf_bias: HTFBias | None,
) -> tuple[bool, str]:
    """Validate trading signal against HTF bias.

    Args:
        signal_direction: Signal direction ("long", "short")
        htf_bias: HTF bias object (None if not available)

    Returns:
        Tuple of (is_valid, rejection_reason)

    Logic:
        - Reject signals opposing strong HTF bias
        - Allow signals aligned with HTF bias
        - Cautious on neutral HTF bias
    """
    # Handle None HTF bias (treat as neutral)
    if htf_bias is None:
        logger.debug("HTF bias is None, allowing signal with caution")
        return True, ""

    # Rule 1: Reject if conflict detected
    if htf_bias.conflict_detected:
        reason = f"HTF conflict detected: {htf_bias.conflict_reason}"
        logger.info(f"Signal rejected - {reason}")
        return False, reason

    # Rule 2: DXY chop rejection removed - now handled per-setup in validation layer
    # (DXY_CONTINUATION still blocked by dxy_chop_5m in validation.py)

    # Rule 3: Reject signals opposing strong HTF bias (high confidence)
    if htf_bias.confidence == "high":
        # Check if signal direction opposes HTF direction
        if signal_direction == "long" and htf_bias.direction == "short":
            reason = (
                f"Signal direction (long) opposes strong HTF bias "
                f"(bearish, score={htf_bias.score:.1f})"
            )
            logger.info(f"Signal rejected - {reason}")
            return False, reason
        elif signal_direction == "short" and htf_bias.direction == "long":
            reason = (
                f"Signal direction (short) opposes strong HTF bias "
                f"(bullish, score={htf_bias.score:.1f})"
            )
            logger.info(f"Signal rejected - {reason}")
            return False, reason

    # Rule 4: Warn on neutral HTF bias but allow signal
    if htf_bias.bias == "neutral":
        reason = f"HTF bias is neutral (score={htf_bias.score:.1f})"
        logger.debug(f"Signal allowed with caution - {reason}")
        return True, ""  # Allow but flag for lower confidence

    # Rule 5: Allow signals aligned with HTF
    if signal_direction == htf_bias.direction:
        logger.debug(
            f"Signal validated - direction ({signal_direction}) aligns with HTF "
            f"({htf_bias.direction}, {htf_bias.confidence} confidence)"
        )
        return True, ""

    # Default: Allow if no strong rejection criteria
    return True, ""


def adjust_score_with_htf(
    base_score: float,
    htf_bias: HTFBias | None,
    signal_direction: str,
    context: dict | None = None,
) -> tuple[float, dict]:
    """Adjust signal score based on HTF bias alignment.

    Args:
        base_score: Base signal score before HTF adjustment
        htf_bias: HTF bias object (None if not available)
        signal_direction: Signal direction ("long", "short")
        context: Optional context dict with enforcer_tier for tier-aware adjustments

    Returns:
        Tuple of (adjusted_score, adjustment_details)

    Logic:
        - Strong alignment: Boost score
        - Weak alignment: Minimal adjustment (tier-aware for neutral)
        - Misalignment: Reduce score or reject
    """
    adjusted_score = base_score
    adjustments = {}
    
    # Default context if not provided
    if context is None:
        context = {}

    # Handle None HTF bias (no adjustments)
    if htf_bias is None:
        logger.debug("HTF bias is None, no score adjustments applied")
        return adjusted_score, adjustments

    # DEBUG: Log HTF bias fields for troubleshooting
    logger.info(
        f"HTF bias fields for scoring: seasonality_adj={htf_bias.seasonality_adjustment}, "
        f"vwap_confirmed={htf_bias.vwap_trend_confirmed}, "
        f"dxy_aligned={htf_bias.dxy_alignment}, "
        f"confidence={htf_bias.confidence}"
    )

    # 1. Apply seasonality adjustment (already calculated in HTFBias)
    if htf_bias.seasonality_adjustment != 0.0:
        adjusted_score += htf_bias.seasonality_adjustment
        adjustments["seasonality"] = htf_bias.seasonality_adjustment
        logger.debug(
            f"Applied seasonality adjustment: {htf_bias.seasonality_adjustment:+.2f} "
            f"(period={htf_bias.seasonality_period})"
        )

    # Note: FVG alignment is now handled in calculate_factor_scores via
    # calculate_fvg_alignment and is already included in base_score.
    # Do not add it again here to avoid double-counting.

    # 2. Boost for strong HTF alignment (high confidence + matching direction)
    # Only boost when both have clear directional alignment (not neutral)
    if (
        htf_bias.confidence == "high"
        and signal_direction == htf_bias.direction
        and signal_direction != "neutral"
        and htf_bias.direction != "neutral"
    ):
        boost = 1.0  # Strong alignment bonus
        adjusted_score += boost
        adjustments["htf_strong_alignment"] = boost
        logger.debug(
            f"Applied strong HTF alignment boost: +{boost:.2f} "
            f"(HTF {htf_bias.confidence} confidence, score={htf_bias.score:.1f})"
        )

    # 4. Moderate boost for medium confidence alignment
    # Only boost when both have clear directional alignment (not neutral)
    elif (
        htf_bias.confidence == "medium"
        and signal_direction == htf_bias.direction
        and signal_direction != "neutral"
        and htf_bias.direction != "neutral"
    ):
        boost = 0.5  # Medium alignment bonus
        adjusted_score += boost
        adjustments["htf_medium_alignment"] = boost
        logger.debug(
            f"Applied medium HTF alignment boost: +{boost:.2f} "
            f"(HTF {htf_bias.confidence} confidence, score={htf_bias.score:.1f})"
        )

    # 5. Penalty for neutral HTF or low confidence (tier-aware for neutral)
    if htf_bias.bias == "neutral" or htf_bias.confidence == "low":
        # Tier-aware penalty for neutral HTF
        enforcer_tier = context.get("enforcer_tier", "Conservative")
        
        if htf_bias.bias == "neutral" and enforcer_tier == "EarlyMild":
            # Softer penalty for EarlyMild tier
            penalty = -0.25
            logger.debug(
                f"Applied soft neutral HTF penalty for EarlyMild: {penalty:.2f}"
            )
        else:
            # Standard penalty for other tiers
            penalty = -0.5
            logger.debug(
                f"Applied standard weak HTF bias penalty: {penalty:.2f} "
                f"(bias={htf_bias.bias}, confidence={htf_bias.confidence}, "
                f"tier={enforcer_tier})"
            )
        
        adjusted_score += penalty
        adjustments["htf_weak_bias"] = penalty

    # 6. Bonus for VWAP trend confirmation
    # Only boost when both have clear directional alignment (not neutral)
    if (
        htf_bias.vwap_trend_confirmed
        and signal_direction == htf_bias.direction
        and signal_direction != "neutral"
        and htf_bias.direction != "neutral"
    ):
        bonus = 0.5
        adjusted_score += bonus
        adjustments["vwap_confirmation"] = bonus
        logger.debug(f"Applied VWAP trend confirmation bonus: +{bonus:.2f}")

    # 7. Bonus for DXY alignment
    # Only boost when both have clear directional alignment (not neutral)
    if (
        htf_bias.dxy_alignment
        and signal_direction == htf_bias.direction
        and signal_direction != "neutral"
        and htf_bias.direction != "neutral"
    ):
        bonus = 0.5
        adjusted_score += bonus
        adjustments["dxy_alignment"] = bonus
        logger.debug(f"Applied DXY alignment bonus: +{bonus:.2f}")

    # Note: BOS (Break of Structure) bonus is now handled in
    # calculate_structure_alignment via the factor scoring system.
    # Do not add it again here to avoid double-counting.

    # 8. Penalty for CHoCH (indicates potential reversal)
    if htf_bias.choch_detected:
        penalty = -0.3
        adjusted_score += penalty
        adjustments["choch_detected"] = penalty
        logger.debug(f"Applied CHoCH detection penalty: {penalty:.2f}")

    # Cap final score at 10.0
    adjusted_score = min(adjusted_score, 10.0)


    # Log final adjustment
    total_adjustment = adjusted_score - base_score
    logger.info(
        f"HTF score adjustment: {base_score:.2f} → {adjusted_score:.2f} "
        f"(delta: {total_adjustment:+.2f})"
    )

    return adjusted_score, adjustments

