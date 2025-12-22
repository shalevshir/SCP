"""Tests for retry logic with exponential backoff."""

import asyncio

import pytest
import redis.asyncio as redis

from scp_shared.messaging.retry import RetryConfig, with_retry


class TestRetryConfig:
    """Test retry configuration."""

    def test_default_config(self) -> None:
        """RetryConfig has sensible defaults."""
        config = RetryConfig()

        assert config.initial_delay_ms == 100
        assert config.max_delay_ms == 30000
        assert config.multiplier == 2.0
        assert config.max_retries == 5
        assert config.jitter == 0.2

    def test_custom_config(self) -> None:
        """Can customize retry configuration."""
        config = RetryConfig(
            initial_delay_ms=50,
            max_delay_ms=10000,
            multiplier=1.5,
            max_retries=3,
            jitter=0.1,
        )

        assert config.initial_delay_ms == 50
        assert config.max_delay_ms == 10000
        assert config.multiplier == 1.5
        assert config.max_retries == 3
        assert config.jitter == 0.1


class TestWithRetryDecorator:
    """Test retry decorator functionality."""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self) -> None:
        """Successful calls don't trigger retries."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3))
        async def successful_operation() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_operation()

        assert result == "success"
        assert call_count == 1  # Called only once

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self) -> None:
        """Retries on Redis connection errors."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, initial_delay_ms=10))
        async def failing_then_success() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise redis.ConnectionError("Connection refused")
            return "success"

        result = await failing_then_success()

        assert result == "success"
        assert call_count == 3  # Failed twice, succeeded on third

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises(self) -> None:
        """Raises original exception when max retries exceeded."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=2, initial_delay_ms=10))
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise redis.ConnectionError("Connection refused")

        with pytest.raises(redis.ConnectionError, match="Connection refused"):
            await always_fails()

        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self) -> None:
        """Delays increase exponentially between retries."""
        call_times: list[float] = []

        @with_retry(
            RetryConfig(
                max_retries=3,
                initial_delay_ms=100,
                multiplier=2.0,
                jitter=0.0,  # No jitter for predictable timing
            )
        )
        async def failing_operation() -> str:
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 3:
                raise redis.ConnectionError("Connection refused")
            return "success"

        await failing_operation()

        # Check that delays increase
        assert len(call_times) == 3
        
        # First retry delay: ~100ms
        delay1 = (call_times[1] - call_times[0]) * 1000
        assert 90 <= delay1 <= 110  # Allow some tolerance

        # Second retry delay: ~200ms (100 * 2)
        delay2 = (call_times[2] - call_times[1]) * 1000
        assert 190 <= delay2 <= 210

    @pytest.mark.asyncio
    async def test_jitter_applied_to_delay(self) -> None:
        """Jitter randomizes delay to prevent thundering herd."""
        call_times: list[float] = []

        @with_retry(
            RetryConfig(
                max_retries=1,
                initial_delay_ms=100,
                jitter=0.2,  # 20% jitter
            )
        )
        async def failing_once() -> str:
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 2:
                raise redis.ConnectionError("Connection refused")
            return "success"

        await failing_once()

        # Check delay is within jitter range (80ms to 120ms with 20% jitter)
        # Allow small tolerance for event loop scheduling overhead
        delay = (call_times[1] - call_times[0]) * 1000
        assert 80 <= delay <= 125  # Allow up to 5ms overhead for event loop scheduling

    @pytest.mark.asyncio
    async def test_max_delay_cap(self) -> None:
        """Delay is capped at max_delay_ms."""
        call_times: list[float] = []

        @with_retry(
            RetryConfig(
                max_retries=5,
                initial_delay_ms=100,
                max_delay_ms=150,  # Cap at 150ms
                multiplier=2.0,
                jitter=0.0,
            )
        )
        async def failing_operation() -> str:
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 4:
                raise redis.ConnectionError("Connection refused")
            return "success"

        await failing_operation()

        # After first retry (100ms), second retry would be 200ms but capped at 150ms
        delay2 = (call_times[2] - call_times[1]) * 1000
        assert 145 <= delay2 <= 155

        # Third retry should also be capped at 150ms
        delay3 = (call_times[3] - call_times[2]) * 1000
        assert 145 <= delay3 <= 155

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self) -> None:
        """Non-connection errors are not retried."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3))
        async def failing_with_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid value")

        with pytest.raises(ValueError, match="Invalid value"):
            await failing_with_value_error()

        assert call_count == 1  # No retries for non-connection errors

    @pytest.mark.asyncio
    async def test_retry_with_args_and_kwargs(self) -> None:
        """Decorated functions can accept arguments."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=2, initial_delay_ms=10))
        async def operation_with_args(x: int, y: int, message: str = "default") -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise redis.ConnectionError("Connection refused")
            return f"{message}: {x + y}"

        result = await operation_with_args(5, 3, message="sum")

        assert result == "sum: 8"
        assert call_count == 2

