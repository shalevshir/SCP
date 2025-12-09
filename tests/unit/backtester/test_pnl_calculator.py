"""Unit tests for PnL calculator - dollar-based PnL with slippage and commission.

Following TDD principles: tests written first to define behavior.
"""

import pytest
from backtester.pnl_calculator import (
    calculate_commission_cost,
    calculate_gross_pnl,
    calculate_net_pnl,
    calculate_slippage_cost,
)


class TestCalculateGrossPnL:
    """Tests for gross PnL calculation (before costs)."""

    def test_long_trade_win(self):
        """Test gross PnL for winning long trade."""
        entry_price = 2650.0
        exit_price = 2665.0
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1

        gross_pnl = calculate_gross_pnl(
            entry_price, exit_price, direction, contracts, tick_value, tick_size
        )

        # 15 points × $10/point × 1 contract = $1,500
        assert gross_pnl == pytest.approx(1500.0)

    def test_long_trade_loss(self):
        """Test gross PnL for losing long trade."""
        entry_price = 2650.0
        exit_price = 2645.0
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1

        gross_pnl = calculate_gross_pnl(
            entry_price, exit_price, direction, contracts, tick_value, tick_size
        )

        # -5 points × $10/point × 1 contract = -$500
        assert gross_pnl == pytest.approx(-500.0)

    def test_short_trade_win(self):
        """Test gross PnL for winning short trade."""
        entry_price = 2650.0
        exit_price = 2645.0
        direction = "short"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1

        gross_pnl = calculate_gross_pnl(
            entry_price, exit_price, direction, contracts, tick_value, tick_size
        )

        # 5 points × $10/point × 1 contract = $500
        assert gross_pnl == pytest.approx(500.0)

    def test_short_trade_loss(self):
        """Test gross PnL for losing short trade."""
        entry_price = 2650.0
        exit_price = 2665.0
        direction = "short"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1

        gross_pnl = calculate_gross_pnl(
            entry_price, exit_price, direction, contracts, tick_value, tick_size
        )

        # -15 points × $10/point × 1 contract = -$1,500
        assert gross_pnl == pytest.approx(-1500.0)

    def test_multiple_contracts(self):
        """Test gross PnL with multiple contracts."""
        entry_price = 2650.0
        exit_price = 2660.0
        direction = "long"
        contracts = 3
        tick_value = 10.0
        tick_size = 0.1

        gross_pnl = calculate_gross_pnl(
            entry_price, exit_price, direction, contracts, tick_value, tick_size
        )

        # 10 points × $10/point × 3 contracts = $3,000
        assert gross_pnl == pytest.approx(3000.0)

    def test_breakeven_trade(self):
        """Test gross PnL for trade at breakeven."""
        entry_price = 2650.0
        exit_price = 2650.0
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1

        gross_pnl = calculate_gross_pnl(
            entry_price, exit_price, direction, contracts, tick_value, tick_size
        )

        assert gross_pnl == pytest.approx(0.0)

    def test_zero_contracts(self):
        """Test gross PnL with zero contracts."""
        entry_price = 2650.0
        exit_price = 2665.0
        direction = "long"
        contracts = 0
        tick_value = 10.0
        tick_size = 0.1

        gross_pnl = calculate_gross_pnl(
            entry_price, exit_price, direction, contracts, tick_value, tick_size
        )

        assert gross_pnl == pytest.approx(0.0)

    def test_different_symbol_es(self):
        """Test gross PnL for ES futures ($12.5/tick)."""
        entry_price = 4500.0
        exit_price = 4510.0
        direction = "long"
        contracts = 1
        tick_value = 12.5
        tick_size = 0.25

        gross_pnl = calculate_gross_pnl(
            entry_price, exit_price, direction, contracts, tick_value, tick_size
        )

        # 10 points × $12.5/point × 1 contract = $500
        assert gross_pnl == pytest.approx(500.0)


class TestCalculateSlippageCost:
    """Tests for slippage cost calculation."""

    def test_slippage_cost_long(self):
        """Test slippage cost for long trade."""
        direction = "long"
        contracts = 1
        slippage_ticks = 1.5
        tick_value = 10.0

        slippage_cost = calculate_slippage_cost(
            direction, contracts, slippage_ticks, tick_value
        )

        # 1.5 ticks × $10/tick × 1 contract = -$15
        assert slippage_cost == pytest.approx(-15.0)

    def test_slippage_cost_short(self):
        """Test slippage cost for short trade."""
        direction = "short"
        contracts = 1
        slippage_ticks = 1.5
        tick_value = 10.0

        slippage_cost = calculate_slippage_cost(
            direction, contracts, slippage_ticks, tick_value
        )

        # 1.5 ticks × $10/tick × 1 contract = -$15
        assert slippage_cost == pytest.approx(-15.0)

    def test_slippage_cost_multiple_contracts(self):
        """Test slippage cost with multiple contracts."""
        direction = "long"
        contracts = 3
        slippage_ticks = 1.5
        tick_value = 10.0

        slippage_cost = calculate_slippage_cost(
            direction, contracts, slippage_ticks, tick_value
        )

        # 1.5 ticks × $10/tick × 3 contracts = -$45
        assert slippage_cost == pytest.approx(-45.0)

    def test_slippage_cost_zero_slippage(self):
        """Test slippage cost with zero slippage."""
        direction = "long"
        contracts = 1
        slippage_ticks = 0.0
        tick_value = 10.0

        slippage_cost = calculate_slippage_cost(
            direction, contracts, slippage_ticks, tick_value
        )

        assert slippage_cost == pytest.approx(0.0)

    def test_slippage_cost_high_slippage(self):
        """Test slippage cost with high slippage (5 ticks)."""
        direction = "long"
        contracts = 1
        slippage_ticks = 5.0
        tick_value = 10.0

        slippage_cost = calculate_slippage_cost(
            direction, contracts, slippage_ticks, tick_value
        )

        # 5 ticks × $10/tick × 1 contract = -$50
        assert slippage_cost == pytest.approx(-50.0)

    def test_slippage_cost_is_always_negative_or_zero(self):
        """Test that slippage cost is always negative or zero."""
        direction = "long"
        contracts = 1
        slippage_ticks = 2.0
        tick_value = 10.0

        slippage_cost = calculate_slippage_cost(
            direction, contracts, slippage_ticks, tick_value
        )

        assert slippage_cost <= 0.0


class TestCalculateCommissionCost:
    """Tests for commission cost calculation."""

    def test_commission_cost_single_contract(self):
        """Test commission cost for single contract."""
        contracts = 1
        commission_per_contract = 5.0

        commission_cost = calculate_commission_cost(contracts, commission_per_contract)

        # Entry + Exit: $5 × 2 × 1 contract = -$10
        assert commission_cost == pytest.approx(-10.0)

    def test_commission_cost_multiple_contracts(self):
        """Test commission cost for multiple contracts."""
        contracts = 3
        commission_per_contract = 5.0

        commission_cost = calculate_commission_cost(contracts, commission_per_contract)

        # Entry + Exit: $5 × 2 × 3 contracts = -$30
        assert commission_cost == pytest.approx(-30.0)

    def test_commission_cost_zero_contracts(self):
        """Test commission cost with zero contracts."""
        contracts = 0
        commission_per_contract = 5.0

        commission_cost = calculate_commission_cost(contracts, commission_per_contract)

        assert commission_cost == pytest.approx(0.0)

    def test_commission_cost_different_rate(self):
        """Test commission cost with different commission rate."""
        contracts = 1
        commission_per_contract = 2.5

        commission_cost = calculate_commission_cost(contracts, commission_per_contract)

        # Entry + Exit: $2.5 × 2 × 1 contract = -$5
        assert commission_cost == pytest.approx(-5.0)

    def test_commission_cost_is_always_negative_or_zero(self):
        """Test that commission cost is always negative or zero."""
        contracts = 1
        commission_per_contract = 5.0

        commission_cost = calculate_commission_cost(contracts, commission_per_contract)

        assert commission_cost <= 0.0


class TestCalculateNetPnL:
    """Tests for complete net PnL calculation."""

    def test_long_trade_win_with_costs(self):
        """Test net PnL for winning long trade with all costs.

        As per plan validation:
        Entry: 2650.0, Exit: 2665.0 (TP)
        Gross: +$1,500 (15 points × $10/point × 1 contract)
        Slippage: -$15 (1.5 ticks × $10)
        Commission: -$10 (entry + exit)
        Net: +$1,475
        """
        entry_price = 2650.0
        exit_price = 2665.0
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1
        slippage_ticks = 1.5
        commission_per_contract = 5.0

        pnl_breakdown = calculate_net_pnl(
            entry_price,
            exit_price,
            direction,
            contracts,
            tick_value,
            tick_size,
            slippage_ticks,
            commission_per_contract,
        )

        assert pnl_breakdown["gross_pnl"] == pytest.approx(1500.0)
        assert pnl_breakdown["slippage_cost"] == pytest.approx(-15.0)
        assert pnl_breakdown["commission_cost"] == pytest.approx(-10.0)
        assert pnl_breakdown["net_pnl"] == pytest.approx(1475.0)
        assert pnl_breakdown["pnl_per_contract"] == pytest.approx(1475.0)

    def test_short_trade_win_with_costs(self):
        """Test net PnL for winning short trade with all costs.

        As per plan validation:
        Entry: 2650.0, Exit: 2645.0 (TP)
        Gross: +$500 (5 points × $10/point × 1 contract)
        Slippage: -$15
        Commission: -$10
        Net: +$475
        """
        entry_price = 2650.0
        exit_price = 2645.0
        direction = "short"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1
        slippage_ticks = 1.5
        commission_per_contract = 5.0

        pnl_breakdown = calculate_net_pnl(
            entry_price,
            exit_price,
            direction,
            contracts,
            tick_value,
            tick_size,
            slippage_ticks,
            commission_per_contract,
        )

        assert pnl_breakdown["gross_pnl"] == pytest.approx(500.0)
        assert pnl_breakdown["slippage_cost"] == pytest.approx(-15.0)
        assert pnl_breakdown["commission_cost"] == pytest.approx(-10.0)
        assert pnl_breakdown["net_pnl"] == pytest.approx(475.0)

    def test_long_trade_loss_with_costs(self):
        """Test net PnL for losing long trade with all costs."""
        entry_price = 2650.0
        exit_price = 2645.0  # Stop loss
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1
        slippage_ticks = 1.5
        commission_per_contract = 5.0

        pnl_breakdown = calculate_net_pnl(
            entry_price,
            exit_price,
            direction,
            contracts,
            tick_value,
            tick_size,
            slippage_ticks,
            commission_per_contract,
        )

        # Gross: -$500, Slippage: -$15, Commission: -$10 = -$525
        assert pnl_breakdown["gross_pnl"] == pytest.approx(-500.0)
        assert pnl_breakdown["net_pnl"] == pytest.approx(-525.0)

    def test_breakeven_trade_with_costs(self):
        """Test net PnL for breakeven trade (still has costs)."""
        entry_price = 2650.0
        exit_price = 2650.0
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1
        slippage_ticks = 1.5
        commission_per_contract = 5.0

        pnl_breakdown = calculate_net_pnl(
            entry_price,
            exit_price,
            direction,
            contracts,
            tick_value,
            tick_size,
            slippage_ticks,
            commission_per_contract,
        )

        # Gross: $0, Slippage: -$15, Commission: -$10 = -$25
        assert pnl_breakdown["gross_pnl"] == pytest.approx(0.0)
        assert pnl_breakdown["net_pnl"] == pytest.approx(-25.0)

    def test_multiple_contracts_with_costs(self):
        """Test net PnL with multiple contracts."""
        entry_price = 2650.0
        exit_price = 2660.0
        direction = "long"
        contracts = 3
        tick_value = 10.0
        tick_size = 0.1
        slippage_ticks = 1.5
        commission_per_contract = 5.0

        pnl_breakdown = calculate_net_pnl(
            entry_price,
            exit_price,
            direction,
            contracts,
            tick_value,
            tick_size,
            slippage_ticks,
            commission_per_contract,
        )

        # Gross: $3,000, Slippage: -$45, Commission: -$30 = $2,925
        assert pnl_breakdown["gross_pnl"] == pytest.approx(3000.0)
        assert pnl_breakdown["slippage_cost"] == pytest.approx(-45.0)
        assert pnl_breakdown["commission_cost"] == pytest.approx(-30.0)
        assert pnl_breakdown["net_pnl"] == pytest.approx(2925.0)
        assert pnl_breakdown["pnl_per_contract"] == pytest.approx(975.0)

    def test_zero_slippage_zero_commission(self):
        """Test net PnL with no costs (equals gross)."""
        entry_price = 2650.0
        exit_price = 2665.0
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1
        slippage_ticks = 0.0
        commission_per_contract = 0.0

        pnl_breakdown = calculate_net_pnl(
            entry_price,
            exit_price,
            direction,
            contracts,
            tick_value,
            tick_size,
            slippage_ticks,
            commission_per_contract,
        )

        assert pnl_breakdown["net_pnl"] == pnl_breakdown["gross_pnl"]

    def test_high_slippage(self):
        """Test net PnL with high slippage (5 ticks)."""
        entry_price = 2650.0
        exit_price = 2665.0
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1
        slippage_ticks = 5.0
        commission_per_contract = 5.0

        pnl_breakdown = calculate_net_pnl(
            entry_price,
            exit_price,
            direction,
            contracts,
            tick_value,
            tick_size,
            slippage_ticks,
            commission_per_contract,
        )

        # Gross: $1,500, Slippage: -$50, Commission: -$10 = $1,440
        assert pnl_breakdown["slippage_cost"] == pytest.approx(-50.0)
        assert pnl_breakdown["net_pnl"] == pytest.approx(1440.0)

    def test_pnl_breakdown_has_all_keys(self):
        """Test that PnL breakdown returns all required keys."""
        entry_price = 2650.0
        exit_price = 2665.0
        direction = "long"
        contracts = 1
        tick_value = 10.0
        tick_size = 0.1
        slippage_ticks = 1.5
        commission_per_contract = 5.0

        pnl_breakdown = calculate_net_pnl(
            entry_price,
            exit_price,
            direction,
            contracts,
            tick_value,
            tick_size,
            slippage_ticks,
            commission_per_contract,
        )

        assert "gross_pnl" in pnl_breakdown
        assert "slippage_cost" in pnl_breakdown
        assert "commission_cost" in pnl_breakdown
        assert "net_pnl" in pnl_breakdown
        assert "pnl_per_contract" in pnl_breakdown
