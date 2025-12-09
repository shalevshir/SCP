"""Higher Timeframe (HTF) Bias Calculator - DEPRECATED.

This module has been migrated to rule_engine.htf for better modularity.
This file is kept for backward compatibility.

DEPRECATION NOTICE:
    This module is deprecated and will be removed in a future version.
    Please migrate to:
        from rule_engine.htf.calculator import compute_htf_bias_multi_timeframe
        from rule_engine.htf.calculator import compute_htf_bias
        from rule_engine.htf.calculator import is_london_or_ny_session

See rule_engine/htf/README.md for migration guide and new features.

Epic: Full HTF Bias Engine Upgrade
"""

from __future__ import annotations

import warnings

# Import from new location
from rule_engine.htf.calculator import (
    compute_htf_bias_multi_timeframe,
    is_london_or_ny_session,
)

# Deprecation warning
warnings.warn(
    "rule_engine.htf_calculator is deprecated. "
    "Please use rule_engine.htf.calculator instead. "
    "See rule_engine/htf/README.md for details.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "compute_htf_bias_multi_timeframe",
    "is_london_or_ny_session",
]
