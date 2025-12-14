"""Trade Table - Interactive trade breakdown table."""

import dash_bootstrap_components as dbc
import pandas as pd
from backtester.replay_loop import BacktestResults
from dash import dash_table, dcc, html


def create_trade_table() -> dbc.Card:
    """Create the trade breakdown table panel.

    Returns:
        Dash Bootstrap Card containing the table and controls
    """
    return dbc.Card(
        [
            dbc.CardHeader("Trade Breakdown"),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Filter by Setup:", className="me-2"),
                                    dcc.Dropdown(
                                        id="trade-table-filter-setup",
                                        options=[
                                            {"label": "All", "value": "all"},
                                            {
                                                "label": "VWAP_RECLAIM",
                                                "value": "VWAP_RECLAIM",
                                            },
                                            {
                                                "label": "VWAP_FADE",
                                                "value": "VWAP_FADE",
                                            },
                                            {
                                                "label": "DXY_CONTINUATION",
                                                "value": "DXY_CONTINUATION",
                                            },
                                        ],
                                        value="all",
                                        clearable=False,
                                        className="mb-2",
                                    ),
                                ],
                                width=4,
                            ),
                            dbc.Col(
                                [
                                    html.Label(
                                        "Filter by Direction:", className="me-2"
                                    ),
                                    dcc.Dropdown(
                                        id="trade-table-filter-direction",
                                        options=[
                                            {"label": "All", "value": "all"},
                                            {"label": "Long", "value": "long"},
                                            {"label": "Short", "value": "short"},
                                        ],
                                        value="all",
                                        clearable=False,
                                        className="mb-2",
                                    ),
                                ],
                                width=4,
                            ),
                            dbc.Col(
                                [
                                    html.Button(
                                        "Export CSV",
                                        id="trade-table-export-btn",
                                        className="btn btn-sm btn-outline-primary",
                                    ),
                                    dcc.Download(id="trade-table-download"),
                                ],
                                width=4,
                                className="d-flex align-items-end",
                            ),
                        ],
                        className="mb-2",
                    ),
                    html.Div(id="trade-table-content"),
                ]
            ),
        ]
    )


def render_trade_table(
    results: BacktestResults,
    setup_filter: str = "all",
    direction_filter: str = "all",
) -> dash_table.DataTable:
    """Render trade breakdown table.

    Args:
        results: BacktestResults object with all trades
        setup_filter: Filter by setup type ("all", "VWAP_RECLAIM", etc.)
        direction_filter: Filter by direction ("all", "long", "short")

    Returns:
        Dash DataTable component
    """
    if not results.trades:
        return html.Div("No trades to display", className="text-muted")

    # Filter trades
    filtered_trades = results.trades
    if setup_filter != "all":
        filtered_trades = [t for t in filtered_trades if t.setup_type == setup_filter]
    if direction_filter != "all":
        filtered_trades = [
            t for t in filtered_trades if t.direction == direction_filter
        ]

    # Build DataFrame
    rows = []
    for trade in filtered_trades:
        signal = trade.entry_execution.signal
        rows.append(
            {
                "Trade ID": trade.trade_id[:8],
                "Entry Time": trade.entry_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "Direction": trade.direction.upper(),
                "Setup": trade.setup_type,
                "Entry": f"{trade.entry_price:.2f}",
                "Exit": f"{trade.exit_price:.2f}" if trade.exit_price else "N/A",
                "SL": f"{trade.stop_loss:.2f}",
                "TP": f"{trade.take_profit:.2f}",
                # Keep raw numeric for conditional styling; use None for N/A
                "PnL (pts)": trade.pnl if trade.pnl is not None else None,
                "PnL ($)": trade.pnl_net if trade.pnl_net is not None else None,
                "R": trade.r_realized if trade.r_realized is not None else None,
                "Duration": (
                    f"{trade.duration_bars} bars" if trade.duration_bars else "N/A"
                ),
                "Exit Reason": trade.exit_reason or "N/A",
                "Score": signal.score,
                "Confidence": signal.confidence,
            }
        )

    df = pd.DataFrame(rows)

    # Define columns with formatting for numeric types
    columns = []
    for col in df.columns:
        col_def = {"name": col, "id": col, "sortable": True, "selectable": False}

        # Apply number formatting for specific columns
        if col == "PnL (pts)":
            col_def["type"] = "numeric"
            col_def["format"] = {"specifier": ".2f"}
        elif col == "PnL ($)":
            col_def["type"] = "numeric"
            col_def["format"] = {"specifier": "$,.2f"}
        elif col == "R":
            col_def["type"] = "numeric"
            col_def["format"] = {"specifier": ".2f"}
        elif col == "Score":
            col_def["type"] = "numeric"
            col_def["format"] = {"specifier": ".1f"}

        columns.append(col_def)

    # Create DataTable
    table = dash_table.DataTable(
        id="trade-table",
        columns=columns,
        data=df.to_dict("records"),
        sort_action="native",
        filter_action="native",
        page_action="native",
        page_current=0,
        page_size=20,
        style_cell={
            "textAlign": "left",
            "padding": "10px",
            "fontSize": "12px",
        },
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_data={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
        },
        style_data_conditional=[
            # Color losing trades red (PnL < 0, excluding None/N/A)
            {
                "if": {
                    "filter_query": "{PnL (pts)} < 0",
                    "column_id": "PnL (pts)",
                },
                "backgroundColor": "rgba(239, 83, 80, 0.2)",
                "color": "#ef5350",
            },
            {
                "if": {"filter_query": "{PnL (pts)} < 0"},
                "backgroundColor": "rgba(239, 83, 80, 0.2)",
            },
            # Color winning trades green (PnL > 0)
            {
                "if": {
                    "filter_query": "{PnL (pts)} > 0",
                    "column_id": "PnL (pts)",
                },
                "backgroundColor": "rgba(38, 166, 154, 0.2)",
                "color": "#26a69a",
            },
            {
                "if": {"filter_query": "{PnL (pts)} > 0"},
                "backgroundColor": "rgba(38, 166, 154, 0.2)",
            },
            # Style PnL ($) column based on its own value
            {
                "if": {
                    "filter_query": "{PnL ($)} < 0",
                    "column_id": "PnL ($)",
                },
                "color": "#ef5350",
            },
            {
                "if": {
                    "filter_query": "{PnL ($)} > 0",
                    "column_id": "PnL ($)",
                },
                "color": "#26a69a",
            },
            # Style R column based on its own value
            {
                "if": {
                    "filter_query": "{R} < 0",
                    "column_id": "R",
                },
                "color": "#ef5350",
            },
            {
                "if": {
                    "filter_query": "{R} > 0",
                    "column_id": "R",
                },
                "color": "#26a69a",
            },
        ],
    )

    return table
