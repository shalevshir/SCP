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
from scp_shared.validation.trading_sessions import (
    SESSION_ENCODING,
    SESSION_WINDOWS,
    SessionWindow,
    TradingSession,
    format_session_for_display,
    get_current_session,
    get_session_info,
    is_session_tradeable,
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
    # Trading sessions
    "TradingSession",
    "SessionWindow",
    "SESSION_WINDOWS",
    "SESSION_ENCODING",
    "get_current_session",
    "is_session_tradeable",
    "get_session_info",
    "format_session_for_display",
]
