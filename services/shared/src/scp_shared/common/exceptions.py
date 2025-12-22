"""Exception hierarchy for SCP application.

This module defines a consistent exception hierarchy with a base AppError
and domain-specific exceptions for different parts of the application.
"""

from typing import Any


class AppError(Exception):
    """Base exception for all SCP application errors.

    This is the root of the SCP exception hierarchy. All custom exceptions
    in the application should inherit from this class.

    Args:
        message: Human-readable error message
        *args: Additional positional arguments passed to Exception
        cause: Optional original exception that caused this error
        **kwargs: Additional context attributes stored on the exception

    Attributes:
        message: The error message
        cause: The original exception if this wraps another exception
        Additional attributes from kwargs are available as instance attributes

    Example:
        >>> try:
        ...     risky_operation()
        ... except ValueError as e:
        ...     raise AppError("Operation failed", cause=e, context="data") from e
    """

    def __init__(
        self,
        message: str,
        *args: Any,
        cause: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize AppError with message and optional context."""
        super().__init__(message, *args)
        self.message = message
        self.cause = cause

        # Store additional context as instance attributes
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self) -> str:
        """Return the error message."""
        return self.message

    def __repr__(self) -> str:
        """Return a detailed representation of the error."""
        return f"{self.__class__.__name__}('{self.message}')"


class ConfigError(AppError):
    """Configuration-related errors.

    Raised when there are issues with configuration loading, parsing,
    or validation. This includes:
    - Invalid YAML/JSON syntax
    - Missing required configuration parameters
    - Invalid configuration values
    - Unsupported configuration formats

    Example:
        >>> raise ConfigError(
        ...     "Invalid log level",
        ...     path="config/core.yaml",
        ...     field="system.log_level",
        ...     value="INVALID"
        ... )
    """

    pass


class DataSourceError(AppError):
    """Data loading and connection errors.

    Raised when there are issues accessing or loading data from external
    sources. This includes:
    - File access failures
    - API connection errors
    - Database connection issues
    - Data file format problems

    Example:
        >>> raise DataSourceError(
        ...     "Failed to load CSV file",
        ...     path="/data/market.csv",
        ...     source="local_filesystem"
        ... )
    """

    pass


class NormalizationError(AppError):
    """Data normalization and validation errors.

    Raised when data doesn't meet expected schema or quality requirements.
    This includes:
    - Schema mismatches
    - Missing required fields
    - Invalid data types
    - Data quality issues

    Example:
        >>> raise NormalizationError(
        ...     "Missing required column",
        ...     column="close_price",
        ...     available_columns=["open", "high", "low"]
        ... )
    """

    pass

