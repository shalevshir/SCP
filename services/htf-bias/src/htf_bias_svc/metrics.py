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

# HTF Bias detailed state metrics (for trader decision dashboard)
htf_bias_score = create_gauge(
    "htf_bias_score",
    "HTF bias score (0-10 scale)",
)

htf_bias_confidence = create_gauge(
    "htf_bias_confidence",
    "HTF bias confidence level (A+=4, A=3, B=2, C=1)",
)

htf_dxy_aligned = create_gauge(
    "htf_dxy_aligned",
    "DXY alignment status (1=aligned, 0=not aligned)",
)

htf_chop_detected = create_gauge(
    "htf_chop_detected",
    "Chop detected (1=yes, 0=no)",
)

htf_conflict_detected = create_gauge(
    "htf_conflict_detected",
    "HTF conflict detected (1=yes, 0=no)",
)

htf_vwap_trend_confirmed = create_gauge(
    "htf_vwap_trend_confirmed",
    "VWAP trend confirmation (1=confirmed, 0=not confirmed)",
)

htf_bos_detected = create_gauge(
    "htf_bos_detected",
    "Break of Structure detected (1=yes, 0=no)",
)

htf_liquidity_sweep_detected = create_gauge(
    "htf_liquidity_sweep_detected",
    "Liquidity sweep detected (1=yes, 0=no)",
)

htf_structure_15m = create_gauge(
    "htf_structure_15m",
    "15m structure encoding (HH=1, HL=2, LH=3, LL=4, NEUTRAL=0)",
)

htf_structure_1h = create_gauge(
    "htf_structure_1h",
    "1h structure encoding (HH=1, HL=2, LH=3, LL=4, NEUTRAL=0)",
)

htf_seasonality_adjustment = create_gauge(
    "htf_seasonality_adjustment",
    "Seasonality score adjustment (float value)",
)


# Track last bias for change detection
_last_bias: str | None = None

# Structure label mappings for encoding
STRUCTURE_ENCODING = {
    "HH": 1.0,
    "HL": 2.0,
    "LH": 3.0,
    "LL": 4.0,
    "NEUTRAL": 0.0,
    None: 0.0,
}

# Confidence level mappings
CONFIDENCE_ENCODING = {
    "A+": 4.0,
    "A": 3.0,
    "B": 2.0,
    "C": 1.0,
}


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


def update_htf_detail_metrics(bias_msg, mode: str, service: str) -> None:
    """Update detailed HTF bias metrics for trader decision dashboard.

    Args:
        bias_msg: HTFBiasMessage containing all bias details
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (htf-bias)
    """
    # Score and confidence
    htf_bias_score.labels(mode=mode, service=service).set(bias_msg.score)
    confidence_value = CONFIDENCE_ENCODING.get(bias_msg.confidence, 0.0)
    htf_bias_confidence.labels(mode=mode, service=service).set(confidence_value)

    # DXY and chop
    htf_dxy_aligned.labels(mode=mode, service=service).set(
        1.0 if bias_msg.dxy_aligned else 0.0
    )
    htf_chop_detected.labels(mode=mode, service=service).set(
        1.0 if bias_msg.chop_detected else 0.0
    )

    # Conflict detection
    conflict_value = 1.0 if getattr(bias_msg, "conflict_detected", False) else 0.0
    htf_conflict_detected.labels(mode=mode, service=service).set(conflict_value)

    # VWAP trend confirmation
    vwap_confirmed = 1.0 if getattr(bias_msg, "vwap_trend_confirmed", False) else 0.0
    htf_vwap_trend_confirmed.labels(mode=mode, service=service).set(vwap_confirmed)

    # Structure events
    bos_value = 1.0 if getattr(bias_msg, "bos_detected", False) else 0.0
    htf_bos_detected.labels(mode=mode, service=service).set(bos_value)

    sweep_value = 1.0 if getattr(bias_msg, "liquidity_sweep_detected", False) else 0.0
    htf_liquidity_sweep_detected.labels(mode=mode, service=service).set(sweep_value)

    # Structure labels (encode as numbers for Grafana)
    structure_15m_value = STRUCTURE_ENCODING.get(bias_msg.structure_15m, 0.0)
    htf_structure_15m.labels(mode=mode, service=service).set(structure_15m_value)

    structure_1h_value = STRUCTURE_ENCODING.get(bias_msg.structure_1h, 0.0)
    htf_structure_1h.labels(mode=mode, service=service).set(structure_1h_value)

    # Seasonality adjustment
    seasonality_adj = getattr(bias_msg, "seasonality_adjustment", 0.0)
    htf_seasonality_adjustment.labels(mode=mode, service=service).set(seasonality_adj)
