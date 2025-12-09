"""Signal logger for RuleEngine.

This module provides functionality to log signals to JSONL files for
auditability and post-session analysis. Signals are organized by date
in separate files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from rule_engine.signal import Signal

if TYPE_CHECKING:
    from validation.engine import ValidationResult
    from validation.guardrails import BehaviorState
    from validation.session_validator import SessionConstraints


def signal_to_dict(
    signal: Signal,
    validation_result: ValidationResult | None = None,
    session_constraints: SessionConstraints | None = None,
    behavior_state: BehaviorState | None = None,
) -> dict:
    """Convert Signal object to JSON-serializable dictionary with validation details.

    Args:
        signal: Signal object to convert
        validation_result: Optional ValidationResult from ValidationEngine
        session_constraints: Optional SessionConstraints from SessionValidator
        behavior_state: Optional BehaviorState from BehaviorStateTracker

    Returns:
        Dictionary with all signal fields and optional validation context

    Example:
        >>> signal = Signal(...)
        >>> signal_dict = signal_to_dict(signal, validation_result, session_constraints)
        >>> json.dumps(signal_dict)  # JSON serializable
    """
    base_dict = {
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

    # Add validation result if provided
    if validation_result is not None:
        base_dict["validation_result"] = {
            "valid": validation_result.valid,
            "errors": validation_result.errors,
            "enforced_tier": validation_result.enforced_tier,
        }

    # Add session constraints if provided
    if session_constraints is not None:
        base_dict["session_constraints"] = {
            "name": session_constraints.name,
            "window": f"{session_constraints.window_start.strftime('%H:%M')}-{session_constraints.window_end.strftime('%H:%M')}",
            "allowed_tiers": list(session_constraints.allowed_tiers),
            "allowed_setups": list(session_constraints.allowed_setups),
            "min_score": session_constraints.min_score,
            "max_losses": session_constraints.max_losses,
            "dxy_correlation_max": session_constraints.dxy_correlation_max,
        }

    # Add behavior state if provided
    if behavior_state is not None:
        base_dict["guardrail_state"] = {
            "consecutive_losses": behavior_state.consecutive_losses,
            "fatigue_flag": behavior_state.fatigue_flag,
            "session_extended": behavior_state.session_extended,
            "last_reset": (
                behavior_state.last_reset.isoformat()
                if behavior_state.last_reset
                else None
            ),
        }

    return base_dict


def log_signal(
    signal: Signal,
    log_dir: str | None = None,
    validation_result: ValidationResult | None = None,
    session_constraints: SessionConstraints | None = None,
    behavior_state: BehaviorState | None = None,
) -> None:
    """Log signal to JSONL file with full validation context.

    Signals are written to files named YYYY-MM-DD.jsonl in the log directory.
    Each signal is written as a single line of JSON (JSONL format) for easy
    parsing and streaming analysis.

    Args:
        signal: Signal object to log
        log_dir: Optional custom log directory path. If None, uses default
                logs/signals/ from project root.
        validation_result: Optional ValidationResult from ValidationEngine
        session_constraints: Optional SessionConstraints from SessionValidator
        behavior_state: Optional BehaviorState from BehaviorStateTracker

    Example:
        >>> signal = Signal(...)
        >>> validation_result = validation_engine.validate(...)
        >>> log_signal(signal, validation_result=validation_result)
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

    # Convert signal to dict with validation details
    signal_dict = signal_to_dict(
        signal,
        validation_result=validation_result,
        session_constraints=session_constraints,
        behavior_state=behavior_state,
    )

    # Append to file as single line of JSON
    with open(log_file, "a") as f:
        json.dump(signal_dict, f)
        f.write("\n")
