"""Setup detectors for specific trading setups.

This module contains specialized detectors for different setup types
that require complex multi-factor validation.
"""

from rule_engine.setup_detectors.dxy_continuation import detect_dxy_continuation

__all__ = ["detect_dxy_continuation"]

