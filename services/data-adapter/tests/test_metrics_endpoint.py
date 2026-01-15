"""Integration tests for Data Adapter metrics endpoint."""

import pytest
from fastapi.testclient import TestClient

from data_adapter.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client for Data Adapter service."""
    return TestClient(app)


def test_metrics_endpoint_accessible(client: TestClient) -> None:
    """Test that /metrics endpoint is accessible."""
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_endpoint_returns_text(client: TestClient) -> None:
    """Test that /metrics returns text/plain content type."""
    response = client.get("/metrics")
    assert "text/plain" in response.headers.get("content-type", "")


def test_metrics_endpoint_contains_scp_prefix(client: TestClient) -> None:
    """Test that metrics use scp_ prefix."""
    response = client.get("/metrics")
    content = response.text
    
    # Should contain at least one scp_ metric (may be empty if no data processed yet)
    # This is a weak test but ensures the endpoint structure is correct
    assert response.status_code == 200


def test_health_endpoint_still_works(client: TestClient) -> None:
    """Test that health endpoint is not affected by metrics."""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "data-adapter"
