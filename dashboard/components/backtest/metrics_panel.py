"""Metrics Panel - Performance summary cards for backtest results."""

import dash_bootstrap_components as dbc
from backtester.replay_loop import BacktestResults
from dash import html


def create_metrics_panel() -> dbc.Card:
    """Create the metrics summary panel.

    Returns:
        Dash Bootstrap Card containing metrics display
    """
    return dbc.Card(
        [
            dbc.CardHeader("Performance Metrics"),
            dbc.CardBody(id="metrics-panel-content"),
        ]
    )


def render_metrics_panel(results: BacktestResults) -> list:
    """Render metrics summary cards.

    Args:
        results: BacktestResults object with all metrics

    Returns:
        List of Dash components (cards with metrics)
    """
    # Calculate setup type distribution
    setup_counts = {}
    for trade in results.trades:
        setup = trade.setup_type
        setup_counts[setup] = setup_counts.get(setup, 0) + 1

    # Format PnL display
    pnl_points_str = f"{results.total_pnl:+.2f} pts"
    pnl_dollars_str = (
        f"${results.total_pnl_dollars:+,.2f}" if results.total_pnl_dollars else "N/A"
    )

    # Color coding for win rate
    win_rate_color = "success" if results.win_rate >= 60 else "warning" if results.win_rate >= 50 else "danger"

    cards = [
        # Row 1: Core Metrics
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("Win Rate", className="text-muted mb-1"),
                                    html.H3(
                                        f"{results.win_rate:.1f}%",
                                        className=f"text-{win_rate_color} mb-0",
                                    ),
                                ]
                            )
                        ],
                        className="mb-3",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("Total Trades", className="text-muted mb-1"),
                                    html.H3(f"{results.total_trades}", className="mb-0"),
                                    html.Small(
                                        f"{results.winning_trades}W / {results.losing_trades}L",
                                        className="text-muted",
                                    ),
                                ]
                            )
                        ],
                        className="mb-3",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("Total PnL", className="text-muted mb-1"),
                                    html.H4(pnl_points_str, className="mb-1"),
                                    html.Small(pnl_dollars_str, className="text-muted"),
                                ]
                            )
                        ],
                        className="mb-3",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("Avg R", className="text-muted mb-1"),
                                    html.H3(
                                        f"{results.average_r:.2f}R",
                                        className="mb-0",
                                    ),
                                ]
                            )
                        ],
                        className="mb-3",
                    ),
                    width=3,
                ),
            ],
            className="mb-3",
        ),
        # Row 2: Guardrail Metrics
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6(
                                        "Max Consecutive Losses",
                                        className="text-muted mb-1",
                                    ),
                                    html.H4(f"{results.max_consecutive_losses}", className="mb-0"),
                                ]
                            )
                        ],
                        className="mb-3",
                    ),
                    width=4,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("PDLL Hits", className="text-muted mb-1"),
                                    html.H4(f"{results.pdll_hits}", className="mb-0"),
                                ]
                            )
                        ],
                        className="mb-3",
                    ),
                    width=4,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6(
                                        "Session Resets",
                                        className="text-muted mb-1",
                                    ),
                                    html.H4(f"{results.session_resets}", className="mb-0"),
                                ]
                            )
                        ],
                        className="mb-3",
                    ),
                    width=4,
                ),
            ],
            className="mb-3",
        ),
        # Row 3: Setup Type Distribution
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Setup Type Distribution"),
                            dbc.CardBody(
                                [
                                    html.Ul(
                                        [
                                            html.Li(
                                                f"{setup}: {count} trades",
                                                className="mb-1",
                                            )
                                            for setup, count in sorted(
                                                setup_counts.items(), key=lambda x: -x[1]
                                            )
                                        ],
                                        className="mb-0",
                                    )
                                ]
                            ),
                        ],
                        className="mb-3",
                    ),
                    width=12,
                ),
            ],
        ),
    ]

    return cards

