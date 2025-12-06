"""Controls Panel Component - Play/Pause, Speed, Progress.

This module provides the simulation controls panel for the dashboard.
"""

import dash_bootstrap_components as dbc
from dash import html


def create_controls_panel() -> dbc.Card:
    """Create the simulation controls panel.

    Returns:
        Dash Bootstrap Card containing control elements
    """
    return dbc.Card(
        [
            dbc.CardHeader("Simulation Controls"),
            dbc.CardBody(
                [
                    # Play/Pause/Step buttons row
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    dbc.Button(
                                        "Play",
                                        id="btn-play",
                                        color="success",
                                        className="me-2",
                                        size="sm",
                                    ),
                                    dbc.Button(
                                        "Pause",
                                        id="btn-pause",
                                        color="warning",
                                        className="me-2",
                                        size="sm",
                                    ),
                                    dbc.Button(
                                        "Step",
                                        id="btn-step",
                                        color="info",
                                        className="me-2",
                                        size="sm",
                                        title="Process one bar",
                                    ),
                                ],
                                width=8,
                            ),
                            dbc.Col(
                                [
                                    html.Div(id="status-indicator", className="text-end"),
                                ],
                                width=4,
                            ),
                        ],
                        className="mb-3",
                    ),
                    # Speed control row
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Speed:", className="me-2"),
                                    dbc.Input(
                                        id="speed-input",
                                        type="number",
                                        value=1.0,
                                        min=0.1,
                                        max=1000,
                                        step=0.5,
                                        size="sm",
                                        style={"width": "80px", "display": "inline-block"},
                                    ),
                                    html.Span("x", className="ms-1"),
                                ],
                                width=6,
                            ),
                            dbc.Col(
                                [
                                    html.Div(id="pause-reason", className="text-warning small"),
                                ],
                                width=6,
                            ),
                        ],
                        className="mb-3",
                    ),
                    html.Hr(),
                    # Timestamp display
                    html.Div(
                        [
                            html.Label("Current Time:"),
                            html.H4(id="current-timestamp", children="--:--:--"),
                        ]
                    ),
                    # Progress bar
                    html.Div(
                        [
                            html.Label("Progress:"),
                            dbc.Progress(id="progress-bar", value=0, className="mb-2"),
                        ]
                    ),
                ]
            ),
        ]
    )


def render_status_indicator(is_running: bool, is_paused: bool) -> html.Span:
    """Render the status indicator based on simulation state.

    Args:
        is_running: Whether simulation is running
        is_paused: Whether simulation is paused

    Returns:
        HTML span element with status indicator
    """
    if is_paused:
        return html.Span("● PAUSED", className="text-warning")
    elif is_running:
        return html.Span("● RUNNING", className="text-success")
    else:
        return html.Span("● STOPPED", className="text-danger")


def render_timestamp(timestamp) -> str:
    """Format timestamp for display.

    Args:
        timestamp: datetime object or None

    Returns:
        Formatted timestamp string
    """
    if timestamp is None:
        return "--:--:--"
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def render_pause_reason(reason: str | None, signal) -> html.Div | str:
    """Render pause reason with signal info.

    Args:
        reason: Pause reason string or None
        signal: Signal that triggered pause (if any)

    Returns:
        HTML div or empty string
    """
    if not reason:
        return ""

    parts = [html.Strong(f"Paused: "), reason]

    if signal:
        parts.append(html.Br())
        parts.append(
            html.Small(
                f"{signal.direction.upper()} | "
                f"Score: {signal.score:.1f} | "
                f"Setup: {signal.setup_type}"
            )
        )

    return html.Div(parts, className="text-warning")

