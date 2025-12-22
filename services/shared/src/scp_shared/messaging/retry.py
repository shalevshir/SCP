"""Retry logic with exponential backoff for Redis operations."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

import redis.asyncio as redis
from pydantic import BaseModel, Field

T = TypeVar("T")


class RetryConfig(BaseModel):
    """Configuration for retry logic with exponential backoff.
    
    Example:
        >>> config = RetryConfig(
        ...     initial_delay_ms=100,
        ...     max_delay_ms=30000,
        ...     max_retries=5,
        ... )
    """

    initial_delay_ms: int = Field(
        default=100,
        description="Initial delay in milliseconds",
        ge=1,
    )
    max_delay_ms: int = Field(
        default=30000,
        description="Maximum delay in milliseconds (30 seconds)",
        ge=1,
    )
    multiplier: float = Field(
        default=2.0,
        description="Multiplier for exponential backoff",
        gt=1.0,
    )
    max_retries: int = Field(
        default=5,
        description="Maximum number of retry attempts",
        ge=0,
    )
    jitter: float = Field(
        default=0.2,
        description="Jitter factor (0.2 = +/- 20% randomization)",
        ge=0.0,
        le=1.0,
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff and jitter.
        
        Args:
            attempt: Retry attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        # Calculate exponential delay
        delay_ms = min(
            self.initial_delay_ms * (self.multiplier ** attempt),
            self.max_delay_ms,
        )

        # Apply jitter to prevent thundering herd
        if self.jitter > 0:
            jitter_range = delay_ms * self.jitter
            delay_ms = delay_ms + random.uniform(-jitter_range, jitter_range)

        # Convert to seconds and ensure non-negative
        return max(0.0, delay_ms / 1000.0)


def with_retry(
    config: RetryConfig | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator to add retry logic with exponential backoff to async functions.
    
    Retries on Redis connection errors. Other exceptions are raised immediately.
    
    Args:
        config: Retry configuration (uses defaults if None)
        
    Example:
        >>> @with_retry(RetryConfig(max_retries=3))
        ... async def publish_message(stream: str, data: dict) -> str:
        ...     return await redis_client.xadd(stream, data)
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (
                    redis.ConnectionError,
                    redis.TimeoutError,
                    ConnectionRefusedError,
                    ConnectionResetError,
                ) as e:
                    last_exception = e

                    # If this was the last attempt, raise the exception
                    if attempt >= config.max_retries:
                        raise

                    # Calculate delay and wait
                    delay = config.calculate_delay(attempt)
                    await asyncio.sleep(delay)

            # This should never be reached, but satisfies type checker
            if last_exception:
                raise last_exception
            return None  # type: ignore[return-value]

        return wrapper

    return decorator

