"""VWAP analysis components for HTF bias.

This package handles:
- HTF VWAP calculation (1H)
- VWAP trend validation
- FVG interaction scoring
- VWAP reclaim detection
- Reclaim sentinel validation
"""

from rule_engine.htf.vwap.calculator import calculate_htf_vwap
from rule_engine.htf.vwap.fvg import score_fvg_alignment
from rule_engine.htf.vwap.reclaim import (
    VWAPReclaimState,
    detect_vwap_reclaim,
    validate_reclaim_prerequisites,
)
from rule_engine.htf.vwap.sentinel import (
    detect_displacement_candle,
    reclaim_sentinel,
)
from rule_engine.htf.vwap.trend import validate_vwap_trend

__all__ = [
    "calculate_htf_vwap",
    "score_fvg_alignment",
    "validate_vwap_trend",
    "VWAPReclaimState",
    "detect_vwap_reclaim",
    "validate_reclaim_prerequisites",
    "reclaim_sentinel",
    "detect_displacement_candle",
]
