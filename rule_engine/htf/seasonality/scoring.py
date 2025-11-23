"""Seasonality scoring adjustments.

Seasonality affects correlation, score minimums, and trend acceptance.

Task: Integrate seasonality into scoring
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

from rule_engine.htf.seasonality.rules import SeasonalityPeriod
from common.logger import get_logger

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
    # TODO: Implement seasonality scoring adjustments
    # See task: https://www.notion.so/2b42bd6fbda68094a7d3d66534da8d66
    raise NotImplementedError("Seasonality scoring adjustments pending implementation")

