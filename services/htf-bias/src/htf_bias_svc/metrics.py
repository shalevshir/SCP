"""Prometheus metrics for HTF Bias service.

Metrics for context sanity monitoring.
"""

from scp_shared.metrics import create_counter, create_gauge, create_histogram

# Bias state tracking
htf_bias_current = create_gauge(
    "htf_bias_current",
    "Current HTF bias (bullish=1, neutral=0, bearish=-1)",
)

htf_bias_changes_total = create_counter(
    "htf_bias_changes",
    "HTF bias state transitions",
    labels=["from_bias", "to_bias"],
)

# Processing metrics
htf_bars_processed_total = create_counter(
    "htf_bars_processed",
    "HTF candles processed",
    labels=["timeframe"],
)

htf_processing_seconds = create_histogram(
    "htf_processing",
    "HTF bias computation latency",
)


# Track last bias for change detection
_last_bias: str | None = None


def update_bias_metrics(current_bias: str, mode: str, service: str) -> None:
    """Update bias metrics including current state and transitions.
    
    Args:
        current_bias: Current bias (bullish/bearish/neutral)
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (htf-bias)
    """
    global _last_bias
    
    # Update current bias gauge
    # Map bias to numeric value for monitoring
    bias_value = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}.get(
        current_bias.lower(), 0.0
    )
    htf_bias_current.labels(mode=mode, service=service).set(bias_value)
    
    # Track bias changes
    if _last_bias is not None and _last_bias != current_bias:
        htf_bias_changes_total.labels(
            mode=mode, service=service, from_bias=_last_bias, to_bias=current_bias
        ).inc()
    
    _last_bias = current_bias
