"""DXY alignment computation using behavior-based SOP rules (streaming mode).

This module implements the SOP-aligned DXY alignment logic for live streaming.
Alignment is determined by correlation, structure (when available), and chop filters.
"""

from scp_shared.common.logger import get_logger

logger = get_logger(__name__)


def compute_dxy_alignment(
    trade_direction: str,
    dxy_structure: str | None,
    dxy_chop_5m: bool,
    dxy_corr_1m: float | None,
    dxy_corr_5m: float | None,
    dxy_corr_15m: float | None = None,
    dxy_corr_1h: float | None = None,
) -> tuple[bool, float, str]:
    """Compute DXY alignment using behavior-based SOP rules (streaming mode).

    Per SOP, DXY alignment requires:
    1. DXY structure matches trade direction (when available)
       - Longs → DXY LL/LH (bearish DXY structure)
       - Shorts → DXY HH/HL (bullish DXY structure)
    2. DXY is not in chop on 5M (when available)
    3. Correlation shows inverse action (< -0.4 from best available source)
    4. HTF correlation 15M/1H (OPTIONAL, provides bonus score)

    Args:
        trade_direction: Trade direction ("long" or "short")
        dxy_structure: DXY structure label ("HH", "HL", "LH", "LL", or None)
        dxy_chop_5m: Whether DXY is in chop on 5M timeframe
        dxy_corr_1m: 1M micro correlation (5-bar window)
        dxy_corr_5m: 5M micro correlation (5-bar window)
        dxy_corr_15m: 15M HTF correlation (optional, 50-bar window)
        dxy_corr_1h: 1H HTF correlation (optional, 50-bar window)

    Returns:
        Tuple of (is_aligned, alignment_score, rationale):
        - is_aligned: True if alignment conditions met
        - alignment_score: 0.0-0.5 bonus score from HTF correlation (only if aligned)
        - rationale: Human-readable explanation

    Example:
        >>> is_aligned, score, rationale = compute_dxy_alignment(
        ...     "long", "LL", False, -0.4, -0.5, -0.4, -0.3
        ... )
        >>> print(f"Aligned: {is_aligned}, Score: {score}, Reason: {rationale}")
    """
    rationale_parts = []

    # 1. DXY structure matches direction (when available)
    # Longs → DXY LL/LH (bearish DXY structure = gold bullish)
    # Shorts → DXY HH/HL (bullish DXY structure = gold bearish)
    structure_aligned = False
    if dxy_structure is None:
        # Structure not available yet - will rely on correlation
        structure_aligned = True
        rationale_parts.append("DXY structure: N/A (relying on correlation)")
    elif trade_direction == "long" and dxy_structure in ["LL", "LH"]:
        structure_aligned = True
        rationale_parts.append(
            f"DXY structure: {dxy_structure} (bearish, supports long)"
        )
    elif trade_direction == "short" and dxy_structure in ["HH", "HL"]:
        structure_aligned = True
        rationale_parts.append(
            f"DXY structure: {dxy_structure} (bullish, supports short)"
        )
    else:
        rationale_parts.append(
            f"DXY structure: {dxy_structure} (conflicts with {trade_direction})"
        )

    # 2. No chop on 5M (when available)
    no_chop = not dxy_chop_5m
    if no_chop:
        rationale_parts.append("DXY 5M: trending (no chop)")
    else:
        rationale_parts.append("DXY 5M: in chop (ranging)")

    # 3. Correlation check - use best available correlation
    # Priority: 5M > 1M > 15M
    micro_aligned = False
    effective_corr = None
    corr_source = None
    
    if dxy_corr_5m is not None:
        effective_corr = dxy_corr_5m
        corr_source = "5M"
    elif dxy_corr_1m is not None:
        effective_corr = dxy_corr_1m
        corr_source = "1M"
    elif dxy_corr_15m is not None:
        effective_corr = dxy_corr_15m
        corr_source = "15M"
    
    if effective_corr is not None:
        # Require inverse correlation < -0.4
        if effective_corr < -0.4:
            micro_aligned = True
            rationale_parts.append(
                f"Correlation: {corr_source}={effective_corr:.2f} (inverse)"
            )
        else:
            rationale_parts.append(
                f"Correlation: {corr_source}={effective_corr:.2f} (weak/positive)"
            )
    else:
        rationale_parts.append("Correlation: N/A (no data)")

    # Final alignment: structure + no_chop + correlation
    is_aligned = structure_aligned and no_chop and micro_aligned

    # 4. HTF correlation bonus (only if already aligned)
    htf_score = 0.0
    if is_aligned:
        htf_parts = []
        if dxy_corr_15m is not None and dxy_corr_15m < -0.3:
            htf_score += 0.25
            htf_parts.append(f"15M={dxy_corr_15m:.2f}")
        if dxy_corr_1h is not None and dxy_corr_1h < -0.25:
            htf_score += 0.25
            htf_parts.append(f"1H={dxy_corr_1h:.2f}")

        if htf_parts:
            rationale_parts.append(
                f"HTF corr: {', '.join(htf_parts)} (+{htf_score:.2f})"
            )
        else:
            rationale_parts.append("HTF corr: weak (no bonus)")

    # Build final rationale
    rationale = " | ".join(rationale_parts)

    if is_aligned:
        logger.debug(f"DXY aligned: {rationale}")
    else:
        logger.debug(f"DXY NOT aligned: {rationale}")

    return is_aligned, htf_score, rationale
