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
    "invalid_state",  # Fallback for unknown/unexpected states
}

# Trading halt reasons (finite set)
trading_halt_reason = create_gauge(
    "trading_halt_reason",
    "Current trading halt reason (1=active for that reason, 0=inactive)",
    labels=["reason"],
)

# Valid halt reasons (finite set)
HALT_REASONS = {
    "NONE",  # No halt (trading allowed)
    "PDLL",  # Per-day loss limit hit
    "LOSS_STREAK",  # Loss streak limit hit
    "FATIGUE",  # Fatigue detection
    "UNSAFE_STATE",  # Unsafe state (kill switch, data lag, etc.)
    "CEO_OVERRIDE",  # Manual override by CEO
    "MAX_TRADES",  # Max trades per day reached
}

# Broker connectivity
broker_connected = create_gauge(
    "broker_connected",
    "Broker connection status (1=connected, 0=disconnected)",
)

# Loss streak tracking
loss_streak_current = create_gauge(
    "loss_streak_current",
    "Current consecutive loss count",
)


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


def set_trading_halt_reason(reason: str, mode: str, service: str) -> None:
    """Set trading halt reason metrics.
    
    Args:
        reason: Halt reason (must be from HALT_REASONS set)
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (execution)
    """
    # Validate reason
    if reason not in HALT_REASONS:
        reason = "UNSAFE_STATE"  # Default for unknown reasons
    
    # Clear all halt reasons first
    for halt_reason in HALT_REASONS:
        trading_halt_reason.labels(mode=mode, service=service, reason=halt_reason).set(0)
    
    # Set the active halt reason
    trading_halt_reason.labels(mode=mode, service=service, reason=reason).set(1)
