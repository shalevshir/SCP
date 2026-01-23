"""Validation layer for SCP trading bot.

This module provides schema definitions and validation logic for ensuring
trade signals comply with SOP (Standard Operating Procedure), CEO directives,
and risk management rules before execution.
"""

from scp_shared.validation.config_loader import load_session_config
from scp_shared.validation.guardrails import (
    BehaviorGuardrails,
    BehaviorState,
    BehaviorStateTracker,
    GuardrailResult,
)
from scp_shared.validation.session_validator import (
    SeasonRule,
    SessionConfig,
    SessionConstraints,
    SessionResult,
    SessionValidator,
)

__all__ = [
    "BehaviorGuardrails",
    "BehaviorState",
    "BehaviorStateTracker",
    "GuardrailResult",
    "SeasonRule",
    "SessionConfig",
    "SessionConstraints",
    "SessionResult",
    "SessionValidator",
    "load_session_config",
]
