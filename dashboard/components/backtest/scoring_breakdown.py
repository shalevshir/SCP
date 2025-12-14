"""Scoring Breakdown - Factor contribution visualization."""

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from backtester.replay_loop import BacktestResults
from dash import dcc, html


def create_scoring_breakdown() -> dbc.Card:
    """Create the scoring breakdown panel.

    Returns:
        Dash Bootstrap Card containing the chart and controls
    """
    return dbc.Card(
        [
            dbc.CardHeader("Signal Scoring Breakdown"),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Filter by Setup:", className="me-2"),
                                    dcc.Dropdown(
                                        id="scoring-breakdown-filter",
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
                                width=12,
                            ),
                        ],
                        className="mb-2",
                    ),
                    dcc.Graph(
                        id="scoring-breakdown-chart",
                        config={"displayModeBar": True},
                        style={"height": "400px"},
                    ),
                ]
            ),
        ]
    )


def render_scoring_breakdown(
    results: BacktestResults, setup_filter: str = "all"
) -> go.Figure:
    """Render signal scoring breakdown chart.

    Args:
        results: BacktestResults object with all trades
        setup_filter: Filter by setup type ("all", "VWAP_RECLAIM", etc.)

    Returns:
        Plotly figure with stacked bar chart of factor contributions
    """
    if not results.trades:
        # Return empty chart
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            xaxis_title="Trade",
            yaxis_title="Score Contribution",
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

    # Filter trades
    filtered_trades = results.trades
    if setup_filter != "all":
        filtered_trades = [t for t in filtered_trades if t.setup_type == setup_filter]

    if not filtered_trades:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            annotations=[
                dict(
                    text="No trades match filter",
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

    # Extract factor names from first trade
    first_signal = filtered_trades[0].entry_execution.signal
    factor_names = list(first_signal.factors.keys())

    # Build data for stacked bar chart
    trade_ids = [t.trade_id[:8] for t in filtered_trades]
    factor_data = {factor: [] for factor in factor_names}

    for trade in filtered_trades:
        signal = trade.entry_execution.signal
        for factor in factor_names:
            factor_data[factor].append(signal.factors.get(factor, 0.0))

    # Create stacked bar chart
    fig = go.Figure()

    # Color mapping for factors
    factor_colors = {
        "structure_alignment": "#26a69a",
        "vwap_relation": "#42a5f5",
        "rsi_state": "#ab47bc",
        "ema_stack": "#ffa726",
        "dxy_corr": "#ef5350",
        "fvg_alignment": "#66bb6a",
        "liquidity_sweep": "#ffca28",
        "htf_bonus": "#ec407a",
    }

    for factor in factor_names:
        fig.add_trace(
            go.Bar(
                name=factor.replace("_", " ").title(),
                x=trade_ids,
                y=factor_data[factor],
                marker_color=factor_colors.get(factor, "#78909c"),
                hovertemplate=(
                    f"{factor.replace('_', ' ').title()}: %{{y:.2f}}<extra></extra>"
                ),
            )
        )

    # Add total score line
    total_scores = [
        filtered_trades[i].entry_execution.signal.score
        for i in range(len(filtered_trades))
    ]
    fig.add_trace(
        go.Scatter(
            x=trade_ids,
            y=total_scores,
            mode="lines+markers",
            name="Total Score",
            line=dict(color="white", width=2, dash="dash"),
            marker=dict(size=6, color="white"),
            yaxis="y2",
        )
    )

    # Update layout
    fig.update_layout(
        template="plotly_dark",
        barmode="stack",
        xaxis_title="Trade ID",
        yaxis_title="Factor Contribution",
        yaxis2=dict(
            title="Total Score",
            overlaying="y",
            side="right",
            range=[0, 10.5],
        ),
        showlegend=True,
        hovermode="x unified",
        height=400,
    )

    return fig
