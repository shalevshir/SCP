"""Unit tests for ResilientDatabentoClient."""

import asyncio
from datetime import UTC, datetime

import pytest

from data_adapter.databento_client import (
    DatabentoClient,
    ResilientDatabentoClient,
    Tick,
)


class MockFailingClient:
    """Mock client that fails N times then succeeds."""

    def __init__(self, fail_count: int = 2):
        self.fail_count = fail_count
        self.attempt = 0
        self._closed = False

    async def stream_ticks(self):
        """Stream ticks, failing first N attempts."""
        self.attempt += 1

        if self.attempt <= self.fail_count:
            raise ConnectionError(f"Mock failure {self.attempt}")

        # Success - yield some ticks
        for i in range(3):
            yield Tick(
                timestamp=datetime(2025, 1, 15, 10, i, 0, tzinfo=UTC),
                price=2650.0 + i,
                volume=100.0,
                symbol="GC",
            )

    async def close(self):
        """Close client."""
        self._closed = True


class MockNormalDisconnectClient:
    """Mock client that completes normally (no exception) after N ticks."""

    def __init__(self, ticks_per_connection: int = 2):
        self.ticks_per_connection = ticks_per_connection
        self.attempt = 0
        self._closed = False

    async def stream_ticks(self):
        """Stream ticks then complete normally (simulating server closing connection)."""
        self.attempt += 1

        # Yield a few ticks, then stream ends normally (no exception)
        for i in range(self.ticks_per_connection):
            yield Tick(
                timestamp=datetime(2025, 1, 15, 10, i, 0, tzinfo=UTC),
                price=2650.0 + i,
                volume=100.0,
                symbol="GC",
            )
        # Stream ends here - no exception raised

    async def close(self):
        """Close client."""
        self._closed = True


@pytest.mark.asyncio
async def test_resilient_client_reconnects_after_failure():
    """Test that ResilientDatabentoClient reconnects after connection failure."""
    # Create mock client that fails twice, then succeeds
    mock_client = MockFailingClient(fail_count=2)

    # Wrap with resilient client (short delays for testing)
    resilient = ResilientDatabentoClient(
        inner=mock_client,
        max_retries=5,
        base_delay=0.01,  # 10ms base delay
        max_delay=0.1,  # 100ms max delay
    )

    # Should eventually succeed after retries
    ticks = []
    async for tick in resilient.stream_ticks():
        ticks.append(tick)
        if len(ticks) >= 3:
            break

    # Verify we got ticks
    assert len(ticks) == 3
    assert ticks[0].symbol == "GC"

    # Verify it retried (3 attempts total: 2 failures + 1 success)
    assert mock_client.attempt == 3


@pytest.mark.asyncio
async def test_resilient_client_gives_up_after_max_retries():
    """Test that ResilientDatabentoClient gives up after max retries."""
    # Create mock client that always fails
    mock_client = MockFailingClient(fail_count=999)

    # Wrap with resilient client with low max_retries
    resilient = ResilientDatabentoClient(
        inner=mock_client,
        max_retries=3,
        base_delay=0.01,
        max_delay=0.1,
    )

    # Should raise after max retries
    with pytest.raises(ConnectionError):
        async for _ in resilient.stream_ticks():
            pass


@pytest.mark.asyncio
async def test_resilient_client_exponential_backoff():
    """Test that ResilientDatabentoClient uses exponential backoff."""
    mock_client = MockFailingClient(fail_count=3)

    resilient = ResilientDatabentoClient(
        inner=mock_client,
        max_retries=5,
        base_delay=0.01,  # 10ms base
        max_delay=0.05,  # 50ms max
    )

    start_time = asyncio.get_event_loop().time()

    ticks = []
    async for tick in resilient.stream_ticks():
        ticks.append(tick)
        if len(ticks) >= 1:
            break

    elapsed = asyncio.get_event_loop().time() - start_time

    # Expected delays: 0.01 (1st retry), 0.02 (2nd retry), 0.04 (3rd retry)
    # Total: ~0.07 seconds
    # Allow some margin for execution time
    assert elapsed >= 0.05  # At least some delay
    assert elapsed < 0.2  # But not too much


@pytest.mark.asyncio
async def test_resilient_client_connection_state():
    """Test that connection state is tracked correctly."""
    mock_client = MockFailingClient(fail_count=1)

    resilient = ResilientDatabentoClient(
        inner=mock_client,
        max_retries=5,
        base_delay=0.01,
        max_delay=0.1,
    )

    # Initially disconnected
    assert resilient.connection_state == "disconnected"

    # Stream ticks - should eventually connect
    async for tick in resilient.stream_ticks():
        # After receiving first tick, should be connected
        assert resilient.connection_state == "connected"
        break


@pytest.mark.asyncio
async def test_resilient_client_closes_inner_on_error():
    """Test that inner client is closed on error for clean reconnection."""
    mock_client = MockFailingClient(fail_count=1)

    resilient = ResilientDatabentoClient(
        inner=mock_client,
        max_retries=5,
        base_delay=0.01,
        max_delay=0.1,
    )

    # Stream ticks - will fail once, then succeed
    async for tick in resilient.stream_ticks():
        break

    # Inner client should have been closed at least once during retry
    assert mock_client._closed


@pytest.mark.asyncio
async def test_resilient_client_backoff_on_normal_disconnect():
    """Test that ResilientDatabentoClient applies backoff when stream ends normally.

    This prevents tight reconnection loops when the server closes the connection
    cleanly (e.g., during rate limiting or maintenance).
    """
    # Create mock client that completes normally after 2 ticks
    mock_client = MockNormalDisconnectClient(ticks_per_connection=2)

    resilient = ResilientDatabentoClient(
        inner=mock_client,
        max_retries=5,
        base_delay=0.05,  # 50ms base (longer for reliable timing)
        max_delay=0.2,  # 200ms max
    )

    # Track timing and reconnection attempts
    start_time = asyncio.get_event_loop().time()
    ticks_received = []

    # Collect ticks - should get 2 from first connection, then backoff, then 2 more
    async for tick in resilient.stream_ticks():
        ticks_received.append(tick)

        # Stop after receiving ticks from 2 reconnections (4 ticks total)
        if len(ticks_received) >= 4:
            break

    elapsed = asyncio.get_event_loop().time() - start_time

    # Verify we received ticks from multiple reconnections
    assert len(ticks_received) >= 4  # 2 ticks per connection * 2 connections
    assert mock_client.attempt >= 2  # Should have reconnected at least once

    # Verify backoff was applied (should take at least base_delay between reconnections)
    # After first connection ends normally, should wait base_delay before reconnecting
    assert elapsed >= 0.05  # At least one base_delay period

    # Verify inner client was closed between reconnections
    assert mock_client._closed
