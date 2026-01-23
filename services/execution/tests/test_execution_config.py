"""Unit tests for configurable execution parameters.

Tests for slippage, commission, and position sizing configuration.

Following strict TDD - these tests are written FIRST and should FAIL until
the configuration is implemented.
"""

import pytest


class TestExecutionConfig:
    """Tests for execution configuration."""

    def test_config_has_slippage_fields(self):
        """ExecutionConfig should have slippage configuration fields."""
        from execution_svc.config import ExecutionConfig

        config = ExecutionConfig()

        assert hasattr(config, "enable_slippage")
        assert hasattr(config, "slippage_points")
        assert isinstance(config.enable_slippage, bool)
        assert isinstance(config.slippage_points, float)

    def test_config_has_commission_fields(self):
        """ExecutionConfig should have commission configuration fields."""
        from execution_svc.config import ExecutionConfig

        config = ExecutionConfig()

        assert hasattr(config, "enable_commission")
        assert hasattr(config, "commission_per_trade")
        assert isinstance(config.enable_commission, bool)
        assert isinstance(config.commission_per_trade, float)

    def test_config_has_sizing_fields(self):
        """ExecutionConfig should have position sizing configuration fields."""
        from execution_svc.config import ExecutionConfig

        config = ExecutionConfig()

        assert hasattr(config, "sizing_mode")
        assert hasattr(config, "fixed_quantity")
        assert hasattr(config, "risk_per_trade_percent")
        assert config.sizing_mode in ("fixed", "risk_ladder")

    def test_config_defaults_for_production(self):
        """Default configuration should be production-safe (no slippage/commission)."""
        from execution_svc.config import ExecutionConfig

        config = ExecutionConfig()

        # Slippage and commission should be disabled by default
        assert config.enable_slippage is False
        assert config.enable_commission is False
        # Fixed quantity mode by default
        assert config.sizing_mode == "fixed"
        assert config.fixed_quantity == 1

    def test_config_can_enable_slippage(self):
        """Configuration should allow enabling slippage for backtest mode."""
        from execution_svc.config import ExecutionConfig

        config = ExecutionConfig(
            enable_slippage=True,
            slippage_points=0.5,
        )

        assert config.enable_slippage is True
        assert config.slippage_points == 0.5

    def test_config_can_enable_commission(self):
        """Configuration should allow enabling commission for backtest mode."""
        from execution_svc.config import ExecutionConfig

        config = ExecutionConfig(
            enable_commission=True,
            commission_per_trade=5.0,
        )

        assert config.enable_commission is True
        assert config.commission_per_trade == 5.0

    def test_config_can_set_risk_ladder_sizing(self):
        """Configuration should allow risk ladder sizing mode."""
        from execution_svc.config import ExecutionConfig

        config = ExecutionConfig(
            sizing_mode="risk_ladder",
            risk_per_trade_percent=1.0,
        )

        assert config.sizing_mode == "risk_ladder"
        assert config.risk_per_trade_percent == 1.0
