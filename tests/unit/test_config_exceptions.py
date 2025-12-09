"""Tests for ConfigError usage in configuration system."""

import tempfile
from pathlib import Path

import pytest
from common.config import load_config
from common.exceptions import ConfigError


def test_config_error_on_invalid_yaml():
    """Test that ConfigError is raised for invalid YAML syntax."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        # Invalid YAML - missing closing quote
        f.write(
            """
system:
  data_path: "./data/
  log_path: "./logs/"
"""
        )
        yaml_path = Path(f.name)

    try:
        with pytest.raises(ConfigError) as exc_info:
            load_config(yaml_path)

        assert "Failed to parse YAML file" in str(exc_info.value)
        assert exc_info.value.cause is not None
    finally:
        yaml_path.unlink()


def test_config_error_on_invalid_json():
    """Test that ConfigError is raised for invalid JSON syntax."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        # Invalid JSON - trailing comma
        f.write(
            """
{
  "system": {
    "data_path": "./data/",
  }
}
"""
        )
        json_path = Path(f.name)

    try:
        with pytest.raises(ConfigError) as exc_info:
            load_config(json_path)

        assert "Failed to parse JSON file" in str(exc_info.value)
        assert exc_info.value.cause is not None
    finally:
        json_path.unlink()


def test_config_error_on_unsupported_format():
    """Test that ConfigError is raised for unsupported file formats."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("some content")
        txt_path = Path(f.name)

    try:
        with pytest.raises(ConfigError) as exc_info:
            load_config(txt_path)

        assert "Unsupported configuration file format" in str(exc_info.value)
        assert ".txt" in str(exc_info.value)
    finally:
        txt_path.unlink()


def test_config_error_preserves_context():
    """Test that ConfigError stores file path context."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("invalid: yaml: content:")
        yaml_path = Path(f.name)

    try:
        with pytest.raises(ConfigError) as exc_info:
            load_config(yaml_path)

        assert hasattr(exc_info.value, "path")
        assert str(yaml_path) in exc_info.value.path
    finally:
        yaml_path.unlink()


def test_config_error_exception_chaining():
    """Test that ConfigError properly chains with underlying exceptions."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{invalid json}")
        json_path = Path(f.name)

    try:
        with pytest.raises(ConfigError) as exc_info:
            load_config(json_path)

        # Verify exception chaining
        assert exc_info.value.__cause__ is not None
        assert exc_info.value.cause is exc_info.value.__cause__
    finally:
        json_path.unlink()
