"""Centralized logging utility with rotating file handlers and console output."""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common.config import SystemConfig

# Module-level flag to track if logging has been initialized
_logging_initialized = False


def setup_logging(config: "SystemConfig") -> None:
    """Initialize logging configuration with file and console handlers.

    Args:
        config: SystemConfig instance containing log_path and log_level settings

    The logging system is configured with:
    - RotatingFileHandler writing to {log_path}/dev/app.log
    - Console handler for real-time output
    - Log rotation: max 10MB per file, keep 5 backup files
    - Log format: timestamp - logger name - level - message
    """
    global _logging_initialized

    # Determine log level (environment variable takes precedence)
    log_level_str = os.environ.get("SCP_LOG_LEVEL", config.log_level).upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Create log directory structure
    log_path = Path(config.log_path)
    dev_log_dir = log_path / "dev"
    dev_log_dir.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler with rotation
    log_file = dev_log_dir / "app.log"
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    _logging_initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger instance for the given module name.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Logger instance configured with file and console handlers

    Note:
        If logging hasn't been initialized via setup_logging(), this will
        return a logger that inherits from the root logger (which may not
        have handlers configured). It's recommended to call setup_logging()
        before using get_logger().
    """
    return logging.getLogger(name)

