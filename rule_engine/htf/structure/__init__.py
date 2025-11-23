"""Structure analysis components for HTF bias.

This package handles:
- Swing high/low identification
- Break of Structure (BOS) detection
- Change of Character (CHoCH) detection
- Liquidity sweep detection
"""

from rule_engine.htf.structure.swings import detect_swings

__all__ = ["detect_swings"]

