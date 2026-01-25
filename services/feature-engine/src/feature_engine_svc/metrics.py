"""Prometheus metrics for Feature Engine service.

Metrics for signal inputs health monitoring.
"""

from scp_shared.metrics import create_counter, create_gauge, create_histogram

# Feature computation metrics
features_computed_total = create_counter(
    "features_computed",
    "Features computed per timeframe",
    labels=["timeframe"],
)

events_processed_total = create_counter(
    "events_processed",
    "Total candle events processed",
)

event_processing_seconds = create_histogram(
    "event_processing",
    "Feature computation latency",
    labels=["timeframe"],
)

# Queue depth
feature_queue_depth = create_gauge(
    "feature_queue_depth",
    "Pending items in candle synchronizer buffer",
)

# Invalid events
invalid_feature_events_total = create_counter(
    "invalid_feature_events",
    "Invalid feature events (NaN, missing data, etc.)",
    labels=["reason"],
)

# Feature detail metrics (for trader decision dashboard)
# VWAP indicators
feature_vwap = create_gauge(
    "feature_vwap",
    "Current VWAP value",
)

feature_vwap_slope = create_gauge(
    "feature_vwap_slope", "VWAP slope (for FADE invalidation)", labels=["symbol"]
)

feature_vwap_deviation = create_gauge(
    "feature_vwap_deviation",
    "VWAP deviation percentage",
)

# Trend indicators
feature_rsi = create_gauge(
    "feature_rsi",
    "RSI value (0-100)",
)

feature_ema_9 = create_gauge(
    "feature_ema_9",
    "9-period EMA",
)

feature_ema_20 = create_gauge(
    "feature_ema_20",
    "20-period EMA",
)

feature_ema_50 = create_gauge(
    "feature_ema_50",
    "50-period EMA",
)

# DXY correlation
feature_dxy_corr = create_gauge(
    "feature_dxy_corr",
    "DXY correlation (1m) [-1 to 1]",
)

feature_dxy_5m_corr = create_gauge(
    "feature_dxy_5m_corr",
    "DXY 5m correlation [-1 to 1]",
)

feature_dxy_structure = create_gauge(
    "feature_dxy_structure",
    "DXY structure label (encoded: HH=4, HL=3, LH=2, LL=1, N/A=0)",
)

# Structure fields
feature_bos_recent = create_gauge(
    "feature_bos_recent",
    "BOS detected recently (1=yes, 0=no)",
)

feature_bos_age = create_gauge(
    "feature_bos_age",
    "Age of most recent BOS in bars",
)

feature_choch_detected = create_gauge(
    "feature_choch_detected",
    "CHoCH detected (1=yes, 0=no)",
)

feature_structure_clarity = create_gauge(
    "feature_structure_clarity",
    "Structure clarity score (0-1)",
)

# Expansion and confirmation
feature_expansion_detected = create_gauge(
    "feature_expansion_detected",
    "VWAP_RECLAIM expansion detected (1=yes, 0=no)",
)

feature_second_confirmation_long = create_gauge(
    "feature_second_confirmation_long",
    "Second confirmation for long satisfied (1=yes, 0=no)",
)

feature_second_confirmation_short = create_gauge(
    "feature_second_confirmation_short",
    "Second confirmation for short satisfied (1=yes, 0=no)",
)


def update_feature_metrics(features_msg, mode: str, service: str) -> None:
    """Update detailed feature metrics for trader decision dashboard.

    Args:
        features_msg: FeaturesMessage containing all feature details
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (feature-engine)
    """
    # VWAP indicators
    if features_msg.vwap is not None:
        feature_vwap.labels(mode=mode, service=service).set(features_msg.vwap)

    if features_msg.vwap_slope is not None:
        feature_vwap_slope.labels(
            mode=mode, service=service, symbol=features_msg.symbol
        ).set(features_msg.vwap_slope)

    if features_msg.vwap_deviation is not None:
        feature_vwap_deviation.labels(mode=mode, service=service).set(
            features_msg.vwap_deviation
        )

    # Trend indicators
    if features_msg.rsi is not None:
        feature_rsi.labels(mode=mode, service=service).set(features_msg.rsi)

    if features_msg.ema_9 is not None:
        feature_ema_9.labels(mode=mode, service=service).set(features_msg.ema_9)

    if features_msg.ema_20 is not None:
        feature_ema_20.labels(mode=mode, service=service).set(features_msg.ema_20)

    if features_msg.ema_50 is not None:
        feature_ema_50.labels(mode=mode, service=service).set(features_msg.ema_50)

    # DXY correlation (check both field names for backward compatibility)
    dxy_corr = (
        features_msg.dxy_corr
        if features_msg.dxy_corr is not None
        else features_msg.dxy_correlation
    )
    if dxy_corr is not None:
        feature_dxy_corr.labels(mode=mode, service=service).set(dxy_corr)

    if features_msg.dxy_5m_corr is not None:
        feature_dxy_5m_corr.labels(mode=mode, service=service).set(
            features_msg.dxy_5m_corr
        )

    # DXY structure (encode as numeric for Prometheus)
    dxy_structure_map = {"HH": 4.0, "HL": 3.0, "LH": 2.0, "LL": 1.0}
    if features_msg.dxy_structure is not None:
        encoded_value = dxy_structure_map.get(features_msg.dxy_structure, 0.0)
        feature_dxy_structure.labels(mode=mode, service=service).set(encoded_value)
    else:
        feature_dxy_structure.labels(mode=mode, service=service).set(0.0)

    # Structure fields
    bos_recent_value = 1.0 if features_msg.bos_recent else 0.0
    feature_bos_recent.labels(mode=mode, service=service).set(bos_recent_value)

    if features_msg.bos_age is not None:
        feature_bos_age.labels(mode=mode, service=service).set(features_msg.bos_age)

    choch_value = 1.0 if features_msg.choch_detected else 0.0
    feature_choch_detected.labels(mode=mode, service=service).set(choch_value)

    if features_msg.structure_clarity is not None:
        feature_structure_clarity.labels(mode=mode, service=service).set(
            features_msg.structure_clarity
        )

    # Expansion and confirmation
    expansion_value = 1.0 if features_msg.expansion_detected else 0.0
    feature_expansion_detected.labels(mode=mode, service=service).set(expansion_value)

    second_conf_long = 1.0 if features_msg.second_confirmation_long else 0.0
    feature_second_confirmation_long.labels(mode=mode, service=service).set(
        second_conf_long
    )

    second_conf_short = 1.0 if features_msg.second_confirmation_short else 0.0
    feature_second_confirmation_short.labels(mode=mode, service=service).set(
        second_conf_short
    )
