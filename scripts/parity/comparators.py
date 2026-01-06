"""Comparison functions for backtester vs microservices parity testing."""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from common.logger import get_logger

logger = get_logger(__name__)

# Default tolerances for numeric comparisons
DEFAULT_TOLERANCES = {
    "ema_9": 0.01,
    "ema_20": 0.01,
    "ema_50": 0.01,
    "vwap": 0.01,
    "rsi": 0.5,
    "dxy_corr": 0.001,
    "dxy_correlation": 0.001,
    "structure_clarity": 0.001,
    "trend_confidence": 0.001,
    "vwap_deviation": 0.001,
    "atr_5": 0.01,
    "atr_compression_ratio": 0.001,
}


@dataclass
class FeatureComparison:
    """Result of comparing features between backtester and microservices.

    Attributes:
        timestamp: Timestamp of the compared bar
        matches: Whether features match within tolerances
        differences: Dict of field -> (bt_value, ms_value) for differing fields
        all_fields_compared: Number of fields compared
        matching_fields: Number of fields that matched
    """

    timestamp: datetime
    matches: bool
    differences: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    all_fields_compared: int = 0
    matching_fields: int = 0

    def summary(self) -> str:
        """Generate human-readable summary."""
        if self.matches:
            return f"✓ All {self.all_fields_compared} fields match"

        mismatch_count = len(self.differences)
        summary = f"✗ {mismatch_count}/{self.all_fields_compared} fields differ:\n"
        for field_name, (bt_val, ms_val) in list(self.differences.items())[:5]:
            summary += f"  - {field_name}: {bt_val} (BT) vs {ms_val} (MS)\n"
        if len(self.differences) > 5:
            summary += f"  ... and {len(self.differences) - 5} more\n"
        return summary


@dataclass
class SignalComparison:
    """Result of comparing signals between backtester and microservices.

    Attributes:
        timestamp: Timestamp of the compared bar
        matches: Whether signals match
        bt_signal: Backtester signal (None if no signal generated)
        ms_signal: Microservices signal (None if no signal generated)
        field_diffs: Dict of field -> (bt_value, ms_value) for differing fields
    """

    timestamp: datetime
    matches: bool
    bt_signal: Any | None = None
    ms_signal: Any | None = None
    field_diffs: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate human-readable summary."""
        if self.matches:
            if self.bt_signal is None and self.ms_signal is None:
                return "✓ Both: no signal"
            return f"✓ Both: {self.bt_signal.setup_type} {self.bt_signal.confidence}"

        if self.bt_signal is None and self.ms_signal is not None:
            ms_setup = self.ms_signal.setup_type
            ms_conf = self.ms_signal.confidence
            return f"✗ BT: no signal, MS: {ms_setup} {ms_conf}"
        
        if self.bt_signal is not None and self.ms_signal is None:
            bt_setup = self.bt_signal.setup_type
            bt_conf = self.bt_signal.confidence
            return f"✗ BT: {bt_setup} {bt_conf}, MS: no signal"
        
        # Both have signals but they differ
        summary = "✗ Signals differ:\n"
        for field_name, (bt_val, ms_val) in self.field_diffs.items():
            summary += f"  - {field_name}: {bt_val} (BT) vs {ms_val} (MS)\n"
        return summary


def _is_close(val1: Any, val2: Any, tolerance: float) -> bool:
    """Check if two values are close within tolerance.

    Handles None, NaN, and numeric comparisons.
    """
    # Both None or both NaN
    if val1 is None and val2 is None:
        return True

    # One is None/NaN, other isn't
    if val1 is None or val2 is None:
        return False

    # Check for NaN
    try:
        if math.isnan(val1) and math.isnan(val2):
            return True
        if math.isnan(val1) or math.isnan(val2):
            return False
    except (TypeError, ValueError):
        pass

    # Numeric comparison
    try:
        return abs(float(val1) - float(val2)) <= tolerance
    except (TypeError, ValueError):
        # Non-numeric, use equality
        return val1 == val2


def compare_features(
    bt_features: pd.Series,
    ms_features: pd.Series,
    tolerances: dict[str, float] | None = None,
) -> FeatureComparison:
    """Compare feature series with configurable tolerances.

    Args:
        bt_features: Backtester feature series
        ms_features: Microservices feature series
        tolerances: Custom tolerances per field (uses defaults if None)

    Returns:
        FeatureComparison result
    """
    if tolerances is None:
        tolerances = DEFAULT_TOLERANCES

    timestamp = bt_features.get("timestamp", ms_features.get("timestamp"))

    # Get all fields present in either series
    all_fields = set(bt_features.index) | set(ms_features.index)

    # Exclude timestamp and metadata fields from comparison
    exclude_fields = {
        "timestamp",
        "symbol",
        "timeframe",
        "source",
        "session_ok",
        "enforcer_tier",  # Context fields
    }
    comparison_fields = all_fields - exclude_fields

    differences = {}
    matching_count = 0

    for field_name in comparison_fields:
        bt_val = bt_features.get(field_name)
        ms_val = ms_features.get(field_name)

        # Get tolerance for this field
        tolerance = tolerances.get(field_name, 1e-6)
        
        if _is_close(bt_val, ms_val, tolerance):
            matching_count += 1
        else:
            differences[field_name] = (bt_val, ms_val)

    matches = len(differences) == 0

    return FeatureComparison(
        timestamp=timestamp,
        matches=matches,
        differences=differences,
        all_fields_compared=len(comparison_fields),
        matching_fields=matching_count,
    )


def compare_signals(
    bt_signal: Any | None,
    ms_signal: Any | None,
    tolerances: dict[str, float] | None = None,
) -> SignalComparison:
    """Compare signal objects.

    Args:
        bt_signal: Backtester Signal object (or None)
        ms_signal: Microservices Signal object (or None)
        tolerances: Custom tolerances for numeric fields

    Returns:
        SignalComparison result
    """
    if tolerances is None:
        tolerances = {"score": 0.1}  # Allow 0.1 point difference in score

    # Extract timestamp
    timestamp = None
    if bt_signal is not None:
        timestamp = bt_signal.timestamp
    elif ms_signal is not None:
        timestamp = ms_signal.timestamp

    # Case 1: Both None (no signals)
    if bt_signal is None and ms_signal is None:
        return SignalComparison(
            timestamp=timestamp,
            matches=True,
            bt_signal=None,
            ms_signal=None,
        )

    # Case 2: One has signal, other doesn't
    if (bt_signal is None) != (ms_signal is None):
        return SignalComparison(
            timestamp=timestamp,
            matches=False,
            bt_signal=bt_signal,
            ms_signal=ms_signal,
            field_diffs={
                "signal_generated": (bt_signal is not None, ms_signal is not None)
            },
        )

    # Case 3: Both have signals - compare fields
    field_diffs = {}

    # Compare key signal fields
    signal_fields = ["setup_type", "direction", "confidence", "score"]
    for field_name in signal_fields:
        bt_val = getattr(bt_signal, field_name, None)
        ms_val = getattr(ms_signal, field_name, None)
        
        # Special handling for score (numeric)
        if field_name == "score":
            tolerance = tolerances.get("score", 0.1)
            if not _is_close(bt_val, ms_val, tolerance):
                field_diffs[field_name] = (bt_val, ms_val)
        else:
            # Exact match for categorical fields
            if bt_val != ms_val:
                field_diffs[field_name] = (bt_val, ms_val)

    matches = len(field_diffs) == 0

    return SignalComparison(
        timestamp=timestamp,
        matches=matches,
        bt_signal=bt_signal,
        ms_signal=ms_signal,
        field_diffs=field_diffs,
    )
