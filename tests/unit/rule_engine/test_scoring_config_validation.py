"""Test scoring configuration constraints and validation."""

from pathlib import Path

import yaml


def test_all_setup_weights_sum_to_max_10_points():
    """Verify that all setup type weights sum to exactly 10 points or less.

    This constraint is documented in the scoring_config.yaml header comment:
    'weights: Dict of factor names to point values (max 10 total)'

    This test ensures scoring integrity and prevents setups from exceeding
    the intended maximum score baseline before HTF adjustments.
    """
    config_path = (
        Path(__file__).parent.parent.parent.parent / "config" / "scoring_config.yaml"
    )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    setup_types = config["setup_types"]

    for setup_name, setup_config in setup_types.items():
        weights = setup_config["weights"]
        total = sum(weights.values())

        assert total <= 10.0, (
            f"Setup '{setup_name}' weights sum to {total}, exceeding max 10 points. "
            f"Weights: {weights}"
        )

        # Also verify the total is close to 10 (within 0.5) to ensure we're using
        # the full scoring range available
        assert total >= 9.5, (
            f"Setup '{setup_name}' weights sum to {total}, which is below 9.5. "
            f"Consider utilizing more of the available 10-point scale."
        )


def test_scoring_config_structure():
    """Verify the scoring configuration has required structure."""
    config_path = (
        Path(__file__).parent.parent.parent.parent / "config" / "scoring_config.yaml"
    )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Required top-level keys
    assert "setup_types" in config
    assert "confidence" in config
    assert "validation" in config

    # Each setup must have min_score and weights
    for setup_name, setup_config in config["setup_types"].items():
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
    config_path = (
        Path(__file__).parent.parent.parent.parent / "config" / "scoring_config.yaml"
    )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    for setup_name, setup_config in config["setup_types"].items():
        weights = setup_config["weights"]

        for factor_name, weight_value in weights.items():
            assert (
                weight_value > 0
            ), f"Setup '{setup_name}' factor '{factor_name}' has non-positive weight: {weight_value}"
            assert isinstance(
                weight_value, int | float
            ), f"Setup '{setup_name}' factor '{factor_name}' weight must be numeric: {weight_value}"



