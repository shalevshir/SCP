"""Infrastructure metrics for Redis and Database connectivity.

These metrics are available for all services to track infrastructure health.
"""

from scp_shared.metrics.registry import create_gauge, create_histogram

# Redis connectivity
redis_connected = create_gauge(
    "redis_connected",
    "Redis connection status (1=connected, 0=disconnected)",
)

# Database query latency
db_query_seconds = create_histogram(
    "db_query",
    "Database query latency",
    labels=["operation"],  # e.g., "select", "insert", "update"
)

# Database connection pool metrics
db_pool_active_connections = create_gauge(
    "db_pool_active_connections",
    "Number of active database connections in pool",
)

db_pool_idle_connections = create_gauge(
    "db_pool_idle_connections",
    "Number of idle database connections in pool",
)
