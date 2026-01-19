"""Prometheus metrics for Bot Core service.

Metrics for decision sanity layer monitoring.
"""

from scp_shared.metrics import create_counter, create_gauge, create_histogram

# Signal generation metrics
signals_generated_total = create_counter(
    "signals_generated",
    "A+ signals published",
    labels=["setup_type", "timeframe"],
)

signals_rejected_total = create_counter(
    "signals_rejected",
    "Signals blocked by reason",
    labels=["reason"],
)

signal_generation_seconds = create_histogram(
    "signal_generation",
    "Signal evaluation latency",
)

# Signal quality tracking
last_signal_score = create_gauge(
    "last_signal_score",
    "Score of most recent signal evaluated (0-10 scale)",
)

signal_score = create_gauge(
    "signal_score",
    "Current signal score (0-10 scale, updated on each evaluation)",
)

# Enforcer tier tracking
enforcer_tier = create_gauge(
    "enforcer_tier",
    "Active enforcer tier (1=Conservative, 2=Early Mild, 3=Mild, 4=Offensive)",
)

# Session and setup tracking (for trader decision dashboard)
session_valid = create_gauge(
    "session_valid",
    "Session validity status (1=valid, 0=invalid)",
)

current_setup_type = create_gauge(
    "current_setup_type",
    "Current setup type (VWAP_RECLAIM=1, VWAP_FADE=2, DXY_CONTINUATION=3, NONE=0)",
)

# Map enforcer tier names to numeric values
ENFORCER_TIER_MAP = {
    "Conservative": 1.0,
    "Early Mild": 2.0,
    "Mild": 3.0,
    "Offensive": 4.0,
}

# Setup type encoding for metrics
SETUP_TYPE_ENCODING = {
    "VWAP_RECLAIM": 1.0,
    "VWAP_FADE": 2.0,
    "DXY_CONTINUATION": 3.0,
    None: 0.0,
}

# Valid rejection reasons (finite set to prevent cardinality explosion)
REJECTION_REASONS = {
    "risk_limit",  # PDLL or loss streak
    "session_filter",  # Outside trading hours
    "confidence_filter",  # Below A+ threshold
    "htf_validity",  # HTF conflict or DXY chop detected
    "neutral_direction",  # Signal direction is neutral
    "cooldown",  # Re-entry cooldown active
    "invalid_context",  # Missing DXY, bad features
    "warmup",  # Warmup period active
    "kill_switch",  # Kill switch active
    "active_trade",  # Max concurrent trades reached
}


def record_signal_rejection(reason: str, mode: str, service: str) -> None:
    """Record a signal rejection with validation of reason label.
    
    Args:
        reason: Rejection reason (must be from REJECTION_REASONS set)
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (bot-core)
    """
    # Validate reason is from known set to prevent cardinality explosion
    if reason not in REJECTION_REASONS:
        reason = "invalid_context"  # Default for unknown reasons
    
    signals_rejected_total.labels(mode=mode, service=service, reason=reason).inc()
