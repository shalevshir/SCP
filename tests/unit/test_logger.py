"""Tests for logging wrapper utility."""

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from common.config import SystemConfig, load_config
from common.logger import get_logger, setup_logging


def test_get_logger_returns_logger_instance():
    """Test that get_logger returns a Logger instance."""
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_logger_has_file_and_console_handlers():
    """Test that logger has both file and console handlers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "logs"
        config = SystemConfig(log_path=str(log_path), log_level="INFO")
        setup_logging(config)
        
        # Handlers are on root logger, child loggers propagate to it
        root_logger = logging.getLogger()
        handlers = root_logger.handlers
        
        # Should have at least file and console handlers
        handler_types = [type(h).__name__ for h in handlers]
        assert "RotatingFileHandler" in handler_types
        assert "StreamHandler" in handler_types


def test_logger_creates_log_directory():
    """Test that logger creates the logs/dev/ directory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "logs"
        config = SystemConfig(log_path=str(log_path), log_level="INFO")
        setup_logging(config)
        
        dev_log_dir = log_path / "dev"
        assert dev_log_dir.exists()
        assert dev_log_dir.is_dir()


def test_logger_uses_rotating_file_handler():
    """Test that logger uses RotatingFileHandler."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "logs"
        config = SystemConfig(log_path=str(log_path), log_level="INFO")
        setup_logging(config)
        
        # Handlers are on root logger
        root_logger = logging.getLogger()
        file_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) > 0
        assert file_handlers[0].maxBytes == 10 * 1024 * 1024  # 10MB
        assert file_handlers[0].backupCount == 5


def test_logger_respects_log_level_from_config():
    """Test that logger respects log level from config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "logs"
        config = SystemConfig(log_path=str(log_path), log_level="DEBUG")
        setup_logging(config)
        
        # Root logger level is set, child loggers inherit
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG


def test_logger_respects_env_log_level_override():
    """Test that logger respects SCP_LOG_LEVEL environment variable override."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "logs"
        config = SystemConfig(log_path=str(log_path), log_level="INFO")
        
        os.environ["SCP_LOG_LEVEL"] = "DEBUG"
        try:
            setup_logging(config)
            # Root logger level is set, child loggers inherit
            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG
        finally:
            os.environ.pop("SCP_LOG_LEVEL", None)


def test_logger_logs_to_file_and_console():
    """Test that logger writes messages to both file and console."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "logs"
        config = SystemConfig(log_path=str(log_path), log_level="INFO")
        setup_logging(config)
        
        logger = get_logger("test_module")
        test_message = "Test log message for file and console"
        logger.info(test_message)
        
        # Check file log
        log_file = log_path / "dev" / "app.log"
        assert log_file.exists()
        log_content = log_file.read_text()
        assert test_message in log_content


def test_get_logger_uses_module_name():
    """Test that get_logger uses the provided module name."""
    logger1 = get_logger("module1")
    logger2 = get_logger("module2")
    
    assert logger1.name == "module1"
    assert logger2.name == "module2"
    assert logger1 is not logger2


def test_logger_handles_missing_log_path_gracefully():
    """Test that logger handles missing log path gracefully by creating it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "nonexistent" / "logs"
        config = SystemConfig(log_path=str(log_path), log_level="INFO")
        
        # Should not raise an error, should create the directory
        setup_logging(config)
        assert log_path.exists()
        assert (log_path / "dev").exists()


def test_logger_integration_with_config_loading():
    """Test that logger works with actual config loading from load_config()."""
    config_path = Path(__file__).parent.parent.parent / "config" / "core.yaml"
    config = load_config(config_path)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override log_path for testing
        config.system.log_path = str(Path(tmpdir) / "logs")
        setup_logging(config.system)
        
        logger = get_logger("integration_test")
        logger.info("Integration test message")
        
        log_file = Path(config.system.log_path) / "dev" / "app.log"
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "Integration test message" in log_content

