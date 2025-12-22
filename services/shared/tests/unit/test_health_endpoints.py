"""Tests for health check endpoints."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scp_shared.health import create_health_router


class TestHealthEndpoint:
    """Test /health liveness probe."""

    def test_health_returns_healthy(self) -> None:
        """Health endpoint returns healthy status."""
        router = create_health_router(service_name="test-service", version="1.0.0")
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "test-service"
        assert data["version"] == "1.0.0"
        assert "timestamp" in data


class TestReadinessEndpoint:
    """Test /ready readiness probe."""

    def test_ready_with_no_checks(self) -> None:
        """Ready endpoint returns ready=True when no checks configured."""
        router = create_health_router(service_name="test-service")
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["checks"] == {}

    def test_ready_with_passing_check(self) -> None:
        """Ready endpoint returns ready=True when check passes."""
        router = create_health_router(
            service_name="test-service",
            readiness_checks={"db": lambda: True},
        )
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["checks"]["db"] is True

    def test_ready_with_failing_check_returns_false(self) -> None:
        """Ready endpoint returns ready=False when check returns False.

        This is the bug regression test - checks that return False
        should cause ready=False.
        """
        router = create_health_router(
            service_name="test-service",
            readiness_checks={"db": lambda: False},
        )
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["checks"]["db"] is False
        # BUG: This assertion will fail before the fix
        assert (
            data["ready"] is False
        ), "Service should NOT be ready when check returns False"

    def test_ready_with_check_that_raises_exception(self) -> None:
        """Ready endpoint returns ready=False when check raises exception."""

        def failing_check() -> bool:
            raise ConnectionError("Cannot connect to database")

        router = create_health_router(
            service_name="test-service",
            readiness_checks={"db": failing_check},
        )
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["checks"]["db"] is False
        assert data["ready"] is False

    def test_ready_with_mixed_checks(self) -> None:
        """Ready endpoint returns ready=False if any check fails."""
        router = create_health_router(
            service_name="test-service",
            readiness_checks={
                "redis": lambda: True,
                "db": lambda: False,  # This one fails
                "external_api": lambda: True,
            },
        )
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["checks"]["redis"] is True
        assert data["checks"]["db"] is False
        assert data["checks"]["external_api"] is True
        # Overall should be not ready
        assert data["ready"] is False

    def test_ready_with_all_checks_passing(self) -> None:
        """Ready endpoint returns ready=True when all checks pass."""
        router = create_health_router(
            service_name="test-service",
            readiness_checks={
                "redis": lambda: True,
                "db": lambda: True,
                "external_api": lambda: True,
            },
        )
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert all(v is True for v in data["checks"].values())

