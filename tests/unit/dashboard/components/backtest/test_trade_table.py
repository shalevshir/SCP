"""Tests for trade table component.

Verifies that:
- Numeric columns use proper numeric types for conditional styling
- None/null values are handled correctly (don't break filter queries)
- Winning/losing trade coloring works correctly
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from dashboard.components.backtest.trade_table import render_trade_table


def create_mock_trade(
    pnl: float | None = 10.0,
    pnl_net: float | None = 8.0,
    r_realized: float | None = 1.5,
    direction: str = "long",
    setup_type: str = "VWAP_RECLAIM",
) -> MagicMock:
    """Create a mock Trade object for testing."""
    trade = MagicMock()
    trade.trade_id = "test-1234-5678-abcd"
    trade.entry_timestamp = datetime(2025, 1, 1, 10, 30, 0, tzinfo=UTC)
    trade.direction = direction
    trade.setup_type = setup_type
    trade.entry_price = 2700.50
    trade.exit_price = 2710.50 if pnl and pnl > 0 else 2690.50
    trade.stop_loss = 2690.00
    trade.take_profit = 2730.00
    trade.pnl = pnl
    trade.pnl_net = pnl_net
    trade.r_realized = r_realized
    trade.duration_bars = 15
    trade.exit_reason = "TP" if pnl and pnl > 0 else "SL"

    # Mock entry_execution.signal
    signal = MagicMock()
    signal.score = 8.5
    signal.confidence = "HIGH"
    trade.entry_execution = MagicMock()
    trade.entry_execution.signal = signal

    return trade


def create_mock_backtest_results(trades: list) -> MagicMock:
    """Create a mock BacktestResults object."""
    results = MagicMock()
    results.trades = trades
    return results


class TestTradeTableNumericConditionalStyling:
    """Test that numeric columns support proper conditional styling."""

    def test_render_table_with_positive_pnl_has_numeric_column(self) -> None:
        """Winning trade should have numeric PnL value for filter queries."""
        trade = create_mock_trade(pnl=15.5, pnl_net=12.0, r_realized=2.0)
        results = create_mock_backtest_results([trade])

        table = render_trade_table(results)

        # Verify table is a DataTable (not an error div)
        assert hasattr(table, "data"), "Should return a DataTable, not a Div"

        # Check that PnL column contains raw numeric, not string
        row = table.data[0]
        pnl_value = row["PnL (pts)"]

        # Should be raw float, not formatted string
        assert isinstance(pnl_value, float), (
            f"PnL (pts) should be float for filter queries, got {type(pnl_value)}"
        )
        assert pnl_value == 15.5

    def test_render_table_with_negative_pnl_has_numeric_column(self) -> None:
        """Losing trade should have numeric PnL value for filter queries."""
        trade = create_mock_trade(pnl=-8.25, pnl_net=-10.0, r_realized=-0.8)
        results = create_mock_backtest_results([trade])

        table = render_trade_table(results)
        row = table.data[0]

        # Should be raw float for proper < 0 comparison
        pnl_value = row["PnL (pts)"]
        assert isinstance(pnl_value, float), (
            f"PnL (pts) should be float for filter queries, got {type(pnl_value)}"
        )
        assert pnl_value == -8.25

    def test_render_table_with_none_pnl_handles_gracefully(self) -> None:
        """Trade with None PnL should not break filter queries."""
        trade = create_mock_trade(pnl=None, pnl_net=None, r_realized=None)
        results = create_mock_backtest_results([trade])

        table = render_trade_table(results)
        row = table.data[0]

        # Should be None (not "N/A" string) so filter queries skip it
        pnl_value = row["PnL (pts)"]
        assert pnl_value is None, (
            f"None PnL should stay None, not be converted to '{pnl_value}'"
        )

    def test_columns_have_numeric_type_for_pnl_columns(self) -> None:
        """PnL, R, and Score columns should have numeric type for proper filtering."""
        trade = create_mock_trade(pnl=10.0)
        results = create_mock_backtest_results([trade])

        table = render_trade_table(results)

        # Check column definitions
        columns_by_id = {col["id"]: col for col in table.columns}

        assert columns_by_id["PnL (pts)"]["type"] == "numeric"
        assert columns_by_id["PnL ($)"]["type"] == "numeric"
        assert columns_by_id["R"]["type"] == "numeric"
        assert columns_by_id["Score"]["type"] == "numeric"

    def test_columns_have_format_specifier(self) -> None:
        """Numeric columns should have format specifiers for display."""
        trade = create_mock_trade(pnl=10.0)
        results = create_mock_backtest_results([trade])

        table = render_trade_table(results)

        columns_by_id = {col["id"]: col for col in table.columns}

        # Check format specifiers are set
        assert "format" in columns_by_id["PnL (pts)"]
        assert "format" in columns_by_id["PnL ($)"]
        assert "format" in columns_by_id["R"]
        assert "format" in columns_by_id["Score"]

        # Verify format specifiers
        assert columns_by_id["PnL (pts)"]["format"]["specifier"] == ".2f"
        assert columns_by_id["PnL ($)"]["format"]["specifier"] == "$,.2f"
        assert columns_by_id["R"]["format"]["specifier"] == ".2f"
        assert columns_by_id["Score"]["format"]["specifier"] == ".1f"


class TestTradeTableConditionalStyles:
    """Test that conditional styling rules are properly configured."""

    def test_style_data_conditional_includes_row_coloring(self) -> None:
        """Should have conditional styles for winning/losing row backgrounds."""
        trade = create_mock_trade(pnl=10.0)
        results = create_mock_backtest_results([trade])

        table = render_trade_table(results)

        style_conditionals = table.style_data_conditional

        # Find row background styles (not column-specific)
        row_styles = [
            s for s in style_conditionals
            if "column_id" not in s.get("if", {})
            and "backgroundColor" in s
        ]

        assert len(row_styles) >= 2, (
            f"Should have row background styles for win/loss, got {len(row_styles)}"
        )

        # Check we have both positive and negative PnL styles
        filter_queries = [s["if"]["filter_query"] for s in row_styles]
        assert any("< 0" in q for q in filter_queries), "Missing losing trade row style"
        assert any("> 0" in q for q in filter_queries), "Missing winning trade row style"

    def test_style_data_conditional_uses_proper_column_reference(self) -> None:
        """Filter queries should reference {PnL (pts)} column properly."""
        trade = create_mock_trade(pnl=10.0)
        results = create_mock_backtest_results([trade])

        table = render_trade_table(results)

        # All filter queries should use proper column reference format
        for style in table.style_data_conditional:
            query = style.get("if", {}).get("filter_query", "")
            if "PnL" in query:
                # Should be {PnL (pts)} not '{PnL (pts)}'
                assert "{PnL" in query, (
                    f"Filter query should use {{column}} format, got: {query}"
                )


class TestTradeTableFiltering:
    """Test trade filtering functionality."""

    def test_filter_by_direction_long(self) -> None:
        """Should filter to only long trades."""
        long_trade = create_mock_trade(direction="long")
        short_trade = create_mock_trade(direction="short")
        results = create_mock_backtest_results([long_trade, short_trade])

        table = render_trade_table(results, direction_filter="long")

        assert len(table.data) == 1
        assert table.data[0]["Direction"] == "LONG"

    def test_filter_by_setup_type(self) -> None:
        """Should filter by setup type."""
        vwap_reclaim = create_mock_trade(setup_type="VWAP_RECLAIM")
        vwap_fade = create_mock_trade(setup_type="VWAP_FADE")
        results = create_mock_backtest_results([vwap_reclaim, vwap_fade])

        table = render_trade_table(results, setup_filter="VWAP_FADE")

        assert len(table.data) == 1
        assert table.data[0]["Setup"] == "VWAP_FADE"

    def test_empty_trades_returns_div_not_table(self) -> None:
        """Empty trades should return info div, not table."""
        results = create_mock_backtest_results([])

        result = render_trade_table(results)

        # Should return html.Div, not DataTable
        assert not hasattr(result, "data"), (
            "Empty results should return Div, not DataTable"
        )

