"""Equity Chart - Cumulative PnL and drawdown visualization."""

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from backtester.replay_loop import BacktestResults
from dash import dcc, html


def create_equity_chart() -> dbc.Card:
    """Create the equity curve panel.

    Returns:
        Dash Bootstrap Card containing the chart and controls
    """
    return dbc.Card(
        [
            dbc.CardHeader("Equity Curve & Drawdown"),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Display:", className="me-2"),
                                    dcc.RadioItems(
                                        id="equity-display-mode",
                                        options=[
                                            {"label": "Points", "value": "points"},
                                            {"label": "Dollars", "value": "dollars"},
                                        ],
                                        value="points",
                                        inline=True,
                                        className="mb-2",
                                    ),
                                ],
                                width=12,
                            ),
                        ],
                        className="mb-2",
                    ),
                    dcc.Graph(
                        id="equity-chart",
                        config={"displayModeBar": True},
                        style={"height": "400px"},
                    ),
                ]
            ),
        ]
    )


def render_equity_chart(
    results: BacktestResults, display_mode: str = "points"
) -> go.Figure:
    """Render equity curve and drawdown chart.

    Args:
        results: BacktestResults object with all trades
        display_mode: "points" or "dollars" for PnL display

    Returns:
        Plotly figure with equity curve and drawdown subplots
    """
    if not results.trades:
        # Return empty chart
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            xaxis_title="Trade #",
            yaxis_title="PnL" if display_mode == "points" else "PnL ($)",
            showlegend=True,
            annotations=[
                dict(
                    text="No trades to display",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=16, color="gray"),
                )
            ],
        )
        return fig

    # Build cumulative PnL series
    trades_sorted = sorted(results.trades, key=lambda t: t.entry_timestamp)
    cumulative_pnl = []
    cumulative_dollars = []
    timestamps = []
    trade_numbers = []

    running_pnl = 0.0
    running_dollars = 0.0

    for i, trade in enumerate(trades_sorted):
        if trade.pnl is not None:
            running_pnl += trade.pnl
            cumulative_pnl.append(running_pnl)

            if trade.pnl_net is not None:
                running_dollars += trade.pnl_net
                cumulative_dollars.append(running_dollars)
            else:
                cumulative_dollars.append(running_dollars)

            timestamps.append(trade.exit_timestamp or trade.entry_timestamp)
            trade_numbers.append(i + 1)

    # Calculate drawdown
    if display_mode == "points":
        equity_series = cumulative_pnl
        yaxis_title = "PnL (Points)"
    else:
        equity_series = cumulative_dollars
        yaxis_title = "PnL ($)"

    # Calculate drawdown from peak
    peak = equity_series[0] if equity_series else 0.0
    drawdown = []
    for value in equity_series:
        if value > peak:
            peak = value
        drawdown.append(value - peak)

    # Create subplots
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=("Equity Curve", "Drawdown"),
        row_heights=[0.7, 0.3],
    )

    # Equity curve
    fig.add_trace(
        go.Scatter(
            x=trade_numbers,
            y=equity_series,
            mode="lines+markers",
            name="Cumulative PnL",
            line=dict(color="#26a69a", width=2),
            marker=dict(size=4),
            hovertemplate="Trade #%{x}<br>PnL: %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # Drawdown
    fig.add_trace(
        go.Scatter(
            x=trade_numbers,
            y=drawdown,
            mode="lines",
            name="Drawdown",
            fill="tozeroy",
            fillcolor="rgba(239, 83, 80, 0.3)",
            line=dict(color="#ef5350", width=2),
            hovertemplate="Trade #%{x}<br>Drawdown: %{y:.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    # Highlight PDLL events (if any)
    if results.pdll_hits > 0:
        # Find trades where PDLL might have been hit
        # This is approximate - actual PDLL detection would need session-level tracking
        pass

    # Update layout
    fig.update_layout(
        template="plotly_dark",
        height=500,
        showlegend=True,
        hovermode="x unified",
    )

    fig.update_xaxes(title_text="Trade #", row=2, col=1)
    fig.update_yaxes(title_text=yaxis_title, row=1, col=1)
    fig.update_yaxes(title_text="Drawdown", row=2, col=1)

    return fig

