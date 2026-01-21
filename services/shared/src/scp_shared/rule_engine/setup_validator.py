"""Config-driven setup validator.

This module provides a configuration-driven approach to validating trading setups.
Instead of hardcoding validation logic in Python, constraints are defined as
expressions in config/setups.yaml and evaluated at runtime.

Example:
    >>> validator = SetupValidator()
    >>> context = {"rsi": 35, "structure_clarity": 0.6, ...}
    >>> result = validator.validate_setup("VWAP_FADE", context)
    >>> if result.is_valid:
    ...     print("Setup is valid!")
    ... else:
    ...     print(f"Rejected: {result.reject_reason}")
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scp_shared.common.logger import get_logger
from scp_shared.rule_engine.expression_eval import (
    ExpressionEvalError,
    evaluate_expression,
    validate_expression_syntax,
)

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of setup validation.

    Attributes:
        is_valid: Whether the setup passed all constraints
        reject_reason: Reason for rejection (if is_valid is False)
        failed_constraint: Name of the constraint that failed (if any)
        evaluated_constraints: List of constraint names that were evaluated
    """

    is_valid: bool
    reject_reason: str | None = None
    failed_constraint: str | None = None
    evaluated_constraints: list[str] = field(default_factory=list)


def load_setups_config(config_path: str | None = None) -> dict[str, Any]:
    """Load setups configuration from YAML file.

    Args:
        config_path: Path to setups config file. If None, loads default
                    config/setups.yaml from project root or /config (Docker).

    Returns:
        Dictionary containing parsed configuration

    Raises:
        FileNotFoundError: If config file not found
        yaml.YAMLError: If YAML parsing fails
    """
    if config_path is None:
        # Try multiple locations:
        # 1. /config/setups.yaml (Docker container mount)
        # 2. config/setups.yaml from project root (local development)
        docker_config = Path("/config/setups.yaml")
        if docker_config.exists():
            config_path = str(docker_config)
        else:
            # Navigate from services/shared/src/scp_shared/rule_engine to project root
            project_root = Path(__file__).parent.parent.parent.parent.parent.parent
            config_path = str(project_root / "config" / "setups.yaml")

    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Setups config file not found: {config_path}")

    with open(config_file) as f:
        config_data = yaml.safe_load(f)

    # Validate configuration structure
    _validate_setups_config(config_data)

    return config_data


def _validate_setups_config(config_data: dict[str, Any]) -> None:
    """Validate setups configuration structure.

    Args:
        config_data: Dictionary containing configuration data

    Raises:
        ValueError: If validation fails
    """
    if "setups" not in config_data:
        raise ValueError("Missing required key: 'setups'")

    setups = config_data["setups"]
    if not isinstance(setups, dict):
        raise ValueError("'setups' must be a dictionary")

    for setup_name, setup_config in setups.items():
        # Check required fields
        required_fields = ["enabled", "min_score", "constraints", "weights"]
        for field_name in required_fields:
            if field_name not in setup_config:
                raise ValueError(
                    f"Setup '{setup_name}' missing required field: {field_name}"
                )

        # Validate constraints
        constraints = setup_config["constraints"]
        if not isinstance(constraints, dict):
            raise ValueError(f"Setup '{setup_name}' constraints must be a dictionary")

        for constraint_name, constraint in constraints.items():
            if "expression" not in constraint:
                raise ValueError(
                    f"Constraint '{setup_name}.{constraint_name}' "
                    "missing 'expression'"
                )
            if "reject_reason" not in constraint:
                raise ValueError(
                    f"Constraint '{setup_name}.{constraint_name}' "
                    "missing 'reject_reason'"
                )

            # Validate expression syntax
            expression = constraint["expression"]
            is_valid, error = validate_expression_syntax(expression)
            if not is_valid:
                raise ValueError(
                    f"Invalid expression in '{setup_name}.{constraint_name}': {error}"
                )

        # Validate weights
        weights = setup_config["weights"]
        if not isinstance(weights, dict):
            raise ValueError(f"Setup '{setup_name}' weights must be a dictionary")


class SetupValidator:
    """Config-driven setup validator.

    Loads setup configuration from YAML and validates setups against
    feature data using expression evaluation.

    Example:
        >>> validator = SetupValidator()
        >>> context = {
        ...     "rsi": 35.0,
        ...     "structure_clarity": 0.6,
        ...     "direction": "long",
        ...     ...
        ... }
        >>> result = validator.validate_setup("VWAP_FADE", context)
        >>> print(f"Valid: {result.is_valid}, Reason: {result.reject_reason}")
    """

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize validator with configuration.

        Args:
            config_path: Optional path to setups.yaml. If None, uses default.
        """
        self._config = load_setups_config(config_path)
        self._setups = self._config["setups"]

    def is_setup_enabled(self, setup_name: str) -> bool:
        """Check if a setup is enabled.

        Args:
            setup_name: Name of the setup (e.g., "VWAP_RECLAIM")

        Returns:
            True if setup exists and is enabled, False otherwise
        """
        if setup_name not in self._setups:
            return False
        return self._setups[setup_name].get("enabled", False)

    def get_enabled_setups(self) -> list[str]:
        """Get list of all enabled setup names.

        Returns:
            List of enabled setup names
        """
        return [
            name
            for name, config in self._setups.items()
            if config.get("enabled", False)
        ]

    def get_setup_params(self, setup_name: str) -> dict[str, Any] | None:
        """Get parameters for a setup.

        Args:
            setup_name: Name of the setup

        Returns:
            Dictionary of parameters or None if setup not found
        """
        if setup_name not in self._setups:
            return None
        return self._setups[setup_name].get("params")

    def get_setup_weights(self, setup_name: str) -> dict[str, float] | None:
        """Get factor weights for a setup.

        Args:
            setup_name: Name of the setup

        Returns:
            Dictionary of weights or None if setup not found
        """
        if setup_name not in self._setups:
            return None
        return self._setups[setup_name].get("weights")

    def get_setup_min_score(self, setup_name: str) -> float | None:
        """Get minimum score for a setup.

        Args:
            setup_name: Name of the setup

        Returns:
            Minimum score or None if setup not found
        """
        if setup_name not in self._setups:
            return None
        return self._setups[setup_name].get("min_score")

    def validate_setup(
        self,
        setup_name: str,
        context: dict[str, Any],
    ) -> ValidationResult:
        """Validate a setup against context data.

        Evaluates all constraints defined for the setup against the provided
        context. All constraints must pass for the setup to be valid.

        Args:
            setup_name: Name of the setup to validate
            context: Dictionary of feature values and computed data

        Returns:
            ValidationResult with is_valid flag and rejection reason if any

        Example:
            >>> context = {
            ...     "structure_1h": "HH",
            ...     "structure_clarity": 0.6,
            ...     "close": 2650.0,
            ...     "vwap": 2645.0,
            ...     "direction": "long",
            ...     ...
            ... }
            >>> result = validator.validate_setup("VWAP_RECLAIM", context)
        """
        # Check if setup exists
        if setup_name not in self._setups:
            return ValidationResult(
                is_valid=False,
                reject_reason=f"Unknown setup: {setup_name}",
            )

        # Check if setup is enabled
        setup_config = self._setups[setup_name]
        if not setup_config.get("enabled", False):
            return ValidationResult(
                is_valid=False,
                reject_reason=f"Setup '{setup_name}' is disabled",
            )

        # Evaluate all constraints
        constraints = setup_config["constraints"]
        evaluated = []

        for constraint_name, constraint in constraints.items():
            expression = constraint["expression"]
            reject_reason = constraint["reject_reason"]

            try:
                result = evaluate_expression(expression, context)
                evaluated.append(constraint_name)

                if not result:
                    logger.debug(
                        f"Setup {setup_name} failed constraint '{constraint_name}': "
                        f"expression='{expression}' evaluated to False"
                    )
                    return ValidationResult(
                        is_valid=False,
                        reject_reason=reject_reason,
                        failed_constraint=constraint_name,
                        evaluated_constraints=evaluated,
                    )

            except ExpressionEvalError as e:
                # Log the error but treat missing variables as constraint failure
                logger.warning(
                    f"Expression error in {setup_name}.{constraint_name}: {e}"
                )
                return ValidationResult(
                    is_valid=False,
                    reject_reason=f"Constraint evaluation error: {e.reason}",
                    failed_constraint=constraint_name,
                    evaluated_constraints=evaluated,
                )

        # All constraints passed
        logger.debug(
            f"Setup {setup_name} passed all {len(constraints)} constraints"
        )
        return ValidationResult(
            is_valid=True,
            evaluated_constraints=evaluated,
        )

    def validate_all_setups(
        self,
        context: dict[str, Any],
    ) -> dict[str, ValidationResult]:
        """Validate all enabled setups against context.

        Args:
            context: Dictionary of feature values

        Returns:
            Dictionary mapping setup names to ValidationResult
        """
        results = {}
        for setup_name in self.get_enabled_setups():
            results[setup_name] = self.validate_setup(setup_name, context)
        return results

    def get_valid_setups(
        self,
        context: dict[str, Any],
    ) -> list[str]:
        """Get list of setups that pass validation.

        Args:
            context: Dictionary of feature values

        Returns:
            List of setup names that passed validation
        """
        results = self.validate_all_setups(context)
        return [name for name, result in results.items() if result.is_valid]


# Singleton instance for convenience
_validator: SetupValidator | None = None


def get_setup_validator() -> SetupValidator:
    """Get singleton SetupValidator instance.

    Returns:
        Shared SetupValidator instance

    Example:
        >>> validator = get_setup_validator()
        >>> result = validator.validate_setup("VWAP_RECLAIM", context)
    """
    global _validator
    if _validator is None:
        _validator = SetupValidator()
    return _validator


def reset_setup_validator() -> None:
    """Reset singleton validator (for testing)."""
    global _validator
    _validator = None
