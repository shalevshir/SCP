"""Structure analysis components for HTF bias.

This package handles:
- Swing high/low identification
- Break of Structure (BOS) detection
- Change of Character (CHoCH) detection
- Liquidity sweep detection
- Fair Value Gap (FVG) detection
- Structure event candle extraction
"""

from rule_engine.htf.structure.bos import detect_bos
from rule_engine.htf.structure.choch import detect_choch
from rule_engine.htf.structure.events import (
    extract_bos_candle,
    extract_choch_candle,
    extract_confirmation_candle,
    extract_structure_candles,
    extract_sweep_candle,
)
from rule_engine.htf.structure.fvg import check_fvg_filled, detect_fvg
from rule_engine.htf.structure.liquidity import detect_liquidity_sweeps
from rule_engine.htf.structure.swings import detect_swings

__all__ = [
    "detect_swings",
    "detect_bos",
    "detect_choch",
    "detect_liquidity_sweeps",
    "detect_fvg",
    "check_fvg_filled",
    "extract_bos_candle",
    "extract_choch_candle",
    "extract_sweep_candle",
    "extract_confirmation_candle",
    "extract_structure_candles",
]

