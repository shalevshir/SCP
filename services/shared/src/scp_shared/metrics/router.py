"""FastAPI router for Prometheus metrics endpoint."""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def create_metrics_router() -> APIRouter:
    """Create FastAPI router with /metrics endpoint.

    Returns:
        APIRouter with GET /metrics endpoint that exposes Prometheus metrics

    Example:
        >>> from fastapi import FastAPI
        >>> from scp_shared.metrics import create_metrics_router
        >>>
        >>> app = FastAPI()
        >>> metrics_router = create_metrics_router()
        >>> app.include_router(metrics_router)
    """
    router = APIRouter(tags=["metrics"])

    @router.get(
        "/metrics",
        response_class=Response,
        summary="Prometheus metrics",
        description="Expose metrics in Prometheus exposition format",
    )
    async def metrics() -> Response:
        """Return Prometheus metrics in exposition format."""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return router
