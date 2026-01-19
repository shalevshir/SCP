"""Prometheus metrics for Data Adapter service.

Metrics for market data integrity monitoring.
"""

from datetime import datetime

from scp_shared.metrics import create_counter, create_gauge, create_histogram

# Market data metrics
market_ticks_total = create_counter(
    "market_ticks",
    "Raw ticks received from data provider",
    labels=["symbol"],
)

bars_emitted_total = create_counter(
    "bars_emitted",
    "Candles published to Redis",
    labels=["symbol", "timeframe"],
)

market_data_lag_seconds = create_gauge(
    "market_data_lag_seconds",
    "Time since last tick received (staleness indicator)",
    labels=["symbol"],
)

# Data quality metrics
data_gaps_detected_total = create_counter(
    "data_gaps_detected",
    "Data gap detection events",
    labels=["symbol"],
)

gap_backfills_total = create_counter(
    "gap_backfills",
    "Successful gap backfill operations",
    labels=["symbol"],
)

# Provider connectivity
data_provider_connected = create_gauge(
    "data_provider_connected",
    "Data provider connection status (1=connected, 0=disconnected)",
    labels=["provider"],
)

# Processing latency
tick_processing_seconds = create_histogram(
    "tick_processing",
    "Tick aggregation latency",
    labels=["symbol"],
)

# Track last tick timestamp per symbol for lag calculation
_last_tick_timestamps: dict[str, datetime] = {}


def update_tick_timestamp(symbol: str, timestamp: datetime) -> None:
    """Update last tick timestamp for lag calculation.
    
    Args:
        symbol: Symbol (GC, DXY)
        timestamp: Tick timestamp
    """
    _last_tick_timestamps[symbol] = timestamp


def update_lag_metrics(current_time: datetime, mode: str, service: str) -> None:
    """Update market data lag metrics based on last tick timestamps.
    
    Args:
        current_time: Current time for lag calculation
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (data-adapter)
    """
    for symbol, last_tick_time in _last_tick_timestamps.items():
        lag = (current_time - last_tick_time).total_seconds()
        # Update lag gauge for this symbol
        market_data_lag_seconds.labels(mode=mode, service=service, symbol=symbol).set(lag)
