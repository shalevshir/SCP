"""Tests for exception hierarchy."""


from common.exceptions import (
    AppError,
    ConfigError,
    DataSourceError,
    NormalizationError,
)


def test_app_error_is_base_exception():
    """Test that AppError inherits from Exception."""
    error = AppError("Test error")
    assert isinstance(error, Exception)
    assert isinstance(error, AppError)


def test_app_error_with_message():
    """Test that AppError stores and displays message correctly."""
    message = "Something went wrong"
    error = AppError(message)

    assert error.message == message
    assert str(error) == message


def test_app_error_with_cause():
    """Test that AppError properly chains exceptions."""
    original_error = ValueError("Original error")
    message = "Wrapped error"

    error = AppError(message, cause=original_error)

    assert error.message == message
    assert error.cause is original_error


def test_app_error_with_context_attributes():
    """Test that AppError accepts and stores custom context attributes."""
    error = AppError("Configuration failed", path="/path/to/file", line_number=42)

    assert error.message == "Configuration failed"
    assert error.path == "/path/to/file"
    assert error.line_number == 42


def test_config_error_inherits_from_app_error():
    """Test that ConfigError inherits from AppError."""
    error = ConfigError("Config error")

    assert isinstance(error, AppError)
    assert isinstance(error, ConfigError)
    assert isinstance(error, Exception)


def test_data_source_error_inherits_from_app_error():
    """Test that DataSourceError inherits from AppError."""
    error = DataSourceError("Data source error")

    assert isinstance(error, AppError)
    assert isinstance(error, DataSourceError)
    assert isinstance(error, Exception)


def test_normalization_error_inherits_from_app_error():
    """Test that NormalizationError inherits from AppError."""
    error = NormalizationError("Normalization error")

    assert isinstance(error, AppError)
    assert isinstance(error, NormalizationError)
    assert isinstance(error, Exception)


def test_exception_str_representation():
    """Test that exceptions have clear string representations."""
    error1 = AppError("Base error")
    assert str(error1) == "Base error"

    error2 = ConfigError("Invalid YAML")
    assert str(error2) == "Invalid YAML"

    error3 = DataSourceError("Connection failed")
    assert str(error3) == "Connection failed"


def test_exception_chaining_preserves_traceback():
    """Test that exception chaining with 'from' preserves original traceback."""
    try:
        try:
            raise ValueError("Original error")
        except ValueError as e:
            raise ConfigError("Wrapped error", cause=e) from e
    except ConfigError as config_err:
        assert config_err.message == "Wrapped error"
        assert config_err.cause is not None
        assert isinstance(config_err.cause, ValueError)
        assert str(config_err.cause) == "Original error"
        # Check that __cause__ is set (used by traceback)
        assert config_err.__cause__ is not None


def test_exception_repr():
    """Test that exceptions have useful repr."""
    error = ConfigError("Test error")
    repr_str = repr(error)

    assert "ConfigError" in repr_str
    assert "Test error" in repr_str


def test_multiple_context_attributes():
    """Test that multiple context attributes work correctly."""
    error = DataSourceError(
        "Failed to load data",
        source="CSV",
        file_path="/data/market.csv",
        row_count=1000,
        error_row=500,
    )

    assert error.source == "CSV"
    assert error.file_path == "/data/market.csv"
    assert error.row_count == 1000
    assert error.error_row == 500


def test_exception_hierarchy():
    """Test the complete exception hierarchy."""
    # All custom exceptions should be catchable as AppError
    exceptions = [
        ConfigError("config"),
        DataSourceError("data"),
        NormalizationError("norm"),
    ]

    for exc in exceptions:
        assert isinstance(exc, AppError)

    # But they should be distinct types
    assert not isinstance(ConfigError("test"), DataSourceError)
    assert not isinstance(DataSourceError("test"), NormalizationError)
    assert not isinstance(NormalizationError("test"), ConfigError)
