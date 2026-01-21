"""Rule engine package for SCP trading bot."""

from scp_shared.rule_engine.config_loader import ScoringConfig, load_scoring_config
from scp_shared.rule_engine.expression_eval import (
    ExpressionEvalError,
    evaluate_expression,
)
from scp_shared.rule_engine.scoring import score_signal
from scp_shared.rule_engine.setup_validator import (
    SetupValidator,
    ValidationResult,
    get_setup_validator,
    load_setups_config,
)
from scp_shared.rule_engine.signal import Signal

__all__ = [
    "Signal",
    "score_signal",
    "ScoringConfig",
    "load_scoring_config",
    # New config-driven setup validation
    "SetupValidator",
    "ValidationResult",
    "get_setup_validator",
    "load_setups_config",
    "evaluate_expression",
    "ExpressionEvalError",
]
