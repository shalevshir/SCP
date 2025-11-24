"""RuleEngine integration for HTF Bias.

Handles integration of HTF bias into RuleEngine scoring and validation.

Task: Integrate into RuleEngine scoring
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

from rule_engine.htf.types import HTFBias
from common.logger import get_logger

logger = get_logger(__name__)


def validate_signal_with_htf(
    signal_direction: str,
    htf_bias: HTFBias,
) -> tuple[bool, str]:
    """Validate trading signal against HTF bias.

    Args:
        signal_direction: Signal direction ("long", "short")
        htf_bias: HTF bias object

    Returns:
        Tuple of (is_valid, rejection_reason)

    Logic:
        - Reject signals opposing strong HTF bias
        - Allow signals aligned with HTF bias
        - Cautious on neutral HTF bias

    DoD:
        - RuleEngine rejects signals when HTF invalid
        - RuleEngine boosts signals when HTF strongly aligned
        - End-to-end test passes
    """
    # Rule 1: Reject if conflict detected
    if htf_bias.conflict_detected:
        reason = f"HTF conflict detected: {htf_bias.conflict_reason}"
        logger.info(f"Signal rejected - {reason}")
        return False, reason
    
    # Rule 2: Reject if DXY chop detected
    if htf_bias.dxy_chop_detected:
        reason = "DXY in chop mode - no directional bias"
        logger.info(f"Signal rejected - {reason}")
        return False, reason
    
    # Rule 3: Reject signals opposing strong HTF bias (high confidence)
    if htf_bias.confidence == "high":
        # Check if signal direction opposes HTF direction
        if signal_direction == "long" and htf_bias.direction == "short":
            reason = f"Signal direction (long) opposes strong HTF bias (bearish, score={htf_bias.score:.1f})"
            logger.info(f"Signal rejected - {reason}")
            return False, reason
        elif signal_direction == "short" and htf_bias.direction == "long":
            reason = f"Signal direction (short) opposes strong HTF bias (bullish, score={htf_bias.score:.1f})"
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
    htf_bias: HTFBias,
    signal_direction: str,
) -> tuple[float, dict]:
    """Adjust signal score based on HTF bias alignment.

    Args:
        base_score: Base signal score before HTF adjustment
        htf_bias: HTF bias object
        signal_direction: Signal direction ("long", "short")

    Returns:
        Tuple of (adjusted_score, adjustment_details)

    Logic:
        - Strong alignment: Boost score
        - Weak alignment: Minimal adjustment
        - Misalignment: Reduce score or reject

    DoD:
        - RuleEngine rejects signals when HTF invalid
        - RuleEngine boosts signals when HTF strongly aligned
        - End-to-end test passes
    """
    adjusted_score = base_score
    adjustments = {}
    
    # 1. Apply seasonality adjustment (already calculated in HTFBias)
    if htf_bias.seasonality_adjustment != 0.0:
        adjusted_score += htf_bias.seasonality_adjustment
        adjustments["seasonality"] = htf_bias.seasonality_adjustment
        logger.debug(
            f"Applied seasonality adjustment: {htf_bias.seasonality_adjustment:+.2f} "
            f"(period={htf_bias.seasonality_period})"
        )
    
    # 2. Apply FVG alignment score
    if htf_bias.fvg_alignment_score != 0.0:
        adjusted_score += htf_bias.fvg_alignment_score
        adjustments["fvg_alignment"] = htf_bias.fvg_alignment_score
        logger.debug(
            f"Applied FVG alignment: {htf_bias.fvg_alignment_score:+.2f}"
        )
    
    # 3. Boost for strong HTF alignment (high confidence + matching direction)
    # Only boost when both have clear directional alignment (not neutral)
    if (htf_bias.confidence == "high" and 
        signal_direction == htf_bias.direction and
        signal_direction != "neutral" and htf_bias.direction != "neutral"):
        boost = 1.0  # Strong alignment bonus
        adjusted_score += boost
        adjustments["htf_strong_alignment"] = boost
        logger.debug(
            f"Applied strong HTF alignment boost: +{boost:.2f} "
            f"(HTF {htf_bias.confidence} confidence, score={htf_bias.score:.1f})"
        )
    
    # 4. Moderate boost for medium confidence alignment
    # Only boost when both have clear directional alignment (not neutral)
    elif (htf_bias.confidence == "medium" and 
          signal_direction == htf_bias.direction and
          signal_direction != "neutral" and htf_bias.direction != "neutral"):
        boost = 0.5  # Medium alignment bonus
        adjusted_score += boost
        adjustments["htf_medium_alignment"] = boost
        logger.debug(
            f"Applied medium HTF alignment boost: +{boost:.2f} "
            f"(HTF {htf_bias.confidence} confidence, score={htf_bias.score:.1f})"
        )
    
    # 5. Penalty for neutral HTF or low confidence
    if htf_bias.bias == "neutral" or htf_bias.confidence == "low":
        penalty = -0.5
        adjusted_score += penalty
        adjustments["htf_weak_bias"] = penalty
        logger.debug(
            f"Applied weak HTF bias penalty: {penalty:.2f} "
            f"(bias={htf_bias.bias}, confidence={htf_bias.confidence})"
        )
    
    # 6. Bonus for VWAP trend confirmation
    # Only boost when both have clear directional alignment (not neutral)
    if (htf_bias.vwap_trend_confirmed and 
        signal_direction == htf_bias.direction and
        signal_direction != "neutral" and htf_bias.direction != "neutral"):
        bonus = 0.5
        adjusted_score += bonus
        adjustments["vwap_confirmation"] = bonus
        logger.debug(f"Applied VWAP trend confirmation bonus: +{bonus:.2f}")
    
    # 7. Bonus for DXY alignment
    # Only boost when both have clear directional alignment (not neutral)
    if (htf_bias.dxy_alignment and 
        signal_direction == htf_bias.direction and
        signal_direction != "neutral" and htf_bias.direction != "neutral"):
        bonus = 0.5
        adjusted_score += bonus
        adjustments["dxy_alignment"] = bonus
        logger.debug(f"Applied DXY alignment bonus: +{bonus:.2f}")
    
    # 8. Bonus for structure events (BOS indicates continuation)
    # Only boost when both have clear directional alignment (not neutral)
    if (htf_bias.bos_detected and 
        signal_direction == htf_bias.direction and
        signal_direction != "neutral" and htf_bias.direction != "neutral"):
        bonus = 0.3
        adjusted_score += bonus
        adjustments["bos_detected"] = bonus
        logger.debug(f"Applied BOS detection bonus: +{bonus:.2f}")
    
    # 9. Penalty for CHoCH (indicates potential reversal)
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

