"""FastAPI health check endpoints."""

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, status
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: datetime
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Readiness check response model."""

    ready: bool
    timestamp: datetime
    service: str
    checks: dict[str, bool]


def create_health_router(
    service_name: str,
    version: str = "0.1.0",
    readiness_checks: dict[str, Callable[[], bool]] | None = None,
) -> APIRouter:
    """Create health check router for a microservice.

    Args:
        service_name: Name of the service
        version: Service version
        readiness_checks: Dict of check name -> check function

    Returns:
        FastAPI router with /health and /ready endpoints

    Example:
        >>> def check_redis():
        ...     return redis_client.ping()
        >>>
        >>> router = create_health_router(
        ...     service_name="data-adapter",
        ...     version="0.1.0",
        ...     readiness_checks={"redis": check_redis},
        ... )
        >>> app.include_router(router)
    """
    router = APIRouter(tags=["health"])

    @router.get(
        "/health",
        response_model=HealthResponse,
        status_code=status.HTTP_200_OK,
        summary="Liveness probe",
        description="Check if service is alive",
    )
    async def health() -> HealthResponse:
        """Liveness probe - always returns 200 if service is running."""
        return HealthResponse(
            status="healthy",
            timestamp=datetime.now(UTC),
            service=service_name,
            version=version,
        )

    @router.get(
        "/ready",
        response_model=ReadinessResponse,
        summary="Readiness probe",
        description="Check if service is ready to accept traffic",
    )
    async def ready() -> ReadinessResponse:
        """Readiness probe - checks dependencies are available."""
        checks: dict[str, bool] = {}
        all_ready = True

        if readiness_checks:
            for check_name, check_func in readiness_checks.items():
                try:
                    result = check_func()
                    checks[check_name] = result
                    if not result:
                        all_ready = False
                except Exception:
                    checks[check_name] = False
                    all_ready = False

        return ReadinessResponse(
            ready=all_ready,
            timestamp=datetime.now(UTC),
            service=service_name,
            checks=checks,
        )

    return router
