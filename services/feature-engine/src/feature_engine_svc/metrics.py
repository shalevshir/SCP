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
