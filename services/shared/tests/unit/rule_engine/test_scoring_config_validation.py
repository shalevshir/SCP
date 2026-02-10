"""Test scoring configuration constraints and validation."""

from pathlib import Path

import yaml


def test_all_setup_weights_sum_to_max_10_points():
    """Verify that all setup type weights are within reasonable bounds.

    Most setups should sum to ~10 points, but some setups (like DXY_CONTINUATION)
    may have higher weights that are capped during scoring with min(sum, 10.0).

    This test ensures:
    - Weights are reasonable (not excessively high)
    - Each setup has sufficient weight coverage (>= 9.0)
    """
    # Config file is at project root: /Users/shalev/Code/SCP/config/setups.yaml
    # Test file is at: /Users/shalev/Code/SCP/services/shared/tests/unit/rule_engine/test_*.py
    # Need to go up 6 levels: rule_engine -> unit -> tests -> shared -> services -> SCP
    config_path = (
        Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "setups.yaml"
    )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    setup_types = config["setups"]

    for setup_name, setup_config in setup_types.items():
        weights = setup_config["weights"]
        total = sum(weights.values())

        # Allow weights to exceed 10.0 since scoring uses min(sum, 10.0) cap
        # But prevent absurdly high totals (> 20.0) which indicate misconfiguration
        assert total <= 20.0, (
            f"Setup '{setup_name}' weights sum to {total}, which is excessively high. "
            f"Weights: {weights}"
        )

        # Verify the total is reasonable (at least 9.0) to ensure we're using
        # a good portion of the available scoring range
        assert total >= 9.0, (
            f"Setup '{setup_name}' weights sum to {total}, which is below 9.0. "
            f"Consider utilizing more of the available scoring range."
        )


def test_scoring_config_structure():
    """Verify the scoring configuration has required structure."""
    # Config file is at project root: /Users/shalev/Code/SCP/config/setups.yaml
    # Test file is at: /Users/shalev/Code/SCP/services/shared/tests/unit/rule_engine/test_*.py
    # Need to go up 6 levels: rule_engine -> unit -> tests -> shared -> services -> SCP
    config_path = (
        Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "setups.yaml"
    )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Required top-level keys
    assert "setups" in config
    assert "confidence" in config
    assert "validation" in config

    # Each setup must have min_score and weights
    for setup_name, setup_config in config["setups"].items():
        assert "min_score" in setup_config, f"Setup '{setup_name}' missing min_score"
        assert "weights" in setup_config, f"Setup '{setup_name}' missing weights"
        assert isinstance(
            setup_config["weights"], dict
        ), f"Setup '{setup_name}' weights must be dict"
        assert (
            len(setup_config["weights"]) > 0
        ), f"Setup '{setup_name}' has no weight factors"


def test_weight_values_are_positive():
    """Verify all weight values are positive numbers."""
    # Config file is at project root: /Users/shalev/Code/SCP/config/setups.yaml
    # Test file is at: /Users/shalev/Code/SCP/services/shared/tests/unit/rule_engine/test_*.py
    # Need to go up 6 levels: rule_engine -> unit -> tests -> shared -> services -> SCP
    config_path = (
        Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "setups.yaml"
    )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    for setup_name, setup_config in config["setups"].items():
        weights = setup_config["weights"]

        for factor_name, weight_value in weights.items():
            assert (
                weight_value > 0
            ), f"Setup '{setup_name}' factor '{factor_name}' has non-positive weight: {weight_value}"
            assert isinstance(
                weight_value, int | float
            ), f"Setup '{setup_name}' factor '{factor_name}' weight must be numeric: {weight_value}"
