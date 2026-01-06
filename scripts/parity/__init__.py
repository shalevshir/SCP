"""Parity testing utilities for comparing backtester and microservices implementations.

This package provides tools for bar-by-bar comparison of both implementations
to identify divergences at the feature, signal, and decision levels.
"""

from scripts.parity.comparators import (
    FeatureComparison,
    SignalComparison,
    compare_features,
    compare_signals,
)
from scripts.parity.report import (
    Divergence,
    DivergenceReport,
)

__all__ = [
    "FeatureComparison",
    "SignalComparison",
    "compare_features",
    "compare_signals",
    "Divergence",
    "DivergenceReport",
]
