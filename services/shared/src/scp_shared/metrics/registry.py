"""Prometheus metrics registry with automatic labeling.

This module provides factory functions for creating Prometheus metrics with:
- Consistent `scp_` prefix
- Default labels (`mode`, `service`) on all metrics
- Sensible default buckets for latency histograms
"""

from prometheus_client import Counter, Gauge, Histogram

# Default labels applied to all metrics
DEFAULT_LABELS = ["mode", "service"]

# Default latency buckets (in seconds)
# Covers 5ms to 10s for most use cases
DEFAULT_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def create_counter(
    name: str,
    description: str,
    labels: list[str] | None = None,
) -> Counter:
    """Create a counter metric with scp_ prefix and default labels.

    Args:
        name: Metric name (will be prefixed with 'scp_' and suffixed with '_total')
        description: Human-readable description
        labels: Additional labels beyond mode/service (optional)

    Returns:
        Counter metric instance

    Example:
        >>> candles_counter = create_counter(
        ...     "candles_published",
        ...     "Candles published to Redis",
        ...     labels=["symbol", "timeframe"]
        ... )
        >>> candles_counter.labels(
        ...     mode="live", service="data-adapter",
        ...     symbol="GC", timeframe="1m"
        ... ).inc()
    """
    all_labels = DEFAULT_LABELS + (labels or [])
    return Counter(f"scp_{name}_total", description, all_labels)


def create_gauge(
    name: str,
    description: str,
    labels: list[str] | None = None,
) -> Gauge:
    """Create a gauge metric with scp_ prefix and default labels.

    Args:
        name: Metric name (will be prefixed with 'scp_')
        description: Human-readable description
        labels: Additional labels beyond mode/service (optional)

    Returns:
        Gauge metric instance

    Example:
        >>> active_trades = create_gauge(
        ...     "active_trades",
        ...     "Currently active trades"
        ... )
        >>> active_trades.labels(mode="live", service="execution").set(2)
    """
    all_labels = DEFAULT_LABELS + (labels or [])
    return Gauge(f"scp_{name}", description, all_labels)


def create_histogram(
    name: str,
    description: str,
    labels: list[str] | None = None,
    buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS,
) -> Histogram:
    """Create a histogram metric with scp_ prefix and default labels.

    Args:
        name: Metric name (will be prefixed with 'scp_' and suffixed with '_seconds')
        description: Human-readable description
        labels: Additional labels beyond mode/service (optional)
        buckets: Histogram buckets (defaults to latency buckets)

    Returns:
        Histogram metric instance

    Example:
        >>> processing_time = create_histogram(
        ...     "feature_computation",
        ...     "Feature computation latency",
        ...     labels=["timeframe"]
        ... )
        >>> with processing_time.labels(
        ...     mode="live", service="feature-engine", timeframe="1m"
        ... ).time():
        ...     # Code to measure
        ...     pass
    """
    all_labels = DEFAULT_LABELS + (labels or [])
    return Histogram(f"scp_{name}_seconds", description, all_labels, buckets=buckets)
