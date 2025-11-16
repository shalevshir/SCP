"""Signal logger for RuleEngine.

This module provides functionality to log signals to JSONL files for
auditability and post-session analysis. Signals are organized by date
in separate files.
"""

import json
from datetime import datetime
from pathlib import Path

from rule_engine.signal import Signal


def signal_to_dict(signal: Signal) -> dict:
    """Convert Signal object to JSON-serializable dictionary.

    Args:
        signal: Signal object to convert

    Returns:
        Dictionary with all signal fields, timestamp as ISO format string

    Example:
        >>> signal = Signal(...)
        >>> signal_dict = signal_to_dict(signal)
        >>> json.dumps(signal_dict)  # JSON serializable
    """
    return {
        "timestamp": signal.timestamp.isoformat(),
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "direction": signal.direction,
        "setup_type": signal.setup_type,
        "htf_bias": signal.htf_bias,
        "score": signal.score,
        "confidence": signal.confidence,
        "factors": signal.factors,
        "rationale": signal.rationale,
        "validation_flags": signal.validation_flags,
        "enforcer_tier": signal.enforcer_tier,
    }


def log_signal(signal: Signal, log_dir: str | None = None) -> None:
    """Log signal to JSONL file organized by date.

    Signals are written to files named YYYY-MM-DD.jsonl in the log directory.
    Each signal is written as a single line of JSON (JSONL format) for easy
    parsing and streaming analysis.

    Args:
        signal: Signal object to log
        log_dir: Optional custom log directory path. If None, uses default
                logs/signals/ from project root.

    Example:
        >>> signal = Signal(...)
        >>> log_signal(signal)  # Logs to logs/signals/2025-01-01.jsonl
    """
    # Determine log directory
    if log_dir is None:
        # Default to logs/signals/ from project root
        project_root = Path(__file__).parent.parent
        log_dir_path = project_root / "logs" / "signals"
    else:
        log_dir_path = Path(log_dir)

    # Create directory if it doesn't exist
    log_dir_path.mkdir(parents=True, exist_ok=True)

    # Determine log file name based on signal timestamp
    date_str = signal.timestamp.strftime("%Y-%m-%d")
    log_file = log_dir_path / f"{date_str}.jsonl"

    # Convert signal to dict
    signal_dict = signal_to_dict(signal)

    # Append to file as single line of JSON
    with open(log_file, "a") as f:
        json.dump(signal_dict, f)
        f.write("\n")

