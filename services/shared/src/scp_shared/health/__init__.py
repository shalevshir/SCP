"""Health check endpoints for microservices."""

from scp_shared.health.endpoints import create_health_router

__all__ = ["create_health_router"]
