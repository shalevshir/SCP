"""DXY analysis components for HTF bias.

This package handles:
- DXY chop detection
- DXY correlation validation
- DXY alignment computation (behavior-based SOP rules)
"""

from scp_shared.rule_engine.htf.dxy.alignment import compute_dxy_alignment
from scp_shared.rule_engine.htf.dxy.chop import detect_dxy_chop

__all__ = ["detect_dxy_chop", "compute_dxy_alignment"]
