"""Backtest Results Viewer - Interactive Dash app for analyzing backtest results.

This module provides a comprehensive dashboard for visualizing and analyzing
backtest results, including equity curves, trade breakdowns, and signal analysis.
"""

import dash
import dash_bootstrap_components as dbc
from backtester.replay_loop import BacktestResults
from common.logger import get_logger
from dash import Input, Output, dcc, html

from dashboard.components.backtest.equity_chart import (
    create_equity_chart,
    render_equity_chart,
)
from dashboard.components.backtest.metrics_panel import (
    create_metrics_panel,
    render_metrics_panel,
)
from dashboard.components.backtest.price_chart import (
    create_price_chart_with_markers,
    render_price_chart_with_markers,
    render_trade_details,
)
from dashboard.components.backtest.scoring_breakdown import (
    create_scoring_breakdown,
    render_scoring_breakdown,
)
from dashboard.components.backtest.trade_table import (
    create_trade_table,
    render_trade_table,
)

logger = get_logger(__name__)


class BacktestResultsViewer:
    """Interactive Dash dashboard for backtest results analysis.

    Provides comprehensive visualization of backtest results including:
    - Performance metrics summary
    - Equity curve and drawdown charts
    - Trade-by-trade breakdown table
    - Price charts with entry/exit markers
    - Signal scoring breakdown analysis
    """

    def __init__(self, results: BacktestResults, gc_df=None):
        """Initialize backtest results viewer.

        Args:
            results: BacktestResults object with all trades and metrics
            gc_df: Optional GC price DataFrame for price chart visualization
        """
        self.results = results
        self.gc_df = gc_df

        # Create Dash app
        self.app = dash.Dash(
            __name__,
            external_stylesheets=[dbc.themes.DARKLY],
            title="Shir Capital Backtest Results",
        )

        # Build layout
        self.app.layout = self._build_layout()

        # Register callbacks
        self._register_callbacks()

        logger.info(
            f"BacktestResultsViewer initialized with {len(results.trades)} trades"
        )

    def _build_layout(self) -> dbc.Container:
        """Build dashboard layout.

        Returns:
            Dash layout container
        """
        return dbc.Container(
            [
                # Header
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H1(
                                    "Shir Capital Backtest Results",
                                    className="text-center mb-4",
                                ),
                                html.Hr(),
                            ]
                        )
                    ]
                ),
                # Metrics Panel
                dbc.Row(
                    [dbc.Col([create_metrics_panel()])],
                    className="mb-4",
                ),
                # Main content: Equity chart and Trade table
                dbc.Row(
                    [
                        dbc.Col([create_equity_chart()], width=12, className="mb-4"),
                    ]
                ),
                dbc.Row(
                    [
                        dbc.Col([create_trade_table()], width=12, className="mb-4"),
                    ]
                ),
                # Price chart and Scoring breakdown
                dbc.Row(
                    [
                        dbc.Col([create_price_chart_with_markers()], width=6, className="mb-4"),
                        dbc.Col([create_scoring_breakdown()], width=6, className="mb-4"),
                    ]
                ),
            ],
            fluid=True,
            className="p-4",
        )

    def _register_callbacks(self) -> None:
        """Register Dash callbacks for interactivity."""

        @self.app.callback(
            Output("metrics-panel-content", "children"),
            Input("equity-display-mode", "value"),
        )
        def update_metrics(_):
            """Update metrics panel."""
            return render_metrics_panel(self.results)

        @self.app.callback(
            [
                Output("equity-chart", "figure"),
                Output("trade-table-content", "children"),
                Output("price-chart-with-markers", "figure"),
                Output("scoring-breakdown-chart", "figure"),
            ],
            [
                Input("equity-display-mode", "value"),
                Input("trade-table-filter-setup", "value"),
                Input("trade-table-filter-direction", "value"),
                Input("price-chart-trade-selector", "value"),
                Input("scoring-breakdown-filter", "value"),
            ],
        )
        def update_all_charts(
            equity_mode,
            table_setup_filter,
            table_direction_filter,
            selected_trade_id,
            scoring_filter,
        ):
            """Update all charts based on filters."""
            # Equity chart
            equity_fig = render_equity_chart(self.results, equity_mode or "points")

            # Trade table
            table = render_trade_table(
                self.results,
                table_setup_filter or "all",
                table_direction_filter or "all",
            )

            # Price chart
            price_fig = render_price_chart_with_markers(
                self.results, self.gc_df, selected_trade_id
            )

            # Scoring breakdown
            scoring_fig = render_scoring_breakdown(
                self.results, scoring_filter or "all"
            )

            return equity_fig, table, price_fig, scoring_fig

        @self.app.callback(
            [
                Output("price-chart-trade-selector", "options"),
                Output("price-chart-trade-details", "children"),
            ],
            [
                Input("price-chart-trade-selector", "value"),
            ],
        )
        def update_trade_selector(selected_trade_id):
            """Update trade selector dropdown and details."""
            # Build options
            options = [
                {
                    "label": f"{t.trade_id[:8]} - {t.direction.upper()} {t.setup_type} @ {t.entry_price:.2f}",
                    "value": t.trade_id,
                }
                for t in self.results.trades
            ]

            # Get selected trade details
            selected_trade = None
            if selected_trade_id:
                selected_trade = next(
                    (t for t in self.results.trades if t.trade_id == selected_trade_id),
                    None,
                )

            details = render_trade_details(selected_trade)

            return options, details

        @self.app.callback(
            Output("trade-table-download", "data"),
            Input("trade-table-export-btn", "n_clicks"),
            prevent_initial_call=True,
        )
        def export_trade_table(n_clicks):
            """Export trade table to CSV."""
            if n_clicks:
                import pandas as pd

                rows = []
                for trade in self.results.trades:
                    signal = trade.entry_execution.signal
                    rows.append(
                        {
                            "Trade ID": trade.trade_id,
                            "Entry Time": trade.entry_timestamp.isoformat(),
                            "Direction": trade.direction,
                            "Setup": trade.setup_type,
                            "Entry": trade.entry_price,
                            "Exit": trade.exit_price,
                            "SL": trade.stop_loss,
                            "TP": trade.take_profit,
                            "PnL (pts)": trade.pnl,
                            "PnL ($)": trade.pnl_net,
                            "R": trade.r_realized,
                            "Duration (bars)": trade.duration_bars,
                            "Exit Reason": trade.exit_reason,
                            "Score": signal.score,
                            "Confidence": signal.confidence,
                        }
                    )

                df = pd.DataFrame(rows)
                return dcc.send_data_frame(df.to_csv, "backtest_trades.csv", index=False)


    def run(self, host: str = "0.0.0.0", port: int = 8051, debug: bool = False) -> None:
        """Run the dashboard server.

        Args:
            host: Host address (default: 0.0.0.0)
            port: Port number (default: 8051)
            debug: Enable debug mode (default: False)
        """
        logger.info(f"Starting backtest results viewer on {host}:{port}")
        self.app.run_server(host=host, port=port, debug=debug)

