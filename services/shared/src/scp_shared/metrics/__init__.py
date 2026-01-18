"""Prometheus metrics for SCP microservices.

This module provides:
- Metric factory functions with automatic labeling (mode, service)
- FastAPI router for /metrics endpoint
- Consistent naming conventions (scp_ prefix)

Example:
    >>> from scp_shared.metrics import (
    ...     create_counter,
    ...     create_gauge,
    ...     create_metrics_router,
    ... )
    >>> 
    >>> # Create metrics
    >>> candles_counter = create_counter(
    ...     "candles_published", "Candles published", labels=["symbol"]
    ... )
    >>> active_trades = create_gauge("active_trades", "Active trades")
    >>> 
    >>> # Add router to FastAPI app
    >>> from fastapi import FastAPI
    >>> app = FastAPI()
    >>> app.include_router(create_metrics_router())
"""

from scp_shared.metrics.registry import (
    create_counter,
    create_gauge,
    create_histogram,
)
from scp_shared.metrics.router import create_metrics_router
from scp_shared.metrics import infrastructure

__all__ = [
    "create_counter",
    "create_gauge",
    "create_histogram",
    "create_metrics_router",
    "infrastructure",
]
