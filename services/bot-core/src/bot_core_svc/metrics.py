"""Prometheus metrics for Bot Core service.

Metrics for decision sanity layer monitoring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scp_shared.metrics import create_counter, create_gauge, create_histogram

if TYPE_CHECKING:
    from scp_shared.messaging.schemas import HTFBiasMessage, SignalMessage
    from scp_shared.rule_engine import Signal

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

detected_setup_type = create_gauge(
    "detected_setup_type",
    "Detected setup type regardless of A+ status (VWAP_RECLAIM=1, VWAP_FADE=2, DXY_CONTINUATION=3, NONE=0)",
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
    "tp_validation",  # TP validation failed
}

# === SIGNAL STATE METRICS (for trader decision dashboard) ===

# Core verdict
signal_aplus_verdict = create_gauge(
    "signal_aplus_verdict",
    "A+ signal verdict (1=EXECUTION PERMITTED, 0=STAND DOWN)",
)

signal_hard_gates_pass = create_gauge(
    "signal_hard_gates_pass",
    "All hard gates passing (1=pass, 0=fail)",
)

signal_direction = create_gauge(
    "signal_direction",
    "Signal direction (1=long, -1=short, 0=neutral/none)",
)

signal_confidence = create_gauge(
    "signal_confidence",
    "Signal confidence (4=A+, 3=A, 2=B, 1=C, 0=none)",
)

# Prices
signal_entry_price = create_gauge("signal_entry_price", "Signal entry price")
signal_sl_price = create_gauge("signal_sl_price", "Signal stop loss price")
signal_tp_price = create_gauge("signal_tp_price", "Signal take profit price (TP1)")
signal_tp2_price = create_gauge(
    "signal_tp2_price", "Signal secondary TP price (0 if none)"
)

# Risk/Reward
signal_rr_tp1 = create_gauge("signal_rr_tp1", "Signal R:R ratio at TP1")
signal_rr_potential = create_gauge("signal_rr_potential", "Signal max R:R potential")
signal_risk_points = create_gauge(
    "signal_risk_points", "Signal risk in points (entry to SL)"
)

# TP Mode
signal_tp_mode = create_gauge(
    "signal_tp_mode", "Signal TP mode (1=static, 2=continuation)"
)
signal_be_after_tp1 = create_gauge(
    "signal_be_after_tp1", "Move to breakeven after TP1 (1=yes, 0=no)"
)

# Rejection tracking
signal_last_rejection = create_gauge(
    "signal_last_rejection",
    "Last rejection reason encoded (0=approved, 1-11=rejection codes)",
)

# Encoding maps for signal state metrics
DIRECTION_ENCODING = {"long": 1.0, "short": -1.0, "neutral": 0.0}
CONFIDENCE_ENCODING = {"A+": 4.0, "A": 3.0, "B": 2.0, "C": 1.0}
TP_MODE_ENCODING = {"static": 1.0, "continuation": 2.0}
REJECTION_ENCODING = {
    None: 0.0,
    "htf_validity": 1.0,
    "confidence_filter": 2.0,
    "tp_validation": 3.0,
    "neutral_direction": 4.0,
    "session_filter": 5.0,
    "risk_limit": 6.0,
    "cooldown": 7.0,
    "warmup": 8.0,
    "kill_switch": 9.0,
    "active_trade": 10.0,
    "invalid_context": 11.0,
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


def update_signal_state_metrics(
    signal_msg: SignalMessage | None,
    raw_signal: Signal | None,
    rejection_reason: str | None,
    htf_bias: HTFBiasMessage | None,
    mode: str,
    service: str,
) -> None:
    """Update all signal state metrics for trader decision dashboard.

    This function updates Prometheus gauges that expose the complete signal state,
    creating a single source of truth for the trader decision dashboard.

    Args:
        signal_msg: SignalMessage if approved (A+), None if rejected
        raw_signal: Raw Signal object with full diagnostics (may be None during warmup)
        rejection_reason: Rejection reason code, None if approved
        htf_bias: HTF bias message for hard gates evaluation
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (bot-core)
    """
    labels = {"mode": mode, "service": service}

    # Hard gates check (HTF conflict, DXY alignment, chop)
    if htf_bias:
        htf_conflict = getattr(htf_bias, "conflict_detected", False)
        dxy_aligned = getattr(htf_bias, "dxy_aligned", True)
        chop = getattr(htf_bias, "chop_detected", False)
        hard_gates_pass = not htf_conflict and dxy_aligned and not chop
    else:
        hard_gates_pass = False

    signal_hard_gates_pass.labels(**labels).set(1.0 if hard_gates_pass else 0.0)

    if signal_msg:
        # Approved A+ signal - expose full signal state
        is_aplus = signal_msg.score >= 8.0 and hard_gates_pass
        signal_aplus_verdict.labels(**labels).set(1.0 if is_aplus else 0.0)
        signal_direction.labels(**labels).set(
            DIRECTION_ENCODING.get(signal_msg.direction, 0.0)
        )
        signal_confidence.labels(**labels).set(
            CONFIDENCE_ENCODING.get(signal_msg.confidence, 0.0)
        )

        # Prices
        signal_entry_price.labels(**labels).set(signal_msg.entry_price)
        signal_sl_price.labels(**labels).set(signal_msg.sl_price)
        signal_tp_price.labels(**labels).set(signal_msg.tp_price)
        signal_tp2_price.labels(**labels).set(signal_msg.tp2_price or 0.0)

        # Risk/Reward
        signal_rr_tp1.labels(**labels).set(signal_msg.rr_tp1 or 0.0)
        signal_rr_potential.labels(**labels).set(signal_msg.rr_potential or 0.0)
        risk_points = abs(signal_msg.entry_price - signal_msg.sl_price)
        signal_risk_points.labels(**labels).set(risk_points)

        # TP Mode
        signal_tp_mode.labels(**labels).set(
            TP_MODE_ENCODING.get(signal_msg.tp_mode, 1.0)
        )
        signal_be_after_tp1.labels(**labels).set(
            1.0 if signal_msg.be_after_tp1 else 0.0
        )

        # Approved = no rejection
        signal_last_rejection.labels(**labels).set(0.0)
    else:
        # No approved signal - clear prices but expose raw signal info if available
        signal_aplus_verdict.labels(**labels).set(0.0)

        if raw_signal:
            signal_direction.labels(**labels).set(
                DIRECTION_ENCODING.get(raw_signal.direction, 0.0)
            )
            signal_confidence.labels(**labels).set(
                CONFIDENCE_ENCODING.get(raw_signal.confidence, 0.0)
            )
        else:
            signal_direction.labels(**labels).set(0.0)
            signal_confidence.labels(**labels).set(0.0)

        # Clear prices when no approved signal
        signal_entry_price.labels(**labels).set(0.0)
        signal_sl_price.labels(**labels).set(0.0)
        signal_tp_price.labels(**labels).set(0.0)
        signal_tp2_price.labels(**labels).set(0.0)
        signal_rr_tp1.labels(**labels).set(0.0)
        signal_rr_potential.labels(**labels).set(0.0)
        signal_risk_points.labels(**labels).set(0.0)
        signal_tp_mode.labels(**labels).set(0.0)
        signal_be_after_tp1.labels(**labels).set(0.0)

        # Set rejection reason
        if rejection_reason is None:
            rejection_value = 0.0
        else:
            rejection_value = REJECTION_ENCODING.get(
                rejection_reason, REJECTION_ENCODING["invalid_context"]
            )

        signal_last_rejection.labels(**labels).set(rejection_value)
