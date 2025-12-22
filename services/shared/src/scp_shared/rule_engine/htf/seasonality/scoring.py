"""Seasonality scoring adjustments.

Seasonality affects correlation, score minimums, and trend acceptance.

Task: Integrate seasonality into scoring
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

from scp_shared.common.logger import get_logger

from scp_shared.rule_engine.htf.seasonality.rules import SeasonalityPeriod

logger = get_logger(__name__)


def apply_seasonality_adjustment(
    base_score: float,
    period: SeasonalityPeriod,
    dxy_corr: float | None,
) -> tuple[float, float]:
    """Apply seasonality adjustments to HTF score.

    Args:
        base_score: Base HTF score before adjustments
        period: Current seasonality period
        dxy_corr: DXY correlation value

    Returns:
        Tuple of (adjusted_score, adjustment_amount)

    Logic:
        - September: Trend score threshold = 8.5
        - Nov-Dec: Relax corr threshold to -0.55
        - Other months: Standard thresholds

    DoD:
        - September trend score threshold = 8.5
        - Nov–Dec relax corr threshold to –0.55
        - Full integration verified via unit tests
    """
    from scp_shared.rule_engine.htf.seasonality.rules import get_seasonality_config

    config = get_seasonality_config(period)
    adjustment = 0.0

    # DXY correlation bonus/penalty based on seasonal threshold
    if dxy_corr is not None:
        dxy_threshold = config["dxy_corr_threshold"]
        # Stronger inverse correlation (more negative) exceeds threshold
        if dxy_corr < dxy_threshold:
            # Bonus for exceeding seasonal DXY requirement
            adjustment += 0.5
            logger.debug(
                "DXY correlation bonus: dxy_corr=%.2f < threshold=%.2f | +0.5",
                dxy_corr,
                dxy_threshold,
            )

    # Trend season (November-December) bonus for strong scores
    if period == "november_december" and base_score >= 8.0:
        adjustment += 0.3
        logger.debug("Trend season bonus applied: +0.3")

    # September defensive mode - penalty if below September threshold
    if period == "september" and base_score < 8.5:
        adjustment -= 0.5
        logger.debug("September penalty: score %.1f < 8.5 threshold | -0.5", base_score)

    # Calculate adjusted score and clamp to [0, 10] range
    adjusted_score = base_score + adjustment
    adjusted_score = max(0.0, min(10.0, adjusted_score))

    logger.debug(
        "Seasonality adjustment applied: period=%s | base=%.2f | adj=%.2f | final=%.2f",
        period,
        base_score,
        adjustment,
        adjusted_score,
    )

    return adjusted_score, adjustment
