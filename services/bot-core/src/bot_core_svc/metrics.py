"""Prometheus metrics for Bot Core service.

Metrics for decision sanity layer monitoring.
"""

from scp_shared.metrics import create_counter, create_histogram

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

# Valid rejection reasons (finite set to prevent cardinality explosion)
REJECTION_REASONS = {
    "risk_limit",  # PDLL or loss streak
    "session_filter",  # Outside trading hours
    "confidence_filter",  # Below A+ threshold
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
