"""Prometheus metrics for Execution service.

MONEY ZONE - Must be observable enough to reconstruct any incident.
"""

from scp_shared.metrics import create_counter, create_gauge, create_histogram

# Trading state
trading_enabled = create_gauge(
    "trading_enabled",
    "Trading status (1=enabled, 0=disabled)",
)

unsafe_state = create_gauge(
    "unsafe_state",
    "Unsafe state indicator (1=unsafe, 0=safe)",
    labels=["reason"],
)

# Order metrics
orders_sent_total = create_counter(
    "orders_sent",
    "Orders submitted to broker",
    labels=["side"],
)

orders_filled_total = create_counter(
    "orders_filled",
    "Orders successfully filled",
    labels=["side"],
)

orders_rejected_total = create_counter(
    "orders_rejected",
    "Orders rejected by broker or risk checks",
    labels=["reason"],
)

# Execution latency
order_ack_seconds = create_histogram(
    "order_ack",
    "Time to broker acknowledgment",
)

order_fill_seconds = create_histogram(
    "order_fill",
    "Time to fill confirmation",
)

# Position & risk
open_positions = create_gauge(
    "open_positions",
    "Current active trades",
)

daily_pnl = create_gauge(
    "daily_pnl",
    "Today's realized P&L (points)",
)

daily_drawdown = create_gauge(
    "daily_drawdown",
    "Today's max drawdown (points)",
)

# Valid rejection reasons (finite set)
ORDER_REJECTION_REASONS = {
    "broker_error",  # Broker rejected
    "risk_limit",  # PDLL/streak limit
    "trading_disabled",  # Kill switch
    "invalid_state",  # Bad signal/state
}

# Valid unsafe state reasons (finite set)
UNSAFE_STATE_REASONS = {
    "data_lag",  # Market data stale
    "broker_disconnected",  # No broker connection
    "risk_limit",  # PDLL breached
    "manual_kill",  # Kill switch active
}


def record_order_rejection(reason: str, mode: str, service: str) -> None:
    """Record an order rejection with validation of reason label.
    
    Args:
        reason: Rejection reason (must be from ORDER_REJECTION_REASONS set)
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (execution)
    """
    # Validate reason is from known set to prevent cardinality explosion
    if reason not in ORDER_REJECTION_REASONS:
        reason = "invalid_state"  # Default for unknown reasons
    
    orders_rejected_total.labels(mode=mode, service=service, reason=reason).inc()


def set_unsafe_state(reason: str | None, mode: str, service: str) -> None:
    """Set unsafe state metrics.
    
    Args:
        reason: Unsafe state reason (None if safe)
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (execution)
    """
    if reason is None:
        # System is safe - clear all unsafe states
        for unsafe_reason in UNSAFE_STATE_REASONS:
            unsafe_state.labels(mode=mode, service=service, reason=unsafe_reason).set(0)
    else:
        # Validate reason
        if reason not in UNSAFE_STATE_REASONS:
            reason = "invalid_state"
        
        # Set this specific unsafe state
        unsafe_state.labels(mode=mode, service=service, reason=reason).set(1)
