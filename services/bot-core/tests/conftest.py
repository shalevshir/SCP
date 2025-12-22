"""Pytest configuration and fixtures for bot-core tests."""

import pytest


@pytest.fixture
def sample_context() -> dict:
    """Sample context for signal generation."""
    return {
        "session_ok": True,
        "enforcer_tier": "Conservative",
    }

