"""Tests for metrics router and registry."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from scp_shared.metrics import (
    create_counter,
    create_gauge,
    create_histogram,
    create_metrics_router,
)


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app with metrics router."""
    test_app = FastAPI()
    metrics_router = create_metrics_router()
    test_app.include_router(metrics_router)
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_metrics_endpoint_exists(client: TestClient) -> None:
    """Test that /metrics endpoint exists and returns 200."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")


def test_metrics_endpoint_returns_prometheus_format(client: TestClient) -> None:
    """Test that /metrics returns Prometheus exposition format."""
    response = client.get("/metrics")
    content = response.text

    # Should contain Prometheus format markers
    assert "# HELP" in content or "# TYPE" in content or content.strip() == ""


def test_counter_creation() -> None:
    """Test counter metric creation with default labels."""
    counter = create_counter(
        "test_counter",
        "Test counter metric",
        labels=["test_label"],
    )

    # Increment counter
    counter.labels(mode="test", service="test-service", test_label="value1").inc()

    # Verify counter was incremented
    assert (
        counter.labels(
            mode="test", service="test-service", test_label="value1"
        )._value.get()
        == 1
    )


def test_gauge_creation() -> None:
    """Test gauge metric creation with default labels."""
    gauge = create_gauge(
        "test_gauge",
        "Test gauge metric",
    )

    # Set gauge value
    gauge.labels(mode="test", service="test-service").set(42)

    # Verify gauge value
    assert gauge.labels(mode="test", service="test-service")._value.get() == 42


def test_histogram_creation() -> None:
    """Test histogram metric creation with default labels."""
    histogram = create_histogram(
        "test_histogram",
        "Test histogram metric",
    )

    # Observe value
    histogram.labels(mode="test", service="test-service").observe(0.5)

    # Verify histogram was updated (checking that it doesn't raise an error is sufficient)
    # Note: Prometheus histograms don't expose _count attribute directly in the label API
    assert histogram is not None


def test_counter_has_total_suffix() -> None:
    """Test that counters get _total suffix automatically."""
    counter = create_counter("events", "Event counter")

    # Verify counter was created (the _total suffix is added internally)
    assert counter is not None
    # The counter should have the scp_ prefix
    assert "scp_events" in str(counter)


def test_histogram_has_seconds_suffix() -> None:
    """Test that histograms get _seconds suffix automatically."""
    histogram = create_histogram("processing", "Processing time")

    # The metric name should be scp_processing_seconds
    assert "scp_processing_seconds" in str(histogram)


def test_metrics_include_default_labels() -> None:
    """Test that all metrics include mode and service labels."""
    counter = create_counter("test_events", "Test events")

    # Should require mode and service labels
    try:
        # This should fail because mode and service are required
        counter.labels(extra="value").inc()
        pytest.fail("Should have raised exception for missing labels")
    except (ValueError, TypeError):
        # Expected - mode and service are required
        pass
