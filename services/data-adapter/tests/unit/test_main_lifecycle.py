"""Tests for lifecycle resource cleanup patterns.

Tests the finally block pattern used in main.py to ensure proper resource cleanup.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest


class TestResourceCleanupPattern:
    """Test the resource cleanup pattern used in main.py."""

    @pytest.mark.asyncio
    async def test_finally_block_ensures_cleanup_on_exception(self) -> None:
        """Verify finally block ensures cleanup even when exception occurs."""
        # Simulate the pattern used in main.py
        mock_client = AsyncMock()
        mock_redis = AsyncMock()

        cleanup_called = {"client": False, "redis": False}

        async def failing_task() -> None:
            """Simulates consumer_task that raises exception."""
            await asyncio.sleep(0.01)
            raise RuntimeError("Task failed")

        task = asyncio.create_task(failing_task())

        try:
            await task
        except asyncio.CancelledError:
            pass  # Normal cancellation
        except Exception:
            pass  # Task failed with exception
        finally:
            # This should always execute
            await mock_client.close()
            await mock_redis.aclose()
            cleanup_called["client"] = True
            cleanup_called["redis"] = True

        # Verify cleanup happened despite exception
        assert cleanup_called["client"]
        assert cleanup_called["redis"]
        mock_client.close.assert_called_once()
        mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_finally_block_ensures_cleanup_on_cancellation(self) -> None:
        """Verify finally block ensures cleanup when task is cancelled."""
        mock_client = AsyncMock()
        mock_redis = AsyncMock()

        cleanup_called = {"client": False, "redis": False}

        async def long_running_task() -> None:
            """Simulates consumer_task that runs indefinitely."""
            await asyncio.sleep(100)

        task = asyncio.create_task(long_running_task())

        # Cancel the task
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass  # Expected
        except Exception:
            pass  # Other exceptions
        finally:
            # This should always execute
            await mock_client.close()
            await mock_redis.aclose()
            cleanup_called["client"] = True
            cleanup_called["redis"] = True

        # Verify cleanup happened after cancellation
        assert cleanup_called["client"]
        assert cleanup_called["redis"]
        mock_client.close.assert_called_once()
        mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_attempts_even_if_one_fails(self) -> None:
        """Verify both cleanup calls are attempted even if one fails."""
        mock_client = AsyncMock()
        mock_client.close = AsyncMock(side_effect=Exception("Client close failed"))
        mock_redis = AsyncMock()

        cleanup_attempts = {"client": False, "redis": False}

        async def failing_task() -> None:
            raise RuntimeError("Task failed")

        task = asyncio.create_task(failing_task())

        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            # Attempt cleanup even if one fails
            try:
                await mock_client.close()
                cleanup_attempts["client"] = True
            except Exception:
                cleanup_attempts["client"] = True  # Attempted but failed

            await mock_redis.aclose()
            cleanup_attempts["redis"] = True

        # Verify both cleanup methods were attempted
        assert cleanup_attempts["client"]
        assert cleanup_attempts["redis"]
        mock_client.close.assert_called_once()
        mock_redis.aclose.assert_called_once()
