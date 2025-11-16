"""RuleEngine module for trade signal generation and scoring.

This module implements the core decision layer that transforms engineered
market features into structured, auditable trade signals following Shir Capital's
SOP requirements.

Components:
    - Signal: Immutable dataclass representing a trade signal
    - score_signal: Main scoring function to generate signals from features
    - validate_signal: SOP compliance validation
    - log_signal: Signal logging for auditability

Example:
    >>> from rule_engine import Signal, score_signal, validate_signal, log_signal
    >>> import pandas as pd
    >>> from datetime import datetime, timezone
    >>>
    >>> # Create feature data
    >>> features = pd.Series({
    ...     "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
    ...     "symbol": "GC",
    ...     "timeframe": "1m",
    ...     "close": 2650.0,
    ...     "vwap": 2645.0,
    ...     "rsi": 55.0,
    ...     "ema_9": 2648.0,
    ...     "ema_20": 2645.0,
    ...     "ema_50": 2640.0,
    ...     "dxy_corr": -0.75,
    ... })
    >>>
    >>> # Score signal
    >>> context = {
    ...     "htf_bias": "bullish",
    ...     "htf_direction": "long",
    ...     "session_ok": True,
    ...     "enforcer_tier": "Early Mild",
    ... }
    >>> signal = score_signal(features, context)
    >>>
    >>> # Validate against SOP
    >>> validated_signal = validate_signal(signal, context)
    >>>
    >>> # Log for auditability
    >>> if validated_signal.confidence == "A+":
    ...     log_signal(validated_signal)
"""

from rule_engine.config_loader import ScoringConfig, load_scoring_config
from rule_engine.scoring import (
    classify_confidence,
    determine_setup_type,
    score_signal,
)
from rule_engine.signal import Signal
from rule_engine.signal_logger import log_signal, signal_to_dict
from rule_engine.validation import validate_signal

__all__ = [
    # Core types
    "Signal",
    "ScoringConfig",
    # Main functions
    "score_signal",
    "validate_signal",
    "log_signal",
    # Config
    "load_scoring_config",
    # Helper functions
    "classify_confidence",
    "determine_setup_type",
    "signal_to_dict",
]
