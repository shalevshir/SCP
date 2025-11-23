"""FVG (Fair Value Gap) interaction scoring.

Increase/decrease HTF bias score based on FVG alignment.

Task: Add FVG interaction scoring
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

import pandas as pd

from common.logger import get_logger

logger = get_logger(__name__)


def score_fvg_alignment(
    df: pd.DataFrame,
    current_bias: str,
) -> pd.Series:
    """Score FVG alignment with HTF bias.

    Args:
        df: DataFrame with FVG data (if available)
        current_bias: Current HTF bias ("bullish", "bearish", "neutral")

    Returns:
        Series with FVG alignment score adjustments

    Logic:
        - FVG aligned with trend: +0.5 to HTF score
        - FVG opposing trend: -0.5 to HTF score (reduces confidence)
        - No FVG: 0 adjustment

    DoD:
        - FVG adds +0.5 to aligned trend
        - Opposing FVG reduces HTF score
        - Unit tests verify expected scoring behavior
    """
    # TODO: Implement FVG interaction scoring
    # See task: https://www.notion.so/2b42bd6fbda6806281cbf1eb4cff5704
    raise NotImplementedError("FVG interaction scoring pending implementation")

