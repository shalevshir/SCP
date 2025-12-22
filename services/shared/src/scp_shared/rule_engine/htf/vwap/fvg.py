"""FVG (Fair Value Gap) interaction scoring.

Increase/decrease HTF bias score based on FVG alignment.

Task: Add FVG interaction scoring
Epic: Full HTF Bias Engine Upgrade
Status: In Progress
"""

from __future__ import annotations

import pandas as pd
from scp_shared.common.logger import get_logger

logger = get_logger(__name__)


def score_fvg_alignment(
    fvg_df: pd.DataFrame,
    current_bias: str,
) -> float:
    """Score FVG alignment with HTF bias.

    Args:
        fvg_df: DataFrame from detect_fvg() with 'filled' status updated
        current_bias: Current HTF bias ("bullish", "bearish", "neutral")

    Returns:
        Float score adjustment:
        - Positive: FVGs aligned with bias (increases confidence)
        - Negative: FVGs oppose bias (decreases confidence)
        - Zero: No FVGs or neutral bias

    Raises:
        ValueError: If current_bias is not one of: "bullish", "bearish", "neutral"

    Logic:
        - Each unfilled bullish FVG aligned with bullish bias: +0.5
        - Each unfilled bearish FVG aligned with bearish bias: +0.5
        - Each unfilled FVG opposing current bias: -0.5
        - Filled FVGs ignored (no longer relevant)
        - Neutral bias always returns 0.0

    Example:
        >>> from scp_shared.rule_engine.htf.structure import detect_fvg, check_fvg_filled
        >>> fvg_df = detect_fvg(df_1h)
        >>> fvg_df = check_fvg_filled(df_1h, fvg_df)
        >>> score_adj = score_fvg_alignment(fvg_df, "bullish")
        >>> print(f"FVG adjustment: {score_adj:+.1f}")
        FVG adjustment: +1.5
    """
    # Validate bias input
    valid_biases = ["bullish", "bearish", "neutral"]
    if current_bias not in valid_biases:
        raise ValueError(
            f"Invalid bias: {current_bias}. Must be one of: {valid_biases}"
        )

    # Neutral bias = no adjustment
    if current_bias == "neutral":
        logger.debug("Neutral bias: returning 0.0 score adjustment")
        return 0.0

    # Empty FVG DataFrame = no adjustment
    if len(fvg_df) == 0:
        logger.debug("No FVGs detected: returning 0.0 score adjustment")
        return 0.0

    # Filter unfilled FVGs only (filled ones no longer relevant)
    unfilled_fvgs = fvg_df[~fvg_df["filled"]]

    if len(unfilled_fvgs) == 0:
        logger.debug("All FVGs filled: returning 0.0 score adjustment")
        return 0.0

    # Count by type
    bullish_count = len(unfilled_fvgs[unfilled_fvgs["fvg_type"] == "bullish"])
    bearish_count = len(unfilled_fvgs[unfilled_fvgs["fvg_type"] == "bearish"])

    # Calculate score based on alignment with current bias
    if current_bias == "bullish":
        aligned = bullish_count  # Bullish FVGs support bullish bias
        opposing = bearish_count  # Bearish FVGs oppose bullish bias
    else:  # bearish
        aligned = bearish_count  # Bearish FVGs support bearish bias
        opposing = bullish_count  # Bullish FVGs oppose bearish bias

    # Each aligned FVG adds +0.5, each opposing subtracts -0.5
    score_adjustment = (aligned * 0.5) - (opposing * 0.5)

    logger.debug(
        f"FVG scoring: bias={current_bias}, "
        f"aligned={aligned}, opposing={opposing}, "
        f"adjustment={score_adjustment:+.2f}"
    )

    return score_adjustment
